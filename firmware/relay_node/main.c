/*
 * relay_node - RPL router + heartbeat node
 *
 * Joins the RPL DODAG and acts as a standard RPL router (native GNRC/RPL
 * forwarding handles other nodes' traffic). Additionally sends its own small
 * heartbeat {seq, bpm=0, rank} to the Pi4 every 3 s and checks for a
 * seq-matched "ACK"+seq reply, so the relay has its own rank + loss display
 * (relay->BR->Pi4 round trip) and shows up in the Pi4's per-node table.
 *
 * Wire format (little-endian, same 8 bytes as the HR packet):
 *   uplink:  { uint32 seq; uint16 bpm(=0); uint16 rank }
 *   reply:   'A' 'C' 'K' + uint32 seq   (7 bytes)
 */
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <inttypes.h>
#include <errno.h>

#include "ztimer.h"

#include "net/af.h"
#include "net/sock/udp.h"
#include "net/gnrc/rpl.h"
#include "net/gnrc/rpl/dodag.h"
#include "net/ipv6/addr.h"
#include "net/gnrc/netif.h"
#include "net/gnrc/netif/ipv6.h"

#define PI4_ADDR        "2001:db8:1::2"
#define PI4_PORT        (8888U)

#define SLEEP_MSEC      (500UL)
#define HB_PERIOD_MS    (3000UL)
#define ACK_TIMEOUT_MS  (500UL)
#define LOSS_WINDOW     (20U)

typedef struct __attribute__((packed)) {
    uint32_t seq;
    uint16_t bpm;
    uint16_t rank;
} hb_packet_t;

_Static_assert(sizeof(hb_packet_t) == 8, "hb_packet_t must be 8 bytes");

/* sliding window of the last LOSS_WINDOW outcomes (1 = ACK matched) */
static uint8_t _win[LOSS_WINDOW];
static unsigned _win_idx;
static unsigned _win_fill;

static void _win_push(bool ok)
{
    _win[_win_idx] = ok ? 1 : 0;
    _win_idx = (_win_idx + 1) % LOSS_WINDOW;
    if (_win_fill < LOSS_WINDOW) {
        _win_fill++;
    }
}

static unsigned _win_ok(void)
{
    unsigned ok = 0;
    for (unsigned i = 0; i < _win_fill; i++) {
        ok += _win[i];
    }
    return ok;
}

static bool _joined_dodag(void)
{
    for (unsigned i = 0; i < GNRC_RPL_INSTANCES_NUMOF; i++) {
        if (gnrc_rpl_instances[i].state != 0) {
            return true;
        }
    }
    return false;
}

static gnrc_rpl_dodag_t *_active_dodag(void)
{
    for (unsigned i = 0; i < GNRC_RPL_INSTANCES_NUMOF; i++) {
        if (gnrc_rpl_instances[i].state != 0) {
            return &gnrc_rpl_instances[i].dodag;
        }
    }
    return NULL;
}

static uint16_t _my_rank(void)
{
    gnrc_rpl_dodag_t *d = _active_dodag();
    return (d != NULL) ? d->my_rank : 0;
}

/* print the preferred parent's link-local address whenever it changes */
static void _report_parent_change(void)
{
    static ipv6_addr_t last = IPV6_ADDR_UNSPECIFIED;
    gnrc_rpl_dodag_t *d = _active_dodag();
    if (d == NULL || d->parents == NULL) {
        return;
    }
    if (!ipv6_addr_equal(&last, &d->parents->addr)) {
        char s[IPV6_ADDR_MAX_STR_LEN];
        last = d->parents->addr;
        ipv6_addr_to_str(s, &last, sizeof(s));
        printf("[PARENT] %s (parent rank %u, my rank %u)\n",
               s, (unsigned)d->parents->rank, (unsigned)d->my_rank);
    }
}

int main(void)
{
    puts("relay_node: RPL router + heartbeat");

    /* Wait until we have joined a DODAG */
    while (!_joined_dodag()) {
        puts("[WAIT] not joined to a DODAG yet");
        ztimer_sleep(ZTIMER_MSEC, SLEEP_MSEC);
    }
    uint32_t join_ms = ztimer_now(ZTIMER_MSEC);
    puts("[OK] DODAG joined");

    /* One-time diagnostic: print this node's own global IPv6 address */
    gnrc_netif_t *netif = gnrc_netif_iter(NULL);
    while (netif) {
        for (size_t i = 0; i < CONFIG_GNRC_NETIF_IPV6_ADDRS_NUMOF; i++) {
            if (!ipv6_addr_is_link_local(&netif->ipv6.addrs[i])) {
                char addr_str[IPV6_ADDR_MAX_STR_LEN];
                ipv6_addr_to_str(addr_str, &netif->ipv6.addrs[i], sizeof(addr_str));
                printf("[MY ADDR] %s\n", addr_str);
                break; /* first global address per interface */
            }
        }
        netif = gnrc_netif_iter(netif);
    }
    printf("[DEST] %s port %u\n", PI4_ADDR, (unsigned)PI4_PORT);

    /* UDP socket: ephemeral local port, destination given per send */
    sock_udp_ep_t local = SOCK_IPV6_EP_ANY;
    local.port = 0;
    sock_udp_t sock;
    if (sock_udp_create(&sock, &local, NULL, 0) < 0) {
        puts("[ERR] sock_udp_create failed");
        return 1;
    }

    sock_udp_ep_t remote = { .family = AF_INET6, .netif = SOCK_ADDR_ANY_NETIF,
                             .port = PI4_PORT };
    if (ipv6_addr_from_str((ipv6_addr_t *)&remote.addr.ipv6, PI4_ADDR) == NULL) {
        puts("[ERR] bad PI4_ADDR");
        return 1;
    }

    uint32_t seq = 0;
    uint32_t sent = 0, acked = 0, late = 0;
    bool first_ack_done = false;

    while (1) {
        uint32_t t_start = ztimer_now(ZTIMER_MSEC);
        uint16_t rank = _my_rank();
        _report_parent_change();

        hb_packet_t pkt = { .seq = seq, .bpm = 0, .rank = rank };
        ssize_t sres = sock_udp_send(&sock, &pkt, sizeof(pkt), &remote);
        sent++;

        bool got = false;
        uint32_t rtt = 0;
        int rerr = 0;

        if (sres < 0) {
            rerr = (int)sres;
        }
        else {
            uint8_t rx[16];
            for (;;) {
                uint32_t elapsed = ztimer_now(ZTIMER_MSEC) - t_start;
                if (elapsed >= ACK_TIMEOUT_MS) {
                    rerr = -ETIMEDOUT;
                    break;
                }
                uint32_t left_us = (ACK_TIMEOUT_MS - elapsed) * 1000UL;
                ssize_t n = sock_udp_recv(&sock, rx, sizeof(rx), left_us, NULL);
                if (n < 0) {
                    rerr = (int)n;
                    break;
                }
                if (n == 7 && memcmp(rx, "ACK", 3) == 0) {
                    uint32_t aseq;
                    memcpy(&aseq, rx + 3, sizeof(aseq));
                    if (aseq == seq) {
                        rtt = ztimer_now(ZTIMER_MSEC) - t_start;
                        got = true;
                        break;
                    }
                    if (aseq < seq) {
                        late++;     /* stale ACK of an earlier packet */
                    }
                }
                /* anything else: ignore and keep waiting out the timeout */
            }
        }

        _win_push(got);
        if (got) {
            acked++;
        }
        unsigned fill = _win_fill;
        unsigned ok = _win_ok();
        unsigned loss = fill ? ((fill - ok) * 100U) / fill : 0U;

        if (got) {
            printf("[HB] seq=%" PRIu32 " rank=%u ack=OK rtt=%" PRIu32
                   "ms win_loss=%u%% (%u/%u) sent=%" PRIu32 " acked=%" PRIu32
                   " late=%" PRIu32 "\n",
                   seq, (unsigned)rank, rtt, loss, ok, fill, sent, acked, late);
            if (!first_ack_done) {
                first_ack_done = true;
                printf("[FIRST ACK] %" PRIu32 " ms after DODAG join\n",
                       ztimer_now(ZTIMER_MSEC) - join_ms);
            }
        }
        else {
            printf("[HB] seq=%" PRIu32 " rank=%u ack=MISS (err %d) win_loss=%u%% (%u/%u)"
                   " sent=%" PRIu32 " acked=%" PRIu32 " late=%" PRIu32 "\n",
                   seq, (unsigned)rank, rerr, loss, ok, fill, sent, acked, late);
        }

        seq++;

        /* keep a steady 3 s cadence */
        uint32_t used = ztimer_now(ZTIMER_MSEC) - t_start;
        if (used < HB_PERIOD_MS) {
            ztimer_sleep(ZTIMER_MSEC, HB_PERIOD_MS - used);
        }
    }

    return 0;
}
