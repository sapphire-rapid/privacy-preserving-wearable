# fall_imu on-board validation report (Steps 3a–3d)

Board: bare Seeed XIAO nRF52840 Sense on USB (LSM6DS3TR-C, internal I2C bus).
Branch `fall-imu-onboard`. Firmware under test: commit `10368b0`
(`INFO build=10368b0`), RIOT `fac711a2b4` (untouched), toolchain
arm-none-eabi-gcc 15.2.0. Every number below is a measured value; the log it came
from is given in brackets. Logs live in `firmware/fall_imu/logs/` (gitignored, so
the file names are the provenance).

## 0. Build, flash, RAM

| item | value | source |
|---|---|---|
| text / data / bss (arm-none-eabi-size) | 57688 / 160 / 24432 B (dec 82280) | build output of `10368b0` |
| flash ≈ text+data | 57848 B (linker symbols, `i`) | `i_20261119-120010.log` |
| `printf_float` (newlib-nano) | needed for `%f`/`%g`; part of the above | Makefile |
| first flash (`8b2baa6`) | IMU did not answer: `imu_init_rc=-1`, all register reads failed | `i_20261119-115103.log` |
| cause | `imu.c` used the generic driver defaults I2C_DEV(0)/0x6B (empty header bus); this board's IMU is I2C_DEV(1)/0x6A (`board.h`), power P1.08 set by `board.c`. The old Step 3a `main.c` had the same two constants, so it could never have run on this board. | board.h |
| fix | `10368b0`: use `LSM6DSXX_PARAM_I2C/_ADDR` from `board.h` | git |

Registers read back on the working firmware (`i_20261119-120010.log`):

| register | value | decoded |
|---|---|---|
| WHO_AM_I (0x0F) | 0x6A | I2C_DEV(1), address 0x6A |
| CTRL1_XL (0x10) | 0x34 | ODR_XL = 0x3 (52 Hz nominal), FS_XL = 0x1 (±16 g), LPF1_BW_SEL = 0, BW0_XL = 0 |
| CTRL8_XL (0x17) | 0x00 | LPF2_XL_EN = 0, HPCF_XL = 0, HP_SLOPE_XL_EN = 0, LOW_PASS_ON_6D = 0 |
| CTRL3_C (0x12) | 0x44 | BDU = 1, IF_INC = 1 (set by `imu_init`) |
| CTRL2_G (0x11) | 0x30 | gyro ODR 52 Hz (left on as in the old 3a; unused) |

**Which digital LPF these imply: NOT verified.** The ST datasheet could not be
fetched in this session (server timeout), so no register-description or bandwidth-table
citation is given here. What is established from the readback alone: LPF2 is disabled
(`LPF2_XL_EN = 0`), no high-pass is enabled, and `LPF1_BW_SEL = BW0_XL = 0`.
TODO: look up the CTRL1_XL/CTRL8_XL bandwidth tables in the LSM6DS3TR-C datasheet and
fill in the bandwidth.

## 1. Step 3a — 60 s timing (`t`)

Board flat and still on the table. Log: `t_20261119-120142.log`
(EVENT lines `start/end flat_still_on_table`).

| quantity | measured |
|---|---|
| samples in 60.006 s | 3264 (expected 3120 at nominal 52 Hz: +4.6 %) |
| **real ODR** (n−1)/elapsed | **54.378 Hz (+4.57 % vs nominal 52 Hz)** |
| interval mean / σ / min / max | 18.390 / 0.808 / 9.999 / 20.013 ms (nominal 19.231 ms) |
| per-second sample counts (60 s) | 54 ×37, 55 ×22 → spread 1 |
| outside 19.231 ± 3 ms | 1 of 3263 (0.031 %) — the one 9.999 ms interval (likely a delayed detection of the preceding sample; not investigated) |
| \|a\| mean / σ / min / max | 1.0455 / 0.0008 / 1.0420 / 1.0511 g |
| overruns / I2C errors | 0 / 0 |
| device resets | none |

Clock cross-check (same log, 60 per-second lines): host wall clock 59.110 s,
`ztimer_msec` (`up_ms`) 59.112 s, `ztimer_usec` labels 59 s; 3208 samples → 54.27 Hz
(host) / 54.27 Hz (`up_ms`). All three clocks agree, so the extra rate is the sensor's
real output rate, not a timing error in the sampler.

The "52 Hz" setting therefore runs at ~54.4 Hz on this unit. ST community threads on
related parts say the ODR derives from an internal oscillator and 52 Hz is nominal/typical
(<https://community.st.com/mems-sensors-48/tolerance-of-imu-internal-clock-sampling-frequency-127675>);
no tolerance figure from the datasheet itself was obtained.

**Pass criterion for 3a (redefined by the project owner after this measurement):**
stable rate (per-second counts within ±1), 0 overruns, 0 I2C errors, and the real ODR
recorded. All met → **3a PASS, with the characterisation above.** (The original
"≈3120 samples ±2 %, mean dt ≈ 19.23 ms" criteria are NOT met: +4.6 %, 18.39 ms.)

Consequence for the model (unchanged, trained at 52 Hz): at the real rate of
54.378 Hz one 104-sample window spans **1.91 s** (not 2.00 s), the 156-sample confirm
segment **2.87 s** (not 3.00 s), the 52-sample `std_mag_post` window 0.96 s, and the
26-sample tilt windows 0.48 s. `max_jerk` is per sample and the thresholds are in g, so
the shift is a systematic ~4.6 % in time scale only.

Sampler: DRDY-gated (STATUS_REG XLDA poll every 2 ms from a dedicated thread, 6-byte
burst read, timestamp at detection); the poll bounds the interval jitter to about ±2 ms.

## 2. Step 3b — on-device features + LR (`s`)

Log: `s_20261119-121626.log` (firmware `10368b0`; an earlier run on `8b2baa6`,
`s_20261119-115132.log`, gave the same results).

* **12/12 windows and 6/6 stillness segments PASS.** Features within 1e-4 relative
  required; worst per feature: max_mag 1.03e-07, min_mag 9.66e-08, mean_mag 4.20e-07,
  std_mag 6.21e-07, range_mag 1.61e-06, max_jerk 2.06e-06, std_mag_post 4.33e-07,
  count_low 0 (exact), tilt_deg 9.9e-07. Decisions identical on all 12 windows
  (6 triggers, 6 non-triggers) and all 6 segments (3 still, 3 moving).
* Probabilities agree to ≤ 4.5e-8 absolute (per-window expected/got/diff are in the log;
  the full per-feature expected-vs-got table is the `SELFTEST   fN` lines).
* Cosmetic: newlib-nano prints an exact 0 as `0.00e-308` (`%e` and `%g` alike); a
  `rel=0.00e-308` in the log means exactly 0.
* **Time per window (ztimer_usec, 100 runs, cycling over the 12 windows):**
  features + LR mean 554.6 µs / max 592 µs; features only 351.3 / 388 µs;
  LR only 203.3 / 235 µs. (Earlier run on `8b2baa6`: 550.2 / 560 µs.) A window is
  evaluated every 26 samples ≈ 478 ms at the real rate, so this is ~0.12 % duty.

## 3. Step 3b' — replay through the live path (`r`)

Log: `r_20261119-121627.log`. 18 sequences, each through a freshly reset
`fall_pipe_t` (the same ring → stride → features → LR → trigger → confirm code as
live mode), paced at 52 Hz (19230 µs), total 72129 ms. Predicted beforehand by
`host/host_pipe_test` (identical table).

| seq | kind | src win | samples | windows | triggers | CONFIRMED | CANCELLED | w0 prob | expect | result |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | fall+still | 0 | 260 | 7 | 2 | 1 | 0 | 0.988937 | CONFIRMED | PASS |
| 1 | fall+still | 1 | 260 | 7 | 2 | 1 | 0 | 0.999959 | CONFIRMED | PASS |
| 2 | fall+still | 2 | 260 | 7 | 2 | 1 | 0 | 0.995272 | CONFIRMED | PASS |
| 3 | fall+still | 3 | 260 | 7 | 2 | 1 | 0 | 0.987724 | CONFIRMED | PASS |
| 4 | fall+still | 4 | 260 | 7 | 2 | 1 | 0 | 0.935268 | CONFIRMED | PASS |
| 5 | fall+still | 5 | 260 | 7 | 2 | 1 | 0 | 0.999744 | CONFIRMED | PASS |
| 6 | fall+moving | 0 | 260 | 7 | 1 | 0 | 1 | 0.988937 | CANCELLED | PASS |
| 7 | fall+moving | 1 | 260 | 7 | 3 | 0 | 1 | 0.999959 | CANCELLED | PASS |
| 8 | fall+moving | 2 | 260 | 7 | 2 | 0 | 1 | 0.995272 | CANCELLED | PASS |
| 9 | fall+moving | 3 | 260 | 7 | 1 | 0 | 1 | 0.987724 | CANCELLED | PASS |
| 10 | fall+moving | 4 | 260 | 7 | 3 | 0 | 1 | 0.935268 | CANCELLED | PASS |
| 11 | fall+moving | 5 | 260 | 7 | 3 | 0 | 1 | 0.999744 | CANCELLED | PASS |
| 12 | ADL | 6 | 104 | 1 | 0 | 0 | 0 | 0.001851 | no trigger | PASS |
| 13 | ADL | 7 | 104 | 1 | 0 | 0 | 0 | 0.036905 | no trigger | PASS |
| 14 | ADL | 8 | 104 | 1 | 0 | 0 | 0 | 0.003419 | no trigger | PASS |
| 15 | ADL | 9 | 104 | 1 | 0 | 0 | 0 | 0.171104 | no trigger | PASS |
| 16 | ADL | 10 | 104 | 1 | 0 | 0 | 0 | 0.010305 | no trigger | PASS |
| 17 | ADL | 11 | 104 | 1 | 0 | 0 | 0 | 0.001404 | no trigger | PASS |

**18/18 PASS.** Notes on how the sequences are built (`replay_seq.h`): "still" segments
in `test_windows.h` carry only |a|, so they are laid along the direction the fall window
ended in; "moving" samples are ADL windows 6, 7, 10 (windows 8 and 11 are near-still and
would legitimately confirm). In the fall+still rows a second trigger (window 1, n = 130) is
pending when the first confirms at n = 260 and is dropped (same fall, one alarm — as in the
reference). In fall+moving rows, triggers other than the first are still unresolved when the
sequence ends and are not counted as CONFIRMED.

## 4. Step 3c — live smoke test (`l`)

**Skipped by decision**: the current model is waist-trained; live testing waits for the
retrained model. The `l` mode is implemented and exercised only through the replay path.

## 5. Step 3d — raw log (`w`, 52 Hz setting)

Format: `t_us,ax_mg,ay_mg,az_mg` (device `ztimer_usec` 32-bit timestamp at XLDA
detection; mg are the driver's counts×16000/32767 at ±16 g). `host/record.py` unwraps
`t_us`, counts drops against the run's own median interval, and writes
`data/own/<subject>_<activity>_<trial>.csv` (gitignored).

**Run 1 — 120 s (`rawlog_20261119-122224.log`, `data/own/S01_still_1.csv`).** Intended as
60 s still + 60 s wave, but the board did not move at all (|a| σ 0.0008 g in both
"phases", axis σ < 1 mg): it is a valid 120 s *still* recording, not a wave test.
6514 samples, 0 dropped, 0 overruns, 0 I2C errors, 0 resets, rate 54.354 Hz.

**Run 2 — 130 s, still then wave (`rawlog_20261119-122732.log`,
`data/own/S01_still-wave_2.csv`).** Phases found from the data (|a| σ over 1 s windows):
still 0–~57 s (|a| σ 0.0007 g, 1.0451–1.0455 g), sustained gentle motion from ~57 s to the
end (|a| 0.32–3.27 g, 5 s σ up to 0.31 g; the 3.27 g peak is in the last 5 s, presumably
putting the board down).

| quantity | value |
|---|---|
| samples / span | 7056 / 129.730 s |
| **dropped samples (t_us gaps > 1.5 × median)** | **0** (no gap above 20.019 ms) |
| firmware counters | `RAWLOG samples=7056 overruns=0 i2c_errors=0` |
| device resets / USB re-enumerations | 0 / 0 |
| **measured rate from t_us** | **54.382 Hz** overall; 54.388 Hz in the still phase, 54.380 Hz while moving |
| median / mean / max interval | 18.000 / 18.388 / 20.019 ms |
| interval histogram | 18 ms ×5682, 20 ms ×1372, one 14 ms (first interval, see below) |
| per-second counts | 54 ×79, 55 ×50 (spread 1) |

**3d PASS (0 dropped samples, 2 min recording).** Rate is the same as in 3a within
0.01 Hz (54.378 → 54.382 Hz), and is the same while still and while moving.
The 18/20 ms interval pattern is the 2 ms DRDY poll quantising a ~18.4 ms period
(not a sensor property).

Start-up artifact: the first interval after `w` starts is short (6 ms in run 1, 14 ms in
run 2) because the first sample read is one already latched in the sensor before the mode
started (XLDA was still set). It is not a drop; ignore row 0's timestamp. Not fixed
(no firmware changes in this phase); fix = discard the first sample in `imu_start()`.

## 6. Six-position calibration — TODO (measure)
