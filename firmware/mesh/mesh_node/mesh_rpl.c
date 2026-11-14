#include <stdio.h>
#include <string.h>

#include "thread.h"
#include "ztimer.h"

#include "net/gnrc/netif.h"
#include "net/gnrc/rpl.h"
#include "net/gnrc/rpl/dodag.h"
#include "net/ipv6/addr.h"

#include "mesh_rpl.h"

/* Read-only peek at gnrc_rpl's global state from an application thread. The
 * fields are word-sized on a 32-bit MCU; a stale read only delays a DIS or a
 * status print by one period, which is harmless. */
static gnrc_rpl_instance_t *_active_instance(void)
{
    for (unsigned i = 0; i < GNRC_RPL_INSTANCES_NUMOF; i++) {
        if (gnrc_rpl_instances[i].state != 0) {
            return &gnrc_rpl_instances[i];
        }
    }
    return NULL;
}

bool mesh_rpl_joined(void)
{
    gnrc_rpl_instance_t *inst = _active_instance();
    if (inst == NULL) {
        return false;
    }
    /* A wearable is never a legitimate root: "root" here can only mean a
     * floating DODAG, which has no path to the BR. Joined = has a parent. */
    return (inst->dodag.node_status != GNRC_RPL_ROOT_NODE) &&
           (inst->dodag.parents != NULL);
}

uint16_t mesh_rpl_rank(void)
{
    gnrc_rpl_instance_t *inst = _active_instance();
    return (inst && mesh_rpl_joined()) ? inst->dodag.my_rank : 0;
}

void mesh_rpl_print_addrs(void)
{
    gnrc_netif_t *netif = NULL;
    while ((netif = gnrc_netif_iter(netif))) {
        for (size_t i = 0; i < CONFIG_GNRC_NETIF_IPV6_ADDRS_NUMOF; i++) {
            ipv6_addr_t *a = &netif->ipv6.addrs[i];
            if (ipv6_addr_is_unspecified(a) || ipv6_addr_is_link_local(a)) {
                continue;
            }
            char s[IPV6_ADDR_MAX_STR_LEN];
            printf("[ADDR] %s\n", ipv6_addr_to_str(s, a, sizeof(s)));
        }
    }
}

static char _watch_stack[THREAD_STACKSIZE_DEFAULT + THREAD_EXTRA_STACKSIZE_PRINTF];

static void *_watchdog(void *arg)
{
    (void)arg;
    bool was_joined = false;
    uint16_t last_rank = 0;
    ipv6_addr_t last_parent = IPV6_ADDR_UNSPECIFIED;
    uint32_t last_dis = 0;
    bool first = true;

    while (1) {
        uint32_t now = ztimer_now(ZTIMER_MSEC);
        gnrc_rpl_instance_t *inst = _active_instance();
        bool joined = mesh_rpl_joined();

        if (!joined) {
            /* RIOT sends one DIS in gnrc_rpl_init() and never again. If that one
             * was lost (radio not ready, BR not up yet) the node would wait a
             * full Trickle interval for a DIO. Keep asking instead. */
            if (first || (now - last_dis) >= MESH_DIS_PERIOD_MS) {
                gnrc_rpl_send_DIS(NULL, (ipv6_addr_t *)&ipv6_addr_all_rpl_nodes, NULL, 0);
                last_dis = now;
                first = false;
                puts("[RPL] no parent -> multicast DIS");
            }
            if (was_joined) {
                puts("[RPL] LOST parent / left DODAG");
                last_parent = ipv6_addr_unspecified;
                last_rank = 0;
            }
        }
        else {
            uint16_t rank = inst->dodag.my_rank;
            ipv6_addr_t parent = inst->dodag.parents ? inst->dodag.parents->addr
                                                     : ipv6_addr_unspecified;
            if (!was_joined) {
                puts("[RPL] JOINED DODAG");
                mesh_rpl_print_addrs();
            }
            if (!ipv6_addr_equal(&parent, &last_parent) || rank != last_rank) {
                char s[IPV6_ADDR_MAX_STR_LEN];
                printf("[RPL] parent=%s parent_rank=%u my_rank=%u\n",
                       ipv6_addr_to_str(s, &parent, sizeof(s)),
                       inst->dodag.parents ? (unsigned)inst->dodag.parents->rank : 0U,
                       (unsigned)rank);
                last_parent = parent;
                last_rank = rank;
            }
        }

        was_joined = joined;
        ztimer_sleep(ZTIMER_MSEC, MESH_WATCH_PERIOD_MS);
    }
    return NULL;
}

void mesh_rpl_watchdog_start(void)
{
    thread_create(_watch_stack, sizeof(_watch_stack), THREAD_PRIORITY_MAIN - 1,
                  0, _watchdog, NULL, "rpl_watch");
}
