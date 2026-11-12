/*
 * mesh_rpl - small helpers around RIOT's gnrc_rpl for the wearable mesh.
 *
 * - mesh_rpl_joined() / mesh_rpl_rank(): read-only views of RPL state
 * - mesh_rpl_watchdog_start(): background thread that
 *     * re-sends a multicast DIS every MESH_DIS_PERIOD_MS while the node has
 *       no parent (RIOT only sends ONE DIS at boot, gnrc_rpl.c), and
 *     * prints a [RPL] line whenever join state, parent or rank changes.
 */
#ifndef MESH_RPL_H
#define MESH_RPL_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef MESH_DIS_PERIOD_MS
#define MESH_DIS_PERIOD_MS      (5000U)     /* Contiki-NG uses 30 s; we want fast joins */
#endif

#ifndef MESH_WATCH_PERIOD_MS
#define MESH_WATCH_PERIOD_MS    (1000U)
#endif

/** true when the node is in a DODAG AND has a preferred parent (or is root) */
bool mesh_rpl_joined(void);

/** own RPL rank, 0 when not joined */
uint16_t mesh_rpl_rank(void);

/** start the DIS keeper / status thread (call once from main) */
void mesh_rpl_watchdog_start(void);

/** print this node's global IPv6 address(es) */
void mesh_rpl_print_addrs(void);

#ifdef __cplusplus
}
#endif

#endif /* MESH_RPL_H */
