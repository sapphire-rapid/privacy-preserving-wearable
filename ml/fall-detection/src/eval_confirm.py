import os
import re
import glob
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from scipy.signal import resample_poly

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RESULTS = os.path.join(ROOT, "results")
os.makedirs(RESULTS, exist_ok=True)

FS_IN = 200; UP, DOWN = 26, 100
WIN = 104; STRIDE = 26
G_FACTOR = (2 * 16) / (2 ** 13)
FEATURES = ["max_mag", "min_mag", "mean_mag", "std_mag", "range_mag",
            "max_jerk", "std_mag_post", "count_low", "tilt_deg"]
SIS = os.path.join(DATA, "SisFall_dataset")

# raw resampled magnitude per file
def parse_raw(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip().rstrip(";").strip()
            if not line: continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3: continue
            rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
    arr = np.asarray(rows, dtype=float) * G_FACTOR
    out = np.column_stack([resample_poly(arr[:, i], UP, DOWN) for i in range(3)])
    return np.sqrt((out ** 2).sum(axis=1))

mag_cache = {}
for fp in glob.glob(os.path.join(SIS, "*", "*.txt")):
    mag_cache[os.path.basename(fp)] = parse_raw(fp)

# trial windows with features v2
tdf = pd.read_csv(os.path.join(DATA, "features_trials_v2.csv"))
fdf = pd.read_csv(os.path.join(DATA, "features_v2.csv"))
Xtr_all = fdf[FEATURES].values.astype(float)
ytr_all = fdf["label"].values.astype(int)
groups_tr = fdf["subject"].values

gkf = GroupKFold(n_splits=5)

# map trial -> list of (window_idx, feature row)
def trial_windows(subj, fn):
    g = tdf[(tdf["subject"] == subj) & (tdf["file"] == fn)].sort_values("window_idx")
    return g

# Build pooled held-out trial records with per-window probs
# Each record: subject, file, trial_type, activity, age_group, duration, mag array, peak_idx, windows(list of (wi, prob))
all_records = []  # one per trial
for tr_idx, te_idx in gkf.split(Xtr_all, ytr_all, groups_tr):
    held = sorted(set(groups_tr[te_idx]))
    train_subjects = set(groups_tr) - set(held)
    tr_mask = np.array([s in train_subjects for s in groups_tr])
    X = Xtr_all[tr_mask]; y = ytr_all[tr_mask]
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(Xs, y)
    # score held-out trials
    for subj in held:
        files = sorted(set(tdf[tdf["subject"] == subj]["file"]))
        for fn in files:
            g = trial_windows(subj, fn)
            feats = g[FEATURES].values.astype(float)
            probs = model.predict_proba(scaler.transform(feats))[:, 1]
            wins = list(zip(g["window_idx"].tolist(), probs.tolist()))
            magarr = mag_cache[fn]
            all_records.append({
                "subject": subj, "file": fn,
                "trial_type": "F" if fn.startswith("F") else "D",
                "activity": fn[:3], "age_group": subj[:2],
                "duration": len(magarr) / 52.0,
                "mag": magarr,
                "peak_idx": int(np.argmax(magarr)),
                "windows": wins,
            })

records_df = pd.DataFrame([{k: v for k, v in r.items() if k not in ("mag", "windows")} for r in all_records])
print("Pooled held-out trials:", len(all_records),
      "F:", sum(r["trial_type"] == "F" for r in all_records),
      "D:", sum(r["trial_type"] == "D" for r in all_records))

STD_THRS = [0.03, 0.05, 0.08, 0.12, 0.2]
CONF_LENS = [1.5, 2.0, 3.0]
PROB_THRS = np.round(np.arange(0.0, 1.01, 0.01), 2)

def trial_alarm(rec, prob_thr, std_thr, conf_len, conf_samples):
    # returns (alarm bool, latency_sec or None, n_past_end)
    past_end = 0
    for wi, prob in rec["windows"]:
        if prob < prob_thr:
            continue
        start = wi * STRIDE
        seg_start = start + WIN
        seg_end = seg_start + conf_samples
        magarr = rec["mag"]
        if seg_end > len(magarr):
            # cannot fully evaluate -> conservative confirmed
            past_end += 1
            return True, None, past_end  # alarm
        seg = magarr[seg_start:seg_end]
        if seg.std() < std_thr and abs(seg.mean() - 1.0) < 0.2:
            # confirmed
            end_sec = seg_end / 52.0
            peak_sec = rec["peak_idx"] / 52.0
            latency = end_sec - peak_sec
            return True, latency, past_end
    return False, None, past_end

# Grid evaluation
rows = []
# baseline no-confirmation: alarm if any window prob>=thr
# compute baseline chosen thr
def baseline_metrics(prob_thr):
    fall_total = sum(1 for r in all_records if r["trial_type"] == "F")
    adl_total = sum(1 for r in all_records if r["trial_type"] == "D")
    fall_alarm = 0; adl_alarm = 0
    for r in all_records:
        if any(p >= prob_thr for _, p in r["windows"]):
            if r["trial_type"] == "F": fall_alarm += 1
            else: adl_alarm += 1
    fr = fall_alarm / fall_total
    af = adl_alarm / adl_total
    adl_hours = sum(r["duration"] for r in all_records if r["trial_type"] == "D") / 3600.0
    fph = adl_alarm / adl_hours
    se_adl = [r for r in all_records if r["trial_type"] == "D" and r["age_group"] == "SE"]
    se_far = sum(1 for r in se_adl if any(p >= prob_thr for _, p in r["windows"])) / len(se_adl)
    return fr, af, fph, se_far, adl_alarm

# baseline chosen
best_base = None
for thr in PROB_THRS:
    fr, af, fph, se_far, nfa = baseline_metrics(thr)
    if fr >= 0.95:
        if best_base is None or af < best_base[1]:
            best_base = (thr, fr, af, fph, se_far, nfa)
bthr, bfr, baf, bfph, bse, bnfa = best_base
rows.append({
    "STD_THR": None, "CONFIRM_LEN": None, "prob_thr": bthr,
    "fall_recall": bfr, "adl_far": baf, "fa_per_hour": bfph,
    "se_adl_far": bse, "n_fa": bnfa, "label": "baseline_no_confirm",
})

past_end_total = 0
for std_thr in STD_THRS:
    for conf_len in CONF_LENS:
        conf_samples = int(conf_len * 52)
        # sweep prob_thr
        best = None
        for thr in PROB_THRS:
            fall_total = sum(1 for r in all_records if r["trial_type"] == "F")
            adl_total = sum(1 for r in all_records if r["trial_type"] == "D")
            fa_fall = 0; fa_adl = 0; n_fa = 0
            for r in all_records:
                alarm, lat, pe = trial_alarm(r, thr, std_thr, conf_len, conf_samples)
                if alarm:
                    if r["trial_type"] == "F": fa_fall += 1
                    else: fa_adl += 1; n_fa += 1
            fr = fa_fall / fall_total
            af = fa_adl / adl_total
            adl_hours = sum(r["duration"] for r in all_records if r["trial_type"] == "D") / 3600.0
            fph = fa_adl / adl_hours
            se_adl = [r for r in all_records if r["trial_type"] == "D" and r["age_group"] == "SE"]
            se_far = sum(1 for r in se_adl if trial_alarm(r, thr, std_thr, conf_len, conf_samples)[0]) / len(se_adl)
            if fr >= 0.95:
                if best is None or af < best[2] or (af == best[2] and thr > best[0]):
                    best = (thr, fr, af, fph, se_far, n_fa)
        if best is None:
            # fallback: highest recall
            best = None
            for thr in PROB_THRS:
                fall_total = sum(1 for r in all_records if r["trial_type"] == "F")
                adl_total = sum(1 for r in all_records if r["trial_type"] == "D")
                fa_fall = 0; fa_adl = 0; n_fa = 0
                for r in all_records:
                    alarm, lat, pe = trial_alarm(r, thr, std_thr, conf_len, conf_samples)
                    if alarm:
                        if r["trial_type"] == "F": fa_fall += 1
                        else: fa_adl += 1; n_fa += 1
                fr = fa_fall / fall_total
                af = fa_adl / adl_total
                adl_hours = sum(r["duration"] for r in all_records if r["trial_type"] == "D") / 3600.0
                fph = fa_adl / adl_hours
                se_adl = [r for r in all_records if r["trial_type"] == "D" and r["age_group"] == "SE"]
                se_far = sum(1 for r in se_adl if trial_alarm(r, thr, std_thr, conf_len, conf_samples)[0]) / len(se_adl)
                if best is None or fr > best[1] or (fr == best[1] and af < best[2]):
                    best = (thr, fr, af, fph, se_far, n_fa)
        thr, fr, af, fph, se_far, nfa = best
        rows.append({
            "STD_THR": std_thr, "CONFIRM_LEN": conf_len, "prob_thr": thr,
            "fall_recall": fr, "adl_far": af, "fa_per_hour": fph,
            "se_adl_far": se_far, "n_fa": nfa, "label": "confirm",
        })

grid = pd.DataFrame(rows)
grid.to_csv(os.path.join(RESULTS, "confirm_grid.csv"), index=False)
# print table
print("\nSTD_THR  CONFIRM_LEN  prob_thr  fall_recall  adl_far  fa/hr    se_far")
for _, r in grid.iterrows():
    st = "None" if pd.isna(r["STD_THR"]) else f"{r['STD_THR']:.2f}"
    cl = "None" if pd.isna(r["CONFIRM_LEN"]) else f"{r['CONFIRM_LEN']:.1f}"
    print(f"{st:>7}  {cl:>11}  {r['prob_thr']:>8.2f}  {r['fall_recall']:>11.4f}  {r['adl_far']:>7.4f}  {r['fa_per_hour']:>7.2f}  {r['se_adl_far']:>6.4f}")

# best row overall: lowest fa_per_hour among confirm rows with recall>=0.95
conf_rows = grid[(grid["label"] == "confirm") & (grid["fall_recall"] >= 0.95)]
best_overall = conf_rows.sort_values(["fa_per_hour", "adl_far"]).iloc[0]
print("\nBest overall:", best_overall.to_dict())

# best params
best_std = float(best_overall["STD_THR"])
best_cl = float(best_overall["CONFIRM_LEN"])
best_thr = float(best_overall["prob_thr"])
best_conf_samples = int(best_cl * 52)

# (a) fall recall per fall code
print("\n(a) Fall recall per fall code (best params):")
fall_recs = [r for r in all_records if r["trial_type"] == "F"]
from collections import defaultdict
code_stats = defaultdict(lambda: [0, 0])
latencies = []
for r in fall_recs:
    alarm, lat, pe = trial_alarm(r, best_thr, best_std, best_cl, best_conf_samples)
    code_stats[r["activity"]][1] += 1
    if alarm:
        code_stats[r["activity"]][0] += 1
        if lat is not None:
            latencies.append(lat)
for code in sorted(code_stats):
    tp, tot = code_stats[code]
    print(f"  {code}: {tp}/{tot} = {tp/tot:.3f}")

# (b) top ADL codes still causing false alarms
print("\n(b) Top ADL codes causing false alarms (best params):")
adl_recs = [r for r in all_records if r["trial_type"] == "D"]
fa_codes = defaultdict(int)
for r in adl_recs:
    alarm, lat, pe = trial_alarm(r, best_thr, best_std, best_cl, best_conf_samples)
    if alarm:
        fa_codes[r["activity"]] += 1
for code, c in sorted(fa_codes.items(), key=lambda x: -x[1]):
    print(f"  {code}: {c}")

# (c) alert latency
print(f"\n(c) Alert latency: mean {np.mean(latencies):.2f}s (n={len(latencies)})")

# count D trials where segment past end
past_end_count = 0
for r in adl_recs:
    # recompute
    for wi, prob in r["windows"]:
        if prob < best_thr: continue
        start = wi * STRIDE
        seg_end = start + WIN + best_conf_samples
        if seg_end > len(r["mag"]):
            past_end_count += 1
            break
print(f"\nD trials with a trigger segment running past trial end (conservative): {past_end_count}")

# save best params
with open(os.path.join(RESULTS, "best_confirm.txt"), "w") as f:
    f.write(f"prob_thr={best_thr:.2f}\nSTD_THR={best_std}\nCONFIRM_LEN={best_cl}\n"
            f"fall_recall={best_overall['fall_recall']:.4f}\nadl_far={best_overall['adl_far']:.4f}\n"
            f"fa_per_hour={best_overall['fa_per_hour']:.4f}\nse_adl_far={best_overall['se_adl_far']:.4f}\n")
print("\nSaved results/confirm_grid.csv and best_confirm.txt")
