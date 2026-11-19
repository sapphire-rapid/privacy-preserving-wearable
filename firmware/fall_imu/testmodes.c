/*
 * testmodes.c - s (self-test of the on-device feature + LR code against the
 * 12 windows / 6 stillness segments in test_windows.h) and r (replay of those
 * samples through the live pipeline at SAMPLE_RATE_HZ pacing).
 *
 * This is the ONLY translation unit that includes test_windows.h (via
 * replay_seq.h): it holds ~80 kB of const data in flash.
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "ztimer.h"

#include "app.h"
#include "replay_seq.h"

static const char *const FEAT_NAMES[N_FEATURES] = {
    "max_mag", "min_mag", "mean_mag", "std_mag", "range_mag",
    "max_jerk", "std_mag_post", "count_low", "tilt_deg"
};

#define SELFTEST_FEAT_REL   (1e-4f)     /* task: features within 1e-4 relative */
#define SELFTEST_RUNS       (100)

static float _rel_err(float got, float exp)
{
    float d = fabsf(got - exp);
    return (exp == 0.0f) ? d : d / fabsf(exp);
}

static int _feat_ok(float got, float exp)
{
    return (exp == 0.0f) ? (fabsf(got) <= 1e-6f)
                         : (_rel_err(got, exp) <= SELFTEST_FEAT_REL);
}

static volatile float _sink;   /* keeps the timed calls from being optimised away */

typedef struct { double sum; uint32_t max; } _tstat_t;

static void _tacc(_tstat_t *t, uint32_t us)
{
    t->sum += us;
    if (us > t->max) { t->max = us; }
}

static void _tprint(const char *what, const _tstat_t *t)
{
    printf("SELFTEST time %-16s mean=%.1f us max=%lu us (over %d runs)\n", what,
           t->sum / SELFTEST_RUNS, (unsigned long)t->max, SELFTEST_RUNS);
}

/* ------------------------------------------------------------------------- */
void mode_selftest(void)
{
    puts("### START s");
    printf("SELFTEST windows=%d still_segments=%d feat_rel_tol=%.0e thr=%.2f\n",
           N_TEST_WINDOWS, N_STILL_SEGMENTS, (double)SELFTEST_FEAT_REL,
           (double)FALL_PROB_THR);
    FLUSH();

    int win_pass = 0, seg_pass = 0;
    float worst_rel[N_FEATURES];
    memset(worst_rel, 0, sizeof(worst_rel));
    static float feat[N_FEATURES];
    static float win[WIN_SAMPLES][3];

    for (int i = 0; i < N_TEST_WINDOWS; i++) {
        const TestWindow *w = &test_windows[i];
        memcpy(win, w->xyz, sizeof(win));          /* the on-device path */
        fall_features(win, WIN_SAMPLES, feat);
        float prob = fall_lr_prob(feat);
        int trig = fall_trigger(prob);

        printf("SELFTEST win=%d exp_prob=%.9g got_prob=%.9g abs_diff=%.3e exp_trig=%d got_trig=%d\n",
               i, (double)w->prob, (double)prob, (double)fabsf(prob - w->prob),
               w->trigger, trig);
        int feats_ok = 1;
        for (int j = 0; j < N_FEATURES; j++) {
            float rel = _rel_err(feat[j], w->feat[j]);
            int ok = _feat_ok(feat[j], w->feat[j]);
            feats_ok &= ok;
            if (rel > worst_rel[j]) { worst_rel[j] = rel; }
            printf("SELFTEST   f%d %-12s exp=%.9g got=%.9g rel=%.3e %s\n", j, FEAT_NAMES[j],
                   (double)w->feat[j], (double)feat[j], (double)rel, ok ? "ok" : "FAIL");
        }
        int pass = feats_ok && (trig == w->trigger);
        win_pass += pass;
        printf("SELFTEST win=%d %s\n", i, pass ? "PASS" : "FAIL");
        FLUSH();
    }

    for (int i = 0; i < N_STILL_SEGMENTS; i++) {
        const StillSeg *sg = &still_segments[i];
        float mean = 0.0f;
        for (int k = 0; k < CONFIRM_SAMPLES; k++) {
            mean += sg->mag[k];
        }
        mean /= (float)CONFIRM_SAMPLES;
        float sd = fall_std_pop(sg->mag, CONFIRM_SAMPLES);
        int got = fall_is_still(sg->mag, CONFIRM_SAMPLES);
        int pass = (got == sg->is_still);
        seg_pass += pass;
        printf("SELFTEST seg=%d std=%.5f mean=%.5f exp_still=%d got_still=%d %s\n", i,
               (double)sd, (double)mean, sg->is_still, got, pass ? "PASS" : "FAIL");
    }

    printf("SELFTEST worst_rel_per_feature:");
    for (int j = 0; j < N_FEATURES; j++) {
        printf(" %s=%.2e", FEAT_NAMES[j], (double)worst_rel[j]);
    }
    putchar('\n');

    /* ---- timing: features + LR per window, 100 runs, ztimer_usec ---------- */
    _tstat_t t_tot = { 0, 0 }, t_feat = { 0, 0 }, t_lr = { 0, 0 };
    for (int r = 0; r < SELFTEST_RUNS; r++) {
        const TestWindow *w = &test_windows[r % N_TEST_WINDOWS];
        memcpy(win, w->xyz, sizeof(win));
        uint32_t a = ztimer_now(ZTIMER_USEC);
        fall_features(win, WIN_SAMPLES, feat);
        uint32_t b = ztimer_now(ZTIMER_USEC);
        float p = fall_lr_prob(feat);
        uint32_t c = ztimer_now(ZTIMER_USEC);
        _sink = p;
        _tacc(&t_feat, b - a);
        _tacc(&t_lr, c - b);
        _tacc(&t_tot, c - a);
    }
    _tprint("features+LR", &t_tot);
    _tprint("features", &t_feat);
    _tprint("LR", &t_lr);

    int all = (win_pass == N_TEST_WINDOWS) && (seg_pass == N_STILL_SEGMENTS);
    printf("SELFTEST SUMMARY windows %d/%d still_segments %d/%d %s\n", win_pass,
           N_TEST_WINDOWS, seg_pass, N_STILL_SEGMENTS, all ? "PASS" : "FAIL");
    puts("### DONE s");
    FLUSH();
}

/* ------------------------------------------------------------------------- */
/* r: replay                                                                  */
/* ------------------------------------------------------------------------- */
static fall_pipe_t _pipe;

void mode_replay(void)
{
    puts("### START r");
    const uint32_t period_us = 1000000u / SAMPLE_RATE_HZ;
    printf("REPLAY sequences=%d period_us=%lu rate=%d win=%d stride=%d confirm=%d thr=%.2f\n",
           REPLAY_N_SEQ, (unsigned long)period_us, SAMPLE_RATE_HZ, WIN_SAMPLES,
           STRIDE_SAMPLES, CONFIRM_SAMPLES, (double)FALL_PROB_THR);
    FLUSH();

    replay_res_t res[REPLAY_N_SEQ];
    uint8_t pend[REPLAY_N_SEQ];
    int done = 0;
    bool stopped = false;
    uint32_t t_start = ztimer_now(ZTIMER_MSEC);

    for (int idx = 0; idx < REPLAY_N_SEQ && !stopped; idx++) {
        int kind, src;
        replay_seq_desc(idx, &kind, &src);
        int len = replay_seq_len(kind);
        memset(&res[idx], 0, sizeof(res[idx]));
        fall_pipe_reset(&_pipe);
        printf("REPLAY seq=%d kind=%s src_win=%d len=%d expect=%s\n", idx,
               replay_kind_name[kind], src, len, replay_expect(kind));

        uint32_t last = ztimer_now(ZTIMER_USEC);
        for (int k = 0; k < len; k++) {
            if (app_stop_requested()) {
                stopped = true;
                break;
            }
            float s[3];
            fall_ev_t ev;
            replay_seq_sample(kind, src, k, s);
            fall_pipe_push(&_pipe, s[0], s[1], s[2], &ev);
            replay_account(&res[idx], &ev);
            if (ev.trigger) {
                printf("REPLAY seq=%d n=%lu TRIGGER wi=%lu p=%.6f\n", idx,
                       (unsigned long)_pipe.n, (unsigned long)ev.wi, (double)ev.prob);
            }
            if (ev.conf) {
                printf("REPLAY seq=%d n=%lu %s trig_n=%lu std=%.4f mean=%.4f\n", idx,
                       (unsigned long)_pipe.n,
                       ev.conf == FALL_CONF_CONFIRMED ? "CONFIRMED" : "CANCELLED",
                       (unsigned long)ev.conf_trig_n, (double)ev.conf_std,
                       (double)ev.conf_mean);
            }
            if (ev.trigger || ev.conf) {
                FLUSH();
            }
            ztimer_periodic_wakeup(ZTIMER_USEC, &last, period_us);   /* pacing */
        }
        if (!stopped) {
            pend[idx] = _pipe.n_pend;
            done++;
        }
    }

    puts("REPLAY_TABLE idx sequence src n wins trig conf canc pending w0_prob expect result");
    int npass = 0;
    for (int idx = 0; idx < done; idx++) {
        int kind, src;
        replay_seq_desc(idx, &kind, &src);
        int pass = replay_pass(kind, &res[idx]);
        npass += pass;
        printf("REPLAY_ROW %d %s %d %d %d %d %d %d %u %.6f %s %s\n", idx,
               replay_kind_name[kind], src, replay_seq_len(kind), res[idx].windows,
               res[idx].n_trig, res[idx].n_conf, res[idx].n_canc, (unsigned)pend[idx],
               (double)res[idx].w0_prob, replay_expect(kind), pass ? "PASS" : "FAIL");
    }
    printf("REPLAY SUMMARY %d/%d %s elapsed_ms=%lu\n", npass, REPLAY_N_SEQ,
           (npass == REPLAY_N_SEQ && done == REPLAY_N_SEQ) ? "PASS" : "FAIL",
           (unsigned long)(ztimer_now(ZTIMER_MSEC) - t_start));
    printf(stopped ? "### STOPPED r\n" : "### DONE r\n");
    FLUSH();
}
