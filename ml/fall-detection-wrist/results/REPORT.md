# Wrist fall detection — retraining report (`wrist-retrain`)

Same 9 features, same logistic-regression pipeline as the SisFall-waist model, retrained on WEDA-FALL + SmartFallMM (Meta_wrist) at 26 Hz. All numbers below were measured by the scripts in `src/` (commands at the end); tables are generated from `results/*.csv`, not typed.

## 0. Read this first — four things that change how to read the results

1. **The specified stillness-confirm stage cannot reach the ≥95 % fall-recall target on wrist data.** With std ∈ {0.05, 0.065, 0.08} and |mean−1| < 0.2 over 3 s, even at probability threshold 0 only about half of the confirm-eligible falls have *any* still post-impact segment (table in §4.1); meanwhile a large share of ADL segments contain a still window anyway. Every model — LR, tree, MLP, at 26 and 52 Hz — hits the same ceiling, so this is a property of the rule on wrist data (SmartFallMM trials are cropped tightly around the fall and wrists keep moving), not of the classifier. The pre-registered nested procedure therefore returns degenerate thresholds (≈0.00, §4.2). I did **not** silently change the rule: results are shown for (A) the rule as specified, (B) the same tuning with the confirm stage left out of tuning (trigger-only ≥95 % recall at lowest ADL false-alarm rate) and (C) a wider std grid as sensitivity. **A decision is needed on how the deployed operating point should be defined.**
2. **BITS held-out test has NOT been run.** Rule 5 (timestamp span vs N/20 within 10 %) as written drops 900 of the 912 files that pass rule 4 (322 of 328 falls), because BITS timestamps are rounded to 3 significant digits and the check is undecidable for all but a handful of files. The single permitted BITS run is reserved until that rule and the operating point (item 1) are settled; running it on 12 files would waste it.
3. **BITS is not a geriatric cohort**: the dataset paper (Nandi et al., Data in Brief 52, 2024, read by a sub-agent from PMC10709028, not independently re-verified) lists 41 volunteers aged 20–47 (mean ≈ 27.9). The folder name `bits_geriatric` is misleading; the held-out set tests cross-dataset/cross-device generalisation, not elderly generalisation. The paper's prose also describes `acc` as the accelerometer and `acg` as linear acceleration — the data show the reverse, and the data were used.
4. **The exported header is provisional** (`include/fall_model.h`): the weights are final; the probability threshold (mode `trig`, 0.671) and the stillness parameters are placeholders until item 1 is decided (`src/export_final.py --op/--thr/--std` regenerates everything).

## 1. Data card summary (full card: `DATA_CARD.md`)

| dataset | role | rate (measured) | units → g | fall trials used | fall trials confirm-eligible | ADL segments used | notes |
|---|---|---|---|---|---|---|---|
| WEDA-FALL | train pool | falls 39.8 Hz / ADL 49.7 Hz (median effective) | ÷9.80665 | 350 | 345 | 619 | Fitbit Sense wrist; falls young only (U01–U14), elderly ADL-only; fall files ≈39.8 Hz vs ADL ≈49.7 Hz effective, burst-stamped → per-trial linear time axis |
| SmartFallMM | train pool | 1983 segments ≈50 Hz, 530 ≈25 Hz, 4 other | already g | 691 | 351 | 1826 | SmartFallMM Meta_wrist (© SmartFall Group, Texas State Univ.; credit required, not redistributed); 50 Hz and 25 Hz sessions; ISO clock; 32 non-g ADL files dropped; split at gaps > 1 s |
| BITS | held-out (not run) | unverifiable (nominal 20 Hz) | ÷9.80665 (`acg`) | 328 files | – | 656 files | rule 4 drops 72 files (0 falls); rule 5 undecided (§0.2) |

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

## 4. Results on the train pool (WEDA + SmartFallMM) — nested, subject-grouped 5-fold CV

Outer GroupKFold(5) by subject, inner GroupKFold(3) on the outer-train subjects tunes (probability threshold on a 0.001 grid, stillness std). Metrics: **trigger-only** = trial detected iff any window has p ≥ thr (all fall trials, N = 1041); **with confirm** = detected iff a window with p ≥ thr is followed by 3 s of stillness, reported only on the **confirm-eligible** falls (N = 696) with the coverage stated next to every number. An ADL false alarm = any confirmed event in the trial (trigger-only column: any trigger). ADL time = 7.52 h; 'alarmed ADL trials / h' = alarmed trials ÷ ADL hours (reference convention), 'events / h' merges alarms < 5 s apart. 95 % CIs are percentile bootstrap over subjects (2000 resamples). The ADL false-alarm rate is per *trial* (any window of a multi-minute trial may fire); windows not followed by 3 s of recording are never confirmed (strict); the conservative variant (counted as confirmed) is `adl_far_confirm_cons` in the summary CSVs (LR@26, mode B: 23.5% [19.6, 27.5]).

### 4.1 Why the stillness rule cannot work here

Share of confirm-eligible falls that have *at least one* impact-containing window whose following 3 s is still (std below the column value and |mean−1| < 0.2), irrespective of any classifier, versus the share of ADL segments that contain a still window:

| dataset | eligible falls | with a still post-impact segment at std < 0.05 | < 0.065 | < 0.08 | < 0.12 | < 0.20 | < 0.30 |
|---|---|---|---|---|---|---|---|
| WEDA | 345 | 57.4% | 65.5% | 68.4% | 80.9% | 94.8% | 98.0% |
| SFMM | 351 | 7.4% | 10.8% | 14.0% | 26.2% | 57.3% | 81.8% |
| ADL segments with ≥ 1 still evaluable window (any probability) | 2445 | 18.6% | 23.3% | 28.1% | 43.1% | 65.0% | 80.0% |

### 4.2 (A) The rule as specified: std ∈ {0.05, 0.065, 0.08}, tune to ≥ 95 % recall at lowest ADL false alarms

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

### 4.3 (B) Threshold tuned without the confirm stage (≥ 95 % trigger-only recall on all falls at the lowest trigger-only ADL false-alarm rate); confirm applied afterwards with std 0.08

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

### 4.4 (C) Sensitivity: wider stillness grid std ∈ {0.05, 0.065, 0.08, 0.12, 0.2, 0.3}

Recall with confirm gets closer to the target only by accepting stillness thresholds so loose that the confirm stage no longer filters ADL (false-alarm rates near 80 %).

| model | fall recall, trigger-only (all falls) | fall recall, with confirm (eligible falls; coverage) | ADL false-alarm rate / trial, trigger-only | ADL false-alarm rate / trial, confirmed | confirmed alarmed ADL trials / h | confirmed alarm events / h | confirmed ADL FAR young | confirmed ADL FAR old |
|---|---|---|---|---|---|---|---|---|
| LR @ 26 Hz (primary) | 100.0% [100.0, 100.0] (1041/1041) | 93.4% [89.6, 96.9] (650/696); coverage 696/1041 = 67% | 97.7% [96.4, 98.9] (2339/2393) | 78.6% [75.9, 81.4] (1882/2393) | 250.22 [236.52, 263.25] | 259.66 [246.80, 271.80] | 79.9% [76.6, 83.0] (1207/1511) | 76.5% [71.4, 81.5] (675/882) |
| LR @ 52 Hz | 100.0% [100.0, 100.0] (1041/1041) | 91.7% [87.0, 95.8] (637/695); coverage 695/1041 = 67% | 100.0% [100.0, 100.0] (2393/2393) | 79.4% [76.7, 82.1] (1900/2393) | 252.83 [237.96, 266.54] | 262.15 [248.39, 275.79] | 80.7% [77.3, 84.2] (1220/1511) | 77.1% [72.8, 81.4] (680/882) |
| Decision tree (depth 5) @ 26 Hz | 100.0% [100.0, 100.0] (1041/1041) | 93.7% [90.0, 97.1] (652/696); coverage 696/1041 = 67% | 100.0% [100.0, 100.0] (2393/2393) | 81.6% [79.1, 84.1] (1953/2393) | 259.66 [245.08, 273.57] | 268.57 [255.11, 281.94] | 82.5% [79.1, 85.7] (1246/1511) | 80.2% [76.1, 84.0] (707/882) |
| MLP (1×16) @ 26 Hz | 100.0% [100.0, 100.0] (1041/1041) | 93.7% [90.0, 97.1] (652/696); coverage 696/1041 = 67% | 100.0% [100.0, 100.0] (2393/2393) | 81.6% [79.1, 84.1] (1953/2393) | 259.66 [245.08, 273.57] | 268.57 [255.11, 281.94] | 82.5% [79.1, 85.7] (1246/1511) | 80.2% [76.1, 84.0] (707/882) |
| **Baseline**: SisFall-waist LR, unchanged, 52 Hz (thr 0.93, std 0.05) | 79.1% [72.9, 85.6] (823/1041) | 27.9% [16.0, 40.8] (194/695); coverage 695/1041 = 67% | 31.6% [28.4, 35.1] (757/2393) | 1.5% [0.6, 2.6] (35/2393) | 4.66 [2.04, 7.88] | 4.79 [2.04, 8.25] | 2.3% [1.0, 4.0] (34/1511) | 0.1% [0.0, 0.4] (1/882) |

## 5. Model comparison (offline; LR is the deploy candidate)

| model | trigger recall (mode B) | ADL trigger-only FAR | recall with confirm (coverage) | parameters | classifier flash, bytes (measured) | + shared feature code | total flash |
|---|---|---|---|---|---|---|---|
| LR @ 26 Hz | 95.0% [91.8, 97.7] (989/1041) | 34.2% [29.9, 38.5] (818/2393) | 40.2% [26.9, 53.8] (280/696); cov. 696/1041 | 28 (28 floats = 112 B) | 324 | 720 | 1044 |
| Decision tree (depth ≤ 5) @ 26 Hz | 94.6% [91.4, 97.4] (985/1041) | 30.2% [26.5, 34.3] (722/2393) | 40.4% [27.2, 53.7] (281/696); cov. 696/1041 | 61 (tree nodes) | 816 | 720 | 1536 |
| MLP (1×16) @ 26 Hz | 95.3% [92.2, 97.8] (992/1041) | 27.4% [23.5, 31.6] (655/2393) | 39.7% [26.5, 53.1] (276/696); cov. 696/1041 | 195 (floats) | 944 | 720 | 1664 |
| LR @ 52 Hz | 95.6% [92.9, 97.8] (995/1041) | 36.5% [32.4, 41.0] (873/2393) | 39.6% [26.1, 53.2] (275/695); cov. 695/1041 | 28 | same code as LR@26 | – | – |

Flash = `arm-none-eabi-gcc -Os -mcpu=cortex-m4 -mfloat-abi=hard` object text+rodata for the final pool-trained model (tree: depth 5, 31 leaves; MLP: 9→16→1 ReLU/sigmoid), libm excluded. Subject-bootstrap CIs of the three models overlap on every metric (no paired test was run); LR is the cheapest in flash and the only one the firmware already supports.

## 6. Waist → wrist domain gap

| model | recall trigger-only | ADL trigger-only FAR | recall with confirm (eligible; coverage) | ADL confirmed FAR |
|---|---|---|---|---|
| SisFall-waist LR, unchanged, 52 Hz (thr 0.93) | 79.1% [72.9, 85.6] (823/1041) | 31.6% [28.4, 35.1] (757/2393) | 27.9% [16.0, 40.8] (194/695); 695/1041 | 1.5% [0.6, 2.6] (35/2393) |
| Wrist LR @ 52 Hz (mode B) | 95.6% [92.9, 97.8] (995/1041) | 36.5% [32.4, 41.0] (873/2393) | 39.6% [26.1, 53.2] (275/695); 695/1041 | 3.6% [2.1, 5.3] (85/2393) |
| Wrist LR @ 26 Hz (mode B) | 95.0% [91.8, 97.7] (989/1041) | 34.2% [29.9, 38.5] (818/2393) | 40.2% [26.9, 53.8] (280/696); 696/1041 | 3.6% [2.2, 5.4] (87/2393) |

The waist model transfers poorly: at its own fixed threshold it detects the minority of wrist falls while still triggering on about a third of ADL trials. The comparison is not threshold-matched (the baseline is unchanged by construction); the wrist LR at its tuned threshold reaches 95 % trigger-only recall at a similar ADL trigger-only false-alarm rate.

## 7. BITS held-out test — NOT RUN

- Preprocessed (`acg`, g, 20→26 Hz and 20→52 Hz) and filtered by the pre-specified rules; no model has seen it.
- Rule 4 (rest |a| of `acg` within 1 ± 0.1 g): 72 of 984 files dropped (0 falls, 72 ADL) → 912 files remain (328 falls, 584 ADL).
- Rule 5 (|timestamp span − N/20| > 10 % ⇒ drop): would drop 900 of 912 (falls 322 of 328). Timestamps keep 3 significant digits, so the span has a quantisation error larger than 10 % of the expected duration for all but 16 of the 912 files; of those 16, 3 agree within 10 %. The rule therefore removes the data rather than testing the sampling rate.
- Index → activity: not documented in the paper's text; per-index energy follows the paper's table (jogging/jumping highest, lying lowest, seated falls gentlest), so per-fall-type recall can be computed with an *inferred* mapping once the run is released (`DATA_CARD.md` §6).
- Caveat that will accompany the result: 20 Hz is assumed by sample order; the HR-block cross-check (median 20.2 samples per HR row, IQR 7–51) is consistent at the median only.

## 8. Export and C parity

`include/fall_model.h` and `include/test_windows.h` (12 real train-pool windows + 6 stillness segments, taken from WEDA-FALL only because SmartFallMM is all-rights-reserved, with expected features, probabilities and decisions; every float literal is positional with a decimal point before `f`). `firmware/fall_imu/include/` was not modified. Header fixes vs the reference exporter: all rate macros incl. TILT_PRE/POST/FALLBACK, POST_STD and `MODEL_IMU_ODR_ENUM = LSM6DSXX_DATA_RATE_26HZ` (imu.c already selects 26 Hz from `SAMPLE_RATE_HZ`); stillness thresholds are emitted as the macros `FALL_STILL_STD_THR / FALL_STILL_MEAN_TOL` — the reference header's `static const STILL_STD_THR` is never read by `fall_features.h`, so a tuned std would have been ignored on the device.


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


## 9. Caveats

- Operating point and stillness stage unresolved (§0.1); the exported thresholds are placeholders.
- SmartFallMM falls are manually cropped and short: only a subset is confirm-eligible, and the post-fall segment length is determined by the crop, not by the person; WEDA falls were done on a mattress by young participants.
- ADL false-alarm rates are per trial of very different lengths (WEDA/SFMM trials from seconds to minutes) — compare with the per-hour columns.
- Subject-level CIs are wide for per-fall-type and young/old splits (few subjects); elderly data come from ADL only (WEDA 11, SmartFallMM old folder 24 subjects), so elderly *fall* detection is untested.
- SmartFallMM is © SmartFall Group, Texas State University, all rights reserved, credit required; only derived model weights/aggregate results are in git, no raw or resampled data.

## 10. Reproduce

```
cd ml/fall-detection-wrist && python3 -m venv .venv && .venv/bin/pip install numpy scipy pandas scikit-learn
.venv/bin/python -I src/data_card.py && .venv/bin/python -I src/preprocess.py && .venv/bin/python -I src/exclusion_log.py
.venv/bin/python -I src/test_preprocess.py && .venv/bin/python -I src/test_features.py && .venv/bin/python -I src/rate_leak_check.py
.venv/bin/python -I src/build_dataset.py
for m in 'lr 26' 'lr 52' 'tree 26' 'mlp 26'; do set -- $m; for g in spec trig ext; do .venv/bin/python -I src/eval_nested.py --model $1 --fs $2 --grid $g; done; done   # resumable per fold
.venv/bin/python -I src/eval_baseline.py && .venv/bin/python -I src/final_model.py && .venv/bin/python -I src/export_final.py
.venv/bin/python -I src/parity.py && .venv/bin/python -I src/flash_size.py && .venv/bin/python -I src/make_report.py
```

