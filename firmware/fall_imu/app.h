/* app.h - shared declarations for the fall_imu serial-menu firmware */
#ifndef APP_H
#define APP_H

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

/* 'x' typed on the serial port (set by the input thread) */
bool app_stop_requested(void);
/* device uptime in ms (ztimer msec since boot; a drop = reset/brownout) */
uint32_t app_up_ms(void);

#define FLUSH() fflush(stdout)

/* modes.c */
void mode_timing(void);     /* t */
void mode_live(void);       /* l */
void mode_rawlog(void);     /* w */
/* testmodes.c */
void mode_selftest(void);   /* s */
void mode_replay(void);     /* r */

#endif /* APP_H */
