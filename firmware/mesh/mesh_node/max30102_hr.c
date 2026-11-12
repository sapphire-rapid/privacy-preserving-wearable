#include "max30102_hr.h"

#if MESH_ROLE_HR

#include <stdbool.h>
#include "periph/i2c.h"
#include "ztimer.h"

#define MAX30102_I2C_DEV       I2C_DEV(0)
#define MAX30102_ADDR          0x57

#define REG_FIFO_WR_PTR        0x04
#define REG_OVF_COUNTER        0x05
#define REG_FIFO_RD_PTR        0x06
#define REG_FIFO_DATA          0x07
#define REG_FIFO_CONFIG        0x08
#define REG_MODE_CONFIG        0x09
#define REG_SPO2_CONFIG        0x0A
#define REG_LED1_PA            0x0C
#define REG_LED2_PA            0x0D

#define MODE_RESET             0x40
#define MODE_SPO2              0x03

#define SAMPLE_PERIOD_MS       10       /* 100 Hz, no averaging (SPO2_CONFIG 0x27) */
#define DC_ALPHA_NUM           1
#define DC_ALPHA_DEN           16
#define MIN_PEAK_AMPLITUDE     200
#define REFRACTORY_MS          300
#define MAX_PLAUSIBLE_JUMP     40000
#define BPM_AVG_WINDOW         4

static int32_t  _dc;
static bool     _dc_init;
static int32_t  _prev_ac;
static uint32_t _prev_ir;
static bool     _have_prev_ir;
static bool     _rising;
static uint32_t _t_ms;              /* sample-clock time */
static uint32_t _last_peak_ms;
static bool     _have_last_peak;
static uint32_t _intervals[BPM_AVG_WINDOW];
static int      _interval_count;
static int      _interval_idx;
static uint16_t _bpm;
static uint32_t _ovf_total;

static int _write(uint8_t reg, uint8_t val)
{
    return i2c_write_reg(MAX30102_I2C_DEV, MAX30102_ADDR, reg, val, 0);
}

int hr_init(void)
{
    i2c_acquire(MAX30102_I2C_DEV);
    int res = _write(REG_MODE_CONFIG, MODE_RESET);
    if (res == 0) {
        ztimer_sleep(ZTIMER_MSEC, 100);
        _write(REG_FIFO_CONFIG, 0x10);
        _write(REG_SPO2_CONFIG, 0x27);
        _write(REG_LED1_PA, 0x24);
        _write(REG_LED2_PA, 0x24);
        _write(REG_FIFO_WR_PTR, 0x00);
        _write(REG_OVF_COUNTER, 0x00);
        _write(REG_FIFO_RD_PTR, 0x00);
        res = _write(REG_MODE_CONFIG, MODE_SPO2);
    }
    i2c_release(MAX30102_I2C_DEV);
    return res;
}

static void _process_sample(uint32_t ir)
{
    _t_ms += SAMPLE_PERIOD_MS;

    if (_have_prev_ir) {
        int32_t jump = (int32_t)ir - (int32_t)_prev_ir;
        if (jump < 0) { jump = -jump; }
        if (jump > MAX_PLAUSIBLE_JUMP) { return; }
    }
    _prev_ir = ir;
    _have_prev_ir = true;

    if (!_dc_init) {
        _dc = (int32_t)ir;
        _dc_init = true;
        return;
    }

    _dc += ((int32_t)ir - _dc) * DC_ALPHA_NUM / DC_ALPHA_DEN;
    int32_t ac = (int32_t)ir - _dc;

    if (_rising && ac < _prev_ac && _prev_ac > MIN_PEAK_AMPLITUDE) {
        if (!_have_last_peak || (_t_ms - _last_peak_ms) >= REFRACTORY_MS) {
            if (_have_last_peak) {
                _intervals[_interval_idx] = _t_ms - _last_peak_ms;
                _interval_idx = (_interval_idx + 1) % BPM_AVG_WINDOW;
                if (_interval_count < BPM_AVG_WINDOW) { _interval_count++; }
                uint32_t sum = 0;
                for (int k = 0; k < _interval_count; k++) { sum += _intervals[k]; }
                uint32_t avg = sum / _interval_count;
                if (avg > 0) { _bpm = (uint16_t)(60000UL / avg); }
            }
            _last_peak_ms = _t_ms;
            _have_last_peak = true;
        }
    }
    _rising = (ac > _prev_ac);
    _prev_ac = ac;
}

void hr_poll(void)
{
    uint8_t wr = 0, rd = 0, ovf = 0;

    i2c_acquire(MAX30102_I2C_DEV);
    i2c_read_reg(MAX30102_I2C_DEV, MAX30102_ADDR, REG_OVF_COUNTER, &ovf, 0);
    i2c_read_reg(MAX30102_I2C_DEV, MAX30102_ADDR, REG_FIFO_WR_PTR, &wr, 0);
    i2c_read_reg(MAX30102_I2C_DEV, MAX30102_ADDR, REG_FIFO_RD_PTR, &rd, 0);
    _ovf_total += ovf;

    int n = (int)wr - (int)rd;
    if (n < 0) { n += 32; }
    if (n == 0 && ovf) { n = 32; }   /* full FIFO after overflow reads as wr == rd */

    for (int i = 0; i < n; i++) {
        uint8_t b[6];
        if (i2c_read_regs(MAX30102_I2C_DEV, MAX30102_ADDR, REG_FIFO_DATA, b, 6, 0) != 0) {
            continue;
        }
        uint32_t ir = (((uint32_t)b[3] << 16) | ((uint32_t)b[4] << 8) | b[5]) & 0x3FFFF;
        _process_sample(ir);
    }
    i2c_release(MAX30102_I2C_DEV);
}

uint16_t hr_bpm(void)       { return _bpm; }
uint32_t hr_overflows(void) { return _ovf_total; }

#else  /* relay build: stubs so main.c needs no #ifs around calls */

int hr_init(void)           { return 0; }
void hr_poll(void)          { }
uint16_t hr_bpm(void)       { return 0; }
uint32_t hr_overflows(void) { return 0; }

#endif
