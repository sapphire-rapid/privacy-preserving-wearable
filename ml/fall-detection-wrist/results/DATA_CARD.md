# DATA CARD — wrist datasets (Step 1)

Every figure is **measured from the raw files** by `src/data_card.py` (per-trial dump: `results/data_card_stats.json`). Raw data stay outside the repo (`~/datasets/wrist`, read-only). *Rest check* = mean |a| over the 1-s window with the smallest std in each trial; tables give median [5th, 95th percentile] over trials.

## 0. Things that look off — decisions needed before Step 2

1. **WEDA-FALL: fall files and ADL files were recorded at different effective sample rates.** The 350 fall trials have a median effective rate of **39.8 Hz** (5–95th pct 39.6–49.6); ADL trials **49.7 Hz** (49.5–50.1). 325/350 fall trials are below 45 Hz versus 0/619 ADL trials, i.e. rate almost perfectly separates the classes and is an acquisition artifact, not a property of falls, so a naive 'index = time at 50 Hz' or per-trial-clock treatment can leak class through time scale (a ×0.8 time-stretch, far outside the {0.95, 1.00, 1.05} augmentation). Timestamps are also burst-stamped (≈67 % of intervals < 5 ms, then ~100 ms gaps = Fitbit batch delivery), so 'interpolate on the timestamps' reconstructs a staircase, not the true signal.
2. **SmartFallMM: README says 50 Hz, but it is a mix: 1959 trials at 50 Hz, 535 at 25 Hz (young subjects S28–S39 only), 5 other.** The epoch-ms column is Excel-mangled in ~19 % of files, so I used the ISO time string as the clock. Also: 34 trials contain gaps > 1 s (concatenated recordings, up to an hour), 28 have non-increasing timestamps, and **32 ADL files are not in g** (median |a| outside 0.5–2 g, e.g. subject S06 ×27, S30A09 ×5; |a| up to ~200). I propose to drop those 32 (all ADL, no falls affected) and split trials at gaps.
3. **SmartFallMM falls have little post-impact data:** only **383/692** fall trials have ≥ 3 s after the |a| peak (contiguous, no gap: 380/692); median 3.32 s. 'With confirm' on SmartFallMM will cover ~55 % of its falls; WEDA covers 347/350.
4. **BITS: tag naming is the opposite of intuition.** Of the sensors in each file, `acg` is the gravity-inclusive accelerometer and `acc` is gravity-free *linear* acceleration (in 923/984 files `acc` low-passed norm < 6 and `acg` > 6 m/s²; reversed in 0; both gravity-inclusive in 61 — likely vigorous motion; neither in 0). You asked for the accelerometer, not linear acc ⇒ **`acg`** (the 9 features need gravity). Please confirm.
5. **BITS sampling rate and regularity cannot be verified**: timestamps are mangled to 3 significant digits (`1.82E+11`), so only 0.30 % of timestamps in a file are unique and 115/984 files are non-monotonic. The only independent hint: samples-per-HR-row (HR nominally 1 Hz) has median 20.2 (IQR 7.0–51.1, 5–95th 2.0–102.4) — consistent with 20 Hz at the median but far too variable to prove it. I will treat BITS as 20 Hz by sample order, as you specified; the held-out result then carries that caveat.
6. BITS has no README: no age, no activity legend, no fall-type labels. Per-fall-type recall and young/old ADL split are therefore **not computable on BITS** (all users are assumed geriatric from the folder name).

## 1. WEDA-FALL (Fitbit Sense, wrist) — `WEDA-FALL/dataset/50Hz`

| item | value |
|---|---|
| file format | one CSV per trial per sensor: `<code>/U<uid>_R<trial>_accel.csv`; header `accel_time_list,accel_x_list,accel_y_list,accel_z_list`; floats. (gyro / orientation / vertical_accel files exist, **not used**.) |
| units | **m/s²** (not stated in README; verified: rest |a| median 9.81 m/s² = 1.001 g, 5–95th [9.66, 9.97]). Time in seconds. Convert ÷ 9.80665. |
| gravity included | **Yes** (|a| = 1.001 g at rest). |
| sampling rate | nominal 50 Hz. Effective (n−1)/duration per trial: **ADL 49.7 Hz, falls 39.8 Hz** (see §0.1). Median dt 2.0 ms. |
| regularity | **irregular / burst-stamped**: 67 % of intervals < 5 ms, 22 % > 50 ms; max gap median 124 ms [5–95th 115, 189]; 24 trials with duplicate/non-increasing timestamps. |
| subjects | young U01–U14 (14; ages 20–23, U14 is 46) ; elderly U21–U31 (11; ages 77–95) |
| trials | **969** accel files: **350 fall**, **619 ADL** (README: 350 falls; 462 young + 157 elderly ADL) |
| ADL split | young ADL 462 trials (1.77 h), elderly ADL 157 trials (0.47 h); total 2.24 h |
| who fell | young only: U01–U14 (14 subjects); elderly fall trials: 0 |
| label mapping | folder code: `F01–F08` → fall, `D01–D11` → ADL (all ADL kept, incl. hard negatives D02 jog, D05 collapse into chair, D07 stumble, D08 jump, D09 hit table, D10 clap) |

| code | activity | trials | subjects | eff. rate Hz (median) |
|---|---|---|---|---|
| F01 | fwd fall walking (slip) | 42 | 14 | 39.8 |
| F02 | lateral fall walking (slip) | 42 | 14 | 39.8 |
| F03 | back fall walking (slip) | 42 | 14 | 39.8 |
| F04 | fwd fall walking (trip) | 42 | 14 | 39.8 |
| F05 | back fall trying to sit | 42 | 14 | 39.8 |
| F06 | fwd fall sitting (faint) | 42 | 14 | 39.8 |
| F07 | back fall sitting (faint) | 42 | 14 | 39.8 |
| F08 | lateral fall sitting (faint) | 56 | 14 | 39.8 |
| D01 | walking | 68 | 25 | 49.6 |
| D02 | jogging | 42 | 14 | 49.6 |
| D03 | stairs up/down | 52 | 22 | 49.5 |
| D04 | sit–wait–stand | 71 | 25 | 49.7 |
| D05 | sit, try to rise, collapse into chair | 42 | 14 | 49.7 |
| D06 | crouch / tie shoes | 42 | 14 | 49.7 |
| D07 | stumble while walking | 42 | 14 | 49.8 |
| D08 | gentle jump | 42 | 14 | 50.0 |
| D09 | hit table with hand | 73 | 25 | 49.9 |
| D10 | clapping | 74 | 25 | 49.7 |
| D11 | open/close door | 71 | 25 | 49.7 |

**Post-fall data after the |a| peak** (argmax |a|): **347/350** fall trials have ≥ 3 s after the peak (post-peak s: min 1.32, median 6.77, max 13.73). Using the README's manual annotation (`fall_timestamps.csv`): 297/350 have ≥ 3 s after the annotated *end* of the fall; the argmax peak lies inside the annotated window (±0.5 s) in 348/350 trials. (README: annotations 'can have mistakes'.)

| code | trials | ≥3 s post-peak |
|---|---|---|
| F01 | 42 | 42 |
| F02 | 42 | 42 |
| F03 | 42 | 42 |
| F04 | 42 | 42 |
| F05 | 42 | 42 |
| F06 | 42 | 41 |
| F07 | 42 | 42 |
| F08 | 56 | 54 |

## 2. SmartFallMM — `Meta_wrist` accelerometer only

*© SmartFall Group, Texas State University — all rights reserved; credit required. Cite: "SmartFallMM: A multimodal dataset for fall detection using commodity devices" (IEEE; https://ieeexplore.ieee.org/abstract/document/11651591; code/data: https://github.com/txst-cs-smartfall/SmartFallMM-Dataset). Raw data are not redistributed.*

| item | value |
|---|---|
| file format | `{young,old}/accelerometer/meta_wrist/S<sid>A<aid>T<tid>.csv`; **no header**; 6 columns: epoch ms, ISO time, elapsed s, x, y, z |
| units | **g** (not stated in README; verified: rest |a| median 1.004 [5–95th 0.959, 1.085]); **32 files are NOT in g** (§0.2). |
| gravity included | **Yes** (≈ 1 g at rest). |
| sampling rate | **1959 trials 50 Hz (dt 20 ms), 535 trials 25 Hz (dt 40 ms; all young S28–S39), 5 other (dt ≈ 31 ms)**, from the ISO clock. |
| regularity | within a trial regular (median fraction of intervals outside [0.5,1.5]× median dt = 0.0 %); epoch-ms column corrupted in ~19 % of files; 34 trials with gaps > 1 s (6 falls), 28 with non-increasing timestamps; 0 unreadable files |
| subjects | young folder: 32 subjects (ids 28–63); old folder: 24 subjects (ids [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 47]); overlap: none. README lists old = 2–26, but the folder also holds S01 and S47 |
| trials | **2499**: **692 fall**, **1807 ADL** |
| ADL split | young 1054 trials (3.14 h, gap-free files), old 753 trials (2.06 h, gap-free files) |
| who fell | 31 subjects, all young (old-folder falls: 0) |
| label mapping | from filename Axx and README: A10 Backfall, A11 Frontfall, A12 Leftfall, A13 Rightfall, A14 Rotatefall → fall; A01–A09 → ADL |

| id | activity | group | trials | subjects |
|---|---|---|---|---|
| A01 | Drinking Water | young | 117 | 24 |
| A01 | Drinking Water | old | 71 | 15 |
| A02 | Pick Up Object | young | 129 | 28 |
| A02 | Pick Up Object | old | 80 | 17 |
| A03 | Put On and Take Off Jacket | young | 128 | 28 |
| A03 | Put On and Take Off Jacket | old | 82 | 20 |
| A04 | Stepping Up | young | 15 | 3 |
| A04 | Stepping Up | old | 104 | 21 |
| A05 | Sweeping Floor | young | 138 | 29 |
| A05 | Sweeping Floor | old | 98 | 21 |
| A06 | Washing Hand | young | 133 | 29 |
| A06 | Washing Hand | old | 118 | 23 |
| A07 | Waving Hand | young | 131 | 29 |
| A07 | Waving Hand | old | 106 | 21 |
| A08 | TUG Test/Walking | young | 124 | 28 |
| A08 | TUG Test/Walking | old | 86 | 18 |
| A09 | Sit/Stand | young | 139 | 29 |
| A09 | Sit/Stand | old | 8 | 3 |
| A10 | Backfall | young | 145 | 31 |
| A11 | Frontfall | young | 136 | 29 |
| A12 | Leftfall | young | 138 | 30 |
| A13 | Rightfall | young | 138 | 30 |
| A14 | Rotatefall | young | 135 | 30 |

**Post-fall data after the |a| peak**: **383/692** fall trials have ≥ 3 s after the peak (≥ 3 s contiguous before any gap: 380); post-peak s: min 0.08, median 3.32, max 67.08. The dataset authors cropped each trial by hand: fall duration median 7.5 s [min 2.9, max 75.6].

| fall type | trials | ≥3 s post-peak | median post-peak s |
|---|---|---|---|
| A10 Backfall | 145 | 90 | 4.24 |
| A11 Frontfall | 136 | 66 | 2.95 |
| A12 Leftfall | 138 | 84 | 3.52 |
| A13 Rightfall | 138 | 70 | 3.02 |
| A14 Rotatefall | 135 | 73 | 3.12 |

Non-g files (median |a| outside 0.5–2 g): S06A01T01, S06A02T01, S06A02T02, S06A02T03, S06A02T04, S06A02T05, S06A03T01, S06A03T02, S06A04T01, S06A04T02, S06A04T03, S06A04T04, S06A06T01, S06A06T02, S06A06T03, S06A06T04, S06A06T05, S06A07T01, S06A07T02, S06A07T03, S06A07T04, S06A07T05, S06A08T01, S06A08T02, S06A08T03, S06A08T04, S06A08T05, S30A09T01, S30A09T02, S30A09T03, S30A09T04, S30A09T05.

## 3. BITS geriatric — HELD-OUT test set (never used for training/tuning)

| item | value |
|---|---|
| file format | `Dataset/{adl,fall}/user<N>/user<N>_{adl,fall}<k>.csv`; header `t,x,y,z,a,`; several sensors concatenated as contiguous blocks, tagged in the **last column**: `acc`, `acg`, `gyro`, `mgm` (`t,x,y,z,3,<tag>`) and `hrt` (`t,<hr>,<status>,hrt,,`). Tag sets per file: {('acc', 'acg', 'gyro', 'hrt', 'mgm'): 984}. No README/metadata. |
| units / gravity | native **m/s²** (inferred): `acg` rest |a| median 9.813 m/s² = 1.001 g ⇒ **gravity included**; `acc` rest median 0.136 m/s² ⇒ **gravity-free linear acceleration** (§0.4). Use `acg`. |
| sampling rate / regularity | **unverifiable** (§0.5). Assumed 20 Hz by sample order. `acc` and `acg` have different sample counts in 709/984 files (separate streams). |
| subjects | 41 users (user1–user41); 41 with ADL, 41 with falls. Age not stated. |
| trials | **984** files: **328 fall** (8 per user), **656 ADL** (16 per user); 4 fall files named `user<N>_.fall<k>.csv` (stray dot, parsed). |
| ADL time | 405835 acg samples = 5.64 h **if 20 Hz** |
| label mapping | `adl/` → ADL, `fall/` → fall; **no activity or fall-type legend** |

**Post-fall data after the `acg` |a| peak**: samples after peak min 0, median 339, max 3060; **280/328** fall trials have ≥ 3 s (60 samples) *if 20 Hz*. Peak |a| of falls: median 6.1 g [min 1.0, max 13.9]; ADL median peak 1.8 g.

HR parsing (`wrist_io.parse_bits_hr`) is written but **not used**.

## 4. Cross-dataset summary

| dataset | rate (measured) | units → g | gravity | fall trials | fall trials ≥3 s post-peak | ADL trials | fall subjects | ADL subjects (young/old) |
|---|---|---|---|---|---|---|---|---|
| WEDA-FALL | ADL 49.7 / fall 39.8 Hz, burst-stamped | ÷9.80665 | yes | 350 | 347 | 619 | 14 young | 14/11 |
| SmartFallMM | 1959×50 Hz, 535×25 Hz | none (g); 32 files bad | yes | 692 | 383 | 1807 (32 non-g) | 31 young | 31/24 |
| BITS (held-out) | unverified (nominal 20 Hz) | ÷9.80665 (`acg`) | yes (`acg`) | 328 | 280 @20 Hz | 656 | 41 (age n/a) | n/a |

Subject ids will be prefixed per dataset (`W`, `S`, `B`) so GroupKFold never merges different people.

