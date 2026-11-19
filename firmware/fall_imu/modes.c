/*
 * modes.c - hardware modes: t (60 s timing), l (live pipeline), w (raw log).
 * All markers ("### START x" / "### DONE x") are what host/serial_log.py waits on.
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "board.h"
#include "ztimer.h"

#include "app.h"
#include "imu.h"
#include "pipeline.h"

/* ------------------------------------------------------------------------- */
/* t: 60 s timing on the DRDY-gated sampler                                   */
/* ------------------------------------------------------------------------- */
#define CHECK_SEC       (60u)
#define TARGET_MS       (1000.0f / (float)SAMPLE_RATE_HZ)
#define TARGET_TOL_MS   (3.0f)

void mode_timing(void)
{
    puts("### START t");
    printf("TIMING target_dt_ms=%.3f tol_ms=%.1f duration_s=%u poll_us=%u odr_hz=%u\n",
           (double)TARGET_MS, (double)TARGET_TOL_MS, (unsigned)CHECK_SEC,
           (unsigned)IMU_POLL_US, imu_odr_hz());
    FLUSH();

    imu_start();

    imu_sample_t s;
    uint32_t n = 0, n_out = 0, t0 = 0, t_prev = 0, min_us = UINT32_MAX, max_us = 0;
    uint32_t last_sec = 0;
    double sum_us = 0.0, sum_us2 = 0.0, mag_sum = 0.0, mag_sum2 = 0.0;
    double mag_min = 1e9, mag_max = 0.0;
    uint32_t elapsed_us = 0;
    bool stopped = false;

    while (1) {
        if (app_stop_requested()) {
            stopped = true;
            break;
        }
        if (!imu_pop(&s)) {
            ztimer_sleep(ZTIMER_USEC, 1000);
            continue;
        }
        float ax = (float)s.x_mg / 1000.0f;
        float ay = (float)s.y_mg / 1000.0f;
        float az = (float)s.z_mg / 1000.0f;
        double a = (double)sqrtf(ax * ax + ay * ay + az * az);
        mag_sum += a;
        mag_sum2 += a * a;
        if (a < mag_min) { mag_min = a; }
        if (a > mag_max) { mag_max = a; }

        if (n == 0) {
            t0 = s.t_us;
        }
        else {
            uint32_t dt = s.t_us - t_prev;
            sum_us += dt;
            sum_us2 += (double)dt * (double)dt;
            if (dt < min_us) { min_us = dt; }
            if (dt > max_us) { max_us = dt; }
            if (fabsf((float)dt / 1000.0f - TARGET_MS) > TARGET_TOL_MS) {
                n_out++;
            }
        }
        if (n < 5) {
            printf("sample %lu: |a|=%.3f g (x=%d y=%d z=%d mg) t_us=%lu\n",
                   (unsigned long)n, a, s.x_mg, s.y_mg, s.z_mg, (unsigned long)s.t_us);
        }
        t_prev = s.t_us;
        n++;

        elapsed_us = s.t_us - t0;
        if (elapsed_us / 1000000u != last_sec) {
            last_sec = elapsed_us / 1000000u;
            printf("t=%lu s n=%lu |a|=%.3f g up_ms=%lu\n", (unsigned long)last_sec,
                   (unsigned long)n, a, (unsigned long)app_up_ms());
            FLUSH();
        }
        if (elapsed_us >= CHECK_SEC * 1000000u) {
            break;
        }
    }
    imu_stop();

    if (n > 1) {
        double m = sum_us / (double)(n - 1);
        double var = sum_us2 / (double)(n - 1) - m * m;
        double mm = mag_sum / (double)n;
        double msd = sqrt(fmax(0.0, mag_sum2 / (double)n - mm * mm));
        puts("=== TIMING CHECK ===");
        printf("TIMING samples=%lu expected=%u elapsed_s=%.3f\n", (unsigned long)n,
               (unsigned)(SAMPLE_RATE_HZ * CHECK_SEC), (double)elapsed_us / 1e6);
        printf("TIMING dt_mean_ms=%.3f dt_std_ms=%.3f dt_min_ms=%.3f dt_max_ms=%.3f\n",
               m / 1000.0, sqrt(fmax(0.0, var)) / 1000.0, (double)min_us / 1000.0,
               (double)max_us / 1000.0);
        printf("TIMING outside_tol=%lu of %lu (%.3f %%)\n", (unsigned long)n_out,
               (unsigned long)(n - 1), 100.0 * (double)n_out / (double)(n - 1));
        printf("TIMING mag_mean_g=%.4f mag_std_g=%.4f mag_min_g=%.4f mag_max_g=%.4f\n",
               mm, msd, mag_min, mag_max);
    }
    printf("TIMING overruns=%lu i2c_errors=%lu\n", (unsigned long)imu_overruns(),
           (unsigned long)imu_i2c_errors());
    printf(stopped ? "### STOPPED t\n" : "### DONE t\n");
    FLUSH();
}

/* ------------------------------------------------------------------------- */
/* l: live pipeline (ring -> stride -> features -> LR -> trigger -> confirm)  */
/* ------------------------------------------------------------------------- */
#define LED_ON_MS   (2000u)

static fall_pipe_t _pipe;

void mode_live(void)
{
    puts("### START l");
    printf("LIVE model: rate=%d win=%d stride=%d confirm=%d thr=%.2f odr_hz=%u\n",
           SAMPLE_RATE_HZ, WIN_SAMPLES, STRIDE_SAMPLES, CONFIRM_SAMPLES,
           (double)FALL_PROB_THR, imu_odr_hz());
    FLUSH();

    fall_pipe_reset(&_pipe);
    LED0_OFF;
    imu_start();

    imu_sample_t s;
    fall_ev_t ev;
    bool led_on = false;
    uint32_t led_t0 = 0;
    bool stopped = false;
    uint32_t n_conf = 0, n_canc = 0, n_trig = 0;

    while (1) {
        if (app_stop_requested()) {
            stopped = true;
            break;
        }
        if (led_on && (app_up_ms() - led_t0) >= LED_ON_MS) {
            LED0_OFF;
            led_on = false;
        }
        if (!imu_pop(&s)) {
            ztimer_sleep(ZTIMER_USEC, 1000);
            continue;
        }
        fall_pipe_push(&_pipe, (float)s.x_mg / 1000.0f, (float)s.y_mg / 1000.0f,
                       (float)s.z_mg / 1000.0f, &ev);
        unsigned long up = (unsigned long)app_up_ms();

        if (ev.window) {
            printf("LIVE up_ms=%lu n=%lu wi=%lu p=%.6f max=%.3f state=%s pend=%u\n",
                   up, (unsigned long)_pipe.n, (unsigned long)ev.wi, (double)ev.prob,
                   (double)ev.feat[0], _pipe.n_pend ? "CONFIRMING" : "IDLE",
                   (unsigned)_pipe.n_pend);
        }
        if (ev.trigger) {
            n_trig++;
            printf("EVT TRIGGER up_ms=%lu n=%lu wi=%lu p=%.6f\n", up,
                   (unsigned long)_pipe.n, (unsigned long)ev.wi, (double)ev.prob);
        }
        if (ev.pend_overflow) {
            puts("EVT ERROR pending list overflow");
        }
        if (ev.conf == FALL_CONF_CONFIRMED) {
            n_conf++;
            printf("EVT CONFIRMED up_ms=%lu n=%lu trig_n=%lu std=%.4f mean=%.4f\n", up,
                   (unsigned long)_pipe.n, (unsigned long)ev.conf_trig_n,
                   (double)ev.conf_std, (double)ev.conf_mean);
            LED0_ON;
            led_on = true;
            led_t0 = app_up_ms();
        }
        else if (ev.conf == FALL_CONF_CANCELLED) {
            n_canc++;
            printf("EVT CANCELLED up_ms=%lu n=%lu trig_n=%lu std=%.4f mean=%.4f\n", up,
                   (unsigned long)_pipe.n, (unsigned long)ev.conf_trig_n,
                   (double)ev.conf_std, (double)ev.conf_mean);
        }
        if (ev.window || ev.conf) {
            FLUSH();
        }
    }
    imu_stop();
    LED0_OFF;
    printf("LIVE samples=%lu triggers=%lu confirmed=%lu cancelled=%lu overruns=%lu i2c_errors=%lu\n",
           (unsigned long)_pipe.n, (unsigned long)n_trig, (unsigned long)n_conf,
           (unsigned long)n_canc, (unsigned long)imu_overruns(),
           (unsigned long)imu_i2c_errors());
    printf(stopped ? "### STOPPED l\n" : "### DONE l\n");
    FLUSH();
}

/* ------------------------------------------------------------------------- */
/* w: raw log "t_us,ax_mg,ay_mg,az_mg" at 52 Hz, whatever the model rate      */
/* ------------------------------------------------------------------------- */
#define RAWLOG_HZ   (52u)

void mode_rawlog(void)
{
    puts("### START w");
    unsigned old_hz = imu_odr_hz();
    if (old_hz != RAWLOG_HZ) {
        printf("RAWLOG switching ODR %u -> %u Hz\n", old_hz, RAWLOG_HZ);
        imu_set_odr_hz(RAWLOG_HZ);
        ztimer_sleep(ZTIMER_MSEC, 100);     /* let the filter settle */
    }
    printf("RAWLOG odr_hz=%u columns=t_us,ax_mg,ay_mg,az_mg\n", imu_odr_hz());
    puts("t_us,ax_mg,ay_mg,az_mg");
    FLUSH();

    imu_start();
    imu_sample_t s;
    uint32_t n = 0;
    bool stopped = false;
    while (1) {
        if (app_stop_requested()) {
            stopped = true;
            break;
        }
        if (!imu_pop(&s)) {
            ztimer_sleep(ZTIMER_USEC, 1000);
            continue;
        }
        printf("%lu,%d,%d,%d\n", (unsigned long)s.t_us, s.x_mg, s.y_mg, s.z_mg);
        FLUSH();
        n++;
    }
    imu_stop();
    if (old_hz != RAWLOG_HZ && old_hz != 0) {
        imu_set_odr_hz(old_hz);
    }
    printf("RAWLOG samples=%lu overruns=%lu i2c_errors=%lu\n", (unsigned long)n,
           (unsigned long)imu_overruns(), (unsigned long)imu_i2c_errors());
    printf(stopped ? "### STOPPED w\n" : "### DONE w\n");
    FLUSH();
}
