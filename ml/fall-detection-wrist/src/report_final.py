"""Final model card, model comparison at the chosen operating point, domain-gap row and BITS section (imported by make_report.py)."""
import os
import sys
import json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evalcore as E
import report_v3 as R3
from eval_curve import NAMES

ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results")
T = 0.90
BITS_NAMES = {"adl1": "walking slowly", "adl2": "walking quickly", "adl3": "jogging", "adl4": "jumping", "adl5": "climbing up slowly", "adl6": "climbing down slowly",
              "adl7": "climbing up normally", "adl8": "climbing down normally", "adl9": "slowly sitting on chair", "adl10": "rapidly sitting on chair",
              "adl11": "nearly sitting and getting up", "adl12": "swinging hands", "adl13": "lying on bed", "adl14": "lying on back, getting up slowly",
              "adl15": "lying on back, getting up normally", "adl16": "sideways to back transition",
              "fall1": "forward fall landing on knee", "fall2": "right fall", "fall3": "left fall", "fall4": "forward fall", "fall5": "seated on bed, falling to ground",
              "fall6": "forward fall, body weight on hand", "fall7": "backward fall from seated", "fall8": "grabbing while falling"}


def _row(s, name, t=None):
    r = s[s.metric == name] if t is None else s[(s.target == t) & (s.metric == name)]
    return None if r.empty else r.iloc[0]


def _p(r, count=True):
    if r is None or not np.isfinite(r.value):
        return "n/a"
    return f"{r.value*100:.1f}% [{r.lo*100:.1f}, {r.hi*100:.1f}]" + (f" ({int(r.n_num)}/{int(r.n_den)})" if count else "")


def _r(r, d=1):
    return "n/a" if r is None else f"{r.value:.{d}f} [{r.lo:.{d}f}, {r.hi:.{d}f}]"


def results_rows(suffix_keys=("", "[WEDA]", "[SFMM]")):
    cv = R3.summ("pool26", "acc9_lr")
    b = pd.read_csv(os.path.join(RES, "bits_summary.csv"))
    rows = []
    for lab, suf in (("CV pooled (WEDA + SmartFallMM)", ""), ("CV WEDA only", "[WEDA]"), ("CV SmartFallMM only", "[SFMM]")):
        g = lambda m: _row(cv, m + suf, T)
        rows.append((lab, g("fall_recall_trigger"), g("adl_far_trigger"), g("fa_per_hour_trigger_trials"), g("fa_per_hour_trigger_events")))
    g = lambda m: _row(b, m)
    rows.append(("**BITS wrist IMU+HR (ages 20–47), single held-out run, thr 0.835**", g("fall_recall_trigger"), g("adl_far_trigger"), g("fa_per_hour_trigger_trials"), g("fa_per_hour_trigger_events")))
    return rows


def results_table():
    L = ["| set | fall recall (trigger) | ADL false alarms **per trial** | alarmed ADL trials **per ADL hour** | alarm events **per ADL hour** |", "|---|---|---|---|---|"]
    for lab, rec, far, fah, fae in results_rows():
        L.append(f"| {lab} | {_p(rec)} | {_p(far)} | {_r(fah)} | {_r(fae)} |")
    return "\n".join(L)


def ftype_table():
    cv = R3.summ("pool26", "acc9_lr"); b = pd.read_csv(os.path.join(RES, "bits_summary.csv"))
    L = ["| fall type | CV recall at 90 % target | BITS recall (thr 0.835; **inferred** index → type mapping) |", "|---|---|---|"]
    cvn = {**{"F%02d" % i: n for i, n in enumerate(["fwd fall walking (slip)", "lateral fall walking (slip)", "back fall walking (slip)", "fwd fall walking (trip)", "back fall trying to sit",
                                                       "fwd fall sitting (faint)", "back fall sitting (faint)", "lateral fall sitting (faint)"], 1)},
           "A10": "backfall", "A11": "frontfall", "A12": "leftfall", "A13": "rightfall", "A14": "rotatefall"}
    for k, n in cvn.items():
        L.append(f"| {'WEDA' if k.startswith('F') else 'SmartFallMM'} {k} {n} | {_p(_row(cv, f'fall_recall_trigger[{k}]', T))} | – |")
    for i in range(1, 9):
        L.append(f"| BITS fall{i} {BITS_NAMES[f'fall{i}']} | – | {_p(_row(b, f'fall_recall_trigger[fall{i}]'))} |")
    return "\n".join(L)


def model_card_md():
    fm = json.load(open(os.path.join(RES, "final_model.json")))
    fl = json.load(open(os.path.join(RES, "flash.json"))); ram = json.load(open(os.path.join(RES, "ram.json"))); par = json.load(open(os.path.join(RES, "parity.json")))
    op = fm["operating_points"]["trig90"]
    st = pd.read_csv(os.path.join(RES, "stillness_finding.csv"))
    sv = lambda ds, T_: st[(st.L_s == 3) & (st["std"] == 0.08) & (st.dataset == ds) & (st.T_s == T_)].iloc[0]
    fw = {k: sv("WEDA", k) for k in (3, 5)}; fs = {k: sv("SFMM", k) for k in (3, 5)}
    names = ["max_mag", "min_mag", "mean_mag", "std_mag", "range_mag", "max_jerk", "std_mag_post", "count_low", "tilt_deg"]
    L = ["## Final model card — wrist fall trigger (acc9 LR @ 26 Hz)\n"]
    A = L.append
    A("| item | value |\n|---|---|")
    A("| decision | accelerometer-only logistic regression, 9 features, 26 Hz, trigger tuned on its own for **90 % fall recall**; gyro deferred (ablation §6); stillness = later long-lie stage (placeholders only) |")
    A("| features (`features_v2.py`, scaled to 26 Hz) | " + ", ".join(names) + " |")
    A("| sampling / windows | `SAMPLE_RATE_HZ` 26 (LSM6DSXX `DATA_RATE_26HZ`), window 52 samples (2 s), stride 13 (0.5 s), tilt pre/post 13, tilt fallback 5, post-std 26 |")
    A(f"| model | StandardScaler + LR (balanced), {fm['n_train_windows']} training windows ({fm['n_pos']} positive, time-stretch 0.95/1.00/1.05) from {fm['n_subjects']} subjects; 28 floats (scaler 18 + coef 9 + intercept) |")
    A(f"| **fall threshold** | **p ≥ {op['thr']:.3f}** — pooled 5-fold subject-grouped CV threshold for ≥ 90 % recall at the lowest ADL false-alarm rate (per outer fold 0.78–0.84; inner-CV recall {op['recall']*100:.1f} %, ADL false alarms {op['far']*100:.1f} % per trial). **To be recalibrated on own-device data.** |")
    A("| long-lie placeholders (not validated, not used by the trigger) | `FALL_STILL_STD_THR` 0.08, `FALL_STILL_MEAN_TOL` 0.2, `CONFIRM_SAMPLES` 78 (3 s) |")
    A(f"| flash (measured, Cortex-M4F, `-Os`, libm excluded) | **{fl['features(shared)']['flash_bytes'] + fl['lr']['flash_bytes']} B** = features {fl['features(shared)']['flash_bytes']} B + LR {fl['lr']['flash_bytes']} B (model constants 112 B) |")
    A(f"| RAM | window buffer {ram['window_buffer_bytes']} B (52 × 3 floats, caller-owned; arithmetic) + stack {ram['stack_bytes_trigger_prob']} B for feature extraction + LR (measured with `-fstack-usage`, libm callees excluded); static data {ram['data_bytes'] + ram['bss_bytes']} B. The long-lie placeholder would add {ram['long_lie_placeholder_buffer_bytes']} B. |")
    A(f"| C parity | host `fall_features.h` vs Python on 1000 random train windows: every feature within 1e-4 relative (worst {max(v['max_rel'] for v in par['windows']['per_feature'].values()):.1e}), {par['windows']['trigger_mismatch_at_exported_thr']} trigger and {par['segments']['still_mismatch']} stillness mismatches; firmware `host_test.c` ALL PASS → **{'PASS' if par['PASS'] else 'FAIL'}** |")
    A("")
    A("### Results at the chosen operating point\n")
    A("Cross-validated rows use the per-fold nested thresholds; the BITS row uses the final threshold 0.835 exactly and was run **once**, with no retuning afterwards. "
      "Every per-trial false-alarm rate has its per-hour counterpart next to it. **The ADL trials in all three datasets are curated, vigorous activities (jogging, jumping, hitting a table, clapping, putting on a jacket, sweeping, stairs, …) — the per-hour figures are a stress test, not a daily-life false-alarm rate.**\n")
    A(results_table() + "\n")
    A(f"BITS: 4 of 912 files after rule 4 are shorter than one 2 s window at 26 Hz and cannot be scored (1 fall, 3 ADL); 20 Hz is assumed by sample order (timestamps are rounded to 3 significant digits); ages 20–47. "
      f"CV recall {_p(_row(R3.summ('pool26','acc9_lr'),'fall_recall_trigger',T), False)} vs BITS {_p(_row(pd.read_csv(os.path.join(RES,'bits_summary.csv')),'fall_recall_trigger'), False)}: the held-out recall is about 9 pp below the target — a real domain shift (different device, wrist, protocol), which is why the threshold must be recalibrated on own-device data.\n")
    A("Per fall type:\n")
    A(ftype_table() + "\n")
    A("### Domain gap, gyro ablation, stillness finding\n")
    A(domain_gap_md(short=True))
    A(f"- **Gyro ablation (§6):** *small significant gain only with an unclipped gyro; deferred for power / full-scale.* With WEDA's native-range gyro, 6 extra orientation-invariant features cut ADL false alarms by ≈ 2 pp at equal recall (paired CIs exclude zero at 85–95 %); with a ±125 dps gyro (SmartFallMM, harmonised pool) the effect is nil. The firmware gyro is currently ±245 dps and unused; ±2000 dps would be needed.")
    A(f"- **Stillness finding (§5):** after a fall, a 3 s stretch with std < 0.08 g / |mean−1| < 0.2 starts within 3 s of the peak in {fw[3].frac*100:.0f} % of evaluable WEDA falls ({int(fw[3].reached)}/{int(fw[3].enough_data)}) and {fs[3].frac*100:.0f} % of SmartFallMM falls ({int(fs[3].reached)}/{int(fs[3].enough_data)}); within 5 s: {fw[5].frac*100:.0f} % ({int(fw[5].reached)}/{int(fw[5].enough_data)}) vs {fs[5].frac*100:.0f} % ({int(fs[5].reached)}/{int(fs[5].enough_data)}). No recall target; 10 s horizon has too little data (2 and 11 falls).\n")
    A("### Limitations\n")
    A("- **Simulated falls only**: every fall is scripted by a volunteer (WEDA on a mattress); no real falls, no real-life ADL stream, so absolute false-alarm rates do not transfer to daily life.\n"
      "- **Young fallers only**: all WEDA and SmartFallMM falls are by young adults (WEDA 14 subjects, one aged 46), BITS volunteers are 20–47; elderly data are ADL-only, so fall detection for older users is untested (the BITS folder name 'geriatric' is wrong).\n"
      "- **One pooled threshold, heterogeneous data**: WEDA falls score higher and WEDA ADL alarm more than SmartFallMM's; the chosen threshold gives different recall / false-alarm trade-offs per dataset and a ≈ 9 pp recall drop on BITS. Recalibrate on own-device data before relying on 90 %.\n"
      "- **Sensor and clock caveats**: WEDA fall files are sampled at ≈ 39.8 Hz vs ≈ 49.7 Hz for ADL (handled with per-trial linear time axes; checked at 26 Hz), SmartFallMM mixes 25 and 50 Hz and its accelerometer saturates near ±2 g per axis ("
      + _sfmm_cap_text() + "), BITS rate and regularity are assumed.\n"
      "- **Confirm/long-lie stage is unvalidated** on wrist data; the placeholders only keep the header self-consistent.\n")
    return "\n".join(L)


def _sfmm_cap_text():
    try:
        d = json.load(open(os.path.join(RES, "data_card_stats.json")))["sfmm"]
        pk = [r["peak_val"] for r in d if r.get("is_fall") and not r.get("bad")]
        return f"{np.mean(np.array(pk) > 3.4)*100:.0f} % of SmartFallMM falls peak at ≈ 3.46 g = 2·√3 g"
    except Exception:
        return "peak |a| of SmartFallMM falls is capped near 3.46 g"


def domain_gap_md(short=False):
    base = pd.read_csv(os.path.join(RES, "summary_baseline_52.csv")); cv = R3.summ("pool26", "acc9_lr"); b = pd.read_csv(os.path.join(RES, "bits_summary.csv"))
    L = ["| model (set) | fall recall (trigger) | ADL false alarms per trial | alarmed ADL trials per ADL hour |", "|---|---|---|---|"]
    rows = [("SisFall-waist LR, unchanged, 52 Hz, own threshold 0.93 (WEDA + SmartFallMM pool)", base, None), ("Wrist LR @ 26 Hz, chosen point (CV, same pool)", cv, T), ("Wrist LR @ 26 Hz, chosen point (BITS single run)", b, None)]
    for lab, s, t in rows:
        g = lambda m: _row(s, m, t)
        L.append(f"| {lab} | {_p(g('fall_recall_trigger'))} | {_p(g('adl_far_trigger'))} | {_r(g('fa_per_hour_trigger_trials'))} |")
    txt = "\n".join(L) + "\n"
    note = ("The waist model transfers poorly to the wrist — at its own fixed threshold it detects 79 % of wrist falls while still alarming on about a third of ADL trials; the retrained wrist LR reaches 90 % recall at a lower false-alarm rate. "
            "The baseline was not run on BITS (BITS was used once, for the final model only). The comparison is not threshold-matched.\n")
    return ("**Waist → wrist domain gap:**\n\n" + txt + "\n" + note) if short else (txt + "\n" + note)


def model_comparison_md():
    fl = json.load(open(os.path.join(RES, "flash.json")))
    L = ["| model | fall recall (trigger) | ADL false alarms per trial | alarmed ADL trials per hour | parameters | classifier flash (B, measured) | + feature code | total flash (B) |", "|---|---|---|---|---|---|---|---|"]
    fe = fl["features(shared)"]["flash_bytes"]
    for lab, ds, m, key in (("**LR @ 26 Hz (chosen)**", "pool26", "acc9_lr", "lr"), ("LR @ 52 Hz", "pool52", "acc9_lr", None), ("Decision tree depth 5 @ 26 Hz", "pool26", "acc9_tree", "tree"), ("MLP 1×16 @ 26 Hz", "pool26", "acc9_mlp", "mlp")):
        s = R3.summ(ds, m)
        g = lambda k: _row(s, k, T)
        if key:
            f = fl[key]; cells = f"{f['n_params']} | {f['flash_bytes']} | {fe} | {f['flash_bytes'] + fe}"
        else:
            cells = "28 | same code | – | –"
        L.append(f"| {lab} | {_p(g('fall_recall_trigger'))} | {_p(g('adl_far_trigger'))} | {_r(g('fa_per_hour_trigger_trials'))} | {cells} |")
    return "\n".join(L)


def bits_md(bits, b4, ok4, b5):
    b = pd.read_csv(os.path.join(RES, "bits_summary.csv")); o = pd.read_csv(os.path.join(RES, "bits_outcomes.csv"))
    L = []
    A = L.append
    A("## 9. BITS wrist IMU+HR (ages 20–47) — single held-out run (done)\n")
    A("Run once with `src/eval_bits.py --op trig90 --rule5 skip` (lock file `results/bits_run.lock` now blocks a second run); nothing was retuned afterwards. The model, threshold (0.835), features and 26 Hz resampling were fixed before the run.\n")
    A(f"- Files: 984 → rule 4 (rest |a| of `acg` within 1 ± 0.1 g) drops {len(b4)} ADL files (0 falls) → {len(ok4)}; rule 5 (timestamp span) skipped by decision; 4 further files are shorter than one 2 s window at 26 Hz → **{int(o.is_fall.sum())} falls and {int((~o.is_fall).sum())} ADL trials** from 41 subjects, ADL time {_row(b, 'fa_per_hour_trigger_trials').n_den:.2f} h *if 20 Hz*.")
    A("- **Assumption:** 20 Hz by sample order (timestamps carry 3 significant digits, so the rate and regularity cannot be verified; the HR-block cross-check gives a median of 20.2 accelerometer samples per HR row but with a wide spread). If the true rate differed, the 26 Hz resampling would stretch time and every time-based feature with it.")
    A("- Ages 20–47 (dataset paper, read by a sub-agent from PMC10709028 and not independently re-verified); acceleration = tag `acg` (gravity included; the paper's prose describes the tags the other way round, the data decided).\n")
    A(results_table() + "\n")
    A("Per fall type (the index → activity mapping is **inferred**: each user has exactly one file per paper activity, and per-index motion energy follows the paper's table; the paper does not document the file naming):\n")
    L2 = ["| fall | trials | recall (95 % CI over subjects) |", "|---|---|---|"]
    for i in range(1, 9):
        r = _row(b, f"fall_recall_trigger[fall{i}]")
        L2.append(f"| fall{i} {BITS_NAMES[f'fall{i}']} | {int(r.n_den)} | {_p(r)} |")
    A("\n".join(L2) + "\n")
    A("The two seated falls (fall5, fall7) are the weakest, backward-fall-from-seated most of all.\n")
    A("ADL false-alarm breakdown, top 5 activities (trigger-only; BITS paper activity names, inferred mapping):\n")
    br = E.adl_breakdown(o, {**BITS_NAMES}, 5)
    L3 = ["| activity | alarmed / trials | false-alarm rate per trial | alarmed trials per hour of that activity | share of all false alarms |", "|---|---|---|---|---|"]
    for _, r in br.iterrows():
        L3.append(f"| {r.ftype} {r.activity} | {int(r.alarmed)}/{int(r.trials)} | {r.far*100:.0f}% | {r.alarmed_per_hour:.0f} | {r.share_of_dataset_FAs*100:.0f}% |")
    A("\n".join(L3) + "\n")
    return "\n".join(L)
