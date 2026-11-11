#ifndef FALL_FEATURES_H
#define FALL_FEATURES_H

#include <math.h>

#include "fall_model.h"

/* Stillness / confirmation thresholds (from FEATURES_SPEC.md section 4) */
#ifndef FALL_STILL_STD_THR
#define FALL_STILL_STD_THR   0.05f
#endif
#ifndef FALL_STILL_MEAN_TOL
#define FALL_STILL_MEAN_TOL  0.2f
#endif

#define FALL_DEG_PER_RAD  (180.0f / 3.14159265358979323846f)

/* |v| of a 3-axis sample, in g */
static inline float fall_mag3(const float *v)
{
    return sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
}

/* population std (ddof=0), two-pass, float accumulators */
static inline float fall_std_pop(const float *a, int n)
{
    float mean = 0.0f;
    for (int i = 0; i < n; i++) {
        mean += a[i];
    }
    mean /= (float)n;
    float ss = 0.0f;
    for (int i = 0; i < n; i++) {
        float d = a[i] - mean;
        ss += d * d;
    }
    return sqrtf(ss / (float)n);
}

/*
 * tilt_deg (verbatim semantics of features_v2.py):
 *   before = 26 samples immediately before the first |a| peak (first-10
 *            fallback when peak < 26)
 *   after  = last 26 samples of the window
 *   angle  = angle between mean(before) and mean(after), clamped/guarded
 * Computed as atan2f(|u x v|, u . v) which equals the arccos form but is
 * stable for small angles.
 */
static inline float fall_tilt_deg(const float xyz[][3], int n)
{
    int peak = 0;
    float best = -1.0f;
    for (int i = 0; i < n; i++) {
        float m = fall_mag3(xyz[i]);
        if (m > best) {          /* strict: first maximum (np.argmax) */
            best = m;
            peak = i;
        }
    }

    int bstart, blen;
    if (peak >= 26) {
        bstart = peak - 26;
        blen = 26;
    }
    else {
        bstart = 0;
        blen = (n < 10) ? n : 10;
    }
    int astart = (n >= 26) ? (n - 26) : 0;
    int alen = n - astart;

    float u[3] = { 0.0f, 0.0f, 0.0f };
    float v[3] = { 0.0f, 0.0f, 0.0f };
    for (int i = 0; i < blen; i++) {
        u[0] += xyz[bstart + i][0];
        u[1] += xyz[bstart + i][1];
        u[2] += xyz[bstart + i][2];
    }
    u[0] /= (float)blen;
    u[1] /= (float)blen;
    u[2] /= (float)blen;
    for (int i = 0; i < alen; i++) {
        v[0] += xyz[astart + i][0];
        v[1] += xyz[astart + i][1];
        v[2] += xyz[astart + i][2];
    }
    v[0] /= (float)alen;
    v[1] /= (float)alen;
    v[2] /= (float)alen;

    float nu = sqrtf(u[0] * u[0] + u[1] * u[1] + u[2] * u[2]);
    float nv = sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
    if (nu == 0.0f || nv == 0.0f) {
        return 0.0f;
    }

    float cx = u[1] * v[2] - u[2] * v[1];
    float cy = u[2] * v[0] - u[0] * v[2];
    float cz = u[0] * v[1] - u[1] * v[0];
    float cross = sqrtf(cx * cx + cy * cy + cz * cz);
    float dot = u[0] * v[0] + u[1] * v[1] + u[2] * v[2];

    return atan2f(cross, dot) * FALL_DEG_PER_RAD;
}

/*
 * features_of_window: the 9 features, in the order of FEATURE_NAMES.
 * xyz: n samples of (x,y,z) acceleration in g.  n must be <= WIN_SAMPLES.
 */
static inline void fall_features(const float xyz[][3], int n, float out[N_FEATURES])
{
    float m[WIN_SAMPLES];
    for (int i = 0; i < n; i++) {
        m[i] = fall_mag3(xyz[i]);
    }

    float mx = m[0];
    float mn = m[0];
    float sum = 0.0f;
    for (int i = 0; i < n; i++) {
        if (m[i] > mx) { mx = m[i]; }
        if (m[i] < mn) { mn = m[i]; }
        sum += m[i];
    }
    float mean = sum / (float)n;

    float jerk = 0.0f;
    for (int i = 1; i < n; i++) {
        float d = m[i] - m[i - 1];
        if (d < 0.0f) { d = -d; }
        if (d > jerk) { jerk = d; }
    }

    int post_n = (n >= 52) ? 52 : n;
    const float *post = &m[n - post_n];

    int nlow = 0;
    for (int i = 0; i < n; i++) {
        if (m[i] < 0.5f) { nlow++; }
    }

    out[0] = mx;                        /* max_mag */
    out[1] = mn;                        /* min_mag */
    out[2] = mean;                      /* mean_mag */
    out[3] = fall_std_pop(m, n);        /* std_mag */
    out[4] = mx - mn;                   /* range_mag */
    out[5] = (n >= 2) ? jerk : 0.0f;    /* max_jerk (|diff(m)|, no dt) */
    out[6] = fall_std_pop(post, post_n);/* std_mag_post (last 52) */
    out[7] = (float)nlow;               /* count_low (|a| < 0.5 g) */
    out[8] = fall_tilt_deg(xyz, n);     /* tilt_deg */
}

/* logistic-regression probability from the standardised features */
static inline float fall_lr_prob(const float feat[N_FEATURES])
{
    double z = (double)FALL_INTERCEPT;
    for (int j = 0; j < N_FEATURES; j++) {
        double xs = ((double)feat[j] - (double)FALL_MEAN[j]) / (double)FALL_SCALE[j];
        z += (double)FALL_COEF[j] * xs;
    }
    return (float)(1.0 / (1.0 + exp(-z)));
}

static inline int fall_trigger(float prob)
{
    return (prob >= FALL_PROB_THR) ? 1 : 0;
}

/*
 * Stillness / confirmation: population std < std_thr AND |mean - 1.0| < 0.2,
 * strict comparisons (FEATURES_SPEC.md section 4).
 */
static inline int fall_is_still(const float *mag, int n)
{
    float mean = 0.0f;
    for (int i = 0; i < n; i++) {
        mean += mag[i];
    }
    mean /= (float)n;
    float std = fall_std_pop(mag, n);
    return (std < FALL_STILL_STD_THR) && (fabsf(mean - 1.0f) < FALL_STILL_MEAN_TOL);
}

#endif /* FALL_FEATURES_H */
