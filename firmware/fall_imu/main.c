/*
 * fall_imu - on-board fall pipeline (Steps 3a-3d) behind a serial command menu.
 *
 *   t  60 s timing of the DRDY-gated sampler        (3a)
 *   s  self-test of on-device features + LR          (3b)
 *   r  replay test windows through the live path     (3b')
 *   l  live pipeline: trigger -> confirm, LED 2 s    (3c)
 *   w  raw log t_us,ax_mg,ay_mg,az_mg at 52 Hz       (3d)
 *   x  stop the current mode / back to the menu
 *   i  info: ODR, FS, CTRL1_XL/CTRL8_XL, model macros, sizes
 *
 * stdin: stdio_cdc_acm (the board default) selects the `stdin` and
 * `stdio_available` modules by itself (RIOT makefiles/stdio.inc.mk), so no
 * extra USEMODULE is needed for input.
 * A dedicated thread blocks on stdio_read(), so 'x' is seen even while a mode
 * is busy printing/sampling.
 */
#include <stdio.h>
#include <stdint.h>

#include "board.h"
#include "thread.h"
#include "ztimer.h"
#include "stdio_base.h"

#include "app.h"
#include "imu.h"
#include "fall_model.h"
#include "fall_features.h"

#ifndef RIOT_VERSION
#define RIOT_VERSION "unknown"
#endif
#ifndef APP_GIT_REV
#define APP_GIT_REV "unknown"
#endif

/* linker symbols (cortexm_base.ld) for a runtime size report */
extern char _sfixed, _etext, _srelocate, _erelocate, _szero, _ezero;

static volatile int _stop;
static volatile uint8_t _cmd[16];
static volatile uint8_t _cmd_wr, _cmd_rd;
static char _in_stack[THREAD_STACKSIZE_DEFAULT];
static int _imu_rc = -99;

bool app_stop_requested(void) { return _stop != 0; }
uint32_t app_up_ms(void) { return ztimer_now(ZTIMER_MSEC); }

static void *_input_thread(void *arg)
{
    (void)arg;
    while (1) {
        char c;
        if (stdio_read(&c, 1) != 1) {
            continue;
        }
        if (c == 'x' || c == 'X') {
            _stop = 1;
        }
        uint8_t wr = _cmd_wr;
        if ((uint8_t)(wr - _cmd_rd) < sizeof(_cmd)) {
            _cmd[wr % sizeof(_cmd)] = (uint8_t)c;
            __asm volatile ("" ::: "memory");
            _cmd_wr = wr + 1;
        }
    }
    return NULL;
}

static int _next_cmd(void)
{
    if (_cmd_rd == _cmd_wr) {
        return -1;
    }
    uint8_t c = _cmd[_cmd_rd % sizeof(_cmd)];
    _cmd_rd++;
    return c;
}

static void _menu(void)
{
    puts("MENU> t=timing(60s) s=selftest r=replay l=live w=rawlog x=stop i=info");
    FLUSH();
}

static void _info(void)
{
    puts("### START i");
    printf("INFO build=%s date=\"%s %s\" riot=%s\n", APP_GIT_REV, __DATE__, __TIME__,
           RIOT_VERSION);
    printf("INFO up_ms=%lu imu_init_rc=%d\n", (unsigned long)app_up_ms(), _imu_rc);

    imu_regs_t r;
    imu_read_regs(&r);
    printf("INFO imu i2c_dev=%u addr=0x%02X poll_us=%u\n", imu_i2c_bus(), imu_i2c_addr(),
           (unsigned)IMU_POLL_US);
    if (!r.ok) {
        puts("INFO imu register read FAILED (values below are not valid)");
    }
    printf("INFO imu who_am_i=0x%02X ok=%d\n", r.who_am_i, r.ok);
    printf("INFO CTRL1_XL(0x10)=0x%02X  ODR_XL=0x%X (%u Hz)  FS_XL=0x%X (%s)  LPF1_BW_SEL=%u  BW0_XL=%u\n",
           r.ctrl1_xl, r.ctrl1_xl >> 4, imu_odr_hz(), (r.ctrl1_xl >> 2) & 3,
           ((r.ctrl1_xl >> 2) & 3) == 1 ? "+/-16 g" :
           ((r.ctrl1_xl >> 2) & 3) == 0 ? "+/-2 g" :
           ((r.ctrl1_xl >> 2) & 3) == 2 ? "+/-4 g" : "+/-8 g",
           (r.ctrl1_xl >> 1) & 1, r.ctrl1_xl & 1);
    printf("INFO CTRL8_XL(0x17)=0x%02X  LPF2_XL_EN=%u  HPCF_XL=%u  HP_SLOPE_XL_EN=%u  LOW_PASS_ON_6D=%u\n",
           r.ctrl8_xl, r.ctrl8_xl >> 7, (r.ctrl8_xl >> 5) & 3, (r.ctrl8_xl >> 2) & 1,
           r.ctrl8_xl & 1);
    printf("INFO CTRL2_G(0x11)=0x%02X CTRL3_C(0x12)=0x%02X CTRL4_C(0x13)=0x%02X CTRL6_C(0x15)=0x%02X\n",
           r.ctrl2_g, r.ctrl3_c, r.ctrl4_c, r.ctrl6_c);
    puts("INFO sampler i2c=100kHz");

    printf("INFO model SAMPLE_RATE_HZ=%d WIN_SAMPLES=%d STRIDE_SAMPLES=%d CONFIRM_SAMPLES=%d "
           "TILT_PRE=%d TILT_POST=%d TILT_FALLBACK=%d POST_STD=%d N_FEATURES=%d\n",
           SAMPLE_RATE_HZ, WIN_SAMPLES, STRIDE_SAMPLES, CONFIRM_SAMPLES,
           TILT_PRE_SAMPLES, TILT_POST_SAMPLES, TILT_FALLBACK_SAMPLES,
           POST_STD_SAMPLES, N_FEATURES);
    printf("INFO model FALL_PROB_THR=%.4f STILL_STD_THR=%.4f STILL_MEAN_TOL=%.4f "
           "FALL_STILL_STD_THR=%.4f FALL_STILL_MEAN_TOL=%.4f\n",
           (double)FALL_PROB_THR, (double)STILL_STD_THR, (double)STILL_MEAN_TOL,
           (double)FALL_STILL_STD_THR, (double)FALL_STILL_MEAN_TOL);

    unsigned long text = (unsigned long)(&_etext - &_sfixed);
    unsigned long data = (unsigned long)(&_erelocate - &_srelocate);
    unsigned long bss = (unsigned long)(&_ezero - &_szero);
    printf("INFO size text=%lu data=%lu bss=%lu flash~%lu (linker symbols; see arm-none-eabi-size)\n",
           text, data, bss, text + data);
    puts("### DONE i");
    FLUSH();
}

int main(void)
{
    /* USB CDC drops output until the host opens the port; the host tool
     * re-requests the menu with a newline, so this banner may be missed. */
    ztimer_sleep(ZTIMER_MSEC, 1500);
    printf("### BOOT fall_imu build=%s up_ms=%lu\n", APP_GIT_REV, (unsigned long)app_up_ms());

    thread_create(_in_stack, sizeof(_in_stack), THREAD_PRIORITY_MAIN - 1,
                  THREAD_CREATE_STACKTEST, _input_thread, NULL, "input");

    _imu_rc = imu_init();
    if (_imu_rc != 0) {
        printf("[ERROR] imu_init failed rc=%d\n", _imu_rc);
    }
    else {
        puts("[OK] LSM6DS3TR-C initialised");
    }
    _menu();

    while (1) {
        int c = _next_cmd();
        if (c < 0) {
            ztimer_sleep(ZTIMER_MSEC, 10);
            continue;
        }
        if (c != 'x' && c != 'X') {
            _stop = 0;                  /* a stop typed before this command is stale */
        }
        switch (c) {
        case 't': if (_imu_rc == 0) { mode_timing(); } else { puts("imu not ready"); } break;
        case 'l': if (_imu_rc == 0) { mode_live(); }   else { puts("imu not ready"); } break;
        case 'w': if (_imu_rc == 0) { mode_rawlog(); } else { puts("imu not ready"); } break;
        case 's': mode_selftest(); break;
        case 'r': mode_replay(); break;
        case 'i': _info(); break;
        case 'x': case 'X': _stop = 0; break;
        default: break;
        }
        _stop = 0;
        _menu();
    }
    return 0;
}
