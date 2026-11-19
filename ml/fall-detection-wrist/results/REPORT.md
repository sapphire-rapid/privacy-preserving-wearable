# Wrist fall detection — retraining report (`wrist-retrain`)

Same 9 features, same logistic-regression pipeline as the SisFall-waist model, retrained on WEDA-FALL + SmartFallMM (Meta_wrist) at 26 Hz. All numbers below were measured by the scripts in `src/` (commands at the end); tables are generated from `results/*.csv`, not typed.

## 0. Read this first

Decisions applied since the first version of this report: (1) **stillness is no longer part of fall detection** — it is the later long-lie (U3 severity) stage; the fall trigger is tuned on its own (trigger-only), post-impact stillness is reported as a finding (§5), and the old confirm-stage tables are kept only in Appendix A; (2) the BITS dataset is called **"BITS wrist IMU+HR (ages 20–47)"** (the on-disk folder `bits_geriatric` is misleading — paper: 41 volunteers aged 20–47, read by a sub-agent from PMC10709028, not independently re-verified); its rule 5 (timestamp-span check) is skipped, the **20 Hz-by-sample-order assumption** stands (timestamps are rounded to 3 significant digits, so the rate cannot be verified), and the **BITS run is ON HOLD** (no lock file created, nothing evaluated).

What to know before reading the numbers:

1. **Operating curve (§4):** at the 90 % recall target the accelerometer-only LR@26 Hz raises a false alarm in about one ADL trial in four (23 %); at 95 % in one in three (34 %). One pooled threshold behaves very differently on the two datasets (§4). The ADL trials are curated vigorous activities, so per-hour rates are a stress test, not daily life.
2. **Gyro (§6):** WEDA's gyro reaches ≈ 2000 dps while SmartFallMM's Meta_wrist gyro clips at ±125 dps in ~97 % of trials, so the gyro comparison is run on two populations. With an unclipped gyro the 6 extra features reduce ADL false alarms by ≈ 2 pp (13–23 % relative) at equal recall; with a ±125 dps gyro they do nothing. The firmware's current gyro config (±245 dps, never read) would clip every fall. **Recommendation (§6.5): stay with the 9 accelerometer features and the 90 % operating point; revisit the gyro on your own recordings.**
3. **Header is provisional:** `include/fall_model.h` carries the final weights, the 95 % threshold (0.671) until you choose a target, and std 0.08 / tol 0.2 / 3 s **as long-lie placeholders**. No C or firmware code was changed in this round.

## 1. Data card summary (full card: `DATA_CARD.md`)

| dataset | role | rate (measured) | units → g | fall trials used | fall trials confirm-eligible | ADL segments used | notes |
|---|---|---|---|---|---|---|---|
| WEDA-FALL | train pool | falls 39.8 Hz / ADL 49.7 Hz (median effective) | ÷9.80665 | 350 | 345 | 619 | Fitbit Sense wrist; falls young only (U01–U14), elderly ADL-only; fall files ≈39.8 Hz vs ADL ≈49.7 Hz effective, burst-stamped → per-trial linear time axis |
| SmartFallMM | train pool | 1983 segments ≈50 Hz, 530 ≈25 Hz, 4 other | already g | 691 | 351 | 1826 | SmartFallMM Meta_wrist (© SmartFall Group, Texas State Univ.; credit required, not redistributed); 50 Hz and 25 Hz sessions; ISO clock; 32 non-g ADL files dropped; split at gaps > 1 s |
| BITS wrist IMU+HR (ages 20–47) | held-out, ON HOLD | 20 Hz assumed by sample order (not verifiable) | ÷9.80665 (`acg`) | 328 files | – | 656 files | rule 4 drops 72 files (0 falls); rule 5 skipped by decision |

After exclusions the pool has **1041 fall trials** (350 WEDA + 691 SFMM) and 2393 ADL trials (2445 segments, 7.52 h); 726 falls have ≥ 3 s after the |a| peak and **696 are confirm-eligible** (a window containing the peak has its full 3 s confirm segment inside the recording; this implies ≥ 3 s after the peak). Subjects: 81 (WEDA 25, SFMM 56). Every exclusion is listed in `DATA_CARD.md` §5.

## 2. Preprocessing and unit tests

Per-trial linear time axis (WEDA) / ISO clock (SmartFallMM) → uniform grid → `resample_poly` to 26 Hz (primary) and 52 Hz (comparison row and waist-baseline input), `padtype='line'` (the default zero padding drags |a| to 0 at trial edges). Raw → g: WEDA ÷ 9.80665, SmartFallMM already g, BITS `acg` ÷ 9.80665.

```
constant-gravity edge test OK
sine time-scale test OK
rest |a| weda  @26 Hz: median 1.0001 g  [5-95%: 0.983, 1.016]  (969 trials)
rest |a| weda  @52 Hz: median 1.0004 g  [5-95%: 0.983, 1.017]  (969 trials)
rest |a| sfmm  @26 Hz: median 1.0027 g  [5-95%: 0.958, 1.066]  (2517 trials)
rest |a| sfmm  @52 Hz: median 1.0029 g  [5-95%: 0.959, 1.069]  (2517 trials)
rest |a| bits  @26 Hz: median 1.0006 g  [5-95%: 0.930, 1.049]  (983 trials)
rest |a| bits  @52 Hz: median 1.0006 g  [5-95%: 0.931, 1.053]  (983 trials)
ALL TESTS PASSED
fs=26  windows=2000  max rel diff per feature: [0. 0. 0. 0. 0. 0. 0. 0. 0.]
fs=52  windows=2000  max rel diff per feature: [0. 0. 0. 0. 0. 0. 0. 0. 0.]
TEST FEATURES PASSED
```

## 3. Windows, features, augmentation

26 Hz constants (scaled from the 52 Hz reference): WIN 52, STRIDE 13, TILT_PRE/POST 13/13, TILT_FALLBACK 5, POST_STD 26, CONFIRM 78; fall label window = peak − int(0.4·WIN), one per fall trial; ADL = all sliding windows (as `features_v2.py`). Vectorised features match the scalar reference exactly (`src/test_features.py`). Training-fold-only augmentation: time-stretch 0.95 / 1.00 / 1.05. Training windows in the pool: 140338 (3123 positive).

### 3.1 Source-rate leak check (WEDA falls ≈39.8 Hz vs ADL ≈49.7 Hz)

619 WEDA ADL trials (14046 windows): direct path (≈49.7 → 26 Hz) vs two-step path (≈49.7 → 39.8 → 26 Hz); relative difference = |a−b| / max(|a|, floor), floors 0.01 g (or g/sample) for magnitude features, 1 sample for count_low, 1° for tilt.

| feature | median rel diff | 99th pct | max rel diff |
|---|---|---|---|
| max_mag | 6.39e-04 | 3.12e-02 | 1.11e-01 |
| min_mag | 8.58e-04 | 8.31e-02 | 1.33e+00 |
| mean_mag | 5.90e-05 | 1.51e-03 | 5.43e-03 |
| std_mag | 8.73e-04 | 1.92e-02 | 1.69e-01 |
| range_mag | 1.65e-03 | 6.38e-02 | 2.77e-01 |
| max_jerk | 3.46e-03 | 1.03e-01 | 3.52e-01 |
| std_mag_post | 9.82e-04 | 2.97e-02 | 1.97e-01 |
| count_low | 0.00e+00 | 1.11e-01 | 1.00e+00 |
| tilt_deg | 9.78e-04 | 2.67e-01 | 5.80e+01 |

Medians are ≤ 3.5e-03 for every feature (i.e. ≤ 0.35 %); tails are heavier (99th pct up to 0.27, driven by near-zero denominators in min_mag, count_low and tilt) but unsystematic. The 26 Hz series is band-limited below 13 Hz, which both source rates cover; the near-zero medians say the extra pre-downsampling step changes the features by well under a percent for a typical window. This is a feature-level check only — I did not train a classifier to predict the source rate.

## 4. Trigger-only operating curve — current accelerometer-only LR @ 26 Hz (9 features)

Stillness plays no role. Nested subject-grouped CV (outer GroupKFold(5), inner GroupKFold(3)); in every outer fold the threshold (0.001 grid) is the one with **≥ target recall on all falls** and the lowest ADL false-alarm rate on the out-of-fold probabilities of the outer-train subjects, and the outer-test subjects are scored once. **One pooled threshold per target is applied to both datasets** — the per-dataset rows are that same operating point evaluated on each dataset. A trial is detected iff any 2 s window (0.5 s stride) has p ≥ thr; an ADL false alarm is any such window in an ADL trial (so the rate is per *trial*, and trials are minutes long). 'Alarmed ADL trials / h' = alarmed trials ÷ ADL hours; 'alarm events / h' merges windows < 5 s apart. 95 % CIs: percentile bootstrap over subjects, 2000 resamples. Pool: 1041 fall trials; ADL time 7.52 h.

| recall target | scope | fall recall (trigger-only) | ADL false alarms per trial | alarmed ADL trials per ADL hour | alarm events per ADL hour (< 5 s merged) |
|---|---|---|---|---|---|
| 80 % | pooled | 80.4% [74.2, 86.2] (837/1041) | 16.5% [13.4, 20.0] (395/2393) | 52.52 [43.49, 62.08] | 57.84 [47.83, 68.20] |
| 80 % | WEDA | 99.1% [97.8, 100.0] (347/350) | 35.5% [29.6, 40.3] (220/619) | 97.77 [83.87, 108.49] | 104.88 [88.62, 117.91] |
| 80 % | SmartFallMM | 70.9% [64.2, 77.0] (490/691) | 9.9% [8.0, 11.8] (175/1774) | 33.20 [26.92, 40.08] | 37.75 [30.57, 45.50] |
| 85 % | pooled | 84.6% [78.7, 89.8] (881/1041) | 19.6% [16.3, 23.2] (468/2393) | 62.22 [52.48, 72.30] | 68.61 [58.44, 79.30] |
| 85 % | WEDA | 99.1% [97.8, 100.0] (347/350) | 39.1% [32.9, 44.2] (242/619) | 107.54 [93.99, 119.21] | 113.76 [98.13, 126.81] |
| 85 % | SmartFallMM | 77.3% [70.4, 83.2] (534/691) | 12.7% [10.6, 14.9] (226/1774) | 42.88 [35.50, 51.14] | 49.33 [40.90, 58.40] |
| 90 % | pooled | 90.1% [85.4, 94.3] (938/1041) | 23.3% [19.7, 27.2] (557/2393) | 74.06 [64.47, 84.24] | 84.16 [73.46, 95.59] |
| 90 % | WEDA | 100.0% [100.0, 100.0] (350/350) | 43.3% [36.9, 48.9] (268/619) | 119.10 [104.58, 131.79] | 127.98 [112.03, 142.94] |
| 90 % | SmartFallMM | 85.1% [79.1, 90.2] (588/691) | 16.3% [13.9, 18.7] (289/1774) | 54.83 [46.75, 63.79] | 65.45 [55.77, 75.37] |
| 95 % | pooled | 95.0% [91.8, 97.7] (989/1041) | 34.2% [29.9, 38.5] (818/2393) | 108.76 [96.85, 120.49] | 124.45 [111.42, 136.82] |
| 95 % | WEDA | 100.0% [100.0, 100.0] (350/350) | 53.6% [46.7, 60.0] (332/619) | 147.54 [130.59, 162.93] | 158.20 [138.52, 176.07] |
| 95 % | SmartFallMM | 92.5% [87.9, 96.1] (639/691) | 27.4% [23.6, 31.2] (486/1774) | 92.20 [79.31, 105.11] | 110.04 [95.41, 124.38] |

Thresholds chosen per outer fold (acc9 LR): 80 %: 0.93, 0.94, 0.92, 0.94, 0.93; 85 %: 0.89, 0.91, 0.87, 0.91, 0.90; 90 %: 0.84, 0.84, 0.78, 0.84, 0.83; 95 %: 0.68, 0.66, 0.60, 0.68, 0.64.

### 4.1 Which ADL activities cause the false alarms (top 5 per dataset)

At the 90 % and 95 % targets (all four targets: `results/ADL_BREAKDOWN.md`). An activity's false-alarm rate is the share of its trials that raised ≥ 1 alarm.

**(i) acc9, LR — recall target 90 %** (ADL trials alarmed / trials, share of that dataset's false alarms)

| dataset | activity | alarmed / trials | false-alarm rate | share of dataset's false alarms |
|---|---|---|---|---|
| SFMM | A03 Put On and Take Off Jacket | 160/208 | 77% | 55% |
| SFMM | A07 Waving Hand | 44/231 | 19% | 15% |
| SFMM | A06 Washing Hand | 20/246 | 8% | 7% |
| SFMM | A09 Sit/Stand | 16/142 | 11% | 6% |
| SFMM | A05 Sweeping Floor | 12/236 | 5% | 4% |
| WEDA | D09 hit table with hand | 57/73 | 78% | 21% |
| WEDA | D02 jogging | 42/42 | 100% | 16% |
| WEDA | D08 gentle jump | 39/42 | 93% | 15% |
| WEDA | D10 clapping | 30/74 | 41% | 11% |
| WEDA | D07 stumble while walking | 28/42 | 67% | 10% |

**(i) acc9, LR — recall target 95 %** (ADL trials alarmed / trials, share of that dataset's false alarms)

| dataset | activity | alarmed / trials | false-alarm rate | share of dataset's false alarms |
|---|---|---|---|---|
| SFMM | A03 Put On and Take Off Jacket | 195/208 | 94% | 40% |
| SFMM | A07 Waving Hand | 98/231 | 42% | 20% |
| SFMM | A06 Washing Hand | 57/246 | 23% | 12% |
| SFMM | A05 Sweeping Floor | 35/236 | 15% | 7% |
| SFMM | A04 Stepping Up | 25/115 | 22% | 5% |
| WEDA | D09 hit table with hand | 64/73 | 88% | 19% |
| WEDA | D02 jogging | 42/42 | 100% | 13% |
| WEDA | D08 gentle jump | 40/42 | 95% | 12% |
| WEDA | D10 clapping | 39/74 | 53% | 12% |
| WEDA | D07 stumble while walking | 33/42 | 79% | 10% |


## 5. Post-impact stillness — a finding, not a detection criterion

Stillness is no longer part of fall detection; it becomes the long-lie (U3 severity) stage, to be validated on your own recordings. There is **no recall target** for it. What the two public datasets say about how soon a wrist is still after a fall (the long-lie placeholder in the header stays std < 0.08, |mean − 1| < 0.2, 3 s):

Fall trials with peak p = argmax|a|; 'reaches stillness within T s' = some start in [p, p+T] is followed by L s of |a| with std < thr and |mean − 1| < 0.2. Only trials with ≥ T + L s of data after the peak are counted (others cannot be judged).

### Placeholder long-lie setting: L = 3 s, std < 0.08, |mean−1| < 0.2

| dataset | horizon | falls with enough post-peak data (≥ T+L s) / all falls | reached stillness within T | median time to stillness (s) |
|---|---|---|---|---|
| WEDA | 3 s | 231/350 | 91.8% (212/231) | 0.88 |
| WEDA | 5 s | 90/350 | 98.9% (89/90) | 0.88 |
| WEDA | 10 s | 2/350 | 100.0% (2/2) | 2.40 |
| SFMM | 3 s | 182/691 | 22.5% (41/182) | 0.58 |
| SFMM | 5 s | 62/691 | 30.6% (19/62) | 0.50 |
| SFMM | 10 s | 11/691 | 45.5% (5/11) | 5.23 |
| pooled | 3 s | 413/1041 | 61.3% (253/413) | 0.85 |
| pooled | 5 s | 152/1041 | 71.1% (108/152) | 0.88 |
| pooled | 10 s | 13/1041 | 53.8% (7/13) | 4.65 |

### Sensitivity: L = 3 s, std < 0.05

| dataset | horizon | falls with enough post-peak data (≥ T+L s) / all falls | reached stillness within T | median time to stillness (s) |
|---|---|---|---|---|
| WEDA | 3 s | 231/350 | 82.7% (191/231) | 1.00 |
| WEDA | 5 s | 90/350 | 92.2% (83/90) | 1.04 |
| WEDA | 10 s | 2/350 | 100.0% (2/2) | 5.08 |
| SFMM | 3 s | 182/691 | 12.1% (22/182) | 0.77 |
| SFMM | 5 s | 62/691 | 21.0% (13/62) | 0.77 |
| SFMM | 10 s | 11/691 | 18.2% (2/11) | 3.48 |
| pooled | 3 s | 413/1041 | 51.6% (213/413) | 1.00 |
| pooled | 5 s | 152/1041 | 63.2% (96/152) | 1.04 |
| pooled | 10 s | 13/1041 | 30.8% (4/13) | 3.48 |

### Sensitivity: L = 3 s, std < 0.12

| dataset | horizon | falls with enough post-peak data (≥ T+L s) / all falls | reached stillness within T | median time to stillness (s) |
|---|---|---|---|---|
| WEDA | 3 s | 231/350 | 95.7% (221/231) | 0.73 |
| WEDA | 5 s | 90/350 | 100.0% (90/90) | 0.73 |
| WEDA | 10 s | 2/350 | 100.0% (2/2) | 2.19 |
| SFMM | 3 s | 182/691 | 37.4% (68/182) | 0.38 |
| SFMM | 5 s | 62/691 | 46.8% (29/62) | 0.31 |
| SFMM | 10 s | 11/691 | 81.8% (9/11) | 4.54 |
| pooled | 3 s | 413/1041 | 70.0% (289/413) | 0.65 |
| pooled | 5 s | 152/1041 | 78.3% (119/152) | 0.65 |
| pooled | 10 s | 13/1041 | 84.6% (11/13) | 4.31 |

### Sensitivity: L = 1 s, std < 0.08

| dataset | horizon | falls with enough post-peak data (≥ T+L s) / all falls | reached stillness within T | median time to stillness (s) |
|---|---|---|---|---|
| WEDA | 3 s | 336/350 | 98.5% (331/336) | 1.00 |
| WEDA | 5 s | 231/350 | 100.0% (231/231) | 1.00 |
| WEDA | 10 s | 11/350 | 100.0% (11/11) | 1.12 |
| SFMM | 3 s | 298/691 | 86.2% (257/298) | 0.92 |
| SFMM | 5 s | 182/691 | 94.0% (171/182) | 0.81 |
| SFMM | 10 s | 17/691 | 100.0% (17/17) | 0.58 |
| pooled | 3 s | 634/1041 | 92.7% (588/634) | 0.96 |
| pooled | 5 s | 413/1041 | 97.3% (402/413) | 0.96 |
| pooled | 10 s | 28/1041 | 100.0% (28/28) | 0.92 |


Reading it: WEDA falls (mattress, young adults) settle almost immediately (≈ 90–99 % reach a still 3 s within 3–5 s after the peak); SmartFallMM falls rarely do (22–31 %), consistent with its hand-cropped trials ending as the participant gets up. The denominators shrink quickly with the horizon (WEDA 2 and SmartFallMM 11 falls have ≥ 13 s of data after the peak), and trials that were recorded for longer are the ones where the person stayed down — so the 10 s row, in particular, is not usable evidence and the others are optimistic for the lying-still case.

## 6. Gyro feature set (v3) — Python only

**Features** (same 2 s / 0.5 s windows, gyro merged onto the accelerometer grid and converted to dps, orientation-invariant; 9 accelerometer features unchanged, 15 in total): `gyro_max`, `gyro_mean`, `gyro_std` (of |ω|), `gyro_rot_win` (Σ|ω|·dt over the window, deg), `gyro_rot_peak` (the same within ±0.5 s of the |a| peak), `gyro_peak_offset_s` (signed time of the |ω| peak minus the |a| peak). Vectorised == scalar reference and rotation invariance are unit-tested (`src/test_gyro_features.py`). Training windows are time-stretched together with the gyro (0.95/1.00/1.05) in training folds only.

**Populations** (data card §7: the SmartFallMM Meta_wrist gyro is a ±125 dps part and clips in ~97 % of its trials, WEDA reaches ≈ 2000 dps — pooling raw gyro features would encode the dataset):

- **v3W — WEDA only, native range**: 350 falls, 619 ADL trials, 25 subjects. This is the realistic-sensor case.
- **v3P — pooled, harmonised**: WEDA clipped per axis to ±125 dps before resampling + SmartFallMM young/old trials whose gyro covers the accel segment (falls 507 of 691, ADL 767 of 1049 young segments, 188 of 777 old segments; the old wrist gyro is a separate `meta_wrist` folder but was cropped separately, so only a minority is usable and its clock agreement is assumed, not verified): 857 falls, 1,574 ADL segments, 74 subjects. This is a lower bound for what the gyro can add (a ±125 dps part throws away the high-rate rotation that distinguishes violent falls).

**Models, same nested CV and targets:** (i) acc9 LR, (ii) acc9 + gyro (15) LR, (iii) L1-LR-selected subset of (ii) followed by a plain LR (C ∈ {0.003, 0.01, 0.03, 0.1, 1} chosen in the inner folds by the mean ADL false-alarm rate over the four targets; selection is redone inside every inner fold), and a depth-5 tree on (ii). (i) is re-run on each population's own trials/subjects/folds so the comparison is matched.

### 6.1 WEDA only, native gyro range

| recall target | model | fall recall | ADL false alarms / trial | alarmed ADL trials / h | alarm events / h |
|---|---|---|---|---|---|
| 80 % | (i) acc9, LR | 80.3% [74.4, 86.2] (281/350) | 6.6% [4.0, 9.3] (41/619) | 18.22 [11.34, 25.18] | 18.22 [11.34, 25.18] |
| 80 % | (ii) acc9 + gyro (15), LR | 80.6% [75.0, 86.5] (282/350) | 5.2% [3.2, 7.1] (32/619) | 14.22 [9.04, 19.21] | 14.22 [9.04, 19.21] |
| 80 % | (iii) L1-selected subset, LR | 80.6% [75.0, 86.5] (282/350) | 5.0% [3.1, 6.8] (31/619) | 13.78 [8.97, 18.59] | 13.78 [8.97, 18.59] |
| 80 % | (ii) acc9 + gyro (15), tree depth ≤ 5 | 72.0% [52.4, 89.5] (252/350) | 12.6% [7.4, 17.7] (78/619) | 34.66 [20.78, 48.22] | 38.66 [22.99, 53.32] |
| 85 % | (i) acc9, LR | 86.0% [80.9, 91.1] (301/350) | 8.4% [5.6, 11.1] (52/619) | 23.11 [15.89, 29.66] | 23.55 [16.30, 30.08] |
| 85 % | (ii) acc9 + gyro (15), LR | 84.9% [79.7, 90.0] (297/350) | 6.5% [4.0, 8.9] (40/619) | 17.78 [11.23, 23.93] | 17.78 [11.23, 23.93] |
| 85 % | (iii) L1-selected subset, LR | 84.9% [79.7, 90.0] (297/350) | 6.5% [4.0, 8.9] (40/619) | 17.78 [11.23, 23.93] | 17.78 [11.23, 23.93] |
| 85 % | (ii) acc9 + gyro (15), tree depth ≤ 5 | 72.0% [52.4, 89.5] (252/350) | 12.6% [7.4, 17.7] (78/619) | 34.66 [20.78, 48.22] | 38.66 [22.99, 53.32] |
| 90 % | (i) acc9, LR | 90.3% [86.3, 93.8] (316/350) | 10.8% [7.8, 13.8] (67/619) | 29.77 [21.93, 37.04] | 30.22 [22.17, 37.41] |
| 90 % | (ii) acc9 + gyro (15), LR | 91.1% [88.0, 94.2] (319/350) | 8.4% [5.7, 10.8] (52/619) | 23.11 [16.36, 29.24] | 23.11 [16.36, 29.24] |
| 90 % | (iii) L1-selected subset, LR | 90.6% [87.0, 93.9] (317/350) | 8.1% [5.4, 10.6] (50/619) | 22.22 [15.19, 28.51] | 22.22 [15.19, 28.51] |
| 90 % | (ii) acc9 + gyro (15), tree depth ≤ 5 | 73.1% [53.2, 90.8] (256/350) | 15.0% [9.6, 20.3] (93/619) | 41.33 [27.06, 54.99] | 45.33 [28.94, 60.13] |
| 95 % | (i) acc9, LR | 95.4% [92.3, 98.0] (334/350) | 16.2% [12.1, 19.8] (100/619) | 44.44 [34.57, 53.06] | 44.88 [34.83, 53.65] |
| 95 % | (ii) acc9 + gyro (15), LR | 95.4% [92.9, 97.8] (334/350) | 14.1% [10.5, 17.4] (87/619) | 38.66 [30.28, 46.21] | 40.00 [31.29, 47.91] |
| 95 % | (iii) L1-selected subset, LR | 95.1% [92.6, 97.3] (333/350) | 13.9% [10.4, 17.2] (86/619) | 38.22 [29.99, 45.39] | 39.11 [30.43, 46.71] |
| 95 % | (ii) acc9 + gyro (15), tree depth ≤ 5 | 95.7% [91.7, 98.8] (335/350) | 23.7% [18.4, 28.9] (147/619) | 65.33 [51.02, 78.97] | 69.33 [53.41, 85.82] |

Paired subject-bootstrap differences (same trials; negative false-alarm change = fewer false alarms):

| recall target | comparison | Δ fall recall (pp) | Δ ADL false alarms / trial (pp; negative = fewer) |
|---|---|---|---|
| 80 % | (ii) acc9 + gyro (15), LR − (i) acc9, LR | +0.3 [-3.5, +3.7] | -1.5 [-3.1, +0.0] |
| 80 % | (iii) L1-selected subset, LR − (i) acc9, LR | +0.3 [-3.5, +3.7] | -1.6 [-3.4, +0.0] |
| 80 % | (ii) acc9 + gyro (15), tree depth ≤ 5 − (i) acc9, LR | -8.3 [-28.3, +8.3] | +6.0 [+1.2, +10.2] |
| 85 % | (ii) acc9 + gyro (15), LR − (i) acc9, LR | -1.1 [-5.2, +2.6] | -1.9 [-3.8, -0.3] |
| 85 % | (iii) L1-selected subset, LR − (i) acc9, LR | -1.1 [-5.2, +2.6] | -1.9 [-3.8, -0.3] |
| 85 % | (ii) acc9 + gyro (15), tree depth ≤ 5 − (i) acc9, LR | -14.0 [-34.0, +3.0] | +4.2 [-0.8, +8.8] |
| 90 % | (ii) acc9 + gyro (15), LR − (i) acc9, LR | +0.9 [-0.9, +2.7] | -2.4 [-4.4, -0.6] |
| 90 % | (iii) L1-selected subset, LR − (i) acc9, LR | +0.3 [-1.5, +2.1] | -2.7 [-4.7, -0.9] |
| 90 % | (ii) acc9 + gyro (15), tree depth ≤ 5 − (i) acc9, LR | -17.1 [-38.6, +1.8] | +4.2 [-1.4, +9.4] |
| 95 % | (ii) acc9 + gyro (15), LR − (i) acc9, LR | +0.0 [-1.3, +1.3] | -2.1 [-3.9, -0.3] |
| 95 % | (iii) L1-selected subset, LR − (i) acc9, LR | -0.3 [-1.5, +1.0] | -2.3 [-4.0, -0.5] |
| 95 % | (ii) acc9 + gyro (15), tree depth ≤ 5 − (i) acc9, LR | +0.3 [-2.3, +2.7] | +7.6 [+4.0, +11.4] |

L1 subset — chosen C and selected features per outer fold:

| outer fold | chosen C | selected features |
|---|---|---|
| 0 | 0.1 | min_mag mean_mag std_mag range_mag max_jerk std_mag_post count_low tilt_deg gyro_max gyro_mean gyro_std gyro_rot_win gyro_rot_peak gyro_peak_offset_s |
| 1 | 0.03 | min_mag mean_mag std_mag range_mag max_jerk std_mag_post count_low tilt_deg gyro_mean gyro_std gyro_rot_win gyro_rot_peak gyro_peak_offset_s |
| 2 | 1.0 | max_mag min_mag mean_mag std_mag range_mag max_jerk std_mag_post count_low tilt_deg gyro_max gyro_mean gyro_std gyro_rot_win gyro_rot_peak gyro_peak_offset_s |
| 3 | 0.1 | min_mag mean_mag std_mag range_mag max_jerk std_mag_post count_low tilt_deg gyro_max gyro_mean gyro_std gyro_rot_win gyro_rot_peak gyro_peak_offset_s |
| 4 | 1.0 | max_mag min_mag mean_mag std_mag range_mag max_jerk std_mag_post count_low tilt_deg gyro_max gyro_mean gyro_std gyro_rot_win gyro_rot_peak gyro_peak_offset_s |

Selection frequency over the 5 outer folds: min_mag 5/5, mean_mag 5/5, std_mag 5/5, range_mag 5/5, max_jerk 5/5, std_mag_post 5/5, count_low 5/5, tilt_deg 5/5, gyro_mean 5/5, gyro_std 5/5, gyro_rot_win 5/5, gyro_rot_peak 5/5, gyro_peak_offset_s 5/5, gyro_max 4/5, max_mag 2/5

ADL false-alarm breakdown (top 5 per dataset) at the 90 % and 95 % targets, acc9 vs acc9 + gyro:

**(i) acc9, LR — recall target 90 %** (ADL trials alarmed / trials, share of that dataset's false alarms)

| dataset | activity | alarmed / trials | false-alarm rate | share of dataset's false alarms |
|---|---|---|---|---|
| WEDA | D09 hit table with hand | 25/73 | 34% | 37% |
| WEDA | D02 jogging | 22/42 | 52% | 33% |
| WEDA | D08 gentle jump | 9/42 | 21% | 13% |
| WEDA | D07 stumble while walking | 5/42 | 12% | 7% |
| WEDA | D05 sit, try to rise, collapse into chair | 3/42 | 7% | 4% |

**(i) acc9, LR — recall target 95 %** (ADL trials alarmed / trials, share of that dataset's false alarms)

| dataset | activity | alarmed / trials | false-alarm rate | share of dataset's false alarms |
|---|---|---|---|---|
| WEDA | D02 jogging | 35/42 | 83% | 35% |
| WEDA | D09 hit table with hand | 28/73 | 38% | 28% |
| WEDA | D08 gentle jump | 16/42 | 38% | 16% |
| WEDA | D07 stumble while walking | 8/42 | 19% | 8% |
| WEDA | D05 sit, try to rise, collapse into chair | 7/42 | 17% | 7% |

**(ii) acc9 + gyro (15), LR — recall target 90 %** (ADL trials alarmed / trials, share of that dataset's false alarms)

| dataset | activity | alarmed / trials | false-alarm rate | share of dataset's false alarms |
|---|---|---|---|---|
| WEDA | D09 hit table with hand | 24/73 | 33% | 46% |
| WEDA | D02 jogging | 12/42 | 29% | 23% |
| WEDA | D08 gentle jump | 8/42 | 19% | 15% |
| WEDA | D05 sit, try to rise, collapse into chair | 4/42 | 10% | 8% |
| WEDA | D07 stumble while walking | 3/42 | 7% | 6% |

**(ii) acc9 + gyro (15), LR — recall target 95 %** (ADL trials alarmed / trials, share of that dataset's false alarms)

| dataset | activity | alarmed / trials | false-alarm rate | share of dataset's false alarms |
|---|---|---|---|---|
| WEDA | D09 hit table with hand | 29/73 | 40% | 33% |
| WEDA | D02 jogging | 22/42 | 52% | 25% |
| WEDA | D08 gentle jump | 15/42 | 36% | 17% |
| WEDA | D05 sit, try to rise, collapse into chair | 8/42 | 19% | 9% |
| WEDA | D07 stumble while walking | 8/42 | 19% | 9% |


### 6.2 Pooled, gyro harmonised to ±125 dps

| recall target | model | fall recall | ADL false alarms / trial | alarmed ADL trials / h | alarm events / h |
|---|---|---|---|---|---|
| 80 % | (i) acc9, LR | 79.9% [74.0, 85.3] (685/857) | 17.2% [12.7, 21.8] (270/1573) | 53.07 [40.37, 65.35] | 56.81 [43.34, 69.75] |
| 80 % | (ii) acc9 + gyro (15), LR | 80.0% [73.9, 85.6] (686/857) | 16.5% [12.2, 20.7] (259/1573) | 50.91 [39.43, 62.12] | 53.66 [41.25, 65.56] |
| 80 % | (iii) L1-selected subset, LR | 79.8% [73.5, 85.5] (684/857) | 16.8% [12.6, 21.3] (265/1573) | 52.09 [40.53, 63.29] | 54.45 [42.08, 66.53] |
| 80 % | (ii) acc9 + gyro (15), tree depth ≤ 5 | 74.3% [63.1, 84.0] (637/857) | 19.4% [14.6, 24.3] (305/1573) | 59.95 [45.68, 74.48] | 66.64 [50.57, 82.79] |
| 85 % | (i) acc9, LR | 85.6% [80.8, 90.0] (734/857) | 20.2% [15.6, 24.8] (317/1573) | 62.31 [49.72, 73.83] | 67.62 [53.84, 80.56] |
| 85 % | (ii) acc9 + gyro (15), LR | 85.5% [80.6, 89.9] (733/857) | 20.3% [15.7, 24.9] (319/1573) | 62.70 [50.06, 74.42] | 68.01 [54.30, 80.51] |
| 85 % | (iii) L1-selected subset, LR | 84.9% [79.8, 89.5] (728/857) | 19.9% [15.4, 24.5] (313/1573) | 61.53 [49.13, 73.47] | 67.03 [53.33, 79.94] |
| 85 % | (ii) acc9 + gyro (15), tree depth ≤ 5 | 74.3% [63.1, 84.0] (637/857) | 19.4% [14.6, 24.3] (305/1573) | 59.95 [45.68, 74.48] | 66.64 [50.57, 82.79] |
| 90 % | (i) acc9, LR | 89.7% [86.2, 92.9] (769/857) | 25.6% [20.9, 30.3] (402/1573) | 79.02 [66.41, 90.84] | 86.69 [72.37, 99.62] |
| 90 % | (ii) acc9 + gyro (15), LR | 90.0% [85.9, 93.4] (771/857) | 25.2% [20.5, 30.0] (396/1573) | 77.84 [64.94, 90.09] | 84.52 [70.28, 97.68] |
| 90 % | (iii) L1-selected subset, LR | 89.5% [85.3, 93.1] (767/857) | 24.7% [19.8, 29.6] (388/1573) | 76.27 [63.06, 88.66] | 83.15 [68.41, 96.81] |
| 90 % | (ii) acc9 + gyro (15), tree depth ≤ 5 | 88.2% [84.5, 91.3] (756/857) | 23.5% [19.0, 27.9] (370/1573) | 72.73 [59.39, 85.38] | 81.58 [66.36, 95.22] |
| 95 % | (i) acc9, LR | 94.7% [91.7, 97.1] (812/857) | 31.3% [26.2, 36.4] (493/1573) | 96.91 [83.58, 109.50] | 108.11 [93.52, 121.48] |
| 95 % | (ii) acc9 + gyro (15), LR | 94.5% [91.3, 97.0] (810/857) | 32.1% [26.6, 37.3] (505/1573) | 99.27 [84.61, 112.47] | 110.86 [94.09, 125.44] |
| 95 % | (iii) L1-selected subset, LR | 94.6% [91.6, 97.0] (811/857) | 31.8% [26.4, 37.1] (500/1573) | 98.28 [83.30, 111.19] | 109.88 [92.96, 124.86] |
| 95 % | (ii) acc9 + gyro (15), tree depth ≤ 5 | 95.6% [93.4, 97.3] (819/857) | 32.2% [26.9, 37.4] (507/1573) | 99.66 [85.40, 113.29] | 111.06 [95.39, 126.02] |

Paired subject-bootstrap differences (same trials; negative false-alarm change = fewer false alarms):

| recall target | comparison | Δ fall recall (pp) | Δ ADL false alarms / trial (pp; negative = fewer) |
|---|---|---|---|
| 80 % | (ii) acc9 + gyro (15), LR − (i) acc9, LR | +0.1 [-1.8, +1.6] | -0.7 [-2.0, +0.5] |
| 80 % | (iii) L1-selected subset, LR − (i) acc9, LR | -0.1 [-2.2, +1.5] | -0.3 [-1.3, +0.7] |
| 80 % | (ii) acc9 + gyro (15), tree depth ≤ 5 − (i) acc9, LR | -5.6 [-15.7, +3.4] | +2.2 [-0.9, +5.0] |
| 85 % | (ii) acc9 + gyro (15), LR − (i) acc9, LR | -0.1 [-2.5, +2.1] | +0.1 [-1.1, +1.3] |
| 85 % | (iii) L1-selected subset, LR − (i) acc9, LR | -0.7 [-3.1, +1.4] | -0.3 [-1.5, +0.9] |
| 85 % | (ii) acc9 + gyro (15), tree depth ≤ 5 − (i) acc9, LR | -11.3 [-22.1, -2.0] | -0.8 [-3.8, +1.8] |
| 90 % | (ii) acc9 + gyro (15), LR − (i) acc9, LR | +0.2 [-1.7, +1.9] | -0.4 [-1.7, +0.9] |
| 90 % | (iii) L1-selected subset, LR − (i) acc9, LR | -0.2 [-2.2, +1.5] | -0.9 [-2.0, +0.1] |
| 90 % | (ii) acc9 + gyro (15), tree depth ≤ 5 − (i) acc9, LR | -1.5 [-4.1, +1.1] | -2.0 [-3.8, -0.3] |
| 95 % | (ii) acc9 + gyro (15), LR − (i) acc9, LR | -0.2 [-1.7, +1.1] | +0.8 [-1.2, +2.7] |
| 95 % | (iii) L1-selected subset, LR − (i) acc9, LR | -0.1 [-1.8, +1.4] | +0.4 [-1.5, +2.3] |
| 95 % | (ii) acc9 + gyro (15), tree depth ≤ 5 − (i) acc9, LR | +0.8 [-1.5, +3.5] | +0.9 [-0.9, +2.8] |

L1 subset — chosen C and selected features per outer fold:

| outer fold | chosen C | selected features |
|---|---|---|
| 0 | 0.003 | min_mag range_mag max_jerk std_mag_post tilt_deg gyro_mean gyro_std gyro_rot_win gyro_rot_peak gyro_peak_offset_s |
| 1 | 0.003 | min_mag range_mag max_jerk std_mag_post tilt_deg gyro_mean gyro_std gyro_rot_win gyro_rot_peak gyro_peak_offset_s |
| 2 | 0.03 | min_mag mean_mag std_mag range_mag max_jerk std_mag_post count_low tilt_deg gyro_mean gyro_std gyro_rot_win gyro_rot_peak gyro_peak_offset_s |
| 3 | 0.003 | min_mag range_mag max_jerk std_mag_post tilt_deg gyro_mean gyro_std gyro_rot_win gyro_rot_peak |
| 4 | 0.03 | min_mag std_mag range_mag max_jerk std_mag_post count_low tilt_deg gyro_max gyro_mean gyro_std gyro_rot_win gyro_rot_peak gyro_peak_offset_s |

Selection frequency over the 5 outer folds: min_mag 5/5, range_mag 5/5, max_jerk 5/5, std_mag_post 5/5, tilt_deg 5/5, gyro_mean 5/5, gyro_std 5/5, gyro_rot_win 5/5, gyro_rot_peak 5/5, gyro_peak_offset_s 4/5, std_mag 2/5, count_low 2/5, mean_mag 1/5, gyro_max 1/5

ADL false-alarm breakdown (top 5 per dataset) at the 90 % and 95 % targets, acc9 vs acc9 + gyro:

**(i) acc9, LR — recall target 90 %** (ADL trials alarmed / trials, share of that dataset's false alarms)

| dataset | activity | alarmed / trials | false-alarm rate | share of dataset's false alarms |
|---|---|---|---|---|
| SFMM | A03 Put On and Take Off Jacket | 83/105 | 79% | 55% |
| SFMM | A07 Waving Hand | 19/119 | 16% | 13% |
| SFMM | A09 Sit/Stand | 13/95 | 14% | 9% |
| SFMM | A04 Stepping Up | 7/42 | 17% | 5% |
| SFMM | A06 Washing Hand | 7/123 | 6% | 5% |
| WEDA | D09 hit table with hand | 57/73 | 78% | 23% |
| WEDA | D02 jogging | 42/42 | 100% | 17% |
| WEDA | D08 gentle jump | 37/42 | 88% | 15% |
| WEDA | D07 stumble while walking | 28/42 | 67% | 11% |
| WEDA | D10 clapping | 23/74 | 31% | 9% |

**(i) acc9, LR — recall target 95 %** (ADL trials alarmed / trials, share of that dataset's false alarms)

| dataset | activity | alarmed / trials | false-alarm rate | share of dataset's false alarms |
|---|---|---|---|---|
| SFMM | A03 Put On and Take Off Jacket | 91/105 | 87% | 43% |
| SFMM | A07 Waving Hand | 37/119 | 31% | 18% |
| SFMM | A06 Washing Hand | 18/123 | 15% | 9% |
| SFMM | A09 Sit/Stand | 17/95 | 18% | 8% |
| SFMM | A02 Pick Up Object | 17/128 | 13% | 8% |
| WEDA | D09 hit table with hand | 60/73 | 82% | 21% |
| WEDA | D02 jogging | 42/42 | 100% | 15% |
| WEDA | D08 gentle jump | 38/42 | 90% | 13% |
| WEDA | D10 clapping | 33/74 | 45% | 12% |
| WEDA | D07 stumble while walking | 29/42 | 69% | 10% |

**(ii) acc9 + gyro (15), LR — recall target 90 %** (ADL trials alarmed / trials, share of that dataset's false alarms)

| dataset | activity | alarmed / trials | false-alarm rate | share of dataset's false alarms |
|---|---|---|---|---|
| SFMM | A03 Put On and Take Off Jacket | 76/105 | 72% | 50% |
| SFMM | A07 Waving Hand | 22/119 | 18% | 14% |
| SFMM | A09 Sit/Stand | 15/95 | 16% | 10% |
| SFMM | A02 Pick Up Object | 9/128 | 7% | 6% |
| SFMM | A06 Washing Hand | 8/123 | 7% | 5% |
| WEDA | D09 hit table with hand | 58/73 | 79% | 24% |
| WEDA | D02 jogging | 42/42 | 100% | 17% |
| WEDA | D08 gentle jump | 35/42 | 83% | 14% |
| WEDA | D07 stumble while walking | 25/42 | 60% | 10% |
| WEDA | D05 sit, try to rise, collapse into chair | 21/42 | 50% | 9% |

**(ii) acc9 + gyro (15), LR — recall target 95 %** (ADL trials alarmed / trials, share of that dataset's false alarms)

| dataset | activity | alarmed / trials | false-alarm rate | share of dataset's false alarms |
|---|---|---|---|---|
| SFMM | A03 Put On and Take Off Jacket | 89/105 | 85% | 41% |
| SFMM | A07 Waving Hand | 35/119 | 29% | 16% |
| SFMM | A09 Sit/Stand | 21/95 | 22% | 10% |
| SFMM | A02 Pick Up Object | 18/128 | 14% | 8% |
| SFMM | A06 Washing Hand | 15/123 | 12% | 7% |
| WEDA | D09 hit table with hand | 61/73 | 84% | 21% |
| WEDA | D02 jogging | 42/42 | 100% | 15% |
| WEDA | D08 gentle jump | 40/42 | 95% | 14% |
| WEDA | D07 stumble while walking | 30/42 | 71% | 10% |
| WEDA | D05 sit, try to rise, collapse into chair | 25/42 | 60% | 9% |


### 6.3 Firmware feasibility notes (no firmware or C code changed)

- **Gyro full scale.** Peak |ω| of WEDA falls (sensor limit ≈ 2000 dps, so the upper tail is itself clipped): median 727, p90 1210, p95 1422, p99 1760, max 2008 dps; 87% of falls exceed ±500 dps, 23% exceed ±1000, 3% exceed ±1500. BITS falls (descriptive only, no clipping): median 491, p95 1031, max 1393 dps. **±2000 dps is needed to avoid clipping the upper tail; ±1000 dps would clip ≈23% of falls near the impact (the features use the maximum and the integrated angle), ±500 dps ≈87%.** SmartFallMM's ±125 dps part cannot tell (it saturates in 83% of its falls) — which is also why the pooled gyro result is a lower bound.
- **LSM6DS3TR-C gyro supply current at 26 Hz: UNVERIFIED.** The ST datasheet fetch timed out twice and the Digi-Key/Mouser copies were not reachable by the fetch tool; a web search returned only combined figures (ST product page: 0.90 mA in high-performance mode; LSM6DS3 datasheet: 0.9 mA combo normal mode, 1.25 mA combo high-performance mode, low-power mode available at ODR 12.5/26/52 Hz via the G_HM_MODE bit in CTRL7_G) — these are the sibling-part/combined numbers, **not** the gyro-only 26 Hz figure needed here. Sources: [ST product page](https://st.com/en/mems-and-sensors/lsm6ds3tr-c.html), [LSM6DS3 datasheet (Arduino mirror)](https://docs.arduino.cc/resources/datasheets/LSM6DS3-datasheet.pdf). Read the gyro rows of the 'electrical characteristics' table before committing to a power budget.
- **Firmware impact (nothing changed):** `imu.c` already configures the gyro (`.gyro_odr = LSM6DSXX_DATA_RATE_52HZ`, **`.gyro_fs = LSM6DSXX_GYRO_FS_245DPS`**, no decimation; grep finds no other gyro reference, so it is configured but never read). The current ±245 dps setting would clip essentially every fall (100% of WEDA falls exceed 250 dps), so v3 needs FS raised to 2000 dps (sensitivity falls from 8.75 to 70 mdps/LSB — datasheet values, unverified here), the gyro ODR set to 26 Hz, and a read path that delivers sample-aligned |ω| and |a| (whether the two sensors share an ODR clock at equal rates is **not verified here**). The six gyro features are norms and angle sums, hence invariant to sensor orientation (checked in `test_gyro_features.py`) — no axis calibration is needed.

### 6.4 Summary: accelerometer-only vs accelerometer + gyro at each recall target

Cells: fall recall / ADL false alarms per trial / alarmed ADL trials per hour (point estimates; CIs in the tables above).

| recall target | population | acc9 LR: recall / ADL FA per trial / FA per h | acc9+gyro LR | L1 subset LR | acc9+gyro tree |
|---|---|---|---|---|---|
| 80 % | WEDA only (native ±2000 dps) | 80.3% / 6.6% / 18.2 | 80.6% / 5.2% / 14.2 | 80.6% / 5.0% / 13.8 | 72.0% / 12.6% / 34.7 |
| 80 % | pooled, harmonised ±125 dps | 79.9% / 17.2% / 53.1 | 80.0% / 16.5% / 50.9 | 79.8% / 16.8% / 52.1 | 74.3% / 19.4% / 60.0 |
| 85 % | WEDA only (native ±2000 dps) | 86.0% / 8.4% / 23.1 | 84.9% / 6.5% / 17.8 | 84.9% / 6.5% / 17.8 | 72.0% / 12.6% / 34.7 |
| 85 % | pooled, harmonised ±125 dps | 85.6% / 20.2% / 62.3 | 85.5% / 20.3% / 62.7 | 84.9% / 19.9% / 61.5 | 74.3% / 19.4% / 60.0 |
| 90 % | WEDA only (native ±2000 dps) | 90.3% / 10.8% / 29.8 | 91.1% / 8.4% / 23.1 | 90.6% / 8.1% / 22.2 | 73.1% / 15.0% / 41.3 |
| 90 % | pooled, harmonised ±125 dps | 89.7% / 25.6% / 79.0 | 90.0% / 25.2% / 77.8 | 89.5% / 24.7% / 76.3 | 88.2% / 23.5% / 72.7 |
| 95 % | WEDA only (native ±2000 dps) | 95.4% / 16.2% / 44.4 | 95.4% / 14.1% / 38.7 | 95.1% / 13.9% / 38.2 | 95.7% / 23.7% / 65.3 |
| 95 % | pooled, harmonised ±125 dps | 94.7% / 31.3% / 96.9 | 94.5% / 32.1% / 99.3 | 94.6% / 31.8% / 98.3 | 95.6% / 32.2% / 99.7 |

### 6.5 Recommendation (for your decision — nothing exported or implemented beyond what is listed)

**Feature set: keep the 9 accelerometer features (LR @ 26 Hz).** With a gyro that does not clip (WEDA, native range) the 6 added features lower ADL false alarms per trial by 2.4 pp at the 90 % target (paired CI [-4.4, -0.6] pp; 2.1 pp at 95 %, [-3.9, -0.3]) at unchanged recall — a 13–23 % relative reduction, with the paired CI excluding zero at the 85, 90, 95 % targets. In the pooled, ±125 dps-harmonised population the same features change nothing measurable (-0.4 pp at 90 %, [-1.7, +0.9]; +0.8 pp at 95 %, [-1.2, +2.7]). The L1 step does not find a smaller useful set (it keeps 13–15 of the 15 features in the WEDA run and 9–14 in the pooled run, with no accuracy difference to (ii)), and the depth-5 tree is worse than LR and cannot reach the 80–90 % targets in the WEDA run because its probabilities are coarse. The gain exists only if the gyro runs at ±2000 dps (the firmware is currently configured for ±245 dps, which clips every fall), needs a read path and a power budget I could not verify, and I could not test it on a second dataset with an unclipped gyro (BITS is on hold). I would therefore **not** add the gyro to the first firmware, and revisit it when you have your own recordings with a ±2000 dps gyro: the question to answer there is whether the ≈2 pp trial-level false-alarm reduction survives.

**Operating point: the 90 % recall target.** Pooled 5-fold CV threshold of the final model: **0.835** (per outer fold 0.84, 0.84, 0.78, 0.84, 0.83); cross-validated recall 90.1 % [85.4, 94.3], ADL false alarms per trial 23.3 % [19.7, 27.2]. Going from 90 % to 95 % recall raises the false-alarm rate from 23.3 % to 34.2 % per trial (alarmed ADL trials per hour 74 → 109), while 85 % → 90 % costs only 3.7 pp — the knee of the curve is at 85–90 %. The thresholds for all four targets are stored in `results/final_model.json` (80 %: 0.934, 85 %: 0.897, 90 %: 0.835, 95 %: 0.671). Two cautions: (a) the *current exported header still carries the 95 % point (0.671)*; regenerate with `src/export_final.py --op trig90` once you choose, then re-run `src/parity.py`; (b) one pooled threshold hides large dataset differences — at 90 % it gives WEDA 100 % recall with 43 % ADL false alarms per trial but SmartFallMM 85 % recall with 16 % (table in §4) — and the ADL trials of both datasets are curated, vigorous activities (jogging, hand hits, stumbles, jumps), so the per-hour figures are an upper-bound stress test, not a daily-life false-alarm rate. Calibrate the final threshold on your own recordings.

## 7. Model comparison (offline; LR is the deploy candidate; trigger-only threshold tuned for 95 % recall)

| model | trigger recall (mode B) | ADL trigger-only FAR | recall with confirm (coverage) | parameters | classifier flash, bytes (measured) | + shared feature code | total flash |
|---|---|---|---|---|---|---|---|
| LR @ 26 Hz | 95.0% [91.8, 97.7] (989/1041) | 34.2% [29.9, 38.5] (818/2393) | 40.2% [26.9, 53.8] (280/696); cov. 696/1041 | 28 (28 floats = 112 B) | 324 | 720 | 1044 |
| Decision tree (depth ≤ 5) @ 26 Hz | 94.6% [91.4, 97.4] (985/1041) | 30.2% [26.5, 34.3] (722/2393) | 40.4% [27.2, 53.7] (281/696); cov. 696/1041 | 61 (tree nodes) | 816 | 720 | 1536 |
| MLP (1×16) @ 26 Hz | 95.3% [92.2, 97.8] (992/1041) | 27.4% [23.5, 31.6] (655/2393) | 39.7% [26.5, 53.1] (276/696); cov. 696/1041 | 195 (floats) | 944 | 720 | 1664 |
| LR @ 52 Hz | 95.6% [92.9, 97.8] (995/1041) | 36.5% [32.4, 41.0] (873/2393) | 39.6% [26.1, 53.2] (275/695); cov. 695/1041 | 28 | same code as LR@26 | – | – |

Flash = `arm-none-eabi-gcc -Os -mcpu=cortex-m4 -mfloat-abi=hard` object text+rodata for the final pool-trained model (tree: depth 5, 31 leaves; MLP: 9→16→1 ReLU/sigmoid), libm excluded. Subject-bootstrap CIs of the three models overlap on every metric (no paired test was run); LR is the cheapest in flash and the only one the firmware already supports.

## 8. Waist → wrist domain gap

| model | recall trigger-only | ADL trigger-only FAR | recall with confirm (eligible; coverage) | ADL confirmed FAR |
|---|---|---|---|---|
| SisFall-waist LR, unchanged, 52 Hz (thr 0.93) | 79.1% [72.9, 85.6] (823/1041) | 31.6% [28.4, 35.1] (757/2393) | 27.9% [16.0, 40.8] (194/695); 695/1041 | 1.5% [0.6, 2.6] (35/2393) |
| Wrist LR @ 52 Hz (mode B) | 95.6% [92.9, 97.8] (995/1041) | 36.5% [32.4, 41.0] (873/2393) | 39.6% [26.1, 53.2] (275/695); 695/1041 | 3.6% [2.1, 5.3] (85/2393) |
| Wrist LR @ 26 Hz (mode B) | 95.0% [91.8, 97.7] (989/1041) | 34.2% [29.9, 38.5] (818/2393) | 40.2% [26.9, 53.8] (280/696); 696/1041 | 3.6% [2.2, 5.4] (87/2393) |

The waist model transfers poorly: at its own fixed threshold it detects the minority of wrist falls while still triggering on about a third of ADL trials. The comparison is not threshold-matched (the baseline is unchanged by construction); the wrist LR at its tuned threshold reaches 95 % trigger-only recall at a similar ADL trigger-only false-alarm rate.

## 9. BITS wrist IMU+HR (ages 20–47) held-out run — ON HOLD

- Preprocessed (`acg`, g, 20→26 Hz and 20→52 Hz) and filtered by the pre-specified rules; no model has seen it.
- Rule 4 (rest |a| of `acg` within 1 ± 0.1 g): 72 of 984 files dropped (0 falls, 72 ADL) → 912 files remain (328 falls, 584 ADL).
- Rule 5 (|timestamp span − N/20| > 10 % ⇒ drop) is **skipped by decision**: it would have dropped 900 of 912 files (falls 322 of 328) because the timestamps keep only 3 significant digits. **Assumption: 20 Hz by sample order.**
- Index → activity: not documented in the paper's text; per-index energy follows the paper's table (jogging/jumping highest, lying lowest, seated falls gentlest), so per-fall-type recall can be computed with an *inferred* mapping once the run is released (`DATA_CARD.md` §6).
- Caveat that will accompany the result: 20 Hz is assumed by sample order; the HR-block cross-check (median 20.2 samples per HR row, IQR 7–51) is consistent at the median only.

## 10. Export and C parity

`include/fall_model.h` and `include/test_windows.h` (12 real train-pool windows + 6 stillness segments for the long-lie placeholder, taken from WEDA-FALL only because SmartFallMM is all-rights-reserved, with expected features, probabilities and decisions; every float literal is positional with a decimal point before `f`). `firmware/fall_imu/include/` was not modified. Header fixes vs the reference exporter: all rate macros incl. TILT_PRE/POST/FALLBACK, POST_STD and `MODEL_IMU_ODR_ENUM = LSM6DSXX_DATA_RATE_26HZ` (imu.c already selects 26 Hz from `SAMPLE_RATE_HZ`); the (placeholder, long-lie) stillness thresholds are emitted as the macros `FALL_STILL_STD_THR / FALL_STILL_MEAN_TOL` — the reference header's `static const STILL_STD_THR` is never read by `fall_features.h`, so a tuned std would have been ignored on the device.


Firmware `fall_features.h` sha256[:16] `9ec8875932bda914` (copied unmodified to a build dir; firmware include dir untouched). Exported operating point: mode `trig`, thr 0.671, std 0.08, tol 0.2 (provisional=True).

- `host_test.c` built with gcc against the new headers: compile rc=0; run rc=0; last lines:

```
4     0          PASS  
5     0          PASS  

RESULT: ALL PASS (12 windows, 6 still segments)
```

- 1000 random train windows (800 random sliding + 200 fall-impact) through the C feature code vs Python float64 on the same float32 inputs; PASS needs every feature within 0.0001 relative:

| feature | max rel err | max abs err | windows over 1e-4 |
|---|---|---|---|
| max_mag | 8.98e-08 | 4.07e-07 | 0 |
| min_mag | 9.39e-08 | 9.40e-08 | 0 |
| mean_mag | 4.12e-07 | 5.10e-07 | 0 |
| std_mag | 4.28e-06 | 2.19e-07 | 0 |
| range_mag | 1.76e-05 | 5.48e-07 | 0 |
| max_jerk | 9.90e-06 | 6.01e-07 | 0 |
| std_mag_post | 1.95e-05 | 1.53e-07 | 0 |
| count_low | 0.00e+00 | 0.00e+00 | 0 |
| tilt_deg | 6.98e-05 | 2.50e-05 | 0 |

- probability: max |C − Python| = 3.77e-07
- trigger decisions at the exported threshold 0.671: **0 mismatches** of 1000 (249 triggers; 0 windows within 1e-4 of the threshold)
- same comparison at other thresholds: 0.003: 0 mismatches (980 triggers); 0.5: 0 mismatches (292 triggers); 0.671: 0 mismatches (249 triggers); 0.93: 0 mismatches (164 triggers)
- stillness decisions on 1000 random 3 s segments (std<0.08, |mean−1|<0.2): **0 mismatches** (131 still)

**RESULT: PASS** (features≤1e-4: True, decisions identical: True, host_test: True)


## 11. Caveats

- The recall target (operating point) is still to be chosen (§6.5); the exported threshold is the 95 % point and the stillness parameters are long-lie placeholders.
- SmartFallMM falls are manually cropped and short: only a subset is confirm-eligible, and the post-fall segment length is determined by the crop, not by the person; WEDA falls were done on a mattress by young participants.
- ADL false-alarm rates are per trial of very different lengths (WEDA/SFMM trials from seconds to minutes) — compare with the per-hour columns.
- Subject-level CIs are wide for per-fall-type and young/old splits (few subjects); elderly data come from ADL only (WEDA 11, SmartFallMM old folder 24 subjects), so elderly *fall* detection is untested.
- SmartFallMM is © SmartFall Group, Texas State University, all rights reserved, credit required; only derived model weights/aggregate results are in git, no raw or resampled data.

## 12. Reproduce

```
cd ml/fall-detection-wrist && python3 -m venv .venv && .venv/bin/pip install numpy scipy pandas scikit-learn
.venv/bin/python -I src/data_card.py && .venv/bin/python -I src/preprocess.py && .venv/bin/python -I src/exclusion_log.py
.venv/bin/python -I src/test_preprocess.py && .venv/bin/python -I src/test_features.py && .venv/bin/python -I src/rate_leak_check.py
.venv/bin/python -I src/build_dataset.py
for m in 'lr 26' 'lr 52' 'tree 26' 'mlp 26'; do set -- $m; for g in spec trig ext; do .venv/bin/python -I src/eval_nested.py --model $1 --fs $2 --grid $g; done; done   # resumable per fold
.venv/bin/python -I src/eval_baseline.py && .venv/bin/python -I src/final_model.py && .venv/bin/python -I src/export_final.py
.venv/bin/python -I src/parity.py && .venv/bin/python -I src/flash_size.py && .venv/bin/python -I src/make_report.py
```

## Appendix A — superseded: confirm-stage results on the train pool (nested, subject-grouped 5-fold CV)

*Written before the decision to move stillness out of fall detection; kept for the record. The trigger-only operating curve in §4 is the current analysis.*

Outer GroupKFold(5) by subject, inner GroupKFold(3) on the outer-train subjects tunes (probability threshold on a 0.001 grid, stillness std). Metrics: **trigger-only** = trial detected iff any window has p ≥ thr (all fall trials, N = 1041); **with confirm** = detected iff a window with p ≥ thr is followed by 3 s of stillness, reported only on the **confirm-eligible** falls (N = 696) with the coverage stated next to every number. An ADL false alarm = any confirmed event in the trial (trigger-only column: any trigger). ADL time = 7.52 h; 'alarmed ADL trials / h' = alarmed trials ÷ ADL hours (reference convention), 'events / h' merges alarms < 5 s apart. 95 % CIs are percentile bootstrap over subjects (2000 resamples). The ADL false-alarm rate is per *trial* (any window of a multi-minute trial may fire); windows not followed by 3 s of recording are never confirmed (strict); the conservative variant (counted as confirmed) is `adl_far_confirm_cons` in the summary CSVs (LR@26, mode B: 23.5% [19.6, 27.5]).

### A.1 Why the stillness rule cannot work as a fall-recall criterion here

Share of confirm-eligible falls that have *at least one* impact-containing window whose following 3 s is still (std below the column value and |mean−1| < 0.2), irrespective of any classifier, versus the share of ADL segments that contain a still window:

| dataset | eligible falls | with a still post-impact segment at std < 0.05 | < 0.065 | < 0.08 | < 0.12 | < 0.20 | < 0.30 |
|---|---|---|---|---|---|---|---|
| WEDA | 345 | 57.4% | 65.5% | 68.4% | 80.9% | 94.8% | 98.0% |
| SFMM | 351 | 7.4% | 10.8% | 14.0% | 26.2% | 57.3% | 81.8% |
| ADL segments with ≥ 1 still evaluable window (any probability) | 2445 | 18.6% | 23.3% | 28.1% | 43.1% | 65.0% | 80.0% |

### A.2 (A) The rule as specified: std ∈ {0.05, 0.065, 0.08}, tune to ≥ 95 % recall at lowest ADL false alarms

Target unreachable in every fold (chosen thresholds ≈ 0, i.e. 'any still window'). These are the pre-registered results:

| model | fall recall, trigger-only (all falls) | fall recall, with confirm (eligible falls; coverage) | ADL false-alarm rate / trial, trigger-only | ADL false-alarm rate / trial, confirmed | confirmed alarmed ADL trials / h | confirmed alarm events / h | confirmed ADL FAR young | confirmed ADL FAR old |
|---|---|---|---|---|---|---|---|---|
| LR @ 26 Hz (primary) | 100.0% [100.0, 100.0] (1041/1041) | 49.9% [37.4, 62.2] (347/696); coverage 696/1041 = 67% | 99.0% [98.2, 99.7] (2370/2393) | 28.0% [24.5, 31.7] (671/2393) | 89.21 [79.95, 98.76] | 96.79 [86.24, 108.20] | 29.8% [25.6, 34.7] (451/1511) | 24.9% [19.8, 31.5] (220/882) |
| LR @ 52 Hz | 100.0% [100.0, 100.0] (1041/1041) | 49.1% [36.7, 61.6] (341/695); coverage 695/1041 = 67% | 99.1% [98.2, 99.8] (2371/2393) | 26.7% [23.2, 30.2] (638/2393) | 84.90 [75.91, 94.33] | 92.08 [81.69, 102.83] | 28.5% [24.4, 33.2] (431/1511) | 23.5% [18.3, 29.6] (207/882) |
| Decision tree (depth 5) @ 26 Hz | 100.0% [100.0, 100.0] (1041/1041) | 50.0% [37.7, 62.2] (348/696); coverage 696/1041 = 67% | 100.0% [100.0, 100.0] (2393/2393) | 28.7% [25.3, 32.4] (687/2393) | 91.34 [82.76, 100.68] | 98.92 [88.75, 109.93] | 30.0% [25.9, 34.9] (454/1511) | 26.4% [21.3, 32.6] (233/882) |
| MLP (1×16) @ 26 Hz | 100.0% [100.0, 100.0] (1041/1041) | 50.0% [37.7, 62.2] (348/696); coverage 696/1041 = 67% | 100.0% [100.0, 100.0] (2393/2393) | 28.7% [25.3, 32.4] (687/2393) | 91.34 [82.76, 100.68] | 98.92 [88.75, 109.93] | 30.0% [25.9, 34.9] (454/1511) | 26.4% [21.3, 32.6] (233/882) |
| **Baseline**: SisFall-waist LR, unchanged, 52 Hz (thr 0.93, std 0.05) | 79.1% [72.9, 85.6] (823/1041) | 27.9% [16.0, 40.8] (194/695); coverage 695/1041 = 67% | 31.6% [28.4, 35.1] (757/2393) | 1.5% [0.6, 2.6] (35/2393) | 4.66 [2.04, 7.88] | 4.79 [2.04, 8.25] | 2.3% [1.0, 4.0] (34/1511) | 0.1% [0.0, 0.4] (1/882) |

Chosen parameters per outer fold, LR@26:

| outer fold | test subjects | chosen thr | chosen std | recall on inner tuning data | ADL FAR on tuning data | target reached |
|---|---|---|---|---|---|---|
| 0 | 16 | 0.000 | 0.080 | 51.6% | 28.5% | **no** |
| 1 | 16 | 0.000 | 0.080 | 49.9% | 28.3% | **no** |
| 2 | 16 | 0.004 | 0.080 | 49.9% | 26.9% | **no** |
| 3 | 17 | 0.002 | 0.080 | 49.6% | 28.8% | **no** |
| 4 | 16 | 0.002 | 0.080 | 49.1% | 28.7% | **no** |

### A.3 (B) Threshold tuned without the confirm stage (≥ 95 % trigger-only recall on all falls at the lowest trigger-only ADL false-alarm rate); confirm applied afterwards with std 0.08

This is the only row set in which the probability threshold is meaningful. The 'with confirm' columns show what the (untuned) stillness stage then does: it removes most ADL false alarms and most falls.

| model | fall recall, trigger-only (all falls) | fall recall, with confirm (eligible falls; coverage) | ADL false-alarm rate / trial, trigger-only | ADL false-alarm rate / trial, confirmed | confirmed alarmed ADL trials / h | confirmed alarm events / h | confirmed ADL FAR young | confirmed ADL FAR old |
|---|---|---|---|---|---|---|---|---|
| LR @ 26 Hz (primary) | 95.0% [91.8, 97.7] (989/1041) | 40.2% [26.9, 53.8] (280/696); coverage 696/1041 = 67% | 34.2% [29.9, 38.5] (818/2393) | 3.6% [2.2, 5.4] (87/2393) | 11.57 [7.16, 16.44] | 11.70 [7.20, 16.82] | 5.4% [3.3, 8.1] (81/1511) | 0.7% [0.1, 1.3] (6/882) |
| LR @ 52 Hz | 95.6% [92.9, 97.8] (995/1041) | 39.6% [26.1, 53.2] (275/695); coverage 695/1041 = 67% | 36.5% [32.4, 41.0] (873/2393) | 3.6% [2.1, 5.3] (85/2393) | 11.31 [7.00, 16.14] | 11.44 [7.03, 16.44] | 5.2% [3.1, 7.9] (79/1511) | 0.7% [0.2, 1.2] (6/882) |
| Decision tree (depth 5) @ 26 Hz | 94.6% [91.4, 97.4] (985/1041) | 40.4% [27.2, 53.7] (281/696); coverage 696/1041 = 67% | 30.2% [26.5, 34.3] (722/2393) | 2.9% [1.7, 4.5] (70/2393) | 9.31 [5.40, 13.99] | 9.44 [5.47, 14.36] | 4.4% [2.5, 6.7] (66/1511) | 0.5% [0.1, 0.9] (4/882) |
| MLP (1×16) @ 26 Hz | 95.3% [92.2, 97.8] (992/1041) | 39.7% [26.5, 53.1] (276/696); coverage 696/1041 = 67% | 27.4% [23.5, 31.6] (655/2393) | 2.6% [1.5, 4.2] (63/2393) | 8.38 [4.79, 12.81] | 8.51 [4.82, 13.15] | 4.0% [2.2, 6.4] (60/1511) | 0.3% [0.0, 0.7] (3/882) |
| **Baseline**: SisFall-waist LR, unchanged, 52 Hz (thr 0.93, std 0.05) | 79.1% [72.9, 85.6] (823/1041) | 27.9% [16.0, 40.8] (194/695); coverage 695/1041 = 67% | 31.6% [28.4, 35.1] (757/2393) | 1.5% [0.6, 2.6] (35/2393) | 4.66 [2.04, 7.88] | 4.79 [2.04, 8.25] | 2.3% [1.0, 4.0] (34/1511) | 0.1% [0.0, 0.4] (1/882) |

Per dataset (LR@26 and baseline; note the different confirm coverage):

| model | dataset | recall trigger-only | recall with confirm (eligible) | coverage of confirm | ADL FAR confirmed |
|---|---|---|---|---|---|
| LR @ 26 Hz (primary) | WEDA | 100.0% [100.0, 100.0] (350/350) | 69.3% [53.2, 84.1] (239/345) | 345/350 | 9.7% [5.7, 13.6] (60/619) |
| LR @ 26 Hz (primary) | SFMM | 92.5% [87.9, 96.1] (639/691) | 11.7% [5.7, 19.6] (41/351) | 351/691 | 1.5% [0.7, 2.6] (27/1774) |
| Baseline (SisFall-waist) | WEDA | 98.3% [96.7, 99.7] (344/350) | 52.5% [33.6, 70.7] (181/345) | 345/350 | 4.0% [1.3, 7.5] (25/619) |
| Baseline (SisFall-waist) | SFMM | 69.3% [62.5, 76.2] (479/691) | 3.7% [0.7, 8.2] (13/350) | 350/691 | 0.6% [0.2, 1.1] (10/1774) |

Per fall type (mode B):

| fall type | trials | LR@26 recall trigger-only | LR@26 recall with confirm (eligible/trials) | baseline recall trigger-only | baseline with confirm |
|---|---|---|---|---|---|
| F01 fwd fall walking (slip) | 42 | 100.0% [100.0, 100.0] (42/42) | 81.0% [66.7, 94.9] (34/42) | 100.0% [100.0, 100.0] (42/42) | 61.9% [41.7, 81.8] (26/42) |
| F02 lateral fall walking (slip) | 42 | 100.0% [100.0, 100.0] (42/42) | 66.7% [45.2, 87.2] (28/42) | 97.6% [92.3, 100.0] (41/42) | 52.4% [28.6, 75.8] (22/42) |
| F03 back fall walking (slip) | 42 | 100.0% [100.0, 100.0] (42/42) | 59.5% [38.1, 79.2] (25/42) | 100.0% [100.0, 100.0] (42/42) | 52.4% [29.6, 75.0] (22/42) |
| F04 fwd fall walking (trip) | 42 | 100.0% [100.0, 100.0] (42/42) | 75.6% [53.7, 93.3] (31/41) | 100.0% [100.0, 100.0] (42/42) | 63.4% [38.5, 84.4] (26/41) |
| F05 back fall trying to sit | 42 | 100.0% [100.0, 100.0] (42/42) | 51.2% [31.6, 69.5] (21/41) | 97.6% [92.1, 100.0] (41/42) | 43.9% [26.7, 60.6] (18/41) |
| F06 fwd fall sitting (faint) | 42 | 100.0% [100.0, 100.0] (42/42) | 73.2% [48.1, 93.5] (30/41) | 97.6% [92.3, 100.0] (41/42) | 58.5% [36.4, 79.5] (24/41) |
| F07 back fall sitting (faint) | 42 | 100.0% [100.0, 100.0] (42/42) | 73.8% [51.5, 93.0] (31/42) | 100.0% [100.0, 100.0] (42/42) | 59.5% [33.3, 84.6] (25/42) |
| F08 lateral fall sitting (faint) | 56 | 100.0% [100.0, 100.0] (56/56) | 72.2% [53.6, 88.1] (39/54) | 94.6% [86.5, 100.0] (53/56) | 33.3% [12.0, 57.1] (18/54) |
| A10 backfall | 145 | 94.5% [87.2, 99.4] (137/145) | 14.5% [6.2, 24.7] (12/83) | 80.7% [71.2, 88.6] (117/145) | 3.6% [0.0, 7.8] (3/84) |
| A11 frontfall | 135 | 90.4% [83.9, 95.7] (122/135) | 11.1% [1.4, 25.4] (7/63) | 63.0% [53.2, 72.6] (85/135) | 3.2% [0.0, 8.6] (2/63) |
| A12 leftfall | 138 | 90.6% [83.7, 96.2] (125/138) | 11.2% [2.5, 22.9] (9/80) | 60.1% [48.0, 72.9] (83/138) | 3.8% [0.0, 9.9] (3/79) |
| A13 rightfall | 138 | 95.7% [92.4, 98.6] (132/138) | 13.1% [4.3, 24.5] (8/61) | 83.3% [74.3, 91.7] (115/138) | 3.3% [0.0, 9.2] (2/61) |
| A14 rotatefall | 135 | 91.1% [83.1, 97.2] (123/135) | 7.8% [2.1, 15.0] (5/64) | 58.5% [46.9, 70.6] (79/135) | 4.8% [0.0, 11.6] (3/63) |

Chosen parameters per outer fold, LR@26 (mode B):

| outer fold | test subjects | chosen thr | chosen std | recall on inner tuning data | ADL FAR on tuning data | target reached |
|---|---|---|---|---|---|---|
| 0 | 16 | 0.682 | 0.080 | 95.2% | 33.1% | yes |
| 1 | 16 | 0.656 | 0.080 | 95.1% | 34.2% | yes |
| 2 | 16 | 0.603 | 0.080 | 95.0% | 39.0% | yes |
| 3 | 17 | 0.684 | 0.080 | 95.1% | 31.7% | yes |
| 4 | 16 | 0.643 | 0.080 | 95.2% | 34.5% | yes |

### A.4 (C) Sensitivity: wider stillness grid std ∈ {0.05, 0.065, 0.08, 0.12, 0.2, 0.3}

Recall with confirm gets closer to the target only by accepting stillness thresholds so loose that the confirm stage no longer filters ADL (false-alarm rates near 80 %).

| model | fall recall, trigger-only (all falls) | fall recall, with confirm (eligible falls; coverage) | ADL false-alarm rate / trial, trigger-only | ADL false-alarm rate / trial, confirmed | confirmed alarmed ADL trials / h | confirmed alarm events / h | confirmed ADL FAR young | confirmed ADL FAR old |
|---|---|---|---|---|---|---|---|---|
| LR @ 26 Hz (primary) | 100.0% [100.0, 100.0] (1041/1041) | 93.4% [89.6, 96.9] (650/696); coverage 696/1041 = 67% | 97.7% [96.4, 98.9] (2339/2393) | 78.6% [75.9, 81.4] (1882/2393) | 250.22 [236.52, 263.25] | 259.66 [246.80, 271.80] | 79.9% [76.6, 83.0] (1207/1511) | 76.5% [71.4, 81.5] (675/882) |
| LR @ 52 Hz | 100.0% [100.0, 100.0] (1041/1041) | 91.7% [87.0, 95.8] (637/695); coverage 695/1041 = 67% | 100.0% [100.0, 100.0] (2393/2393) | 79.4% [76.7, 82.1] (1900/2393) | 252.83 [237.96, 266.54] | 262.15 [248.39, 275.79] | 80.7% [77.3, 84.2] (1220/1511) | 77.1% [72.8, 81.4] (680/882) |
| Decision tree (depth 5) @ 26 Hz | 100.0% [100.0, 100.0] (1041/1041) | 93.7% [90.0, 97.1] (652/696); coverage 696/1041 = 67% | 100.0% [100.0, 100.0] (2393/2393) | 81.6% [79.1, 84.1] (1953/2393) | 259.66 [245.08, 273.57] | 268.57 [255.11, 281.94] | 82.5% [79.1, 85.7] (1246/1511) | 80.2% [76.1, 84.0] (707/882) |
| MLP (1×16) @ 26 Hz | 100.0% [100.0, 100.0] (1041/1041) | 93.7% [90.0, 97.1] (652/696); coverage 696/1041 = 67% | 100.0% [100.0, 100.0] (2393/2393) | 81.6% [79.1, 84.1] (1953/2393) | 259.66 [245.08, 273.57] | 268.57 [255.11, 281.94] | 82.5% [79.1, 85.7] (1246/1511) | 80.2% [76.1, 84.0] (707/882) |
| **Baseline**: SisFall-waist LR, unchanged, 52 Hz (thr 0.93, std 0.05) | 79.1% [72.9, 85.6] (823/1041) | 27.9% [16.0, 40.8] (194/695); coverage 695/1041 = 67% | 31.6% [28.4, 35.1] (757/2393) | 1.5% [0.6, 2.6] (35/2393) | 4.66 [2.04, 7.88] | 4.79 [2.04, 8.25] | 2.3% [1.0, 4.0] (34/1511) | 0.1% [0.0, 0.4] (1/882) |

