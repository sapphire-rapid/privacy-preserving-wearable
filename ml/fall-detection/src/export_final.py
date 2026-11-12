import os
import re
import glob
import numpy as np
import pandas as pd
from scipy.signal import resample_poly
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
INC = os.path.join(ROOT, "include")
SIS = os.path.join(DATA, "SisFall_dataset")
os.makedirs(INC, exist_ok=True)

FS_IN = 200; UP, DOWN = 26, 100
WIN = 104; STRIDE = 26
G_FACTOR = (2 * 16) / (2 ** 13)
FEATURES = ["max_mag", "min_mag", "mean_mag", "std_mag", "range_mag",
            "max_jerk", "std_mag_post", "count_low", "tilt_deg"]

def flt(x):
    s = f"{float(x):.9g}"
    if "." not in s and "e" not in s and "E" not in s:
        s += ".0"
    return s + "f"

def parse_raw_xyz(path):
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
    before = sig[peak-26:peak] if peak >= 26 else sig[:10]
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
    return np.array([float(m.max()), float(m.min()), float(m.mean()), float(m.std()),
            float(m.max() - m.min()), float(jerk.max()) if len(jerk) else 0.0,
            float(post.std()), float((m < 0.5).sum()), tilt_deg(w)], dtype=np.float32)

if __name__ == "__main__":
    # 1. Train final LR on all 38
    fdf = pd.read_csv(os.path.join(DATA, "features_v2.csv"))
    X = fdf[FEATURES].values.astype(float)
    y = fdf["label"].values.astype(int)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(Xs, y)
    print("Trained final LR on", len(fdf), "windows,", fdf["subject"].nunique(), "subjects")

    mean = scaler.mean_
    scale = scaler.scale_
    coef = model.coef_[0]
    intercept = model.intercept_[0]

    prob_thr = 0.93
    std_thr = 0.05
    mean_tol = 0.2
    confirm_len_s = 3.0
    confirm_samples = int(confirm_len_s * 52)

    # 2. Write fall_model.h
    def arr(name, vals):
        return "static const float " + name + "[] = {\n    " + ", ".join(flt(v) for v in vals) + "\n};"

    h = []
    h.append("#ifndef FALL_MODEL_H")
    h.append("#define FALL_MODEL_H")
    h.append("")
    h.append("#define N_FEATURES 9")
    h.append("/* Feature order (features_v2.py):")
    for i, fn in enumerate(FEATURES):
        h.append(f" *  {i}: {fn}")
    h.append(" */")
    h.append("")
    h.append(arr("FALL_MEAN", mean))
    h.append(arr("FALL_SCALE", scale))
    h.append(arr("FALL_COEF", coef))
    h.append(f"static const float FALL_INTERCEPT = {flt(intercept)};")
    h.append(f"static const float FALL_PROB_THR = {flt(prob_thr)};")
    h.append(f"static const float STILL_STD_THR = {flt(std_thr)};")
    h.append(f"static const float STILL_MEAN_TOL = {flt(mean_tol)};")
    h.append(f"#define CONFIRM_SAMPLES {confirm_samples}")
    h.append(f"#define WIN_SAMPLES {WIN}")
    h.append(f"#define STRIDE_SAMPLES {STRIDE}")
    h.append(f"#define SAMPLE_RATE_HZ {52}")
    h.append("")
    h.append("#endif")
    with open(os.path.join(INC, "fall_model.h"), "w") as f:
        f.write("\n".join(h) + "\n")
    print("wrote fall_model.h")

    # 3. test_windows.h
    # pick 6 fall impact windows, 6 ADL windows (include 2 hard ADL)
    rng = np.random.default_rng(7)
    fall_files = sorted(glob.glob(os.path.join(SIS, "*", "F*.txt")))
    adl_files = sorted(glob.glob(os.path.join(SIS, "*", "D*.txt")))
    # hard ADL: jogging (D03/D04) and jumping (D19)
    hard_adl = [f for f in adl_files if os.path.basename(f)[:3] in ("D03", "D04", "D19")]

    def impact_window_xyz(path):
        sig = parse_raw_xyz(path)
        m = mag(sig)
        peak = int(np.argmax(m))
        start = peak - int(0.4 * WIN)
        start = max(0, min(start, len(sig) - WIN))
        return sig[start:start + WIN], path

    # 6 falls
    fall_picks = list(rng.choice(fall_files, 6, replace=False))
    # 6 adl: 2 hard + 4 random
    adl_picks = list(rng.choice(hard_adl, 2, replace=False)) + list(rng.choice(adl_files, 4, replace=False))

    def prob_of_window(w):
        f = wfeat(w).astype(float)
        xs = (f - mean) / scale
        logit = float(np.dot(xs, coef) + intercept)
        return 1.0 / (1.0 + np.exp(-logit))

    # Build raw arrays and features
    fall_raws = []
    fall_feats = []
    fall_probs = []
    for fp in fall_picks:
        w, _ = impact_window_xyz(fp)
        fall_raws.append(w)
        fall_feats.append(wfeat(w))
        fall_probs.append(prob_of_window(w))
    adl_raws = []
    adl_feats = []
    adl_probs = []
    for fp in adl_picks:
        sig = parse_raw_xyz(fp)
        # choose a random window
        n = len(sig)
        starts = list(range(0, n - WIN + 1, STRIDE))
        s = int(rng.choice(starts))
        w = sig[s:s + WIN]
        adl_raws.append(w)
        adl_feats.append(wfeat(w))
        adl_probs.append(prob_of_window(w))

    # stillness segments: 3 still, 3 moving, 156 samples of |a|
    def make_still(seg_len=156):
        # gravity ~1g with tiny noise
        return np.abs(np.random.default_rng().normal(1.0, 0.01, seg_len)).astype(np.float32)
    def make_moving(seg_len=156):
        return np.abs(np.random.default_rng().normal(1.0, 0.3, seg_len) + np.sin(np.linspace(0, 6*np.pi, seg_len))*0.5).astype(np.float32)

    still_segs = [make_still() for _ in range(3)] + [make_moving() for _ in range(3)]
    still_labels = [1, 1, 1, 0, 0, 0]

    # Write test_windows.h
    tw = []
    tw.append("#ifndef TEST_WINDOWS_H")
    tw.append("#define TEST_WINDOWS_H")
    tw.append("")
    tw.append("#include \"fall_model.h\"")
    tw.append("")
    tw.append("typedef struct { float xyz[WIN_SAMPLES][3]; float feat[N_FEATURES]; float prob; int trigger; } TestWindow;")
    tw.append("typedef struct { float mag[CONFIRM_SAMPLES]; int is_still; } StillSeg;")
    tw.append("")
    tw.append("static const TestWindow test_windows[] = {")
    for group, raws, feats, probs in [("fall", fall_raws, fall_feats, fall_probs),
                                      ("adl", adl_raws, adl_feats, adl_probs)]:
        for w, f, p in zip(raws, feats, probs):
            tw.append("  {")
            # xyz
            tw.append("    .xyz = {")
            for row in w:
                tw.append(f"      {{{flt(row[0])}, {flt(row[1])}, {flt(row[2])}}},")
            tw.append("    },")
            tw.append("    .feat = {" + ", ".join(flt(v) for v in f) + "},")
            tw.append(f"    .prob = {flt(p)},")
            tw.append(f"    .trigger = {(1 if p >= prob_thr else 0)},")
            tw.append("  },")
    tw.append("};")
    tw.append(f"#define N_TEST_WINDOWS {len(fall_raws)+len(adl_raws)}")
    tw.append("")
    tw.append("static const StillSeg still_segments[] = {")
    for seg, lab in zip(still_segs, still_labels):
        tw.append("  {")
        tw.append("    .mag = {" + ", ".join(flt(v) for v in seg) + "},")
        tw.append(f"    .is_still = {lab},")
        tw.append("  },")
    tw.append("};")
    tw.append(f"#define N_STILL_SEGMENTS {len(still_segs)}")
    tw.append("")
    tw.append("#endif")
    with open(os.path.join(INC, "test_windows.h"), "w") as f:
        f.write("\n".join(tw) + "\n")
    print("wrote test_windows.h")

    print("fall_model.h size:", os.path.getsize(os.path.join(INC, "fall_model.h")), "bytes")
    print("test_windows.h size:", os.path.getsize(os.path.join(INC, "test_windows.h")), "bytes")
    print("\nFirst test window features:", fall_feats[0].tolist())
    print("First test window prob:", fall_probs[0])
    print("\nPaths to copy:")
    print(os.path.join(INC, "fall_model.h"))
    print(os.path.join(INC, "test_windows.h"))
