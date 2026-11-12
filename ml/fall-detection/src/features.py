import os
import re
import glob
import numpy as np
import pandas as pd
from scipy.signal import resample_poly

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "SisFall_dataset")
OUT = os.path.join(ROOT, "data", "features.csv")

FS_IN = 200
FS_OUT = 52
UP, DOWN = 26, 100  # 200 * 26/100 = 52
WIN = 104            # 2 s @ 52 Hz
STRIDE = 26          # 0.5 s
G_FACTOR = (2 * 16) / (2 ** 13)  # ADXL345: 32/8192

FEATURE_NAMES = ["max_mag", "min_mag", "mean_mag", "std_mag", "range_mag",
                 "max_jerk", "std_mag_post", "count_low"]


def parse_file(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip().rstrip(";").strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
    arr = np.asarray(rows, dtype=float) * G_FACTOR
    # resample each axis 200 -> 52 Hz
    out = np.column_stack([resample_poly(arr[:, i], UP, DOWN) for i in range(3)])
    return out


def mag(a):
    return np.sqrt((a ** 2).sum(axis=1))


def features_of_window(w):
    m = mag(w)
    jerk = np.abs(np.diff(m))
    post = m[-52:] if len(m) >= 52 else m
    return [
        float(m.max()),
        float(m.min()),
        float(m.mean()),
        float(m.std()),
        float(m.max() - m.min()),
        float(jerk.max()) if len(jerk) else 0.0,
        float(post.std()),
        float((m < 0.5).sum()),
    ]


def process_file(path):
    subj = re.search(r"_([A-Z]{2}\d{2})_", os.path.basename(path)).group(1)
    is_fall = os.path.basename(path).startswith("F")
    sig = parse_file(path)
    m = mag(sig)
    n = len(sig)
    rows = []
    if not is_fall:
        # every window ADL
        start = 0
        while start + WIN <= n:
            w = sig[start:start + WIN]
            rows.append((subj, os.path.basename(path), 0, features_of_window(w)))
            start += STRIDE
    else:
        # impact peak
        peak = int(np.argmax(m))
        win_start = peak - int(0.4 * WIN)
        win_start = max(0, min(win_start, n - WIN))
        if win_start + WIN <= n:
            w = sig[win_start:win_start + WIN]
            rows.append((subj, os.path.basename(path), 1, features_of_window(w)))
    return rows


def main():
    files = sorted(glob.glob(os.path.join(DATA, "*", "*.txt")))
    all_rows = []
    for fp in files:
        all_rows.extend(process_file(fp))
    df = pd.DataFrame(
        [{"subject": r[0], "file": r[1], "label": r[2],
          **dict(zip(FEATURE_NAMES, r[3]))} for r in all_rows]
    )
    df.to_csv(OUT, index=False)
    print("total windows:", len(df))
    print("class counts:", df["label"].value_counts().to_dict())
    # per age group
    df["group"] = df["subject"].str[:2]
    print("\nclass counts per age group:")
    print(df.groupby(["group", "label"]).size().unstack(fill_value=0))
    print("\nsaved:", OUT)


if __name__ == "__main__":
    main()
