/*
 * imu.c - see imu.h.
 *
 * Verified against the RIOT source (~/riotproject, fac711a2b4):
 *   drivers/lsm6dsxx/include/lsm6dsxx_internal.h: STATUS_REG 0x1E, OUTX_L_XL
 *   LSM6DS3TR-C: STATUS_REG bit0 = XLDA; CTRL3_C bit6 = BDU, bit2 = IF_INC
 *   lsm6dsxx_params.h defaults: I2C_DEV(0), addr 0x6B
 */
#include <stdint.h>

#include "thread.h"
#include "ztimer.h"
#include "periph/i2c.h"
#include "lsm6dsxx.h"
#include "lsm6dsxx_internal.h"

#include "fall_model.h"
#include "imu.h"

#define IMU_I2C              I2C_DEV(0)
#define IMU_ADDR             0x6B

#define STATUS_XLDA          (0x01u)
#define CTRL3_C_BDU          (0x40u)      /* block data update */
#define CTRL3_C_IF_INC       (0x04u)      /* register auto-increment */

#define RING_N               (256u)       /* power of two */
#define MEM_BARRIER()        __asm volatile ("" ::: "memory")

/* ODR from the model's sample rate: a 26 Hz model is a header swap */
#if SAMPLE_RATE_HZ == 26
#define IMU_ODR_ENUM         LSM6DSXX_DATA_RATE_26HZ
#elif SAMPLE_RATE_HZ == 52
#define IMU_ODR_ENUM         LSM6DSXX_DATA_RATE_52HZ
#elif SAMPLE_RATE_HZ == 104
#define IMU_ODR_ENUM         LSM6DSXX_DATA_RATE_104HZ
#else
#error "SAMPLE_RATE_HZ must be 26, 52 or 104 (LSM6DS3TR-C ODR)"
#endif

static const lsm6dsxx_params_t _params = {
    .i2c             = IMU_I2C,
    .addr            = IMU_ADDR,
    .acc_odr         = IMU_ODR_ENUM,
    .gyro_odr        = LSM6DSXX_DATA_RATE_52HZ,   /* as in Step 3a */
    .acc_fs          = LSM6DSXX_ACC_FS_16G,
    .gyro_fs         = LSM6DSXX_GYRO_FS_245DPS,
    .acc_decimation  = LSM6DSXX_DECIMATION_NO,
    .gyro_decimation = LSM6DSXX_DECIMATION_NO,
};

static lsm6dsxx_t _dev;
static imu_sample_t _ring[RING_N];
static volatile uint32_t _wr, _rd;
static volatile uint32_t _overruns, _i2c_err;
static volatile int _running;

static char _stack[THREAD_STACKSIZE_DEFAULT + 512];

static int _reg_rd(uint8_t reg, uint8_t *v)
{
    i2c_acquire(IMU_I2C);
    int r = i2c_read_reg(IMU_I2C, IMU_ADDR, reg, v, 0);
    i2c_release(IMU_I2C);
    return r;
}

static int _reg_wr(uint8_t reg, uint8_t v)
{
    i2c_acquire(IMU_I2C);
    int r = i2c_write_reg(IMU_I2C, IMU_ADDR, reg, v, 0);
    i2c_release(IMU_I2C);
    return r;
}

static void *_sampler(void *arg)
{
    (void)arg;
    uint32_t next = ztimer_now(ZTIMER_USEC) + IMU_POLL_US;

    while (1) {
        if (!_running) {
            ztimer_sleep(ZTIMER_USEC, 5000);
            next = ztimer_now(ZTIMER_USEC) + IMU_POLL_US;
            continue;
        }
        int32_t wait = (int32_t)(next - ztimer_now(ZTIMER_USEC));
        if (wait > 0) {
            ztimer_sleep(ZTIMER_USEC, (uint32_t)wait);
        }
        else if (wait < -100000) {
            next = ztimer_now(ZTIMER_USEC);     /* far behind: resync grid */
        }
        next += IMU_POLL_US;

        uint8_t status = 0;
        uint8_t b[6];
        uint32_t t_us;

        i2c_acquire(IMU_I2C);
        int r = i2c_read_reg(IMU_I2C, IMU_ADDR, LSM6DSXX_REG_STATUS_REG, &status, 0);
        t_us = ztimer_now(ZTIMER_USEC);
        if (r < 0) {
            i2c_release(IMU_I2C);
            _i2c_err++;
            continue;
        }
        if (!(status & STATUS_XLDA)) {
            i2c_release(IMU_I2C);
            continue;                               /* sensor clock decides */
        }
        r = i2c_read_regs(IMU_I2C, IMU_ADDR, LSM6DSXX_REG_OUTX_L_XL, b, 6, 0);
        i2c_release(IMU_I2C);
        if (r < 0) {
            _i2c_err++;
            continue;
        }

        /* counts -> mg exactly as the RIOT driver does (range 16000 / INT16_MAX) */
        int16_t cx = (int16_t)(b[0] | (b[1] << 8));
        int16_t cy = (int16_t)(b[2] | (b[3] << 8));
        int16_t cz = (int16_t)(b[4] | (b[5] << 8));

        uint32_t wr = _wr;
        if (wr - _rd >= RING_N) {
            _overruns++;
            continue;
        }
        imu_sample_t *s = &_ring[wr % RING_N];
        s->t_us = t_us;
        s->x_mg = (int16_t)(((int32_t)cx * 16000) / INT16_MAX);
        s->y_mg = (int16_t)(((int32_t)cy * 16000) / INT16_MAX);
        s->z_mg = (int16_t)(((int32_t)cz * 16000) / INT16_MAX);
        MEM_BARRIER();
        _wr = wr + 1;
    }
    return NULL;
}

int imu_init(void)
{
    if (lsm6dsxx_init(&_dev, &_params) != LSM6DSXX_OK) {
        return -1;
    }
    /* BDU: output registers are not updated between the L and H byte reads;
     * IF_INC: burst reads auto-increment (default on, set explicitly) */
    uint8_t c3 = 0;
    if (_reg_rd(LSM6DSXX_REG_CTRL3_C, &c3) < 0 ||
        _reg_wr(LSM6DSXX_REG_CTRL3_C, c3 | CTRL3_C_BDU | CTRL3_C_IF_INC) < 0) {
        return -2;
    }
    thread_create(_stack, sizeof(_stack), THREAD_PRIORITY_MAIN - 2,
                  THREAD_CREATE_STACKTEST, _sampler, NULL, "imu");
    return 0;
}

int imu_set_odr_hz(unsigned hz)
{
    uint8_t code;
    switch (hz) {
    case 26:  code = LSM6DSXX_DATA_RATE_26HZ;  break;
    case 52:  code = LSM6DSXX_DATA_RATE_52HZ;  break;
    case 104: code = LSM6DSXX_DATA_RATE_104HZ; break;
    default:  return -1;
    }
    uint8_t c1;
    if (_reg_rd(LSM6DSXX_REG_CTRL1_XL, &c1) < 0) {
        return -2;
    }
    c1 = (uint8_t)((c1 & 0x0F) | (code << 4));
    return (_reg_wr(LSM6DSXX_REG_CTRL1_XL, c1) < 0) ? -3 : 0;
}

unsigned imu_odr_hz(void)
{
    uint8_t c1;
    if (_reg_rd(LSM6DSXX_REG_CTRL1_XL, &c1) < 0) {
        return 0;
    }
    switch (c1 >> 4) {
    case 2:  return 26;
    case 3:  return 52;
    case 4:  return 104;
    case 5:  return 208;
    default: return 0;
    }
}

void imu_start(void)
{
    _rd = _wr;                 /* flush (single consumer context) */
    _overruns = 0;
    _i2c_err = 0;
    MEM_BARRIER();
    _running = 1;
}

void imu_stop(void)
{
    _running = 0;
    ztimer_sleep(ZTIMER_USEC, 10000);   /* let an in-flight read finish */
    _rd = _wr;
}

int imu_pop(imu_sample_t *s)
{
    uint32_t rd = _rd;
    if (rd == _wr) {
        return 0;
    }
    *s = _ring[rd % RING_N];
    MEM_BARRIER();
    _rd = rd + 1;
    return 1;
}

uint32_t imu_overruns(void)   { return _overruns; }
uint32_t imu_i2c_errors(void) { return _i2c_err; }

int imu_read_regs(imu_regs_t *r)
{
    int e = 0;
    e |= _reg_rd(LSM6DSXX_REG_WHO_AM_I, &r->who_am_i) < 0;
    e |= _reg_rd(LSM6DSXX_REG_CTRL1_XL, &r->ctrl1_xl) < 0;
    e |= _reg_rd(LSM6DSXX_REG_CTRL2_G,  &r->ctrl2_g)  < 0;
    e |= _reg_rd(LSM6DSXX_REG_CTRL3_C,  &r->ctrl3_c)  < 0;
    e |= _reg_rd(LSM6DSXX_REG_CTRL4_C,  &r->ctrl4_c)  < 0;
    e |= _reg_rd(LSM6DSXX_REG_CTRL6_C,  &r->ctrl6_c)  < 0;
    e |= _reg_rd(LSM6DSXX_REG_CTRL8_XL, &r->ctrl8_xl) < 0;
    r->ok = !e;
    return e ? -1 : 0;
}
