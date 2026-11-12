import os
import glob
import json
import argparse
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

print("BOOT", flush=True)
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
    out = np.column_stack([__import__("scipy.signal", fromlist=["resample_poly"]).resample_poly(arr[:, i], UP, DOWN) for i in range(3)])
    return np.sqrt((out ** 2).sum(axis=1))

mag_cache = {}
for fp in glob.glob(os.path.join(SIS, "*", "*.txt")):
    mag_cache[os.path.basename(fp)] = parse_raw(fp)

tdf = pd.read_csv(os.path.join(DATA, "features_trials_v2.csv"))
fdf = pd.read_csv(os.path.join(DATA, "features_v2.csv"))
Xtr_all = fdf[FEATURES].values.astype(float)
ytr_all = fdf["label"].values.astype(int)
groups_tr = fdf["subject"].values

parser = argparse.ArgumentParser()
parser.add_argument("--fast", action="store_true")
args = parser.parse_args()

N_OUTER = 2 if args.fast else 5
PROB_STEP = 0.05 if args.fast else 0.01
PROB_THRS = np.round(np.arange(0.0, 1.0001, PROB_STEP), 2)

outer_gkf = GroupKFold(n_splits=N_OUTER)
inner_gkf = GroupKFold(n_splits=3)

STD_THRS = [0.03, 0.05, 0.08, 0.12, 0.2]
CONF_LENS = [1.5, 2.0, 3.0]
PROB_THRS = np.round(np.arange(0.0, 1.0001, 0.01), 2)

def window_probs_for_subjects(train_subjects, score_subjects):
    tr_mask = np.array([s in train_subjects for s in groups_tr])
    X = Xtr_all[tr_mask]; y = ytr_all[tr_mask]
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(Xs, y)
    wmap = {}
    for subj in score_subjects:
        for fn in sorted(set(tdf[tdf["subject"] == subj]["file"])):
            g = tdf[(tdf["subject"] == subj) & (tdf["file"] == fn)].sort_values("window_idx")
            feats = g[FEATURES].values.astype(float)
            probs = model.predict_proba(scaler.transform(feats))[:, 1]
            wmap[(subj, fn)] = probs.tolist()
    return wmap

def make_trial_records(subjects, wmap):
    recs = []
    for subj in subjects:
        for fn in sorted(set(tdf[tdf["subject"] == subj]["file"])):
            g = tdf[(tdf["subject"] == subj) & (tdf["file"] == fn)].sort_values("window_idx")
            recs.append({
                "subject": subj, "file": fn,
                "trial_type": "F" if fn.startswith("F") else "D",
                "age_group": subj[:2],
                "duration": len(mag_cache[fn]) / 52.0,
                "mag": mag_cache[fn],
                "wis": g["window_idx"].tolist(),
                "probs": wmap[(subj, fn)],
            })
    return recs

def stillness_for_window(rec, wi, std_thr, conf_len):
    conf_samples = int(conf_len * 52)
    start = wi * STRIDE
    seg_start = start + WIN
    seg_end = seg_start + conf_samples
    magarr = rec["mag"]
    if seg_end > len(magarr):
        return None  # past end -> conservative True handled separately
    seg = magarr[seg_start:seg_end]
    return (seg.std() < std_thr) and (abs(seg.mean() - 1.0) < 0.2)

def trial_still_score(rec, std_thr, conf_len):
    # max prob among windows whose confirmation segment is still (or past end -> treat as still)
    best = -1.0
    for wi, prob in zip(rec["wis"], rec["probs"]):
        st = stillness_for_window(rec, wi, std_thr, conf_len)
        is_still = True if st is None else st
        if is_still and prob > best:
            best = prob
    return best  # -1 if none

def choose_params(trial_recs):
    # returns (thr, std, conf)
    best = None  # (adl_far, -thr, thr, std, conf)
    for std_thr in STD_THRS:
        for conf_len in CONF_LENS:
            # compute still score per trial
            scored = []
            for r in trial_recs:
                ss = trial_still_score(r, std_thr, conf_len)
                scored.append((r, ss))
            fall_scores = [ss for r, ss in scored if r["trial_type"] == "F"]
            adl_scores = [ss for r, ss in scored if r["trial_type"] == "D"]
            fall_total = len(fall_scores)
            adl_total = len(adl_scores)
            # For each thr, fall_recall = # fall with ss>=thr / total
            # adl_far = # adl with ss>=thr / total
            # sweep thr over sorted unique scores + 0/1
            cand_thrs = sorted(set([0.0, 1.0] + [s for s in fall_scores + adl_scores if s >= 0]))
            for thr in cand_thrs:
                fr = sum(1 for s in fall_scores if s >= thr) / fall_total
                af = sum(1 for s in adl_scores if s >= thr) / adl_total
                if fr >= 0.95:
                    key = (af, -thr)
                    if best is None or key < best[0]:
                        best = (key, thr, std_thr, conf_len, fr, af)
    if best is None:
        # fallback
        best = None
        for std_thr in STD_THRS:
            for conf_len in CONF_LENS:
                scored = [(r, trial_still_score(r, std_thr, conf_len)) for r in trial_recs]
                fall_scores = [ss for r, ss in scored if r["trial_type"] == "F"]
                adl_scores = [ss for r, ss in scored if r["trial_type"] == "D"]
                for thr in [0.5]:
                    fr = sum(1 for s in fall_scores if s >= thr) / len(fall_scores)
                    af = sum(1 for s in adl_scores if s >= thr) / len(adl_scores)
                    if best is None or fr > best[4]:
                        best = ((af, -thr), thr, std_thr, conf_len, fr, af)
    return best[1], best[2], best[3]

print("START", flush=True)
# Outer loop
held_outcomes = []
for k, (tr_idx, te_idx) in enumerate(outer_gkf.split(Xtr_all, ytr_all, groups_tr)):
    fold_path = os.path.join(RESULTS, f"nested_fold_{k}.json")
    if os.path.exists(fold_path):
        with open(fold_path) as f:
            d = json.load(f)
        print(f"Fold {k}: resuming from {fold_path} (chosen thr={d['chosen_thr']})")
        for o in d["outcomes"]:
            held_outcomes.append(tuple(o))
        continue
    held_subjects = sorted(set(groups_tr[te_idx]))
    train_subjects = sorted(set(groups_tr[tr_idx]))
    # inner
    inner_wmap = {}
    for itr, ite in inner_gkf.split(np.array(train_subjects), np.array(train_subjects), np.array(train_subjects)):
        inner_train = [train_subjects[i] for i in itr]
        inner_held = [train_subjects[i] for i in ite]
        wmap = window_probs_for_subjects(set(inner_train), inner_held)
        inner_wmap.update(wmap)
    inner_recs = make_trial_records(train_subjects, inner_wmap)
    chosen_thr, chosen_std, chosen_cl = choose_params(inner_recs)
    # final model on all train
    final_wmap = window_probs_for_subjects(set(train_subjects), held_subjects)
    held_recs = make_trial_records(held_subjects, final_wmap)
    fold_outcomes = []
    for r in held_recs:
        ss = trial_still_score(r, chosen_std, chosen_cl)
        alarm = ss >= chosen_thr if ss >= 0 else False
        held_outcomes.append((r["trial_type"], r["age_group"], r["duration"], alarm))
        fold_outcomes.append([r["trial_type"], r["age_group"], r["duration"], bool(alarm)])
    print(f"held {held_subjects[:2]}... chosen thr={chosen_thr:.2f} std={chosen_std} conf={chosen_cl}")
    with open(fold_path, "w") as f:
        json.dump({"chosen_thr": chosen_thr, "chosen_std": chosen_std,
                   "chosen_cl": chosen_cl, "outcomes": fold_outcomes}, f)
    print(f"  saved {fold_path}")

fall_total = sum(1 for o in held_outcomes if o[0] == "F")
adl_total = sum(1 for o in held_outcomes if o[0] == "D")
fall_alarm = sum(1 for o in held_outcomes if o[0] == "F" and o[3])
adl_alarm = sum(1 for o in held_outcomes if o[0] == "D" and o[3])
adl_hours = sum(o[2] for o in held_outcomes if o[0] == "D") / 3600.0
se_adl = [o for o in held_outcomes if o[0] == "D" and o[1] == "SE"]
se_far = sum(1 for o in se_adl if o[3]) / len(se_adl) if se_adl else 0
print("\nChosen params per fold:")
for k in range(N_OUTER):
    fp = os.path.join(RESULTS, f"nested_fold_{k}.json")
    if os.path.exists(fp):
        d = json.load(open(fp))
        print(f"  fold {k}: thr={d['chosen_thr']:.2f} std={d['chosen_std']} conf={d['chosen_cl']}")

print("\n========== NESTED (honest) RESULT ==========")
print(f"Fall recall: {fall_alarm}/{fall_total} = {fall_alarm/fall_total:.4f}")
print(f"ADL FAR: {adl_alarm}/{adl_total} = {adl_alarm/adl_total:.4f}")
print(f"False alarms/hour: {adl_alarm/adl_hours:.4f}")
print(f"Elderly (SE) ADL FAR: {se_far:.4f}")
with open(os.path.join(RESULTS, "nested_result.txt"), "w") as f:
    f.write(f"fall_recall={fall_alarm/fall_total:.4f}\n"
            f"adl_far={adl_alarm/adl_total:.4f}\n"
            f"fa_per_hour={adl_alarm/adl_hours:.4f}\n"
            f"se_adl_far={se_far:.4f}\n")
print("Saved results/nested_result.txt")
