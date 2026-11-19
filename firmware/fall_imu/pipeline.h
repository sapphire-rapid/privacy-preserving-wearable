/*
 * pipeline.h - streaming fall pipeline (ring buffer -> stride -> features ->
 * LR -> trigger -> confirm).  Pure C, no RIOT dependencies, so the SAME code
 * runs on the board (live + replay) and in host/host_pipe_test.c.
 *
 * Mirrors the Python reference (eval_confirm_nested.py / FEATURES_SPEC.md s.4):
 *   - window wi covers samples [wi*STRIDE, wi*STRIDE + WIN); it is evaluated
 *     when its last sample arrives (n = wi*STRIDE + WIN samples pushed)
 *   - p >= FALL_PROB_THR  -> trigger; the confirm segment is the CONFIRM_SAMPLES
 *     |a| samples immediately AFTER the triggering window
 *   - confirm: population std < FALL_STILL_STD_THR and |mean - 1| < FALL_STILL_MEAN_TOL
 *       still     -> CONFIRMED
 *       not still -> CANCELLED (scanning simply continues, as in the reference)
 *   - every triggering window has its own confirm segment, so several triggers
 *     can be pending at once (reference evaluates each window independently).
 *   - On CONFIRMED the remaining pending triggers belong to the same fall and
 *     are dropped (reference: one alarm per trial).
 * All sizes come from fall_model.h macros (WIN_SAMPLES, STRIDE_SAMPLES,
 * CONFIRM_SAMPLES, SAMPLE_RATE_HZ ...): a retrained model is a header swap.
 */
#ifndef PIPELINE_H
#define PIPELINE_H

#include <stdint.h>

#include "fall_model.h"
#include "fall_features.h"

#define FALL_MAX_PEND   ((CONFIRM_SAMPLES / STRIDE_SAMPLES) + 2)

typedef enum {
    FALL_CONF_NONE = 0,
    FALL_CONF_CONFIRMED,
    FALL_CONF_CANCELLED,
} fall_conf_t;

typedef struct {
    float    xyz[WIN_SAMPLES][3];      /* ring of the last WIN samples (g)     */
    float    mag[CONFIRM_SAMPLES];     /* ring of the last CONFIRM |a| (g)     */
    float    win[WIN_SAMPLES][3];      /* linearised window scratch            */
    float    seg[CONFIRM_SAMPLES];     /* linearised confirm segment scratch   */
    uint32_t n;                        /* samples pushed since reset           */
    uint32_t pend_end[FALL_MAX_PEND];  /* n at which each pending trigger's
                                          window ended                         */
    uint8_t  n_pend;
} fall_pipe_t;

/* what happened on one push (all fields valid every call) */
typedef struct {
    int         window;        /* 1: a stride window was evaluated on this push */
    uint32_t    wi;            /* its window index                              */
    float       prob;          /* LR probability of that window                 */
    float       feat[N_FEATURES];
    int         trigger;       /* that window triggered (p >= thr)              */
    fall_conf_t conf;          /* a confirm segment completed on this push      */
    uint32_t    conf_trig_n;   /* n of the window end of the trigger it belongs to */
    float       conf_std;      /* stats of the completed confirm segment        */
    float       conf_mean;
    int         pend_overflow; /* trigger dropped: pending list full (bug flag) */
} fall_ev_t;

void fall_pipe_reset(fall_pipe_t *p);

/* push one accelerometer sample (g) and report what it caused */
void fall_pipe_push(fall_pipe_t *p, float x, float y, float z, fall_ev_t *ev);

#endif /* PIPELINE_H */
