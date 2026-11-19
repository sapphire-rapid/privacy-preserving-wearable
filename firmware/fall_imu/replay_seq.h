/*
 * replay_seq.h - test-window replay sequences + pass/fail accounting.
 * Header-only (static inline) so it is shared by the on-device replay mode
 * (testmodes.c) and the host simulation (host/host_pipe_test.c).
 * Include in exactly ONE translation unit per binary (pulls in test_windows.h,
 * ~80 kB of const data).
 *
 * test_windows[0..5]  = fall impact windows, [6..11] = ADL windows (see
 * FEATURES_SPEC.md / export_final.py).  Only windows 6, 7, 10 genuinely move
 * (windows 8 and 11 are near-still, window 9 is borderline), so "moving"
 * samples are built from those three.
 *
 * Sequences (each replayed from a freshly reset pipeline):
 *   FALL_STILL : fall window + CONFIRM_SAMPLES of stillness.  The still
 *                segments in test_windows.h carry |a| only, so they are laid
 *                along the direction the fall window ended in (mean of its last
 *                TILT_POST_SAMPLES samples), i.e. "board came to rest there".
 *   FALL_MOVING: fall window + CONFIRM_SAMPLES of ADL motion (windows 6/7/10).
 *   ADL        : a single ADL window.
 */
#ifndef REPLAY_SEQ_H
#define REPLAY_SEQ_H

#include <math.h>

#include "pipeline.h"
#include "test_windows.h"

#define REPLAY_N_FALL   6
#define REPLAY_N_ADL    6
#define REPLAY_N_SEQ    (REPLAY_N_FALL + REPLAY_N_FALL + REPLAY_N_ADL)

enum { SEQ_FALL_STILL = 0, SEQ_FALL_MOVING = 1, SEQ_ADL = 2 };

static const char *const replay_kind_name[] = { "fall+still", "fall+moving", "ADL" };
static const unsigned replay_movers[3] = { 6, 7, 10 };

/* sequence idx 0..17 -> kind, source window index */
static inline void replay_seq_desc(int idx, int *kind, int *src)
{
    if (idx < REPLAY_N_FALL) {
        *kind = SEQ_FALL_STILL;
        *src = idx;
    }
    else if (idx < 2 * REPLAY_N_FALL) {
        *kind = SEQ_FALL_MOVING;
        *src = idx - REPLAY_N_FALL;
    }
    else {
        *kind = SEQ_ADL;
        *src = REPLAY_N_FALL + (idx - 2 * REPLAY_N_FALL);
    }
}

static inline int replay_seq_len(int kind)
{
    return (kind == SEQ_ADL) ? WIN_SAMPLES : (WIN_SAMPLES + CONFIRM_SAMPLES);
}

/* sample k (0-based) of sequence (kind, src), in g */
static inline void replay_seq_sample(int kind, int src, int k, float out[3])
{
    if (k < WIN_SAMPLES) {
        for (int c = 0; c < 3; c++) {
            out[c] = test_windows[src].xyz[k][c];
        }
        return;
    }
    int j = k - WIN_SAMPLES;
    if (kind == SEQ_FALL_STILL) {
        float u[3] = { 0.0f, 0.0f, 0.0f };
        for (int i = WIN_SAMPLES - TILT_POST_SAMPLES; i < WIN_SAMPLES; i++) {
            for (int c = 0; c < 3; c++) {
                u[c] += test_windows[src].xyz[i][c];
            }
        }
        float nu = sqrtf(u[0] * u[0] + u[1] * u[1] + u[2] * u[2]);
        float m = still_segments[src % 3].mag[j];
        for (int c = 0; c < 3; c++) {
            out[c] = m * u[c] / nu;
        }
    }
    else { /* SEQ_FALL_MOVING */
        unsigned w = replay_movers[(src + (j / WIN_SAMPLES)) % 3];
        for (int c = 0; c < 3; c++) {
            out[c] = test_windows[w].xyz[j % WIN_SAMPLES][c];
        }
    }
}

/* ---- accounting ----------------------------------------------------------- */
typedef struct {
    int   windows;      /* stride windows evaluated        */
    int   n_trig;       /* triggers                        */
    int   n_conf;       /* CONFIRMED events                */
    int   n_canc;       /* CANCELLED events                */
    int   w0_trig;      /* first window (n == WIN) triggered */
    int   w0_outcome;   /* outcome of that trigger: 0 none, 1 CONFIRMED, 2 CANCELLED */
    float w0_prob;      /* probability of the first window */
} replay_res_t;

static inline void replay_account(replay_res_t *r, const fall_ev_t *ev)
{
    if (ev->window) {
        r->windows++;
        if (ev->wi == 0) {
            r->w0_prob = ev->prob;
        }
        if (ev->trigger) {
            r->n_trig++;
            if (ev->wi == 0) {
                r->w0_trig = 1;
            }
        }
    }
    if (ev->conf == FALL_CONF_CONFIRMED) {
        r->n_conf++;
        if (ev->conf_trig_n == WIN_SAMPLES) {
            r->w0_outcome = 1;
        }
    }
    else if (ev->conf == FALL_CONF_CANCELLED) {
        r->n_canc++;
        if (ev->conf_trig_n == WIN_SAMPLES) {
            r->w0_outcome = 2;
        }
    }
}

/* expected outcome string + verdict */
static inline const char *replay_expect(int kind)
{
    return (kind == SEQ_FALL_STILL) ? "CONFIRMED"
         : (kind == SEQ_FALL_MOVING) ? "CANCELLED" : "no trigger";
}

static inline int replay_pass(int kind, const replay_res_t *r)
{
    switch (kind) {
    case SEQ_FALL_STILL:  return r->w0_trig && r->w0_outcome == 1;
    case SEQ_FALL_MOVING: return r->w0_trig && r->w0_outcome == 2 && r->n_conf == 0;
    default:              return r->n_trig == 0;
    }
}

#endif /* REPLAY_SEQ_H */
