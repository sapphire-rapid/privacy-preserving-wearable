import os
import re
import glob
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
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
    return out

def mag(a): return np.sqrt((a ** 2).sum(axis=1))

def tilt_deg(sig):
    m = mag(sig)
    peak = int(np.argmax(m))
    if peak >= 26:
        before = sig[peak - 26:peak]
    else:
        before = sig[:10]
    after = sig[-26:] if len(sig) >= 26 else sig
    u = before.mean(axis=0); v = after.mean(axis=0)
    nu = np.linalg.norm(u); nv = np.linalg.norm(v)
    if nu == 0 or nv == 0: return 0.0
    cos = np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos)))

def wfeat(w):
    m = mag(w)
    jerk = np.abs(np.diff(m))
    post = m[-52:] if len(m) >= 52 else m
    return [float(m.max()), float(m.min()), float(m.mean()), float(m.std()),
            float(m.max() - m.min()), float(jerk.max()) if len(jerk) else 0.0,
            float(post.std()), float((m < 0.5).sum()), tilt_deg(w)]

trials_csv = os.path.join(DATA, "features_trials_v2.csv")
if not os.path.exists(trials_csv):
    files = sorted(glob.glob(os.path.join(SIS, "*", "*.txt")))
    recs = []
    for fp in files:
        bn = os.path.basename(fp)
        subj = re.search(r"_([A-Z]{2}\d{2})_", bn).group(1)
        activity = bn[:3]
        ttype = "F" if bn.startswith("F") else "D"
        age = subj[:2]
        sig = parse_raw(fp)
        n = len(sig)
        wi = 0; start = 0
        while start + WIN <= n:
            w = sig[start:start + WIN]
            recs.append({"subject": subj, "file": bn, "window_idx": wi,
                         "trial_type": ttype, "activity": activity,
                         "age_group": age, **dict(zip(FEATURES, wfeat(w)))})
            start += STRIDE; wi += 1
    tdf = pd.DataFrame(recs)
    tdf.to_csv(trials_csv, index=False)
    print("Built features_trials_v2.csv:", len(tdf), "windows")
else:
    print("Using existing features_trials_v2.csv")
tdf = pd.read_csv(trials_csv)

dur = {}
for fp in glob.glob(os.path.join(SIS, "*", "*.txt")):
    with open(fp) as f:
        cnt = sum(1 for line in f if line.strip())
    dur[os.path.basename(fp)] = cnt / FS_IN

fdf = pd.read_csv(os.path.join(DATA, "features_v2.csv"))
Xtr_all = fdf[FEATURES].values.astype(float)
ytr_all = fdf["label"].values.astype(int)
groups_tr = fdf["subject"].values

gkf = GroupKFold(n_splits=5)
models_cache = {}

def train_model(train_subjects, model_kind):
    tr_idx = np.array([s in train_subjects for s in groups_tr])
    X = Xtr_all[tr_idx]; y = ytr_all[tr_idx]
    if model_kind == "tree":
        m = DecisionTreeClassifier(max_depth=5, class_weight="balanced", random_state=42)
        m.fit(X, y); scaler = None
    else:
        scaler = StandardScaler(); Xs = scaler.fit_transform(X)
        m = LogisticRegression(class_weight="balanced", max_iter=1000)
        m.fit(Xs, y)
    return m, scaler

def get_model(model_kind, held_list):
    key = (model_kind, tuple(sorted(held_list)))
    if key in models_cache:
        return models_cache[key]
    train_subjects = set(groups_tr) - set(held_list)
    m, scaler = train_model(train_subjects, model_kind)
    models_cache[key] = (m, scaler)
    return m, scaler

all_trials = {"tree": [], "lr": []}
for tr_idx, te_idx in gkf.split(Xtr_all, ytr_all, groups_tr):
    held = sorted(set(groups_tr[te_idx]))
    for model_kind in ["tree", "lr"]:
        m, scaler = get_model(model_kind, held)
        sub_df = tdf[tdf["subject"].isin(held)]
        for (subj, f), g in sub_df.groupby(["subject", "file"]):
            feats = g[FEATURES].values.astype(float)
            Xs = scaler.transform(feats) if scaler is not None else feats
            probs = m.predict_proba(Xs)[:, 1]
            all_trials[model_kind].append({
                "subject": subj, "file": f,
                "trial_type": "F" if f.startswith("F") else "D",
                "activity": f[:3], "age_group": subj[:2],
                "score": float(probs.max()), "duration": dur[f],
            })

def sweep(model_kind):
    T = pd.DataFrame(all_trials[model_kind])
    fall = T[T["trial_type"] == "F"]
    adl = T[T["trial_type"] == "D"]
    total_adl_hours = adl["duration"].sum() / 3600.0
    thr_list = np.round(np.linspace(0, 1, 101), 4)
    records = []
    for thr in thr_list:
        fr = (fall["score"] >= thr).mean() if len(fall) else 0.0
        af = (adl["score"] >= thr).mean() if len(adl) else 0.0
        n_fa = int((adl["score"] >= thr).sum())
        fph = n_fa / total_adl_hours if total_adl_hours > 0 else 0.0
        adl_se = adl[adl["age_group"] == "SE"]
        se_far = (adl_se["score"] >= thr).mean() if len(adl_se) else 0.0
        records.append({"threshold": thr, "fall_recall": fr, "adl_far": af,
                        "n_fa": n_fa, "fa_per_hour": fph, "se_adl_far": se_far})
    rdf = pd.DataFrame(records)
    cand = rdf[rdf["fall_recall"] >= 0.95]
    if len(cand) == 0: cand = rdf
    best = cand.sort_values(["adl_far", "threshold"], ascending=[True, False]).iloc[0]
    return rdf, best, T, adl

v2_results = {}
for model_kind, label in [("tree", "DecisionTree"), ("lr", "LogisticRegression")]:
    rdf, best, T, adl = sweep(model_kind)
    rdf.to_csv(os.path.join(RESULTS, f"trial_sweep_v2_{model_kind}.csv"), index=False)
    print(f"\n===== v2 {label} =====")
    print(f"Chosen threshold: {best['threshold']:.4f}")
    print(f"  fall-trial recall: {best['fall_recall']:.4f}")
    print(f"  ADL-trial FAR: {best['adl_far']:.4f}")
    print(f"  false alarms/hour: {best['fa_per_hour']:.4f} ({int(best['n_fa'])} trials)")
    print(f"  elderly (SE) ADL FAR: {best['se_adl_far']:.4f}")
    v2_results[model_kind] = best
    with open(os.path.join(RESULTS, f"best_v2_{model_kind}.txt"), "w") as f:
        f.write(f"threshold={best['threshold']:.4f}\nrecall={best['fall_recall']:.4f}\n"
                f"adl_far={best['adl_far']:.4f}\nfa_per_hour={best['fa_per_hour']:.4f}\n"
                f"se_adl_far={best['se_adl_far']:.4f}\n")

# side-by-side comparison v1 vs v2
print("\n========== SIDE-BY-SIDE v1 vs v2 ==========")
print(f"{'model':<6}{'ver':<4}{'thr':>8}{'recall':>10}{'adl_far':>10}{'fa/hr':>10}{'se_far':>10}")
for model_kind in ["tree", "lr"]:
    # v1
    b1 = {}
    p = os.path.join(RESULTS, f"best_{model_kind}.txt")
    for line in open(p):
        k, v = line.strip().split("="); b1[k] = float(v)
    b2 = {}
    p2 = os.path.join(RESULTS, f"best_v2_{model_kind}.txt")
    for line in open(p2):
        k, v = line.strip().split("="); b2[k] = float(v)
    print(f"{model_kind:<6}{'v1':<4}{b1['threshold']:>8.4f}{b1['recall']:>10.4f}{b1['adl_far']:>10.4f}{b1['fa_per_hour']:>10.4f}{b1['se_adl_far']:>10.4f}")
    print(f"{model_kind:<6}{'v2':<4}{b2['threshold']:>8.4f}{b2['recall']:>10.4f}{b2['adl_far']:>10.4f}{b2['fa_per_hour']:>10.4f}{b2['se_adl_far']:>10.4f}")
