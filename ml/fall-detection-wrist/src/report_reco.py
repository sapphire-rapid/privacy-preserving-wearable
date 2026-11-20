# exec'd from report_sections_v3.py: A, R3, RES, os, pd, np, json in scope.
fm_ = json.load(open(os.path.join(RES, "final_model.json")))["operating_points"]
s_ = R3.summ("pool26", "acc9_lr")


def _g(s, t, m):
    return s[(s.target == t) & (s.metric == m)].iloc[0]


def _paired(ds, model, t, metric):
    base = R3.outc(ds, "acc9_lr"); o = R3.outc(ds, model)
    return R3.E.paired_diff(o[o.target == t], base[base.target == t], [metric]).iloc[0]


pw = {t: _paired("v3W", "gyro15_lr", t, "adl_far_trigger") for t in R3.TARGETS}
pp = {t: _paired("v3P", "gyro15_lr", t, "adl_far_trigger") for t in R3.TARGETS}
sig_w = [int(t * 100) for t in R3.TARGETS if pw[t]["hi"] < 0]
A("### 6.5 Decision taken: acc9 LR, 90 % target; gyro deferred\n")
A("**Feature set (adopted): the 9 accelerometer features, LR @ 26 Hz.** Gyro ablation summary: *small significant gain only with an unclipped gyro; deferred for power / full scale.* "
  f"With a gyro that does not clip (WEDA, native range) the 6 added features lower ADL false alarms per trial by {-pw[0.9]['diff']*100:.1f} pp at the 90 % target "
  f"(paired CI [{pw[0.9]['lo']*100:+.1f}, {pw[0.9]['hi']*100:+.1f}] pp; {-pw[0.95]['diff']*100:.1f} pp at 95 %, [{pw[0.95]['lo']*100:+.1f}, {pw[0.95]['hi']*100:+.1f}]) at unchanged recall — a 13–23 % relative reduction, with the paired CI excluding zero at the {', '.join(map(str, sig_w))} % targets. "
  f"In the pooled, ±125 dps-harmonised population the same features change nothing measurable ({pp[0.9]['diff']*100:+.1f} pp at 90 %, [{pp[0.9]['lo']*100:+.1f}, {pp[0.9]['hi']*100:+.1f}]; {pp[0.95]['diff']*100:+.1f} pp at 95 %, [{pp[0.95]['lo']*100:+.1f}, {pp[0.95]['hi']*100:+.1f}]). "
  "The L1 step does not find a smaller useful set (it keeps 13–15 of the 15 features in the WEDA run and 9–14 in the pooled run, with no accuracy difference to (ii)), and the depth-5 tree is worse than LR and cannot reach the 80–90 % targets in the WEDA run because its probabilities are coarse. "
  "The gain exists only if the gyro runs at ±2000 dps (the firmware is currently configured for ±245 dps, which clips every fall), needs a read path and a power budget I could not verify, and I could not test it on a second dataset with an unclipped gyro (BITS is on hold). "
  "I would therefore **not** add the gyro to the first firmware, and revisit it when you have your own recordings with a ±2000 dps gyro: the question to answer there is whether the ≈2 pp trial-level false-alarm reduction survives.\n")
t90 = R3.TARGETS[2]
A("**Operating point (adopted): the 90 % recall target.** "
  f"Pooled 5-fold CV threshold of the final model: **{fm_['trig90']['thr']:.3f}** (per outer fold {', '.join(f'{v:.2f}' for v in pd.read_csv(os.path.join(RES, 'curve_pool26_acc9_lr_folds.csv'))['thr@90'])}); "
  f"cross-validated recall {_g(s_, 0.9, 'fall_recall_trigger').value*100:.1f} % [{_g(s_, 0.9, 'fall_recall_trigger').lo*100:.1f}, {_g(s_, 0.9, 'fall_recall_trigger').hi*100:.1f}], ADL false alarms per trial {_g(s_, 0.9, 'adl_far_trigger').value*100:.1f} % [{_g(s_, 0.9, 'adl_far_trigger').lo*100:.1f}, {_g(s_, 0.9, 'adl_far_trigger').hi*100:.1f}]. "
  f"Going from 90 % to 95 % recall raises the false-alarm rate from {_g(s_, 0.9, 'adl_far_trigger').value*100:.1f} % to {_g(s_, 0.95, 'adl_far_trigger').value*100:.1f} % per trial (alarmed ADL trials per hour {_g(s_, 0.9, 'fa_per_hour_trigger_trials').value:.0f} → {_g(s_, 0.95, 'fa_per_hour_trigger_trials').value:.0f}), "
  f"while 85 % → 90 % costs only {(_g(s_, 0.9, 'adl_far_trigger').value-_g(s_, 0.85, 'adl_far_trigger').value)*100:.1f} pp — the knee of the curve is at 85–90 %. The thresholds for all four targets are stored in `results/final_model.json` "
  f"(80 %: {fm_['trig80']['thr']:.3f}, 85 %: {fm_['trig85']['thr']:.3f}, 90 %: {fm_['trig90']['thr']:.3f}, 95 %: {fm_['trig95']['thr']:.3f}). "
  "Two cautions: (a) the header was regenerated at this point (`src/export_final.py --op trig90`, parity PASS); "
  "(b) one pooled threshold hides large dataset differences — at 90 % it gives WEDA 100 % recall with 43 % ADL false alarms per trial but SmartFallMM 85 % recall with 16 % (table in §4) — and the ADL trials of both datasets are curated, vigorous activities (jogging, hand hits, stumbles, jumps), "
  "so the per-hour figures are an upper-bound stress test, not a daily-life false-alarm rate. Calibrate the final threshold on your own recordings.\n")
