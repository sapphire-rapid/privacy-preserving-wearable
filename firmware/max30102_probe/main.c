#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#include "periph/i2c.h"
#include "ztimer.h"

#include "net/sock/udp.h"
#include "net/gnrc/rpl.h"
#include "net/gnrc/rpl/dodag.h"
#include "net/ipv6/addr.h"
#include "net/gnrc/netif.h"
#include "net/gnrc/netif/ipv6.h"

#define MAX30102_I2C_DEV       I2C_DEV(0)
#define MAX30102_ADDR          0x57

#define REG_FIFO_WR_PTR        0x04
#define REG_OVF_COUNTER        0x05
#define REG_FIFO_RD_PTR        0x06
#define REG_FIFO_DATA          0x07
#define REG_FIFO_CONFIG        0x08
#define REG_MODE_CONFIG        0x09
#define REG_SPO2_CONFIG        0x0A
#define REG_LED1_PA            0x0C
#define REG_LED2_PA            0x0D

#define MODE_RESET               0x40
#define MODE_SPO2                0x03

#define SAMPLE_PERIOD_MS         10
#define POLL_PERIOD_MS           200

#define DC_ALPHA_NUM             1
#define DC_ALPHA_DEN             16
#define MIN_PEAK_AMPLITUDE       200
#define REFRACTORY_MS            300
#define MAX_PLAUSIBLE_JUMP       40000
#define BPM_AVG_WINDOW           4

#define PI4_DEST_ADDR            "2001:db8:1::2"
#define DEST_PORT                8888
#define LOCAL_PORT                9999
#define REPLY_TIMEOUT_US          500000   /* 500ms */
#define LOSS_WINDOW               20U

typedef struct __attribute__((packed)) {
    uint32_t seq;
    uint16_t bpm;
    uint16_t rank;
} hr_packet_t;

_Static_assert(sizeof(hr_packet_t) == 8, "hr_packet_t must be 8 bytes");

/* sliding window of the last LOSS_WINDOW outcomes (1 = seq-matched ACK received) */
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

static gnrc_rpl_dodag_t *_active_dodag(void)
{
    for (unsigned i = 0; i < GNRC_RPL_INSTANCES_NUMOF; i++) {
        if (gnrc_rpl_instances[i].state != 0) {
            return &gnrc_rpl_instances[i].dodag;
        }
    }
    return NULL;
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

static int max30102_write(uint8_t reg, uint8_t val)
{
    return i2c_write_reg(MAX30102_I2C_DEV, MAX30102_ADDR, reg, val, 0);
}

static int max30102_init(void)
{
    int res = max30102_write(REG_MODE_CONFIG, MODE_RESET);
    if (res != 0) { return res; }
    ztimer_sleep(ZTIMER_MSEC, 100);

    max30102_write(REG_FIFO_CONFIG, 0x10);
    max30102_write(REG_SPO2_CONFIG, 0x27);
    max30102_write(REG_LED1_PA, 0x24);
    max30102_write(REG_LED2_PA, 0x24);

    max30102_write(REG_FIFO_WR_PTR, 0x00);
    max30102_write(REG_OVF_COUNTER, 0x00);
    max30102_write(REG_FIFO_RD_PTR, 0x00);

    return max30102_write(REG_MODE_CONFIG, MODE_SPO2);
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

int main(void)
{
    puts("MAX30102 HR + UDP send (RPL mesh -> Pi4)");

    i2c_acquire(MAX30102_I2C_DEV);
    int res = max30102_init();
    i2c_release(MAX30102_I2C_DEV);
    if (res != 0) {
        printf("Init failed: %d\n", res);
        return 1;
    }
    puts("Sensor init OK. Waiting for RPL DODAG join...");

    sock_udp_ep_t local = { .family = AF_INET6, .port = LOCAL_PORT };
    sock_udp_t sock;
    if (sock_udp_create(&sock, &local, NULL, 0) != 0) {
        puts("[ERROR] failed to create UDP socket");
        return 1;
    }

    sock_udp_ep_t remote = {
        .family = AF_INET6,
        .netif = SOCK_ADDR_ANY_NETIF,
        .port = DEST_PORT,
    };
    ipv6_addr_t dest_addr;
    ipv6_addr_from_str(&dest_addr, PI4_DEST_ADDR);
    memcpy(remote.addr.ipv6, &dest_addr, sizeof(dest_addr));
    printf("[DEST] %s port %u\n", PI4_DEST_ADDR, (unsigned)DEST_PORT);

    int32_t dc = 0;
    bool dc_init = false;
    int32_t prev_ac = 0;
    uint32_t prev_ir = 0;
    bool have_prev_ir = false;
    bool rising = false;

    uint32_t virtual_time_ms = 0;
    uint32_t last_peak_time_ms = 0;
    bool have_last_peak = false;

    uint32_t intervals[BPM_AVG_WINDOW] = {0};
    int interval_count = 0;
    int interval_idx = 0;

    uint32_t last_send_ms = 0;
    int current_bpm = 0;
    uint32_t seq = 0;
    uint32_t sent = 0, acked = 0, late = 0;
    bool joined_logged = false;
    uint32_t join_ms = 0;
    bool first_ack_done = false;

    while (1) {
        uint8_t wr_ptr = 0, rd_ptr = 0;

        i2c_acquire(MAX30102_I2C_DEV);
        i2c_read_reg(MAX30102_I2C_DEV, MAX30102_ADDR, REG_FIFO_WR_PTR, &wr_ptr, 0);
        i2c_read_reg(MAX30102_I2C_DEV, MAX30102_ADDR, REG_FIFO_RD_PTR, &rd_ptr, 0);

        int num_samples = wr_ptr - rd_ptr;
        if (num_samples < 0) { num_samples += 32; }

        for (int i = 0; i < num_samples; i++) {
            uint8_t buf[6];
            int rres = i2c_read_regs(MAX30102_I2C_DEV, MAX30102_ADDR, REG_FIFO_DATA, buf, 6, 0);
            if (rres != 0) { continue; }

            uint32_t ir = ((uint32_t)buf[3] << 16 | (uint32_t)buf[4] << 8 | buf[5]) & 0x3FFFF;
            virtual_time_ms += SAMPLE_PERIOD_MS;

            if (have_prev_ir) {
                int32_t jump = (int32_t)ir - (int32_t)prev_ir;
                if (jump < 0) { jump = -jump; }
                if (jump > MAX_PLAUSIBLE_JUMP) { continue; }
            }
            prev_ir = ir;
            have_prev_ir = true;

            if (!dc_init) {
                dc = (int32_t)ir;
                dc_init = true;
                continue;
            }

            dc += ((int32_t)ir - dc) * DC_ALPHA_NUM / DC_ALPHA_DEN;
            int32_t ac = (int32_t)ir - dc;

            if (rising && ac < prev_ac && prev_ac > MIN_PEAK_AMPLITUDE) {
                if (!have_last_peak || (virtual_time_ms - last_peak_time_ms) >= REFRACTORY_MS) {
                    if (have_last_peak) {
                        uint32_t interval = virtual_time_ms - last_peak_time_ms;
                        intervals[interval_idx] = interval;
                        interval_idx = (interval_idx + 1) % BPM_AVG_WINDOW;
                        if (interval_count < BPM_AVG_WINDOW) { interval_count++; }

                        uint32_t sum = 0;
                        for (int k = 0; k < interval_count; k++) { sum += intervals[k]; }
                        uint32_t avg_interval = sum / interval_count;
                        if (avg_interval > 0) {
                            current_bpm = (int)(60000UL / avg_interval);
                        }
                    }
                    last_peak_time_ms = virtual_time_ms;
                    have_last_peak = true;
                }
            }

            rising = (ac > prev_ac);
            prev_ac = ac;
        }

        i2c_release(MAX30102_I2C_DEV);

        if (virtual_time_ms - last_send_ms >= 3000) {
            last_send_ms = virtual_time_ms;

            if (!_joined_dodag()) {
                puts("[WAIT] not joined to DODAG yet");
            }
            else {
                if (!joined_logged) {
                    joined_logged = true;
                    join_ms = ztimer_now(ZTIMER_MSEC);
                    puts("[OK] DODAG joined");
                }

                // Get rank from first joined RPL instance
                uint16_t rank = 0;
                for (unsigned i = 0; i < GNRC_RPL_INSTANCES_NUMOF; i++) {
                    if (gnrc_rpl_instances[i].state != 0) {
                        rank = gnrc_rpl_instances[i].dodag.my_rank;
                        break;
                    }
                }

                // One-time diagnostic: print this node's own global IPv6 address
                static bool addr_printed = false;
                if (!addr_printed) {
                    addr_printed = true;
                    gnrc_netif_t *netif = gnrc_netif_iter(NULL);
                    while (netif) {
                        for (size_t i = 0; i < CONFIG_GNRC_NETIF_IPV6_ADDRS_NUMOF; i++) {
                            if (!ipv6_addr_is_link_local(&netif->ipv6.addrs[i])) {
                                char addr_str[IPV6_ADDR_MAX_STR_LEN];
                                ipv6_addr_to_str(addr_str, &netif->ipv6.addrs[i], sizeof(addr_str));
                                printf("[MY ADDR] %s\n", addr_str);
                                break; // Print first global address found
                            }
                        }
                        netif = gnrc_netif_iter(netif);
                    }
                }

                hr_packet_t pkt = {
                    .seq = seq,
                    .bpm = (uint16_t)current_bpm,
                    .rank = rank,
                };

                _report_parent_change();

                uint32_t t_send = ztimer_now(ZTIMER_MSEC);
                ssize_t sres = sock_udp_send(&sock, &pkt, sizeof(pkt), &remote);
                sent++;

                bool got = false;
                uint32_t rtt = 0;
                int rerr = 0;

                if (sres < 0) {
                    rerr = (int)sres;
                }
                else {
                    uint8_t rx_buf[32];
                    sock_udp_ep_t reply_ep;
                    for (;;) {
                        uint32_t elapsed_us = (ztimer_now(ZTIMER_MSEC) - t_send) * 1000UL;
                        if (elapsed_us >= REPLY_TIMEOUT_US) {
                            rerr = -ETIMEDOUT;
                            break;
                        }
                        ssize_t rres = sock_udp_recv(&sock, rx_buf, sizeof(rx_buf),
                                                     REPLY_TIMEOUT_US - elapsed_us, &reply_ep);
                        if (rres < 0) {
                            rerr = (int)rres;
                            break;
                        }
                        /* reply format: 'A' 'C' 'K' + uint32 seq (7 bytes) */
                        if (rres == 7 && memcmp(rx_buf, "ACK", 3) == 0) {
                            uint32_t aseq;
                            memcpy(&aseq, rx_buf + 3, sizeof(aseq));
                            if (aseq == seq) {
                                rtt = ztimer_now(ZTIMER_MSEC) - t_send;
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
                unsigned okc = _win_ok();
                unsigned loss = fill ? ((fill - okc) * 100U) / fill : 0U;

                if (got) {
                    printf("[HR] seq=%lu bpm=%d rank=%u ack=OK rtt=%lums win_loss=%u%% (%u/%u)"
                           " sent=%lu acked=%lu late=%lu\n",
                           (unsigned long)seq, current_bpm, (unsigned)rank,
                           (unsigned long)rtt, loss, okc, fill,
                           (unsigned long)sent, (unsigned long)acked, (unsigned long)late);
                    if (!first_ack_done) {
                        first_ack_done = true;
                        printf("[FIRST ACK] %lu ms after DODAG join\n",
                               (unsigned long)(ztimer_now(ZTIMER_MSEC) - join_ms));
                    }
                }
                else {
                    printf("[HR] seq=%lu bpm=%d rank=%u ack=MISS (%s err %d) win_loss=%u%% (%u/%u)"
                           " sent=%lu acked=%lu late=%lu\n",
                           (unsigned long)seq, current_bpm, (unsigned)rank,
                           (sres < 0) ? "send" : "recv", rerr, loss, okc, fill,
                           (unsigned long)sent, (unsigned long)acked, (unsigned long)late);
                }
                seq++;
            }
        }

        ztimer_sleep(ZTIMER_MSEC, POLL_PERIOD_MS);
    }

    return 0;
}
