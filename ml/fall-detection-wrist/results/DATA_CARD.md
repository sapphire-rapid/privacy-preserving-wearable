# DATA CARD — wrist datasets (Step 1)

Every figure is **measured from the raw files** by `src/data_card.py` (per-trial dump: `results/data_card_stats.json`). Raw data stay outside the repo (`~/datasets/wrist`, read-only). *Rest check* = mean |a| over the 1-s window with the smallest std in each trial; tables give median [5th, 95th percentile] over trials.

## 0. Things that look off — decisions needed before Step 2

1. **WEDA-FALL: fall files and ADL files were recorded at different effective sample rates.** The 350 fall trials have a median effective rate of **39.8 Hz** (5–95th pct 39.6–49.6); ADL trials **49.7 Hz** (49.5–50.1). 325/350 fall trials are below 45 Hz versus 0/619 ADL trials, i.e. rate almost perfectly separates the classes and is an acquisition artifact, not a property of falls, so a naive 'index = time at 50 Hz' or per-trial-clock treatment can leak class through time scale (a ×0.8 time-stretch, far outside the {0.95, 1.00, 1.05} augmentation). Timestamps are also burst-stamped (≈67 % of intervals < 5 ms, then ~100 ms gaps = Fitbit batch delivery), so 'interpolate on the timestamps' reconstructs a staircase, not the true signal.
2. **SmartFallMM: README says 50 Hz, but it is a mix: 1959 trials at 50 Hz, 535 at 25 Hz (young subjects S28–S39 only), 5 other.** The epoch-ms column is Excel-mangled in ~19 % of files, so I used the ISO time string as the clock. Also: 34 trials contain gaps > 1 s (concatenated recordings, up to an hour), 28 have non-increasing timestamps, and **32 ADL files are not in g** (median |a| outside 0.5–2 g, e.g. subject S06 ×27, S30A09 ×5; |a| up to ~200). I propose to drop those 32 (all ADL, no falls affected) and split trials at gaps.
3. **SmartFallMM falls have little post-impact data:** only **383/692** fall trials have ≥ 3 s after the |a| peak (contiguous, no gap: 380/692); median 3.32 s. 'With confirm' on SmartFallMM will cover ~55 % of its falls; WEDA covers 347/350.
4. **BITS: tag naming is the opposite of intuition.** Of the sensors in each file, `acg` is the gravity-inclusive accelerometer and `acc` is gravity-free *linear* acceleration (in 923/984 files `acc` low-passed norm < 6 and `acg` > 6 m/s²; reversed in 0; both gravity-inclusive in 61 — likely vigorous motion; neither in 0). You asked for the accelerometer, not linear acc ⇒ **`acg`** (the 9 features need gravity). Please confirm.
5. **BITS sampling rate and regularity cannot be verified**: timestamps are mangled to 3 significant digits (`1.82E+11`), so only 0.30 % of timestamps in a file are unique and 115/984 files are non-monotonic. The only independent hint: samples-per-HR-row (HR nominally 1 Hz) has median 20.2 (IQR 7.0–51.1, 5–95th 2.0–102.4) — consistent with 20 Hz at the median but far too variable to prove it. I will treat BITS as 20 Hz by sample order, as you specified; the held-out result then carries that caveat.
6. BITS has no README: no age, no activity legend, no fall-type labels. Per-fall-type recall and young/old ADL split are therefore **not computable on BITS** (ages are only known from the dataset paper: 20–47, see §6).

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

## 3. BITS wrist IMU+HR (ages 20–47) — HELD-OUT test set (never used for training/tuning; on-disk folder `bits_geriatric`)

| item | value |
|---|---|
| file format | `Dataset/{adl,fall}/user<N>/user<N>_{adl,fall}<k>.csv`; header `t,x,y,z,a,`; several sensors concatenated as contiguous blocks, tagged in the **last column**: `acc`, `acg`, `gyro`, `mgm` (`t,x,y,z,3,<tag>`) and `hrt` (`t,<hr>,<status>,hrt,,`). Tag sets per file: {('acc', 'acg', 'gyro', 'hrt', 'mgm'): 984}. No README/metadata. |
| units / gravity | native **m/s²** (inferred): `acg` rest |a| median 9.813 m/s² = 1.001 g ⇒ **gravity included**; `acc` rest median 0.136 m/s² ⇒ **gravity-free linear acceleration** (§0.4). Use `acg`. |
| sampling rate / regularity | **unverifiable** (§0.5). Assumed 20 Hz by sample order. `acc` and `acg` have different sample counts in 709/984 files (separate streams). |
| subjects | 41 users (user1–user41); 41 with ADL, 41 with falls. Age not stated in the files; the dataset paper (§6) gives 20–47. |
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
| BITS (held-out) | unverified (nominal 20 Hz) | ÷9.80665 (`acg`) | yes (`acg`) | 328 | 280 @20 Hz | 656 | 41 (ages 20–47 per paper) | n/a |

Subject ids will be prefixed per dataset (`W`, `S`, `B`) so GroupKFold never merges different people.

## 5. Exclusion log (Step 2 preprocessing)

Rules (all fixed before any model was trained): SmartFallMM — ISO time string as clock; split at |gap| > 1 s; drop samples with non-increasing timestamps; drop segments < 2 s; fall trials keep only the segment containing the |a| peak; ADL files with median |a| outside 0.5–2 g are not in g and are dropped. WEDA — nothing excluded; per-trial linear time axis. BITS — `acg`, drop files whose rest |a| is not 1 ± 0.1 g.

| dataset | action | class | count |
|---|---|---|---|
| SFMM | file dropped | adl | 32 |
| SFMM | segment | adl | 56 |
| SFMM | segment | fall | 7 |
| SFMM | split | adl | 32 |
| SFMM | split | fall | 6 |
| SFMM | trial | fall | 1 |

**SmartFallMM non-g files dropped (32):** S06A01T01, S06A02T01, S06A02T02, S06A02T03, S06A02T04, S06A02T05, S06A03T01, S06A03T02, S06A04T01, S06A04T02, S06A04T03, S06A04T04, S06A06T01, S06A06T02, S06A06T03, S06A06T04, S06A06T05, S06A07T01, S06A07T02, S06A07T03, S06A07T04, S06A07T05, S06A08T01, S06A08T02, S06A08T03, S06A08T04, S06A08T05, S30A09T01, S30A09T02, S30A09T03, S30A09T04, S30A09T05.

**SmartFallMM segments dropped** (63):

- S30A14T02.csv: fall: segment 1 does not contain the impact peak (dropped)
- S31A11T01.csv: fall: segment 0 does not contain the impact peak (dropped)
- S31A11T01.csv: segment 1 shorter than 2 s (1.80 s)
- S31A11T02.csv: fall: segment 0 does not contain the impact peak (dropped)
- S31A11T04.csv: fall: segment 0 does not contain the impact peak (dropped)
- S32A11T02.csv: fall: segment 1 does not contain the impact peak (dropped)
- S39A08T01.csv: segment 0 shorter than 2 s (1.72 s)
- S39A10T03.csv: fall: segment 1 does not contain the impact peak (dropped)
- S08A03T01.csv: segment 1 shorter than 2 s (1.46 s)
- S13A02T01.csv: segment 3 shorter than 2 s (1.07 s)
- S13A02T02.csv: segment 4 shorter than 2 s (1.07 s)
- S13A02T03.csv: segment 1 shorter than 2 s (1.08 s)
- S13A02T03.csv: segment 5 shorter than 2 s (1.07 s)
- S13A02T04.csv: segment 4 shorter than 2 s (1.07 s)
- S13A02T05.csv: segment 1 shorter than 2 s (1.34 s)
- S13A02T05.csv: segment 4 shorter than 2 s (1.07 s)
- S13A03T03.csv: segment 1 shorter than 2 s (1.07 s)
- S13A03T04.csv: segment 2 shorter than 2 s (1.07 s)
- S13A03T05.csv: segment 2 shorter than 2 s (1.07 s)
- S13A04T01.csv: segment 1 shorter than 2 s (0.16 s)
- S13A04T01.csv: segment 2 shorter than 2 s (1.34 s)
- S13A04T01.csv: segment 5 shorter than 2 s (1.07 s)
- S13A04T02.csv: segment 1 shorter than 2 s (0.88 s)
- S13A04T02.csv: segment 2 shorter than 2 s (0.16 s)
- S13A04T02.csv: segment 3 shorter than 2 s (1.34 s)
- S13A04T02.csv: segment 6 shorter than 2 s (1.07 s)
- S13A04T03.csv: segment 1 shorter than 2 s (0.66 s)
- S13A04T03.csv: segment 4 shorter than 2 s (1.07 s)
- S13A04T04.csv: segment 2 shorter than 2 s (0.66 s)
- S13A04T04.csv: segment 5 shorter than 2 s (1.07 s)
- S13A04T05.csv: segment 1 shorter than 2 s (0.32 s)
- S13A04T05.csv: segment 4 shorter than 2 s (1.07 s)
- S13A05T01.csv: segment 1 shorter than 2 s (0.18 s)
- S13A05T01.csv: segment 4 shorter than 2 s (1.07 s)
- S13A05T02.csv: segment 3 shorter than 2 s (1.07 s)
- S13A05T03.csv: segment 1 shorter than 2 s (1.42 s)
- S13A05T03.csv: segment 3 shorter than 2 s (1.07 s)
- S13A05T04.csv: segment 1 shorter than 2 s (1.56 s)
- S13A05T04.csv: segment 2 shorter than 2 s (1.42 s)
- S13A05T04.csv: segment 4 shorter than 2 s (1.07 s)
- S13A05T05.csv: segment 1 shorter than 2 s (0.54 s)
- S13A05T05.csv: segment 2 shorter than 2 s (1.42 s)
- S13A05T05.csv: segment 4 shorter than 2 s (1.07 s)
- S13A06T03.csv: segment 1 shorter than 2 s (1.14 s)
- S13A06T04.csv: segment 1 shorter than 2 s (0.32 s)
- S13A06T04.csv: segment 2 shorter than 2 s (1.14 s)
- S13A06T05.csv: segment 1 shorter than 2 s (1.18 s)
- S13A06T05.csv: segment 2 shorter than 2 s (0.32 s)
- S13A06T05.csv: segment 3 shorter than 2 s (1.14 s)
- S13A07T01.csv: segment 2 shorter than 2 s (0.76 s)
- S13A07T02.csv: segment 1 shorter than 2 s (0.50 s)
- S13A07T02.csv: segment 2 shorter than 2 s (0.76 s)
- S13A07T03.csv: segment 2 shorter than 2 s (0.20 s)
- S13A07T03.csv: segment 3 shorter than 2 s (0.50 s)
- S13A07T03.csv: segment 4 shorter than 2 s (0.76 s)
- S13A07T04.csv: segment 2 shorter than 2 s (0.20 s)
- S13A07T04.csv: segment 3 shorter than 2 s (0.50 s)
- S13A07T04.csv: segment 4 shorter than 2 s (0.76 s)
- S13A07T05.csv: segment 1 shorter than 2 s (0.42 s)
- S13A07T05.csv: segment 2 shorter than 2 s (0.20 s)
- S13A07T05.csv: segment 3 shorter than 2 s (0.50 s)
- S13A07T05.csv: segment 4 shorter than 2 s (0.76 s)
- S21A07T04.csv: segment 0 shorter than 2 s (1.04 s)

**SmartFallMM fall trials lost entirely:** 1: S31A11T01.csv.

**SmartFallMM files split at gaps > 1 s (38):** S30A14T02 (2 segments); S31A11T01 (2 segments); S31A11T02 (2 segments); S31A11T04 (2 segments); S32A11T02 (2 segments); S39A08T01 (2 segments); S39A10T03 (2 segments); S08A03T01 (2 segments); S13A02T01 (4 segments); S13A02T02 (5 segments); S13A02T03 (6 segments); S13A02T04 (5 segments); S13A02T05 (5 segments); S13A03T01 (2 segments); S13A03T02 (3 segments); S13A03T03 (2 segments); S13A03T04 (3 segments); S13A03T05 (3 segments); S13A04T01 (6 segments); S13A04T02 (7 segments); S13A04T03 (5 segments); S13A04T04 (6 segments); S13A04T05 (5 segments); S13A05T01 (5 segments); S13A05T02 (4 segments); S13A05T03 (4 segments); S13A05T04 (5 segments); S13A05T05 (5 segments); S13A06T01 (3 segments); S13A06T03 (2 segments); S13A06T04 (3 segments); S13A06T05 (4 segments); S13A07T01 (5 segments); S13A07T02 (5 segments); S13A07T03 (7 segments); S13A07T04 (7 segments); S13A07T05 (7 segments); S13A08T05 (2 segments).

**SmartFallMM segments with non-increasing-timestamp samples removed (0):** .

### BITS selection counts (pre-specified rules)

- Rule 4 (rest |a| of `acg` within 1 ± 0.1 g): **72** of 984 files fail (0 falls, 72 ADL); 912 remain (328 falls, 584 ADL). Failing files: B_adl12_u01, B_adl12_u07, B_adl12_u08, B_adl12_u09, B_adl12_u17, B_adl12_u21, B_adl12_u28, B_adl12_u33, B_adl12_u34, B_adl2_u03, B_adl2_u12, B_adl2_u16, B_adl2_u17, B_adl2_u22, B_adl2_u32, B_adl3_u01, B_adl3_u06, B_adl3_u07, B_adl3_u08, B_adl3_u11, B_adl3_u12, B_adl3_u13, B_adl3_u15, B_adl3_u16, B_adl3_u18, B_adl3_u19, B_adl3_u20, B_adl3_u22, B_adl3_u24, B_adl3_u27, B_adl3_u30, B_adl3_u33, B_adl3_u35, B_adl3_u37, B_adl3_u38, B_adl4_u01, B_adl4_u04, B_adl4_u08, B_adl4_u09, B_adl4_u12, B_adl4_u13, B_adl4_u18, B_adl4_u19, B_adl4_u20, B_adl4_u22, B_adl4_u23, B_adl4_u25, B_adl4_u32, B_adl4_u36, B_adl4_u37, B_adl4_u38, B_adl4_u41, B_adl7_u01, B_adl7_u07, B_adl7_u08, B_adl7_u09, B_adl7_u17, B_adl7_u19, B_adl7_u24, B_adl8_u01, B_adl8_u04, B_adl8_u07, B_adl8_u12, B_adl8_u13, B_adl8_u16, B_adl8_u22, B_adl8_u23, B_adl8_u24, B_adl8_u28, B_adl8_u32, B_adl8_u37, B_adl8_u40.
- Rule 5 (|first→last timestamp span − N/20| > 10 % ⇒ drop, timestamps taken as ns): **900** of 912 remaining files fail (322 of 328 falls). **Skipped by decision**: it would leave 12 files, and the check is uninformative because timestamps carry only 3 significant digits (see §0.5). **Assumption: BITS is 20 Hz by sample order** (nominal rate from the dataset paper; not verifiable from the files). The BITS run is on hold.

## 6. Addenda after the BITS paper lookup

Read by a sub-agent from https://pmc.ncbi.nlm.nih.gov/articles/PMC10709028/ (Nandi et al., Data in Brief 52 (2024) 109812); not independently re-verified:
- 41 volunteers, **ages 20–47 (mean ≈ 27.9)**, 27 male / 14 female — i.e. an adult cohort, **not geriatric** (the on-disk folder is still called `bits_geriatric`); wrist-worn device (Snapdragon 820c, MPU6500, MAX30102).
- 16 ADLs and 8 falls, 5 repeats each; motion sensors 20 Hz, HR 1 Hz. The article's tag descriptions say `acc` = accelerometer and `acg` = *linear* accelerometer — **the opposite of what the data show** (`acg` carries gravity, rest ≈ 9.81 m/s²; `acc` rest ≈ 0.14 m/s²). The measurement is used, not the prose.
- ADL list: 1 walking slowly, 2 walking quickly, 3 jogging, 4 jumping, 5 climbing up slowly, 6 climbing down slowly, 7 climbing up normally, 8 climbing down normally, 9 slowly sitting on chair, 10 rapidly sitting on chair, 11 nearly sitting and getting up, 12 swinging hands, 13 lying on bed, 14 lying on back and getting up slowly, 15 … normally, 16 sideways → back transition.
- Fall list: 1 forward fall landing on knee, 2 right fall, 3 left fall, 4 forward fall, 5 seated on bed falling to ground, 6 forward fall, body weight on hand, 7 backward fall from seated, 8 grabbing while falling.
- The article does not state the CSV naming. Each user has exactly 16 `adl` and 8 `fall` files (one per Sr No), and per-index motion energy follows the table (median std of |acg|: adl3 jogging 0.96 g and adl4 jumping 1.17 g highest; adl13 lying on bed 0.02 g lowest; seated falls 5 and 7 have the smallest peaks, 2.9 and 2.5 g). **Index → activity mapping is therefore inferred, consistent with the data, but undocumented.**

## 7. Gyroscope (v3 feature set)

Gyro is merged onto the **accelerometer's uniform grid** (then `resample_poly` to 26 Hz exactly like the accelerometer, so the two series are sample-aligned) and converted to **dps**. A segment is gyro-usable only if the gyro timestamps cover the accel segment to within 0.5 s with no gap > 1 s; otherwise it stays in the accelerometer-only analyses but is excluded from v3. The gyro series is never extrapolated, and BITS gyro parsing (`wrist_io.bits_gyro`) exists but is **unused**.

| item | WEDA-FALL | SmartFallMM young (Meta_wrist) | SmartFallMM old (Meta_wrist) | BITS wrist IMU+HR (descriptive only) |
|---|---|---|---|---|
| file | `<code>/U<uid>_R<k>_gyro.csv` (same layout as accel) | `young/gyroscope/meta_wrist/S..A..T...csv` (epoch ms, ISO time, elapsed, x, y, z) | `old/gyroscope/meta_wrist/…csv` — **different format**: `YYYY-MM-DD HH:MM:SS.fff,x,y,z` (no epoch / elapsed); separate `meta_hip` folder exists | `gyro`-tagged block of the same CSV |
| units | **rad/s** (inferred: walking median |ω| = 69 dps = 1.20 rad/s; the README does not say) → ×57.2958 to dps | **dps** (inferred from the ±125 range below) | dps | rad/s (inferred: max 35.3 rad/s = 2025 dps ≈ MPU6500 ±2000 dps) |
| rate | effective 49.7 Hz ADL / 39.8 Hz falls (same burst-stamped, class-dependent artifact as the accelerometer) | median 50 Hz | median 50 Hz | n_gyro / n_acg median 1.00 |
| sync with accelerometer | first/last timestamps agree to ≤ 0.03 s in 95 % of trials (max 0.48 s); both streams use the per-trial linear time axis → 969/969 usable | young: gyro timestamps within 0.5 s of the accel start *and* end in only 71 % of trials; the rule above gives falls 507/691, ADL 767/1049 usable segments | old: **cropped separately from the accel files** — usable ADL segments 188/777; clocks are assumed common (same device); cross-correlation of |ω| with accel dynamics is too weak (median peak 0.15–0.23) to verify | n/a |
| wrist separated out? | n/a | yes (`meta_wrist` folder) | **yes**: a separate `meta_wrist` folder exists and differs from `meta_hip` in 497/497 paired trials (the README's 'Meta_hip_and_wrist' is two folders here) → old subjects are **kept** in v3 where synced | n/a |
| saturation | max |component| 32.9 rad/s = 1885 dps (≈ ±2000 dps range); 11/969 trials hold their maximum value on ≥ 3 samples | **±125 dps per axis**: 97 % of trials peak at ≈125 dps (|ω| capped near 216 dps); 83 % of fall trials reach the cap; spurious outliers up to 391 dps | same ±125 dps cap (81 % of trials), outliers up to 532 dps | max 2025 dps, no repeated maxima |

**Consequence for v3:** SmartFallMM's wrist gyro is a ±125 dps part and clips in almost every trial, while WEDA reaches ≈2000 dps. Pooled gyro features would therefore encode the dataset. v3 is evaluated on two populations (REPORT §): **WEDA-only, native range** (the realistic-sensor case) and **pooled, harmonised** (WEDA clipped to ±125 dps/axis before resampling, SmartFallMM natively clipped) as the cross-dataset check.

### 7.1 Gyro full scale needed (firmware feasibility)

Peak |ω| (vector norm, dps) over each trial; WEDA is the only dataset here whose sensor does not clip below the values of interest:

| set | p50 | p75 | p90 | p95 | p99 | max | share > 250 dps | > 500 | > 1000 | > 1500 | > 2000 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| WEDA falls (350) | 727 | 981 | 1210 | 1422 | 1760 | 2008 | 100 % | 87 % | 23 % | 3 % | 0 % |
| BITS falls (328, descriptive only) | 491 | 696 | 892 | 1031 | 1297 | 1393 | 91 % | 48 % | 6 % | 0 % | 0 % |
| WEDA ADL (619) | 498 | – | – | 1065 | – | 1872 | | | | | |

LSM6DS3TR-C gyro full-scale options are ±125 / 250 / 500 / 1000 / 2000 dps (datasheet fetch failed — see REPORT §Firmware feasibility; this list is from the part's published range and is **unverified here**).

