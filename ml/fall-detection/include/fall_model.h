#ifndef FALL_MODEL_H
#define FALL_MODEL_H

#define N_FEATURES 9
/* Feature order (features_v2.py):
 *  0: max_mag
 *  1: min_mag
 *  2: mean_mag
 *  3: std_mag
 *  4: range_mag
 *  5: max_jerk
 *  6: std_mag_post
 *  7: count_low
 *  8: tilt_deg
 */

static const float FALL_MEAN[] = {
    1.8715067f, 0.655942231f, 1.06175538f, 0.258464673f, 1.21556447f, 0.586727115f, 0.238395702f, 4.30441725f, 10.3089542f
};
static const float FALL_SCALE[] = {
    1.25144644f, 0.312544733f, 0.128443477f, 0.324947389f, 1.49977461f, 0.879531249f, 0.322407541f, 8.52093423f, 15.2615312f
};
static const float FALL_COEF[] = {
    1.06731162f, -0.479007108f, -0.347062628f, 2.69895549f, 0.990411804f, -0.414278705f, -3.14631548f, -0.774328339f, 1.03918389f
};
static const float FALL_INTERCEPT = -4.88034912f;
static const float FALL_PROB_THR = 0.93f;
static const float STILL_STD_THR = 0.05f;
static const float STILL_MEAN_TOL = 0.2f;
#define CONFIRM_SAMPLES 156
#define WIN_SAMPLES 104
#define STRIDE_SAMPLES 26
#define SAMPLE_RATE_HZ 52

#endif
