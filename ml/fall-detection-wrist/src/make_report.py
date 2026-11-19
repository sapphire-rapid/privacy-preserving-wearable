"""Assemble results/REPORT.md from the result files (no hand-typed numbers in the tables)."""
import os
import sys
import json
import pickle
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as F

ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results")
CACHE = os.path.join(ROOT, "cache")


def S(name):
    return pd.read_csv(os.path.join(RES, f"summary_{name}.csv")).set_index("metric")


def pct(s, m, count=True):
    if m not in s.index or not np.isfinite(s.loc[m, "value"]):
        return "n/a"
    r = s.loc[m]
    t = f"{r.value*100:.1f}% [{r.lo*100:.1f}, {r.hi*100:.1f}]"
    return t + (f" ({int(r.n_num)}/{int(r.n_den)})" if count else "")


def rate(s, m):
    r = s.loc[m]
    return f"{r.value:.2f} [{r.lo:.2f}, {r.hi:.2f}]"


def n(s, m):
    return int(s.loc[m, "n_den"])


ROWS = [("LR @ 26 Hz (primary)", "lr_26"), ("LR @ 52 Hz", "lr_52"), ("Decision tree (depth 5) @ 26 Hz", "tree_26"),
        ("MLP (1×16) @ 26 Hz", "mlp_26")]


def main_table(suffix):
    L = ["| model | fall recall, trigger-only (all falls) | fall recall, with confirm (eligible falls; coverage) | ADL false-alarm rate / trial, trigger-only | ADL false-alarm rate / trial, confirmed | confirmed alarmed ADL trials / h | confirmed alarm events / h | confirmed ADL FAR young | confirmed ADL FAR old |",
         "|---|---|---|---|---|---|---|---|---|"]
    for lab, tag in ROWS + [("**Baseline**: SisFall-waist LR, unchanged, 52 Hz (thr 0.93, std 0.05)", "baseline_52")]:
        s = S(tag if tag == "baseline_52" else tag + suffix)
        cov = f"coverage {int(s.loc['fall_recall_confirm','n_den'])}/{int(s.loc['fall_recall_trigger','n_den'])} = {s.loc['fall_recall_confirm','n_den']/s.loc['fall_recall_trigger','n_den']*100:.0f}%"
        L.append(f"| {lab} | {pct(s,'fall_recall_trigger')} | {pct(s,'fall_recall_confirm')}; {cov} | {pct(s,'adl_far_trigger')} | {pct(s,'adl_far_confirm')} | {rate(s,'fa_per_hour_trials')} | {rate(s,'fa_per_hour_events')} | {pct(s,'adl_far_confirm_young')} | {pct(s,'adl_far_confirm_old')} |")
    return "\n".join(L)


def dataset_table(suffix):
    L = ["| model | dataset | recall trigger-only | recall with confirm (eligible) | coverage of confirm | ADL FAR confirmed |", "|---|---|---|---|---|---|"]
    for lab, tag in ROWS[:1] + [("Baseline (SisFall-waist)", "baseline_52")]:
        s = S(tag if tag == "baseline_52" else tag + suffix)
        for d in ("WEDA", "SFMM"):
            cov = f"{int(s.loc[f'fall_recall_confirm[{d}]','n_den'])}/{int(s.loc[f'fall_recall_trigger[{d}]','n_den'])}"
            L.append(f"| {lab} | {d} | {pct(s,f'fall_recall_trigger[{d}]')} | {pct(s,f'fall_recall_confirm[{d}]')} | {cov} | {pct(s,f'adl_far_confirm[{d}]')} |")
    return "\n".join(L)


def ftype_table(suffix):
    names = {"F01": "F01 fwd fall walking (slip)", "F02": "F02 lateral fall walking (slip)", "F03": "F03 back fall walking (slip)", "F04": "F04 fwd fall walking (trip)",
             "F05": "F05 back fall trying to sit", "F06": "F06 fwd fall sitting (faint)", "F07": "F07 back fall sitting (faint)", "F08": "F08 lateral fall sitting (faint)",
             "A10": "A10 backfall", "A11": "A11 frontfall", "A12": "A12 leftfall", "A13": "A13 rightfall", "A14": "A14 rotatefall"}
    a, b = S("lr_26" + suffix), S("baseline_52")
    L = ["| fall type | trials | LR@26 recall trigger-only | LR@26 recall with confirm (eligible/trials) | baseline recall trigger-only | baseline with confirm |", "|---|---|---|---|---|---|"]
    for k, nm in names.items():
        L.append(f"| {nm} | {n(a,f'fall_recall_trigger[{k}]')} | {pct(a,f'fall_recall_trigger[{k}]')} | {pct(a,f'fall_recall_confirm[{k}]')} | {pct(b,f'fall_recall_trigger[{k}]')} | {pct(b,f'fall_recall_confirm[{k}]')} |")
    return "\n".join(L)


def folds_table(tag):
    f = pd.read_csv(os.path.join(RES, f"folds_{tag}.csv"))
    L = ["| outer fold | test subjects | chosen thr | chosen std | recall on inner tuning data | ADL FAR on tuning data | target reached |", "|---|---|---|---|---|---|---|"]
    for _, r in f.iterrows():
        L.append(f"| {int(r.fold)} | {int(r.n_test_subjects)} | {r.thr:.3f} | {r['std']:.3f} | {r.recall*100:.1f}% | {r.far*100:.1f}% | {'yes' if r.feasible else '**no**'} |")
    return "\n".join(L)


def stillness_ceiling():
    ds = pickle.load(open(os.path.join(CACHE, "ds_26.pkl"), "rb"))
    c = F.CFG26
    best = {"WEDA": [], "SFMM": []}
    for t in ds["trials"]:
        if not (t["is_fall"] and t["elig"]):
            continue
        sl = slice(t["off"], t["off"] + t["cnt"])
        st, ev, sd, mu = ds["w_start"][sl], ds["ev"][sl], ds["sd"][sl], ds["mu"][sl]
        cont = (st <= t["peak"]) & (t["peak"] < st + c.win) & ev
        ok = cont & (np.abs(mu - 1) < F.MEAN_TOL)
        best[t["dataset"]].append(sd[ok].min() if ok.any() else np.inf)
    L = ["| dataset | eligible falls | with a still post-impact segment at std < 0.05 | < 0.065 | < 0.08 | < 0.12 | < 0.20 | < 0.30 |", "|---|---|---|---|---|---|---|---|"]
    for d, v in best.items():
        v = np.array(v)
        L.append(f"| {d} | {len(v)} | " + " | ".join(f"{(v < s).mean()*100:.1f}%" for s in (0.05, 0.065, 0.08, 0.12, 0.2, 0.3)) + " |")
    adl = [t for t in ds["trials"] if not t["is_fall"]]
    row = []
    for s in (0.05, 0.065, 0.08, 0.12, 0.2, 0.3):
        still = ds["ev"] & (ds["sd"] < s) & (np.abs(ds["mu"] - 1) < F.MEAN_TOL)
        row.append(f"{np.mean([still[t['off']:t['off']+t['cnt']].any() for t in adl])*100:.1f}%")
    L.append(f"| ADL segments with ≥ 1 still evaluable window (any probability) | {len(adl)} | " + " | ".join(row) + " |")
    return "\n".join(L)


def main():
    fl = json.load(open(os.path.join(RES, "flash.json")))
    par = json.load(open(os.path.join(RES, "parity.json")))
    leak = json.load(open(os.path.join(RES, "rate_leak_check.json")))
    fin = json.load(open(os.path.join(RES, "final_model.json")))
    excl = json.load(open(os.path.join(RES, "exclusions.json")))
    bits = pickle.load(open(os.path.join(CACHE, "bits.pkl"), "rb"))
    ds = pickle.load(open(os.path.join(CACHE, "ds_26.pkl"), "rb"))
    tr = ds["trials"]
    falls = [t for t in tr if t["is_fall"]]
    s_trig = S("lr_26_trig"); s_spec = S("lr_26"); s_base = S("baseline_52")
    adl_h = s_trig.loc["fa_per_hour_trials", "n_den"]
    b4 = [r for r in bits if not r["rule4_pass"]]; ok4 = [r for r in bits if r["rule4_pass"]]
    b5 = [r for r in ok4 if not r["rule5_pass"]]
    L = []; A = L.append
    A("# Wrist fall detection — retraining report (`wrist-retrain`)\n")
    A("Same 9 features, same logistic-regression pipeline as the SisFall-waist model, retrained on WEDA-FALL + SmartFallMM (Meta_wrist) at 26 Hz. "
      "All numbers below were measured by the scripts in `src/` (commands at the end); tables are generated from `results/*.csv`, not typed.\n")
    A("## 0. Read this first\n")
    A("Decisions applied since the first version of this report: (1) **stillness is no longer part of fall detection** — it is the later long-lie (U3 severity) stage; the fall trigger is tuned on its own (trigger-only), post-impact stillness is reported as a finding (§5), and the old confirm-stage tables are kept only in Appendix A; "
      "(2) the BITS dataset is called **\"BITS wrist IMU+HR (ages 20–47)\"** (the on-disk folder `bits_geriatric` is misleading — paper: 41 volunteers aged 20–47, read by a sub-agent from PMC10709028, not independently re-verified); its rule 5 (timestamp-span check) is skipped, the **20 Hz-by-sample-order assumption** stands (timestamps are rounded to 3 significant digits, so the rate cannot be verified), and the **BITS run is ON HOLD** (no lock file created, nothing evaluated).\n")
    A("What to know before reading the numbers:\n")
    A("1. **Operating curve (§4):** at the 90 % recall target the accelerometer-only LR@26 Hz raises a false alarm in about one ADL trial in four (23 %); at 95 % in one in three (34 %). One pooled threshold behaves very differently on the two datasets (§4). The ADL trials are curated vigorous activities, so per-hour rates are a stress test, not daily life.")
    A("2. **Gyro (§6):** WEDA's gyro reaches ≈ 2000 dps while SmartFallMM's Meta_wrist gyro clips at ±125 dps in ~97 % of trials, so the gyro comparison is run on two populations. With an unclipped gyro the 6 extra features reduce ADL false alarms by ≈ 2 pp (13–23 % relative) at equal recall; with a ±125 dps gyro they do nothing. The firmware's current gyro config (±245 dps, never read) would clip every fall. **Recommendation (§6.5): stay with the 9 accelerometer features and the 90 % operating point; revisit the gyro on your own recordings.**")
    A("3. **Header is provisional:** `include/fall_model.h` carries the final weights, the 95 % threshold (0.671) until you choose a target, and std 0.08 / tol 0.2 / 3 s **as long-lie placeholders**. No C or firmware code was changed in this round.\n")

    A("## 1. Data card summary (full card: `DATA_CARD.md`)\n")
    nf = {d: sum(1 for t in falls if t["dataset"] == d) for d in ("WEDA", "SFMM")}
    wp = pickle.load(open(os.path.join(CACHE, "weda.pkl"), "rb")); sp = pickle.load(open(os.path.join(CACHE, "sfmm.pkl"), "rb"))
    rate_txt = {"WEDA": "falls %.1f Hz / ADL %.1f Hz (median effective)" % (np.median([r["native_rate"] for r in wp if r["is_fall"]]), np.median([r["native_rate"] for r in wp if not r["is_fall"]])),
                "SFMM": "%d segments ≈50 Hz, %d ≈25 Hz, %d other" % (sum(r["native_rate"] > 45 for r in sp), sum(22 < r["native_rate"] < 28 for r in sp), sum(not (r["native_rate"] > 45 or 22 < r["native_rate"] < 28) for r in sp))}
    adl_tr = [t for t in tr if not t["is_fall"]]
    A("| dataset | role | rate (measured) | units → g | fall trials used | fall trials confirm-eligible | ADL segments used | notes |\n|---|---|---|---|---|---|---|---|")
    for d, lab, note in (("WEDA", "train pool", "Fitbit Sense wrist; falls young only (U01–U14), elderly ADL-only; fall files ≈39.8 Hz vs ADL ≈49.7 Hz effective, burst-stamped → per-trial linear time axis"),
                         ("SFMM", "train pool", "SmartFallMM Meta_wrist (© SmartFall Group, Texas State Univ.; credit required, not redistributed); 50 Hz and 25 Hz sessions; ISO clock; 32 non-g ADL files dropped; split at gaps > 1 s")):
        A(f"| {'WEDA-FALL' if d=='WEDA' else 'SmartFallMM'} | {lab} | {rate_txt[d]} | {'÷9.80665' if d=='WEDA' else 'already g'} | {nf[d]} | {sum(1 for t in falls if t['dataset']==d and t['elig'])} | {sum(1 for t in adl_tr if t['dataset']==d)} | {note} |")
    A(f"| BITS wrist IMU+HR (ages 20–47) | held-out, ON HOLD | 20 Hz assumed by sample order (not verifiable) | ÷9.80665 (`acg`) | {sum(r['is_fall'] for r in bits)} files | – | {sum(not r['is_fall'] for r in bits)} files | rule 4 drops {len(b4)} files (0 falls); rule 5 skipped by decision |")
    A(f"\nAfter exclusions the pool has **{len(falls)} fall trials** ({nf['WEDA']} WEDA + {nf['SFMM']} SFMM) and {len({t['trial_id'] for t in adl_tr})} ADL trials ({len(adl_tr)} segments, {adl_h:.2f} h); "
      f"{sum(t['post3'] for t in falls)} falls have ≥ 3 s after the |a| peak and **{sum(t['elig'] for t in falls)} are confirm-eligible** (a window containing the peak has its full 3 s confirm segment inside the recording; this implies ≥ 3 s after the peak). "
      f"Subjects: {len({t['subject'] for t in tr})} (WEDA {len({t['subject'] for t in tr if t['dataset']=='WEDA'})}, SFMM {len({t['subject'] for t in tr if t['dataset']=='SFMM'})}). "
      "Every exclusion is listed in `DATA_CARD.md` §5.\n")

    A("## 2. Preprocessing and unit tests\n")
    A("Per-trial linear time axis (WEDA) / ISO clock (SmartFallMM) → uniform grid → `resample_poly` to 26 Hz (primary) and 52 Hz (comparison row and waist-baseline input), `padtype='line'` (the default zero padding drags |a| to 0 at trial edges). Raw → g: WEDA ÷ 9.80665, SmartFallMM already g, BITS `acg` ÷ 9.80665.\n")
    A("```\n" + open(os.path.join(RES, "preprocess_tests.txt")).read().strip() + "\n```\n")
    A("## 3. Windows, features, augmentation\n")
    c = F.CFG26
    A(f"26 Hz constants (scaled from the 52 Hz reference): WIN {c.win}, STRIDE {c.stride}, TILT_PRE/POST {c.tilt_pre}/{c.tilt_post}, TILT_FALLBACK {c.tilt_fallback}, POST_STD {c.post_std}, CONFIRM {c.confirm}; fall label window = peak − int(0.4·WIN), one per fall trial; ADL = all sliding windows (as `features_v2.py`). "
      f"Vectorised features match the scalar reference exactly (`src/test_features.py`). Training-fold-only augmentation: time-stretch 0.95 / 1.00 / 1.05. Training windows in the pool: {len(ds['ytr'])} ({int(ds['ytr'].sum())} positive).\n")
    A("### 3.1 Source-rate leak check (WEDA falls ≈39.8 Hz vs ADL ≈49.7 Hz)\n")
    A(f"{leak['adl_trials']} WEDA ADL trials ({leak['windows']} windows): direct path (≈49.7 → 26 Hz) vs two-step path (≈49.7 → 39.8 → 26 Hz); relative difference = |a−b| / max(|a|, floor), floors 0.01 g (or g/sample) for magnitude features, 1 sample for count_low, 1° for tilt.\n")
    A(leak["table_md"] + "\n")
    med = max(v["median"] for v in leak["features"].values())
    A(f"Medians are ≤ {med:.1e} for every feature (i.e. ≤ {med*100:.2f} %); tails are heavier (99th pct up to {max(v['p99'] for v in leak['features'].values()):.2f}, driven by near-zero denominators in min_mag, count_low and tilt) but unsystematic. "
      "The 26 Hz series is band-limited below 13 Hz, which both source rates cover; the near-zero medians say the extra pre-downsampling step changes the features by well under a percent for a typical window. This is a feature-level check only — I did not train a classifier to predict the source rate.\n")

    L_main = L
    L = []; A = L.append      # old section 4 (stillness-confirm results) becomes Appendix A
    A("## Appendix A — superseded: confirm-stage results on the train pool (nested, subject-grouped 5-fold CV)\n")
    A("*Written before the decision to move stillness out of fall detection; kept for the record. The trigger-only operating curve in §4 is the current analysis.*\n")
    A(f"Outer GroupKFold(5) by subject, inner GroupKFold(3) on the outer-train subjects tunes (probability threshold on a 0.001 grid, stillness std). "
      f"Metrics: **trigger-only** = trial detected iff any window has p ≥ thr (all fall trials, N = {n(s_trig,'fall_recall_trigger')}); **with confirm** = detected iff a window with p ≥ thr is followed by 3 s of stillness, reported only on the **confirm-eligible** falls (N = {n(s_trig,'fall_recall_confirm')}) with the coverage stated next to every number. "
      f"An ADL false alarm = any confirmed event in the trial (trigger-only column: any trigger). ADL time = {adl_h:.2f} h; 'alarmed ADL trials / h' = alarmed trials ÷ ADL hours (reference convention), 'events / h' merges alarms < 5 s apart. "
      f"95 % CIs are percentile bootstrap over subjects (2000 resamples). The ADL false-alarm rate is per *trial* (any window of a multi-minute trial may fire); windows not followed by 3 s of recording are never confirmed (strict); the conservative variant (counted as confirmed) is `adl_far_confirm_cons` in the summary CSVs "
      f"(LR@26, mode B: {pct(S('lr_26_trig'),'adl_far_confirm_cons',False)}).\n")
    A("### A.1 Why the stillness rule cannot work as a fall-recall criterion here\n")
    A("Share of confirm-eligible falls that have *at least one* impact-containing window whose following 3 s is still (std below the column value and |mean−1| < 0.2), irrespective of any classifier, versus the share of ADL segments that contain a still window:\n")
    A(stillness_ceiling() + "\n")
    A("### A.2 (A) The rule as specified: std ∈ {0.05, 0.065, 0.08}, tune to ≥ 95 % recall at lowest ADL false alarms\n")
    A("Target unreachable in every fold (chosen thresholds ≈ 0, i.e. 'any still window'). These are the pre-registered results:\n")
    A(main_table("") + "\n")
    A("Chosen parameters per outer fold, LR@26:\n")
    A(folds_table("lr_26") + "\n")
    A("### A.3 (B) Threshold tuned without the confirm stage (≥ 95 % trigger-only recall on all falls at the lowest trigger-only ADL false-alarm rate); confirm applied afterwards with std 0.08\n")
    A("This is the only row set in which the probability threshold is meaningful. The 'with confirm' columns show what the (untuned) stillness stage then does: it removes most ADL false alarms and most falls.\n")
    A(main_table("_trig") + "\n")
    A("Per dataset (LR@26 and baseline; note the different confirm coverage):\n")
    A(dataset_table("_trig") + "\n")
    A("Per fall type (mode B):\n")
    A(ftype_table("_trig") + "\n")
    A("Chosen parameters per outer fold, LR@26 (mode B):\n")
    A(folds_table("lr_26_trig") + "\n")
    A("### A.4 (C) Sensitivity: wider stillness grid std ∈ {0.05, 0.065, 0.08, 0.12, 0.2, 0.3}\n")
    A("Recall with confirm gets closer to the target only by accepting stillness thresholds so loose that the confirm stage no longer filters ADL (false-alarm rates near 80 %).\n")
    A(main_table("_ext") + "\n")

    appx = L; L = L_main; A = L.append
    import report_v3 as R3
    g_ = dict(globals()); g_["A"] = A; g_["R3"] = R3
    exec(open(os.path.join(HERE, "report_sections_v3.py")).read(), g_)      # sections 4-6 (operating curve, stillness finding, gyro v3)
    A("## 7. Model comparison (offline; LR is the deploy candidate; trigger-only threshold tuned for 95 % recall)\n")
    fa = lambda t: fl[t]["flash_bytes"]
    L2 = ["| model | trigger recall (mode B) | ADL trigger-only FAR | recall with confirm (coverage) | parameters | classifier flash, bytes (measured) | + shared feature code | total flash |", "|---|---|---|---|---|---|---|---|"]
    for lab, tag, key in (("LR @ 26 Hz", "lr_26", "lr"), ("Decision tree (depth ≤ 5) @ 26 Hz", "tree_26", "tree"), ("MLP (1×16) @ 26 Hz", "mlp_26", "mlp")):
        s = S(tag + "_trig"); f = fl[key]
        cov = f"{int(s.loc['fall_recall_confirm','n_den'])}/{int(s.loc['fall_recall_trigger','n_den'])}"
        L2.append(f"| {lab} | {pct(s,'fall_recall_trigger')} | {pct(s,'adl_far_trigger')} | {pct(s,'fall_recall_confirm')}; cov. {cov} | {f['n_params']} ({'28 floats = 112 B' if key=='lr' else ('tree nodes' if key=='tree' else 'floats')}) | {f['flash_bytes']} | {fl['features(shared)']['flash_bytes']} | {f['flash_bytes']+fl['features(shared)']['flash_bytes']} |")
    s = S("lr_52_trig")
    L2.append(f"| LR @ 52 Hz | {pct(s,'fall_recall_trigger')} | {pct(s,'adl_far_trigger')} | {pct(s,'fall_recall_confirm')}; cov. {int(s.loc['fall_recall_confirm','n_den'])}/{int(s.loc['fall_recall_trigger','n_den'])} | 28 | same code as LR@26 | – | – |")
    A("\n".join(L2) + "\n")
    A(f"Flash = `arm-none-eabi-gcc -Os -mcpu=cortex-m4 -mfloat-abi=hard` object text+rodata for the final pool-trained model (tree: depth {fl['tree']['depth']}, {fl['tree']['leaves']} leaves; MLP: 9→16→1 ReLU/sigmoid), libm excluded. "
      "Subject-bootstrap CIs of the three models overlap on every metric (no paired test was run); LR is the cheapest in flash and the only one the firmware already supports.\n")

    A("## 8. Waist → wrist domain gap\n")
    a, b, c_ = S("baseline_52"), S("lr_52_trig"), S("lr_26_trig")
    A("| model | recall trigger-only | ADL trigger-only FAR | recall with confirm (eligible; coverage) | ADL confirmed FAR |\n|---|---|---|---|---|")
    for lab, s in (("SisFall-waist LR, unchanged, 52 Hz (thr 0.93)", a), ("Wrist LR @ 52 Hz (mode B)", b), ("Wrist LR @ 26 Hz (mode B)", c_)):
        A(f"| {lab} | {pct(s,'fall_recall_trigger')} | {pct(s,'adl_far_trigger')} | {pct(s,'fall_recall_confirm')}; {int(s.loc['fall_recall_confirm','n_den'])}/{int(s.loc['fall_recall_trigger','n_den'])} | {pct(s,'adl_far_confirm')} |")
    A("\nThe waist model transfers poorly: at its own fixed threshold it detects the minority of wrist falls while still triggering on about a third of ADL trials. The comparison is not threshold-matched (the baseline is unchanged by construction); the wrist LR at its tuned threshold reaches 95 % trigger-only recall at a similar ADL trigger-only false-alarm rate.\n")

    A("## 9. BITS wrist IMU+HR (ages 20–47) held-out run — ON HOLD\n")
    A(f"- Preprocessed (`acg`, g, 20→26 Hz and 20→52 Hz) and filtered by the pre-specified rules; no model has seen it.")
    A(f"- Rule 4 (rest |a| of `acg` within 1 ± 0.1 g): {len(b4)} of {len(bits)} files dropped (0 falls, {len(b4)} ADL) → {len(ok4)} files remain ({sum(r['is_fall'] for r in ok4)} falls, {sum(not r['is_fall'] for r in ok4)} ADL).")
    A(f"- Rule 5 (|timestamp span − N/20| > 10 % ⇒ drop) is **skipped by decision**: it would have dropped {len(b5)} of {len(ok4)} files (falls {sum(r['is_fall'] for r in b5)} of {sum(r['is_fall'] for r in ok4)}) because the timestamps keep only 3 significant digits. **Assumption: 20 Hz by sample order.**")
    A("- Index → activity: not documented in the paper's text; per-index energy follows the paper's table (jogging/jumping highest, lying lowest, seated falls gentlest), so per-fall-type recall can be computed with an *inferred* mapping once the run is released (`DATA_CARD.md` §6).")
    A("- Caveat that will accompany the result: 20 Hz is assumed by sample order; the HR-block cross-check (median 20.2 samples per HR row, IQR 7–51) is consistent at the median only.\n")

    A("## 10. Export and C parity\n")
    A(f"`include/fall_model.h` and `include/test_windows.h` (12 real train-pool windows + 6 stillness segments for the long-lie placeholder, taken from WEDA-FALL only because SmartFallMM is all-rights-reserved, with expected features, probabilities and decisions; every float literal is positional with a decimal point before `f`). `firmware/fall_imu/include/` was not modified. "
      f"Header fixes vs the reference exporter: all rate macros incl. TILT_PRE/POST/FALLBACK, POST_STD and `MODEL_IMU_ODR_ENUM = LSM6DSXX_DATA_RATE_26HZ` (imu.c already selects 26 Hz from `SAMPLE_RATE_HZ`); the (placeholder, long-lie) stillness thresholds are emitted as the macros `FALL_STILL_STD_THR / FALL_STILL_MEAN_TOL` — the reference header's `static const STILL_STD_THR` is never read by `fall_features.h`, so a tuned std would have been ignored on the device.\n")
    A(open(os.path.join(RES, "PARITY.md")).read().split("\n", 1)[1])
    A("\n## 11. Caveats\n")
    A("- The recall target (operating point) is still to be chosen (§6.5); the exported threshold is the 95 % point and the stillness parameters are long-lie placeholders.\n"
      "- SmartFallMM falls are manually cropped and short: only a subset is confirm-eligible, and the post-fall segment length is determined by the crop, not by the person; WEDA falls were done on a mattress by young participants.\n"
      "- ADL false-alarm rates are per trial of very different lengths (WEDA/SFMM trials from seconds to minutes) — compare with the per-hour columns.\n"
      "- Subject-level CIs are wide for per-fall-type and young/old splits (few subjects); elderly data come from ADL only (WEDA 11, SmartFallMM old folder 24 subjects), so elderly *fall* detection is untested.\n"
      "- SmartFallMM is © SmartFall Group, Texas State University, all rights reserved, credit required; only derived model weights/aggregate results are in git, no raw or resampled data.\n")
    A("## 12. Reproduce\n")
    A("```\ncd ml/fall-detection-wrist && python3 -m venv .venv && .venv/bin/pip install numpy scipy pandas scikit-learn\n"
      ".venv/bin/python -I src/data_card.py && .venv/bin/python -I src/preprocess.py && .venv/bin/python -I src/exclusion_log.py\n"
      ".venv/bin/python -I src/test_preprocess.py && .venv/bin/python -I src/test_features.py && .venv/bin/python -I src/rate_leak_check.py\n"
      ".venv/bin/python -I src/build_dataset.py\n"
      "for m in 'lr 26' 'lr 52' 'tree 26' 'mlp 26'; do set -- $m; for g in spec trig ext; do .venv/bin/python -I src/eval_nested.py --model $1 --fs $2 --grid $g; done; done   # resumable per fold\n"
      ".venv/bin/python -I src/eval_baseline.py && .venv/bin/python -I src/final_model.py && .venv/bin/python -I src/export_final.py\n"
      ".venv/bin/python -I src/parity.py && .venv/bin/python -I src/flash_size.py && .venv/bin/python -I src/make_report.py\n```\n")
    R3.write_extra()
    L += appx
    open(os.path.join(RES, "REPORT.md"), "w").write("\n".join(L) + "\n")
    print("wrote REPORT.md", len("\n".join(L)))


if __name__ == "__main__":
    main()
