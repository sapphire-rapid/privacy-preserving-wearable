# fall_imu on-board validation report (Steps 3a–3d)

Board: bare Seeed XIAO nRF52840 Sense on USB (LSM6DS3TR-C, internal I2C bus).
Branch `fall-imu-onboard`. Firmware under test: commit `10368b0`
(`INFO build=10368b0`), RIOT `fac711a2b4` (untouched), toolchain
arm-none-eabi-gcc 15.2.0. Every number below is a measured value; the log it came
from is given in brackets. The cited logs are tracked copies in
`firmware/fall_imu/results/logs/` (the live capture directory `logs/` is gitignored).

## 0. Build, flash, RAM

| item | value | source |
|---|---|---|
| text / data / bss (arm-none-eabi-size) | 57688 / 160 / 24432 B (dec 82280) | build output of `10368b0` |
| flash ≈ text+data | 57848 B (linker symbols, `i`) | `results/logs/i_20261119-120010.log` |
| `printf_float` (newlib-nano) | needed for `%f`/`%g`; part of the above | Makefile |
| first flash (`8b2baa6`) | IMU did not answer: `imu_init_rc=-1`, all register reads failed | `results/logs/i_20261119-115103.log` |
| cause | `imu.c` used the generic driver defaults I2C_DEV(0)/0x6B (empty header bus); this board's IMU is I2C_DEV(1)/0x6A (`board.h`), power P1.08 set by `board.c`. The old Step 3a `main.c` had the same two constants, so it could never have run on this board. | board.h |
| fix | `10368b0`: use `LSM6DSXX_PARAM_I2C/_ADDR` from `board.h` | git |

Registers read back on the working firmware (`results/logs/i_20261119-120010.log`):

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

Board flat and still on the table. Log: `results/logs/t_20261119-120142.log`
(EVENT lines `start/end flat_still_on_table`).

| quantity | measured |
|---|---|
| samples in 60.006 s | 3264 (expected 3120 at nominal 52 Hz: +4.6 %) |
| **real ODR** (n−1)/elapsed | **54.378 Hz (+4.57 % vs nominal 52 Hz)** |
| interval mean / σ / min / max | 18.390 / 0.808 / 9.999 / 20.013 ms (nominal 19.231 ms) |
| per-second sample counts (60 s) | 54 ×37, 55 ×22 → spread 1 |
| outside 19.231 ± 3 ms | 1 of 3263 (0.031 %) — the one 9.999 ms interval (likely a delayed detection of the preceding sample; not investigated) |
| \|a\| mean / σ / min / max | 1.0455 / 0.0008 / 1.0420 / 1.0511 g (a +46 mg Z-axis offset, not a scale error: see §6) |
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

Log: `results/logs/s_20261119-121626.log` (firmware `10368b0`; an earlier run on `8b2baa6`,
`results/logs/s_20261119-115132.log`, gave the same results).

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

Log: `results/logs/r_20261119-121627.log`. 18 sequences, each through a freshly reset
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

**Run 1 — 120 s (`results/logs/rawlog_20261119-122224.log`, `data/own/S01_still_1.csv`).** Intended as
60 s still + 60 s wave, but the board did not move at all (|a| σ 0.0008 g in both
"phases", axis σ < 1 mg): it is a valid 120 s *still* recording, not a wave test.
6514 samples, 0 dropped, 0 overruns, 0 I2C errors, 0 resets, rate 54.354 Hz.

**Run 2 — 130 s, still then wave (`results/logs/rawlog_20261119-122732.log`,
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

## 6. Six-position calibration

Procedure: `host/cal_capture.py` x6 (board at rest, braced against a book/box edge, USB
cable slack, 11 s recordings via `w`; the IMU axis that points up is detected from the
data), then `host/calibrate.py --markdown --write-header include/imu_cal.h`. Only the
**middle 8 s** (1–9 s after the first sample, device `t_us`) of each segment is used.
No resets / overruns / USB drops in any capture. Axis directions found: X runs along the
board's length (USB-C end up = −X, down = +X), Y across the width, Z normal to the PCB
(component side up = +Z). (First attempt at the 5th position repeated −X; it was redone
with Y up. The rejected capture was deleted.)

| orientation | file | n | mean x / y / z (mg) | σ max (mg) | \|a\| before (g) | \|a\| after (g) |
|---|---|---|---|---|---|---|
| xp | `results/calibration/S01_cal-xp_1.csv` | 435 | 1030.0 / 20.8 / 96.4 | 1.53 | 1.0347 | 1.0017 |
| xn | `results/calibration/S01_cal-xn_1.csv` | 435 | -987.0 / -45.0 / 27.4 | 0.91 | 0.9884 | 1.0008 |
| yp | `results/calibration/S01_cal-yp_1.csv` | 434 | 14.2 / 990.3 / 42.5 | 0.90 | 0.9913 | 1.0000 |
| yn | `results/calibration/S01_cal-yn_1.csv` | 434 | 22.3 / -1008.4 / 0.4 | 2.82 | 1.0087 | 1.0010 |
| zp | `results/calibration/S01_cal-zp_1.csv` | 435 | 2.1 / -11.6 / 1046.0 | 0.85 | 1.0461 | 1.0002 |
| zn | `results/calibration/S01_cal-zn_1.csv` | 435 | -117.5 / -11.3 / -953.7 | 0.93 | 0.9609 | 1.0095 |

Model: `calibrated_mg = (raw_mg - offset) / scale` per axis, offset = (raw(+1 g) + raw(−1 g))/2,
scale = (raw(+1 g) − raw(−1 g))/2000.

| axis | offset (mg) | scale | scale error |
|---|---|---|---|
| X | +21.49 | 1.00850 | +0.85 % |
| Y | −9.06 | 0.99935 | −0.06 % |
| Z | +46.19 | 0.99984 | −0.02 % |

`\|a\|` over the six orientations: before 0.9609–1.0461 g (mean 1.0050), after
1.0000–1.0095 g (mean 1.0022). Generated `include/imu_cal.h` (offset 21.487, −9.061,
46.187 mg; scale 1.008499, 0.999351, 0.999838) is **not used by the firmware**.

Findings and caveats:

* **The 1.0455 g seen flat on the table in 3a/3d is a Z offset, not a scale error:**
  flat component-side-up reads z = 1046 mg with x, y ≈ 0, and the fitted Z scale is 0.9998.
  The coincidence with the +4.6 % ODR deviation is just that — the two are unrelated.
  X scale is +0.85 %, Y/Z within 0.1 %; the offsets are +21, −9, +46 mg.
* **Placement tilt limits the precision.** The off-axis components after calibration are
  up to 138 mg (zn, 7.9° from vertical); the other positions are 0.5–3.3° off. A two-point
  fit assumes each axis was exactly vertical, so these tilts bias it. Cross-check with a
  tilt-independent fit that only requires |a| = 1 g in all six positions (6 equations, 6
  unknowns, same diagonal model): offsets +22.11 / −9.46 / +41.46 mg, scales 1.00985 /
  0.99978 / 1.00476. It agrees within ~5 mg and ~0.5 % scale, so quote the calibration as
  ±5 mg / ±0.5 %. (The cross-check was an ad-hoc analysis, not saved as a script.)
* Diagonal model only: cross-axis misalignment is not modelled and cannot be separated
  from placement tilt with this data.
* One board, one temperature (room, ~19.11.2026); offset/scale drift with temperature.
* Per-position σ ≤ 2.8 mg (all at rest); `calibrate.py` rejects segments with σ > 10 mg, a
  wrong dominant axis, or < 8 s of data (tested on synthetic data with a known offset/scale,
  recovered to < 0.1 %).

## 7. Open items / not done

* LPF bandwidth implied by CTRL1_XL=0x34 / CTRL8_XL=0x00 not cited from the datasheet
  (could not be fetched) — see section 0.
* ODR tolerance of the part not cited from the datasheet; measured 54.38 Hz (+4.57 %)
  on this unit only. Other units may differ; a retrained model should be rate-tested on
  the target unit (or timestamps used to resample to a fixed rate).
* `l` (live) was not exercised for the 52 Hz model; it was exercised for the 26 Hz wrist model, see section 8.
* First-sample stale artifact in `w`/`t`/`l` (section 5): `imu_start()` should discard
  one sample.
* `ml/fall-detection/src/export_final.py` does not emit the new `TILT_PRE/POST_SAMPLES`,
  `TILT_FALLBACK_SAMPLES`, `POST_STD_SAMPLES` macros, so a header regenerated by it must
  keep those four lines (a hand-merge) until the exporter is updated.
* The old `firmware/fall_imu` Step-3a `main.c` was replaced; its comment/constants
  (`I2C_DEV(0)`, 0x6B) were wrong for this board.

## 8. 26 Hz wrist model, on-board

Firmware: wrist LR @ 26 Hz (`include/fall_model.h` / `test_windows.h` from `ml/fall-detection-wrist/`, threshold
0.835, 9 features, window 52 / stride 13 / confirm 78). Board: the same bare XIAO nRF52840 Sense. Branch
`wrist-retrain`. Logs are tracked in `firmware/fall_imu/results/logs/` (copies of the cited captures from the gitignored `logs/`); every
run went through `host/serial_log.py`, EVENT lines were stamped by the host at the moment of each cue.
All numbers below are measured values.

### 8.1 Build and flash

| item | value | source |
|---|---|---|
| sources | commit `3b3ecc3` (log-only changes below); board reports `build=1703861`, the next commit, which only added `host/analyze_live.py` | `results/logs/i_20261120-112845.log` |
| build | `UF2_SOFTDEV=DROP make`, no warnings; link address 0x1000 | build output |
| text / data / bss (`arm-none-eabi-size`) | 48584 / 160 / 20064 B | build output |
| runtime linker symbols (`i`) | text 48584, data 160, bss 19552, flash ≈ 48744 B (old 52 Hz image: 57848 B) | `results/logs/i_20261120-112845.log` |
| flash procedure | double-tap → `XIAO-SENSE` drive (bootloader: "SoftDevice: not found"); `UF2_SOFTDEV=DROP make flash`: 97792 B written at 0x1000; flashed **once** | make output |
| log-only code changes for this validation | (1) `EVT TRIGGER_FEAT` prints the 9 window features on every live TRIGGER; (2) `i` flags the long-lie parameters as placeholders and prints the threshold with 4 decimals; (3) `s`/`r`/`l` banners print the threshold with 3 decimals (it printed 0.835 as 0.83). No pipeline, feature or model change. | git `3b3ecc3` |

### 8.2 `i` — PASS (`results/logs/i_20261120-112845.log`)

| check | measured |
|---|---|
| WHO_AM_I | 0x6A (I2C_DEV(1), 0x6A), `imu_init_rc=0` |
| `CTRL1_XL` (0x10) | **0x24** = ODR_XL 0x2 (**26 Hz**), FS_XL 0x1 (**±16 g**), LPF1_BW_SEL 0, BW0_XL 0 |
| `CTRL8_XL`, `CTRL2_G`, `CTRL3_C` | 0x00 (LPF2 off, no HP), 0x30 (gyro still 52 Hz, unused), 0x44 (BDU, IF_INC) |
| model macros | SAMPLE_RATE_HZ 26, WIN 52, STRIDE 13, CONFIRM 78, TILT_PRE/POST 13, TILT_FALLBACK 5, POST_STD 26, N_FEATURES 9 |
| threshold | `FALL_PROB_THR=0.8350` |
| long-lie params | printed as "PLACEHOLDERS (not validated, not part of fall detection)": std 0.08, tol 0.2, 78 samples |

### 8.3 `t` — 60 s timing, board flat and still — PASS (`results/logs/t_20261120-113244.log`, EVENT `start/end flat_still_on_table`)

| quantity | measured |
|---|---|
| timing target | `target_dt_ms=38.462` = 1000 / `SAMPLE_RATE_HZ` (derived from the model macro in `modes.c`, not the old 52 Hz constant); `odr_hz=26` |
| samples in 60.016 s | 1632 (nominal 26 Hz would give 1560: +4.6 %) |
| **real ODR** (n−1)/elapsed | **27.176 Hz (+4.52 % vs 26 Hz)**; host clock 27.135 Hz, `up_ms` 27.133 Hz (three clocks agree) |
| per-second sample counts (60 s) | 27 ×49, 28 ×10 → spread 1 |
| interval mean / σ / min / max | 36.797 / 0.995 / 30.002 / 38.015 ms (nominal 38.462 ms) |
| outside 38.462 ± 3 ms | 1 of 1631 (0.061 %), the 30.002 ms interval |
| \|a\| mean / σ / min / max | 1.0463 / 0.0005 / 1.0440 / 1.0490 g |
| overruns / I2C errors / resets | 0 / 0 / none |

PASS criteria (stable per-second counts within ±1, 0 overruns, 0 I2C errors, real ODR recorded) all met. The
oscillator ratio is the same as on the 52 Hz setting (+4.57 % then, +4.52 % now). Derived (arithmetic, not
measured): at 27.176 Hz a 52-sample window spans 1.913 s (not 2.00 s), the 78-sample confirm segment 2.870 s
(not 3.00 s) and the 26-sample `std_mag_post` window 0.957 s; whether this time-scale shift matters at 26 Hz was
not tested.

### 8.4 `s` — self-test — PASS (`results/logs/s_20261120-112855.log`)

* 12/12 windows PASS and 6/6 stillness segments PASS; every trigger / still decision equals the expected one.
* Worst relative feature error vs the Python expectation (tolerance 1e-4): max_mag 8.4e-08, min_mag 1.0e-07,
  mean_mag 2.9e-07, std_mag 1.5e-07, range_mag 1.7e-07, max_jerk 4.7e-07, std_mag_post 3.1e-07, count_low 0
  (exact; newlib prints an exact 0 as `0.00e-308`), tilt_deg 6.6e-07. Largest probability difference 1.19e-07.
* Time per window over 100 runs (`ztimer_usec`): features + LR **mean 385.3 µs / max 417 µs**; features alone
  181.1 / 213 µs; LR alone 204.2 / 236 µs (stride at 26 Hz = 500 ms, so ≈ 0.08 % duty).

### 8.5 `r` — replay through the live path — PASS (`results/logs/r_20261120-112904.log`)

18/18 sequences PASS (period 38461 µs, elapsed 72.1 s): fall+still ×6 → CONFIRMED, fall+moving ×6 → CANCELLED,
ADL ×6 → no trigger. Host reference: `host_pipe_test` built from the same `pipeline.c` and headers
(`results/logs/host_pipe_sim_26hz.txt`, 18/18 PASS). **Row-by-row comparison of kind, source, length, windows, triggers,
confirmed, cancelled, pending, w0 probability (±1e-6), expectation and result: 0 mismatches in 18 rows.**

### 8.6 `l` — live smoke test, no tuning

One operator, one board, held in the hand (not worn), four runs; each phase is bracketed by EVENT lines
(`start/end <phase>`; for the falls also `cue fall_k` at 10/30/50/70/90 s after the start cue, announced by a voice
prompt). `host/analyze_live.py` and the numbers below come from the LIVE lines (`up_ms, wi, p, max, state`);
`max` is the window's max \|a\| (feature `max_mag`). Zero overruns, I2C errors and resets in all four runs.

| phase (EVENT) | log | duration | stride windows | triggers (p ≥ 0.835) | confirmed / cancelled | p min / p25 / median / p75 / p95 / max | windows with max \|a\| > 2 g | > 3.46 g | max \|a\| median / p95 / max (g) |
|---|---|---|---|---|---|---|---|---|---|
| still on table | `results/logs/l_20261120-113959.log` | 60 s | 125 | **0** | 0 / 0 | 0.0026 / 0.0027 / 0.0027 / 0.0027 / 0.0027 / 0.0027 | 0 (0.0 %) | 0 | 1.05 / 1.05 / 1.05 |
| held in hand, typing / waving gently | `results/logs/l_20261120-114139.log` | 60 s | 125 | **0** | 0 / 0 | 0.0027 / 0.0029 / 0.0031 / 0.0038 / 0.0060 / 0.0097 | 0 (0.0 %) | 0 | 1.06 / 1.19 / 1.22 |
| claps, holding the board | `results/logs/l_20261120-114315.log` | 40 s | 84 | **12** | 0 / 12 | 0.0031 / 0.0061 / 0.0629 / 0.4824 / 0.9866 / 0.9949 | 41 (48.8 %) | 0 | 1.84 / 3.21 / 3.38 |
| 5 × fall gesture (swing, set flat, 5 s still) | `results/logs/l_20261120-114646.log` | 110 s | 230 | **16** | **5** / 0 | 0.0026 / 0.0027 / 0.0027 / 0.0031 / 0.9730 / 1.0000 | 22 (9.6 %) | 16 (7.0 %) | 1.05 / 3.81 / 6.39 |

Triggers vs EVENT lines:

* **Still and in-hand phases: 0 triggers** in 250 windows; p stays ≤ 0.0097.
* **Fall gestures: every cue produced triggers** within 8 s of its EVENT line (cue 1: 2, cue 2: 2, cue 3: 4, cue 4: 4,
  cue 5: 4 = all 16 triggers of the phase; **none outside a cue window**), max p 0.9996 / 0.9984 / 1.0000 / 1.0000 /
  1.0000, window max \|a\| 3.70 / 2.80 / 3.89 / 6.39 / 4.89 g. **5 of 5 gestures were CONFIRMED** by the (placeholder)
  stillness check once the board was set flat (confirm segments std 0.0023 / 0.0021 / 0.0059 / 0.0075 / 0.0012,
  mean 1.044 / 1.044 / 1.045 / 1.047 / 0.961 g).
* **Claps: 12 triggers in 3 episodes** (7.9–15.1 s: 6, 29.4–32.8 s: 4, 39.0–39.5 s: 2 after the start event), all 12
  CANCELLED (never a still 3 s). The window maxima show about 13 separate bursts above 2 g; the operator did not
  count the claps, so a triggers-per-clap rate cannot be stated. About half of the clap bursts triggered; clapping is
  the ADL class that also alarms in the training data.

9 feature values of every trigger are in the logs (`EVT TRIGGER_FEAT`). Range over the triggers (min / median / max):

| feature | 12 clap triggers | 16 fall-gesture triggers |
|---|---|---|
| max_mag (g) | 2.402 / 2.994 / 3.375 | 2.796 / 4.394 / 6.395 |
| min_mag (g) | 0.544 / 0.690 / 0.854 | 0.171 / 0.662 / 0.969 |
| mean_mag (g) | 1.038 / 1.065 / 1.084 | 1.135 / 1.327 / 1.603 |
| std_mag (g) | 0.213 / 0.322 / 0.334 | 0.370 / 0.686 / 1.262 |
| range_mag (g) | 1.773 / 2.298 / 2.667 | 2.303 / 3.837 / 6.203 |
| max_jerk (g/sample) | 1.270 / 2.077 / 2.365 | 1.169 / 2.104 / 3.574 |
| std_mag_post (g) | 0.031 / 0.054 / 0.090 | 0.002 / 0.014 / 1.642 |
| count_low | 0 / 0 / 0 | 0 / 0.5 / 2 |
| tilt_deg | 6.1 / 20.8 / 45.3 | 41.8 / 152.7 / 170.4 |

**±2 g clipping check** (SmartFallMM's Meta_wrist accelerometer saturates near ±2 g per axis, \|a\| ≤ 3.46 g;
this board runs at ±16 g). Share of stride windows whose max \|a\| exceeds 2 g: still 0 %, in hand 0 %, claps 48.8 %
(max 3.38 g, never above 3.46 g), fall gestures 9.6 % of all windows, of which **16 windows (7.0 %) exceed 3.46 g**
(4 of the 5 gestures, peaks 3.70–6.39 g). For comparison, the training windows (unstretched, max_mag of the
2 s window; `ml/fall-detection-wrist`): WEDA fall impact windows median 4.97 g, 93.1 % above 3.46 g, max 8.02 g;
SmartFallMM fall impact windows median 2.73 g, 4.3 % above 3.46 g, max 3.82 g; ADL windows above 2 g: WEDA 27.0 %,
SmartFallMM 23.4 %. So the board's gesture peaks are inside the WEDA training range but above what SmartFallMM can
represent; the trigger probabilities of those gestures were ≥ 0.998 regardless, and the gentlest gesture (2.80 g)
still reached p = 0.9984. What this smoke test cannot say is how a real low-energy fall would score.

Not covered: this is a smoke test (one operator, hand-held, hand gestures instead of falls, unknown number of claps),
**not a recall or false-alarm estimate**; wrist wear, body-attached falls and a long daily-life recording were not
tried; no threshold was changed after seeing these runs.

### 8.7 Open items from the on-board run

* Real ODR 27.176 Hz (+4.52 %) on this unit: the model was trained on 26 Hz-resampled data, so windows are 1.913 s
  and the confirm segment 2.870 s on the device; the training-time ±5 % stretch augmentation spans a shift of this
  size, but its effect on the device was not evaluated.
* The long-lie parameters are still placeholders; the 5/5 confirmations here show only that the code path works.
* Wrist-worn recordings with the 26 Hz firmware are needed to recalibrate the threshold on own-device data.
