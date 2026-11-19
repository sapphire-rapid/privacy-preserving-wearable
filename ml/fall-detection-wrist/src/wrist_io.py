"""Raw-file loaders for the three wrist datasets (read-only access to ~/datasets/wrist).

No raw data is copied anywhere; every function takes a path and returns arrays.
Units are returned exactly as stored (native units); conversion to g is done in
preprocess.py so that it is explicit and unit-tested.

SmartFallMM (c) SmartFall Group, Texas State University, all rights reserved.
Credit required: Mauldin et al., "SmartFallMM: A multimodal dataset for fall
detection using commodity devices" (IEEE, 2025), https://github.com/txst-cs-smartfall/SmartFallMM-Dataset
"""
import os
import re
import glob
from datetime import datetime, timezone
import numpy as np

DATA_ROOT = os.path.expanduser("~/datasets/wrist")
WEDA_ROOT = os.path.join(DATA_ROOT, "WEDA-FALL", "dataset")
SFMM_ROOT = os.path.join(DATA_ROOT, "SmartFallMM-Dataset")
BITS_ROOT = os.path.join(DATA_ROOT, "bits_geriatric", "Dataset")

G = 9.80665  # m/s^2 per g

# ----------------------------------------------------------------------------
# WEDA-FALL  (CSV with header; accel_time_list [s], x, y, z in m/s^2)
# ----------------------------------------------------------------------------
WEDA_FALL_CODES = ["F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08"]
WEDA_ADL_CODES = ["D%02d" % i for i in range(1, 12)]


def weda_trials(hz="50Hz"):
    """Yield dicts (code, subject, trial, path, is_fall) for every accel file."""
    out = []
    for p in sorted(glob.glob(os.path.join(WEDA_ROOT, hz, "*", "U*_R*_accel.csv"))):
        code = os.path.basename(os.path.dirname(p))
        m = re.match(r"U(\d+)_R(\d+)_accel\.csv", os.path.basename(p))
        if m is None:      # e.g. U01_R01_vertical_accel.csv (projected accel, not used)
            continue
        out.append(dict(code=code, subject=int(m.group(1)), trial=int(m.group(2)),
                        path=p, is_fall=code.startswith("F")))
    return out


def load_weda(path):
    """-> t [s] (float64), xyz [m/s^2] (N,3)."""
    a = np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.float64, ndmin=2)
    return a[:, 0], a[:, 1:4]


def load_weda_fall_timestamps():
    """fall_timestamps.csv -> {('F01', 1, 1): (start_s, end_s)} keyed (code, subject, trial)."""
    d = {}
    with open(os.path.join(WEDA_ROOT, "fall_timestamps.csv"), encoding="utf-8-sig") as f:
        next(f)
        for line in f:
            fn, s, e = line.strip().split(",")
            code, rest = fn.split("/")
            m = re.match(r"U(\d+)_R(\d+)", rest)
            d[(code, int(m.group(1)), int(m.group(2)))] = (float(s), float(e))
    return d


# ----------------------------------------------------------------------------
# SmartFallMM Meta_wrist accelerometer (no header; epoch ms, iso time, elapsed s, x, y, z in g)
# ----------------------------------------------------------------------------
SFMM_ACTIVITY = {  # from the dataset README ("Activities and Labels")
    1: "Drinking Water", 2: "Pick Up Object", 3: "Put On and Take Off Jacket",
    4: "Stepping Up", 5: "Sweeping Floor", 6: "Washing Hand", 7: "Waving Hand",
    8: "TUG Test/Walking", 9: "Sit/Stand",
    10: "Backfall", 11: "Frontfall", 12: "Leftfall", 13: "Rightfall", 14: "Rotatefall",
}
SFMM_FALL_IDS = {10, 11, 12, 13, 14}


def sfmm_trials():
    out = []
    for grp, folder in (("young", "young"), ("old", "old")):
        pat = os.path.join(SFMM_ROOT, folder, "accelerometer", "meta_wrist", "S*A*T*.csv")
        for p in sorted(glob.glob(pat)):
            m = re.match(r"S(\d+)A(\d+)T(\d+)\.csv", os.path.basename(p))
            if not m:
                continue
            sid, aid, tid = (int(g) for g in m.groups())
            out.append(dict(group=grp, subject=sid, activity=aid, trial=tid, path=p,
                            is_fall=aid in SFMM_FALL_IDS))
    return out


def load_sfmm(path):
    """-> t_iso [s since epoch, UTC-naive] (float64), elapsed_s (float64), xyz [g] (N,3).

    The *epoch-ms* column (col 0) is Excel-mangled in ~19 % of files (e.g. `1.65843E+12`,
    `1658430000000.0`), so the ISO time string (col 1, ms resolution, intact) is the clock.
    Malformed rows are skipped."""
    t, el, xyz = [], [], []
    with open(path) as f:
        for line in f:
            p = line.strip().split(",")
            if len(p) < 6:
                continue
            try:
                ti = datetime.fromisoformat(p[1]).replace(tzinfo=timezone.utc).timestamp()
                e = float(p[2]); x = (float(p[3]), float(p[4]), float(p[5]))
            except ValueError:
                continue
            t.append(ti); el.append(e); xyz.append(x)
    return np.asarray(t), np.asarray(el), np.asarray(xyz).reshape(-1, 3)


# ----------------------------------------------------------------------------
# BITS geriatric: one CSV per trial, header "t,x,y,z,a,", sensor blocks tagged in the LAST column:
#   acc / acg / gyro / mgm : x,y,z,3,<tag>        hrt : <hr>,<status>,hrt,,
# ----------------------------------------------------------------------------
def bits_trials():
    out = []
    for kind in ("adl", "fall"):
        for p in sorted(glob.glob(os.path.join(BITS_ROOT, kind, "user*", "*.csv"))):
            m = re.match(r"user(\d+)_\.?(adl|fall)(\d+)\.csv", os.path.basename(p))
            out.append(dict(kind=kind, subject=int(m.group(1)), trial=int(m.group(3)),
                            path=p, is_fall=(kind == "fall"),
                            odd_name=os.path.basename(p).startswith("user%s_." % m.group(1))))
    return out


def load_bits_raw(path):
    """-> dict tag -> {'t': float64 (rounded to 3 s.f. in the source!), 'v': (N,3) float64}.
    Rows are grouped by their tag, preserving file order.  Row layout differs for 'hrt'
    (see parse_bits_hr)."""
    tags = {}
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline()
        for line in f:
            p = line.rstrip("\n").split(",")
            if len(p) < 6:
                continue
            tag = p[5].strip()
            if tag == "":
                # heart-rate rows: t,hr,status,hrt,, -> tag sits in column 3
                tag = p[3].strip()
                if tag != "hrt":
                    continue
                try:
                    tags.setdefault("hrt", []).append((float(p[0]), float(p[1]), float(p[2])))
                except ValueError:
                    pass
                continue
            try:
                tags.setdefault(tag, []).append((float(p[0]), float(p[1]), float(p[2]), float(p[3])))
            except ValueError:
                continue
    out = {}
    for tag, rows in tags.items():
        a = np.asarray(rows, dtype=np.float64)
        out[tag] = {"t": a[:, 0], "v": a[:, 1:4]}
    return out


def parse_bits_hr(path):
    """HR (MAX30102, ~1 Hz) parsing -- READY BUT UNUSED in this project.
    -> (t_raw, hr_bpm, status) arrays, or None when the file has no 'hrt' block."""
    raw = load_bits_raw(path)
    if "hrt" not in raw:
        return None
    h = raw["hrt"]
    return h["t"], h["v"][:, 0], h["v"][:, 1]
