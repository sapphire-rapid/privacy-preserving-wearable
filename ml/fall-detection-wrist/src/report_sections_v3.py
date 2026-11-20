# exec'd inside make_report.main(): A, R3, RES, os, pd, np, json, F, pickle are in scope.
fo = pd.read_csv(os.path.join(RES, "curve_pool26_acc9_lr_folds.csv"))
A("## 4. Trigger-only operating curve — current accelerometer-only LR @ 26 Hz (9 features)\n")
A("Stillness plays no role. Nested subject-grouped CV (outer GroupKFold(5), inner GroupKFold(3)); in every outer fold the threshold (0.001 grid) is the one with **≥ target recall on all falls** and the lowest ADL false-alarm rate "
  "on the out-of-fold probabilities of the outer-train subjects, and the outer-test subjects are scored once. **One pooled threshold per target is applied to both datasets** — the per-dataset rows are that same operating point evaluated on each dataset. "
  "A trial is detected iff any 2 s window (0.5 s stride) has p ≥ thr; an ADL false alarm is any such window in an ADL trial (so the rate is per *trial*, and trials are minutes long). "
  "'Alarmed ADL trials / h' = alarmed trials ÷ ADL hours; 'alarm events / h' merges windows < 5 s apart. 95 % CIs: percentile bootstrap over subjects, 2000 resamples. "
  f"Pool: {int(R3.summ('pool26','acc9_lr').query('metric==\"fall_recall_trigger\"').n_den.iloc[0])} fall trials; ADL time {R3.summ('pool26','acc9_lr').query('metric==\"fa_per_hour_trigger_trials\"').n_den.iloc[0]:.2f} h.\n")
A(R3.curve_table() + "\n")
A("Thresholds chosen per outer fold (acc9 LR): " + "; ".join(f"{int(t*100)} %: " + ", ".join(f"{v:.2f}" for v in fo[f'thr@{int(t*100)}']) for t in R3.TARGETS) + ".\n")
A("### 4.1 Which ADL activities cause the false alarms (top 5 per dataset)\n")
A("At the 90 % and 95 % targets (all four targets: `results/ADL_BREAKDOWN.md`). An activity's false-alarm rate is the share of its trials that raised ≥ 1 alarm.\n")
A(R3.breakdown_md("pool26", "acc9_lr") + "\n")
A("## 5. Post-impact stillness — a finding, not a detection criterion\n")
A("Stillness is no longer part of fall detection; it becomes the long-lie (U3 severity) stage, to be validated on your own recordings. There is **no recall target** for it. "
  "What the two public datasets say about how soon a wrist is still after a fall (the long-lie placeholder in the header stays std < 0.08, |mean − 1| < 0.2, 3 s):\n")
A(R3.stillness_md() + "\n")
A("Reading it: WEDA falls (mattress, young adults) settle almost immediately (≈ 90–99 % reach a still 3 s within 3–5 s after the peak); SmartFallMM falls rarely do (22–31 %), consistent with its hand-cropped trials ending as the participant gets up. "
  "The denominators shrink quickly with the horizon (WEDA 2 and SmartFallMM 11 falls have ≥ 13 s of data after the peak), and trials that were recorded for longer are the ones where the person stayed down — so the 10 s row, in particular, is not usable evidence and the others are optimistic for the lying-still case.\n")
A("## 6. Gyro feature set (v3) — Python only\n")
A("**Features** (same 2 s / 0.5 s windows, gyro merged onto the accelerometer grid and converted to dps, orientation-invariant; 9 accelerometer features unchanged, 15 in total): "
  "`gyro_max`, `gyro_mean`, `gyro_std` (of |ω|), `gyro_rot_win` (Σ|ω|·dt over the window, deg), `gyro_rot_peak` (the same within ±0.5 s of the |a| peak), `gyro_peak_offset_s` (signed time of the |ω| peak minus the |a| peak). "
  "Vectorised == scalar reference and rotation invariance are unit-tested (`src/test_gyro_features.py`). Training windows are time-stretched together with the gyro (0.95/1.00/1.05) in training folds only.\n")
A("**Populations** (data card §7: the SmartFallMM Meta_wrist gyro is a ±125 dps part and clips in ~97 % of its trials, WEDA reaches ≈ 2000 dps — pooling raw gyro features would encode the dataset):\n")
A("- **v3W — WEDA only, native range**: 350 falls, 619 ADL trials, 25 subjects. This is the realistic-sensor case.\n"
  "- **v3P — pooled, harmonised**: WEDA clipped per axis to ±125 dps before resampling + SmartFallMM young/old trials whose gyro covers the accel segment (falls 507 of 691, ADL 767 of 1049 young segments, 188 of 777 old segments; the old wrist gyro is a separate `meta_wrist` folder but was cropped separately, so only a minority is usable and its clock agreement is assumed, not verified): "
  "857 falls, 1,574 ADL segments, 74 subjects. This is a lower bound for what the gyro can add (a ±125 dps part throws away the high-rate rotation that distinguishes violent falls).\n")
A("**Models, same nested CV and targets:** (i) acc9 LR, (ii) acc9 + gyro (15) LR, (iii) L1-LR-selected subset of (ii) followed by a plain LR (C ∈ {0.003, 0.01, 0.03, 0.1, 1} chosen in the inner folds by the mean ADL false-alarm rate over the four targets; selection is redone inside every inner fold), and a depth-5 tree on (ii). "
  "(i) is re-run on each population's own trials/subjects/folds so the comparison is matched.\n")
for ds, lab in (("v3W", "6.1 WEDA only, native gyro range"), ("v3P", "6.2 Pooled, gyro harmonised to ±125 dps")):
    A(f"### {lab}\n")
    A(R3.cmp_table(ds) + "\n")
    A("Paired subject-bootstrap differences (same trials; negative false-alarm change = fewer false alarms):\n")
    A(R3.paired_table(ds) + "\n")
    A("L1 subset — chosen C and selected features per outer fold:\n")
    A(R3.l1_table(ds) + "\n")
    A("ADL false-alarm breakdown (top 5 per dataset) at the 90 % and 95 % targets, acc9 vs acc9 + gyro:\n")
    A(R3.breakdown_md(ds, "acc9_lr") + "\n" + R3.breakdown_md(ds, "gyro15_lr") + "\n")
A("### 6.3 Firmware feasibility notes (analysis-time findings; gyro not implemented)\n")
A(R3.gyro_fs_md() + "\n")
A("### 6.4 Summary: accelerometer-only vs accelerometer + gyro at each recall target\n")
A("Cells: fall recall / ADL false alarms per trial / alarmed ADL trials per hour (point estimates; CIs in the tables above).\n")
A(R3.summary_table() + "\n")
exec(open(os.path.join(HERE, "report_reco.py")).read())
