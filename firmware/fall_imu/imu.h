/*
 * imu.h - LSM6DS3TR-C accelerometer sampler for the XIAO nRF52840 Sense.
 *
 * A dedicated high-priority thread polls STATUS_REG (0x1E) for XLDA (accel
 * data-ready) and reads the 6 output bytes in one burst when set, stamping the
 * sample with ztimer_usec at detection.  Samples go into an SPSC ring, so the
 * consumer can print/process without ever delaying the sensor read.
 * The sensor clock is the sample clock (DRDY-gated), same as Step 3a.
 */
#ifndef IMU_H
#define IMU_H

#include <stdint.h>

/* poll period of the DRDY check; detection delay is 0..IMU_POLL_US, so interval
 * jitter is bounded by +/- IMU_POLL_US (I2C is 100 kHz: a status read is
 * ~0.5 ms, so 2 ms keeps the bus < ~30 % busy) */
#ifndef IMU_POLL_US
#define IMU_POLL_US          (2000u)
#endif

typedef struct {
    uint32_t t_us;                 /* ztimer_usec at XLDA detection (wraps 2^32) */
    int16_t  x_mg, y_mg, z_mg;     /* milli-g, FS = +/-16 g                      */
} imu_sample_t;

typedef struct {
    uint8_t who_am_i;              /* 0x0F */
    uint8_t ctrl1_xl;              /* 0x10 */
    uint8_t ctrl2_g;               /* 0x11 */
    uint8_t ctrl3_c;               /* 0x12 */
    uint8_t ctrl4_c;               /* 0x13 */
    uint8_t ctrl6_c;               /* 0x15 */
    uint8_t ctrl8_xl;              /* 0x17 */
    int     ok;                    /* all reads succeeded */
} imu_regs_t;

/* init sensor (ODR from SAMPLE_RATE_HZ, FS 16 g), start the (idle) sampler thread */
int imu_init(void);
/* change the accelerometer ODR (26/52/104); call only while stopped */
int imu_set_odr_hz(unsigned hz);
/* ODR in Hz decoded from a CTRL1_XL readback (0 if unknown/power-down) */
unsigned imu_odr_hz(void);

void imu_start(void);              /* flush the ring and start sampling */
void imu_stop(void);
int  imu_pop(imu_sample_t *s);     /* non-blocking; 1 = got a sample */

uint32_t imu_overruns(void);       /* samples dropped because the ring was full */
uint32_t imu_i2c_errors(void);
int imu_read_regs(imu_regs_t *r);
unsigned imu_i2c_bus(void);        /* I2C_DEV index in use */
unsigned imu_i2c_addr(void);       /* 7-bit address in use */

#endif /* IMU_H */
