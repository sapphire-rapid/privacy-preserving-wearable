/*
 * mesh_br - border router + RPL root with the boot-time fixes that replace the
 * old manual post-boot checklist:
 *
 * 1) Uplink on-link prefix.
 *    gnrc_ipv6_static_addr adds 2001:db8:1::1 to the cdc-ecm uplink as a /128,
 *    so the BR never knows 2001:db8:1::/64 (the Pi4) is on-link and cannot
 *    resolve 2001:db8:1::2 -> ACKs to the Pi4 never leave the dongle.
 *    Fix: add 2001:db8:1::/64 to the NIB prefix list on the uplink
 *    (same as the shell's `nib prefix add <if> 2001:db8:1::/64`).
 *
 * 2) DAO refresh after a BR reboot.
 *    The root always boots with the same DODAG version and DTSN = 1. Nodes that
 *    survived the reboot see "same DODAG, same DTSN", do not resend DAOs, and the
 *    fresh BR has no downward routes -> ACKs dropped for up to a minute.
 *    Fix: random DTSN at boot. Nodes resend DAO when the parent's DTSN changes
 *    (gnrc_rpl_control_messages.c: parent->dtsn != dio->dtsn -> delay_dao()).
 *
 * 3) Trickle reset at boot (same as `rpl trickle reset <id>`), so the first
 *    DIOs go out at Imin right away.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>

#include "msg.h"
#include "random.h"
#include "shell.h"
#include "trickle.h"
#include "ztimer.h"

#include "net/gnrc/netif.h"
#include "net/gnrc/netapi.h"
#include "net/gnrc/ipv6/nib/pl.h"
#include "net/gnrc/rpl.h"
#include "net/ipv6/addr.h"
#include "net/netopt.h"

#define MAIN_QUEUE_SIZE     (8)
static msg_t _main_msg_queue[MAIN_QUEUE_SIZE];

static gnrc_netif_t *_find_uplink(void)
{
    gnrc_netif_t *netif = NULL;
    while ((netif = gnrc_netif_iter(netif))) {
        if (gnrc_netapi_get(netif->pid, NETOPT_IS_WIRED, 0, NULL, 0) == 1) {
            return netif;
        }
    }
    return NULL;
}

static void _fix_uplink_prefix(void)
{
    gnrc_netif_t *up = _find_uplink();
    if (up == NULL) {
        puts("[BR] ERROR: no wired (cdc-ecm) uplink found");
        return;
    }
    ipv6_addr_t pfx;
    int len = ipv6_prefix_from_str(&pfx, MESH_UPLINK_PFX);
    if (len <= 0) {
        puts("[BR] ERROR: bad MESH_UPLINK_PFX");
        return;
    }
    int res = gnrc_ipv6_nib_pl_set(up->pid, &pfx, len, UINT32_MAX, UINT32_MAX);
    printf("[BR] uplink if %d: on-link prefix %s %s\n", (int)up->pid, MESH_UPLINK_PFX,
           (res == 0) ? "added" : "FAILED");
}

static gnrc_rpl_instance_t *_root_instance(void)
{
    for (unsigned i = 0; i < GNRC_RPL_INSTANCES_NUMOF; i++) {
        gnrc_rpl_instance_t *inst = &gnrc_rpl_instances[i];
        if (inst->state != 0 && inst->dodag.node_status == GNRC_RPL_ROOT_NODE) {
            return inst;
        }
    }
    return NULL;
}

static void _kick_rpl_root(void)
{
    gnrc_rpl_instance_t *inst = NULL;
    /* root is configured by gnrc_ipv6_static_addr during auto-init; give it a moment */
    for (unsigned i = 0; i < 50 && (inst = _root_instance()) == NULL; i++) {
        ztimer_sleep(ZTIMER_MSEC, 100);
    }
    if (inst == NULL) {
        puts("[BR] ERROR: RPL root not configured (check IPV6_PREFIX / gnrc_rpl)");
        return;
    }

    /* any value != the previous boot's value triggers DAOs; avoid the boot default 1 */
    uint8_t dtsn = (uint8_t)random_uint32_range(2, 250);
    inst->dodag.dtsn = dtsn;
    trickle_reset_timer(&inst->dodag.trickle);

    char s[IPV6_ADDR_MAX_STR_LEN];
    printf("[BR] RPL root instance %u dodag %s dtsn=%u, trickle reset "
           "(Imin=%ums, doublings=%u)\n",
           (unsigned)inst->id, ipv6_addr_to_str(s, &inst->dodag.dodag_id, sizeof(s)),
           (unsigned)dtsn, (unsigned)(1U << inst->dodag.dio_min),
           (unsigned)inst->dodag.dio_interval_doubl);
}

int main(void)
{
    msg_init_queue(_main_msg_queue, MAIN_QUEUE_SIZE);
    puts("mesh_br: RIOT border router + RPL root (auto-config, no manual steps)");

    _fix_uplink_prefix();
    _kick_rpl_root();

    puts("[BR] ready. Shell available (rpl, nib, ifconfig, ping).");
    char line_buf[SHELL_DEFAULT_BUFSIZE];
    shell_run(NULL, line_buf, SHELL_DEFAULT_BUFSIZE);
    return 0;
}
