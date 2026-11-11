/*
 * host_test - runs every window and stillness segment from test_windows.h
 * through fall_features.h and reports PASS/FAIL.
 *
 * Tolerances (per task):
 *   - tilt_deg (feature 8): absolute 0.05 deg
 *   - all other features:   1e-3 relative
 *   - probability:          1e-3
 *   - trigger / still:      exact
 */
#include <stdio.h>
#include <math.h>

#include "fall_features.h"
#include "test_windows.h"

static const char *FEAT_NAMES[N_FEATURES] = {
    "max_mag", "min_mag", "mean_mag", "std_mag", "range_mag",
    "max_jerk", "std_mag_post", "count_low", "tilt_deg"
};

static int feat_within(int j, float got, float exp)
{
    if (j == 8) {                              /* tilt: absolute 0.05 deg */
        return fabsf(got - exp) <= 0.05f;
    }
    float d = fabsf(got - exp);
    if (d <= 1e-3f * fabsf(exp)) {             /* 1e-3 relative */
        return 1;
    }
    return (exp == 0.0f) && (d <= 1e-6f);      /* e.g. count_low == 0 */
}

int main(void)
{
    int all_ok = 1;

    printf("=== FALL FEATURE / MODEL HOST TEST ===\n");
    printf("windows=%d  still_segments=%d\n\n", N_TEST_WINDOWS, N_STILL_SEGMENTS);

    printf("---- WINDOWS ----\n");
    printf("tolerances: feat 1e-3 rel (tilt 0.05 abs), prob 1e-3, trigger exact\n");
    printf("%-4s  %-6s  %-6s  %-8s  %-6s\n", "win", "feat", "prob", "trigger", "result");
    for (int i = 0; i < N_TEST_WINDOWS; i++) {
        const TestWindow *w = &test_windows[i];
        float feat[N_FEATURES];
        fall_features(w->xyz, WIN_SAMPLES, feat);

        int feat_pass = 1;
        for (int j = 0; j < N_FEATURES; j++) {
            if (!feat_within(j, feat[j], w->feat[j])) {
                feat_pass = 0;
            }
        }

        float prob = fall_lr_prob(feat);
        int prob_pass = fabsf(prob - w->prob) <= 1e-3f;
        int trig = fall_trigger(prob);
        int trig_pass = (trig == w->trigger);
        int pass = feat_pass && prob_pass && trig_pass;
        all_ok &= pass;

        printf("%-4d  %-6s  %-6s  %-8s  %-6s\n",
               i, feat_pass ? "PASS" : "FAIL", prob_pass ? "PASS" : "FAIL",
               trig_pass ? "PASS" : "FAIL", pass ? "PASS" : "FAIL");

        if (!pass) {
            printf("      prob  got=%.9g  exp=%.9g\n", (double)prob, (double)w->prob);
            printf("      trig  got=%d  exp=%d\n", trig, w->trigger);
            for (int j = 0; j < N_FEATURES; j++) {
                if (!feat_within(j, feat[j], w->feat[j])) {
                    printf("      %-12s got=%.9g  exp=%.9g  (%s)\n",
                           FEAT_NAMES[j], (double)feat[j], (double)w->feat[j],
                           (j == 8) ? "abs 0.05" : "rel 1e-3");
                }
            }
        }
    }

    printf("\n---- STILLNESS SEGMENTS ----\n");
    printf("%-4s  %-9s  %-6s\n", "seg", "still", "result");
    for (int i = 0; i < N_STILL_SEGMENTS; i++) {
        const StillSeg *s = &still_segments[i];
        int got = fall_is_still(s->mag, CONFIRM_SAMPLES);
        int pass = (got == s->is_still);
        all_ok &= pass;
        printf("%-4d  %-9d  %-6s\n", i, got, pass ? "PASS" : "FAIL");
        if (!pass) {
            printf("      got=%d  exp=%d\n", got, s->is_still);
        }
    }

    printf("\n%s (%d windows, %d still segments)\n",
           all_ok ? "RESULT: ALL PASS" : "RESULT: SOME FAILURES",
           N_TEST_WINDOWS, N_STILL_SEGMENTS);
    return all_ok ? 0 : 1;
}
