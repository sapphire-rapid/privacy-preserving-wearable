/*
 * fall_imu - Step 3a: IMU-only sampling + 60 s timing check.
 *
 * Sensor clock is the sample clock: poll every ~5 ms with ztimer, read
 * STATUS_REG (0x1E) directly over I2C, and accept a sample only when the
 * accelerometer data-ready bit XLDA (bit 0) is set.
 *
 * Verified against the RIOT source:
 *   drivers/lsm6dsxx/include/lsm6dsxx_internal.h: LSM6DSXX_REG_STATUS_REG = 0x1E
 *   LSM6DS3TR-C datasheet: STATUS_REG bit0 = XLDA
 *   lsm6dsxx_params.h defaults: I2C_DEV(0), addr 0x6B, ODR 52 Hz, FS 2 g
 * We override FS to +/-16 g as required for fall peak capture.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <math.h>

#include "ztimer.h"
#include "periph/i2c.h"
#include "lsm6dsxx.h"
#include "lsm6dsxx_internal.h"      /* LSM6DSXX_REG_STATUS_REG */

#define IMU_I2C              I2C_DEV(0)   /* LSM6DSXX_PARAM_I2C default */
#define IMU_ADDR             0x6B         /* LSM6DSXX_PARAM_ADDR default */

#define LSM6DSXX_STATUS_XLDA (0x01u)      /* STATUS_REG bit0: accel data-ready */

#define POLL_US              (5000u)      /* poll every ~5 ms              */
#define CHECK_SEC            (60u)
#define TARGET_MS            (1000.0f / 52.0f)   /* 19.2308 ms           */
#define TARGET_TOL_MS        (3.0f)

static const lsm6dsxx_params_t _params = {
    .i2c             = IMU_I2C,
    .addr            = IMU_ADDR,
    .acc_odr         = LSM6DSXX_DATA_RATE_52HZ,
    .gyro_odr        = LSM6DSXX_DATA_RATE_52HZ,
    .acc_fs          = LSM6DSXX_ACC_FS_16G,
    .gyro_fs         = LSM6DSXX_GYRO_FS_245DPS,
    .acc_decimation  = LSM6DSXX_DECIMATION_NO,
    .gyro_decimation = LSM6DSXX_DECIMATION_NO,
};

/* read STATUS_REG directly and report whether a new accel sample is ready */
static bool _new_accel_data(lsm6dsxx_t *dev)
{
    uint8_t status = 0;
    i2c_acquire(dev->params.i2c);
    int res = i2c_read_reg(dev->params.i2c, dev->params.addr,
                           LSM6DSXX_REG_STATUS_REG, &status, 0);
    i2c_release(dev->params.i2c);
    return (res >= 0) && ((status & LSM6DSXX_STATUS_XLDA) != 0);
}

int main(void)
{
    lsm6dsxx_t dev;
    lsm6dsxx_3d_data_t acc;

    puts("fall_imu 3a: sampling + 60 s timing check");

    if (lsm6dsxx_init(&dev, &_params) != LSM6DSXX_OK) {
        puts("[ERROR] lsm6dsxx_init failed");
        return 1;
    }
    puts("[OK] LSM6DS3TR-C: ODR=52 Hz, FS=+/-16 g");

    uint32_t n = 0, n_out = 0;
    uint32_t t_prev = 0, t0 = 0;
    uint32_t min_us = UINT32_MAX, max_us = 0;
    uint64_t sum_us = 0;
    uint64_t preg = 0;
    float mag_sum = 0.0f;
    uint32_t mag_n = 0;
    uint32_t next_poll = ztimer_now(ZTIMER_USEC) + POLL_US;

    while (1) {
        int32_t wait = (int32_t)(next_poll - ztimer_now(ZTIMER_USEC));
        if (wait > 0) {
            ztimer_sleep(ZTIMER_USEC, (uint32_t)wait);
        }
        next_poll += POLL_US;

        if (!_new_accel_data(&dev)) {
            continue;                   /* sensor clock decides */
        }
        if (lsm6dsxx_read_acc(&dev, &acc) != LSM6DSXX_OK) {
            continue;
        }

        uint32_t now = ztimer_now(ZTIMER_USEC);

        /* driver returns milli-g -> convert to g */
        float ax = (float)acc.x / 1000.0f;
        float ay = (float)acc.y / 1000.0f;
        float az = (float)acc.z / 1000.0f;
        float a  = sqrtf(ax * ax + ay * ay + az * az);

        mag_sum += a;
        mag_n++;

        if (n == 0) {
            t0 = now;
            printf("first sample: |a|=%.3f g  (x=%d y=%d z=%d mg)  t=%lu us\n",
                   (double)a, acc.x, acc.y, acc.z, (unsigned long)now);
        }
        else {
            uint32_t dt = now - t_prev;
            sum_us += dt;
            if (dt < min_us) { min_us = dt; }
            if (dt > max_us) { max_us = dt; }
            if (fabsf((float)dt / 1000.0f - TARGET_MS) > TARGET_TOL_MS) {
                n_out++;
            }
        }
        if (n < 5) {
            printf("sample %lu: |a|=%.3f g  (x=%d y=%d z=%d mg)  t=%lu us\n",
                   (unsigned long)n, (double)a, acc.x, acc.y, acc.z,
                   (unsigned long)now);
        }
        t_prev = now;
        n++;

        uint32_t elapsed_ms = (now - t0) / 1000u;
        if (elapsed_ms / 1000u != preg) {
            preg = elapsed_ms / 1000u;
            printf("t=%lu.%03lu s  n=%lu  |a|=%.3f g\n",
                   (unsigned long)(elapsed_ms / 1000u),
                   (unsigned long)(elapsed_ms % 1000u),
                   (unsigned long)n, (double)a);
        }

        if (elapsed_ms >= (uint32_t)CHECK_SEC * 1000u) {
            break;
        }
    }

    float mean_ms = (n > 1) ? ((float)sum_us / (float)(n - 1) / 1000.0f) : 0.0f;
    putchar('\n');
    puts("=== TIMING CHECK (60 s) ===");
    printf("samples pushed : %lu\n", (unsigned long)n);
    printf("interval mean  : %.3f ms (target %.3f ms)\n",
           (double)mean_ms, (double)TARGET_MS);
    printf("interval min   : %.3f ms\n", (double)(min_us / 1000.0f));
    printf("interval max   : %.3f ms\n", (double)(max_us / 1000.0f));
    printf("outside %.3f +/- %.1f ms : %lu of %lu\n",
           (double)TARGET_MS, (double)TARGET_TOL_MS,
           (unsigned long)n_out, (unsigned long)(n - 1));
    printf("mean |a|       : %.3f g\n", (double)(mag_n ? mag_sum / mag_n : 0.0f));
    puts("=== DONE ===");

    return 0;
}
