/*
 * mesh_node - one firmware for every wearable in the RPL mesh.
 *
 *   make ROLE=hr    : MAX30102 node, sends {seq, bpm, rank} every 3 s
 *   make ROLE=relay : plain RPL router, sends a heartbeat {seq, 0, rank} every 10 s
 *
 * Both roles are full RPL routers: packets from deeper nodes are forwarded
 * upward through the preferred parent, and ACKs from the Pi4 come back down
 * through the DAO (storing-mode) routes. No addresses are hard-coded except the
 * Pi4 sink.
 *
 * Wire format (little-endian), unchanged from max30102_probe/relay_node:
 *   uplink : { uint32 seq; uint16 bpm; uint16 rank }      8 bytes  -> Pi4:8888
 *   reply  : 'A' 'C' 'K' + uint32 seq                      7 bytes  -> node:9999
 *
 * Unlike the old apps, the ACK is received by its own thread, so the sender
 * never blocks and the MAX30102 FIFO is drained every 100 ms (the old 500 ms
 * blocking recv could overflow the 320 ms FIFO).
 */
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <inttypes.h>

#include "mutex.h"
#include "thread.h"
#include "ztimer.h"
#include "net/sock/udp.h"
#include "net/ipv6/addr.h"

#include "mesh_rpl.h"
#include "max30102_hr.h"

#define SINK_ADDR           "2001:db8:1::2"     /* Pi4 usb0 */
#define SINK_PORT           (8888U)
#define LOCAL_PORT          (9999U)

#if MESH_ROLE_HR
#  define ROLE_NAME         "HR"
#  define SEND_PERIOD_MS    (3000U)
#else
#  define ROLE_NAME         "RELAY"
#  define SEND_PERIOD_MS    (10000U)
#endif
#define POLL_PERIOD_MS      (100U)
#define LOSS_WINDOW         (20U)
#define PENDING_SLOTS       (16U)              /* power of two */
#define MIN_HOP_RANK_INC    (256U)             /* CONFIG_GNRC_RPL_DEFAULT_MIN_HOP_RANK_INCREASE */

typedef struct __attribute__((packed)) {
    uint32_t seq;
    uint16_t bpm;
    uint16_t rank;
} mesh_pkt_t;
_Static_assert(sizeof(mesh_pkt_t) == 8, "mesh_pkt_t must be 8 bytes");

typedef struct {
    uint32_t seq;
    uint32_t t_send;
    bool used;
    bool acked;
} pending_t;

static sock_udp_t _sock;
static mutex_t _lock = MUTEX_INIT;
static pending_t _pending[PENDING_SLOTS];

/* sliding loss window, updated when a packet's ACK deadline passes */
static uint8_t _win[LOSS_WINDOW];
static unsigned _win_idx, _win_fill;
static uint32_t _sent, _acked, _late;

static unsigned _hops(uint16_t rank)
{
    return (rank >= 2 * MIN_HOP_RANK_INC) ? (rank / MIN_HOP_RANK_INC) - 1 : (rank ? 1 : 0);
}

static void _win_push(bool ok)
{
    _win[_win_idx] = ok;
    _win_idx = (_win_idx + 1) % LOSS_WINDOW;
    if (_win_fill < LOSS_WINDOW) { _win_fill++; }
}

static unsigned _win_loss_pct(unsigned *ok_out)
{
    unsigned ok = 0;
    for (unsigned i = 0; i < _win_fill; i++) { ok += _win[i]; }
    *ok_out = ok;
    return _win_fill ? ((_win_fill - ok) * 100U) / _win_fill : 0U;
}

/* ---- ACK receiver thread ---------------------------------------------------- */
static char _ack_stack[THREAD_STACKSIZE_DEFAULT + THREAD_EXTRA_STACKSIZE_PRINTF];

static void *_ack_thread(void *arg)
{
    (void)arg;
    uint8_t rx[16];
    while (1) {
        ssize_t n = sock_udp_recv(&_sock, rx, sizeof(rx), SOCK_NO_TIMEOUT, NULL);
        if (n != 7 || memcmp(rx, "ACK", 3) != 0) {
            continue;
        }
        uint32_t aseq;
        memcpy(&aseq, rx + 3, sizeof(aseq));
        uint32_t now = ztimer_now(ZTIMER_MSEC);

        mutex_lock(&_lock);
        pending_t *p = &_pending[aseq & (PENDING_SLOTS - 1)];
        if (p->used && p->seq == aseq && !p->acked) {
            p->acked = true;
            _acked++;
            uint32_t rtt = now - p->t_send;
            mutex_unlock(&_lock);
            printf("[ACK] seq=%" PRIu32 " rtt=%" PRIu32 "ms\n", aseq, rtt);
        }
        else {
            /* slot reused (very late) or duplicate */
            _late++;
            mutex_unlock(&_lock);
            printf("[ACK] seq=%" PRIu32 " late/duplicate\n", aseq);
        }
    }
    return NULL;
}

/* Close out packets whose ACK deadline (one send period) has passed. */
static void _settle(uint32_t now)
{
    mutex_lock(&_lock);
    for (unsigned i = 0; i < PENDING_SLOTS; i++) {
        pending_t *p = &_pending[i];
        if (p->used && (now - p->t_send) >= SEND_PERIOD_MS) {
            if (!p->acked) {
                printf("[MISS] seq=%" PRIu32 " no ACK within %ums\n",
                       p->seq, (unsigned)SEND_PERIOD_MS);
            }
            _win_push(p->acked);
            p->used = false;
        }
    }
    mutex_unlock(&_lock);
}

int main(void)
{
    printf("\nmesh_node role=%s period=%ums sink=[%s]:%u\n",
           ROLE_NAME, (unsigned)SEND_PERIOD_MS, SINK_ADDR, SINK_PORT);

    bool sensor_ok = true;
    if (MESH_ROLE_HR) {
        int res = hr_init();
        if (res != 0) {
            /* keep routing for the others even without a sensor */
            printf("[HR] MAX30102 init failed (%d) - sending bpm=0\n", res);
            sensor_ok = false;
        }
        else {
            puts("[HR] MAX30102 OK (SpO2 mode, 100 Hz)");
        }
    }

    mesh_rpl_watchdog_start();

    sock_udp_ep_t local = SOCK_IPV6_EP_ANY;
    local.port = LOCAL_PORT;
    if (sock_udp_create(&_sock, &local, NULL, 0) < 0) {
        puts("[ERR] sock_udp_create failed");
        return 1;
    }
    sock_udp_ep_t sink = { .family = AF_INET6, .netif = SOCK_ADDR_ANY_NETIF,
                           .port = SINK_PORT };
    ipv6_addr_from_str((ipv6_addr_t *)&sink.addr.ipv6, SINK_ADDR);

    thread_create(_ack_stack, sizeof(_ack_stack), THREAD_PRIORITY_MAIN - 1,
                  0, _ack_thread, NULL, "ack_rx");

    uint32_t seq = 0;
    uint32_t last_send = ztimer_now(ZTIMER_MSEC);
    bool waiting_logged = false;

    while (1) {
        uint32_t now = ztimer_now(ZTIMER_MSEC);

        if (MESH_ROLE_HR && sensor_ok) {
            hr_poll();
        }
        _settle(now);

        if ((now - last_send) >= SEND_PERIOD_MS) {
            last_send = now;

            if (!mesh_rpl_joined()) {
                if (!waiting_logged) {
                    puts("[TX] waiting for a parent (DIS keeper is asking)...");
                    waiting_logged = true;
                }
            }
            else {
                waiting_logged = false;
                uint16_t rank = mesh_rpl_rank();
                mesh_pkt_t pkt = { .seq = seq, .bpm = hr_bpm(), .rank = rank };

                mutex_lock(&_lock);
                pending_t *p = &_pending[seq & (PENDING_SLOTS - 1)];
                if (p->used) {              /* should not happen: settled after 1 period */
                    _win_push(p->acked);
                }
                *p = (pending_t){ .seq = seq, .t_send = now, .used = true, .acked = false };
                mutex_unlock(&_lock);

                ssize_t r = sock_udp_send(&_sock, &pkt, sizeof(pkt), &sink);
                _sent++;

                unsigned ok;
                mutex_lock(&_lock);
                unsigned loss = _win_loss_pct(&ok);
                unsigned fill = _win_fill;
                mutex_unlock(&_lock);

                if (r < 0) {
                    printf("[TX] seq=%" PRIu32 " send error %d\n", seq, (int)r);
                }
                else {
                    printf("[TX] seq=%" PRIu32 " bpm=%u rank=%u hops=%u | loss=%u%% (%u/%u ok)"
                           " sent=%" PRIu32 " acked=%" PRIu32 " late=%" PRIu32 "%s\n",
                           seq, (unsigned)pkt.bpm, (unsigned)rank, _hops(rank),
                           loss, ok, fill, _sent, _acked, _late,
                           (MESH_ROLE_HR && hr_overflows()) ? " FIFO_OVF!" : "");
                }
                seq++;
            }
        }

        ztimer_sleep(ZTIMER_MSEC, POLL_PERIOD_MS);
    }
    return 0;
}
