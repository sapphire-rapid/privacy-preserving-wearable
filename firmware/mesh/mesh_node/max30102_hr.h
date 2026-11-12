/*
 * MAX30102 heart-rate front end (HR role only).
 * Driver + DC-removal + peak detector carried over unchanged from max30102_probe.
 */
#ifndef MAX30102_HR_H
#define MAX30102_HR_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** reset + configure the sensor (SpO2 mode, 100 Hz). 0 on success */
int hr_init(void);

/** drain the FIFO and update the BPM estimate. Call at least every ~250 ms
 *  (32-sample FIFO at 100 Hz = 320 ms before overflow). */
void hr_poll(void);

/** latest averaged BPM (0 until two peaks were seen) */
uint16_t hr_bpm(void);

/** samples lost to FIFO overflow since boot (should stay 0) */
uint32_t hr_overflows(void);

#ifdef __cplusplus
}
#endif

#endif /* MAX30102_HR_H */
