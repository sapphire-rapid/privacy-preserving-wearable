"""Step 2: raw wrist files -> uniform 26 Hz (primary) and 52 Hz series in g.

Per-dataset time axis (decisions of the data-card review):
  WEDA   per-trial linear axis: the samples are taken as evenly spaced between the first and
         last timestamp (fs = (n-1)/(t_last-t_first)); raw timestamps are burst-stamped.
  SFMM   ISO time string (epoch-ms column is corrupt in ~19 % of files).  Split at |gap| > 1 s,
         drop non-increasing samples, interpolate each segment onto a uniform grid at its own
         rate (np.interp), drop segments < 2 s; fall trials keep only the segment holding the
         impact peak; ADL files whose median |a| is outside 0.5-2 g (not in g) are dropped.
  BITS   `acg` (gravity included), m/s^2 -> g, 20 Hz by sample order.
then resample_poly(up, down) with a rational approximation of fs_out/fs_in and
padtype='line' (the default zero padding would pull |a| to 0 at the trial edges).

Outputs cache/{weda,sfmm,bits}.pkl (derived data, git-ignored, not redistributable for SFMM).
Run: .venv/bin/python -I src/preprocess.py
"""
import os
import sys
import json
import pickle
from fractions import Fraction
import numpy as np
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wrist_io as W

ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "cache")
RES = os.path.join(ROOT, "results")
os.makedirs(CACHE, exist_ok=True)

RATES = (26, 52)
GAP_S = 1.0
MIN_SEG_S = 2.0
NON_G_RANGE = (0.5, 2.0)      # median |a| [g] outside this => file is not in g


def resample_to(x, fs_in, fs_out):
    """x (N,3) uniformly sampled at fs_in -> fs_out via resample_poly with a rational ratio."""
    r = Fraction(fs_out / fs_in).limit_denominator(240)
    y = resample_poly(x, r.numerator, r.denominator, axis=0, padtype="line")
    return y, abs(float(r) - fs_out / fs_in) / (fs_out / fs_in)


def to_rates(x, fs_in):
    out, err = {}, 0.0
    for fs in RATES:
        out[fs], e = resample_to(x, fs_in, fs)
        err = max(err, e)
    return out, err


def mag(a):
    return np.sqrt((a ** 2).sum(axis=1))


def rest_g(m, n):
    if len(m) < n + 1:
        return float("nan")
    s = np.lib.stride_tricks.sliding_window_view(m, n)
    return float(s[int(np.argmin(s.std(axis=1)))].mean())


def mk(dataset, subject, group, is_fall, ftype, trial_id, seg, x, fs_in, extra=None):
    d = to_rates(np.asarray(x, dtype=np.float64), fs_in)
    r = dict(dataset=dataset, subject=subject, group=group, is_fall=bool(is_fall), ftype=ftype,
             trial_id=trial_id, seg=seg, fs_in=float(fs_in), ratio_err=d[1])
    for fs in RATES:
        r["x%d" % fs] = d[0][fs].astype(np.float32)
    if extra:
        r.update(extra)
    return r


# ------------------------------------------------------------------ WEDA
def build_weda(excl):
    out = []
    for tr in W.weda_trials("50Hz"):
        t, a = W.load_weda(tr["path"])
        g = a / W.G
        fs = (len(t) - 1) / float(t[-1] - t[0])
        sid = "W%02d" % tr["subject"]
        out.append(mk("WEDA", sid, "young" if tr["subject"] <= 14 else "old", tr["is_fall"], tr["code"],
                      "W_%s_U%02d_R%02d" % (tr["code"], tr["subject"], tr["trial"]), 0, g, fs,
                      dict(native_rate=fs)))
    return out


# ------------------------------------------------------------------ SFMM
def build_sfmm(excl):
    out = []
    for tr in W.sfmm_trials():
        name = os.path.basename(tr["path"])
        t, el, a = W.load_sfmm(tr["path"])
        if len(t) < 3:
            excl.append(dict(dataset="SFMM", file=name, reason="unreadable / <3 rows"))
            continue
        m = mag(a)
        med = float(np.median(m))
        if not (NON_G_RANGE[0] <= med <= NON_G_RANGE[1]):
            excl.append(dict(dataset="SFMM", file=name, reason="not in g: median |a| = %.2f" % med,
                             fall=bool(tr["is_fall"])))
            continue
        d = np.diff(t)
        cut = np.where((d > GAP_S) | (d < -GAP_S))[0] + 1
        bounds = np.concatenate([[0], cut, [len(t)]])
        peak = int(np.argmax(m))
        segs = []
        for k in range(len(bounds) - 1):
            lo, hi = int(bounds[k]), int(bounds[k + 1])
            tt, aa = t[lo:hi], a[lo:hi]
            keep = np.concatenate([[True], tt[1:] > np.maximum.accumulate(tt)[:-1]])  # strictly increasing
            n_drop = int((~keep).sum())
            tt, aa = tt[keep], aa[keep]
            segs.append((lo, hi, tt, aa, n_drop))
        if len(segs) > 1:
            excl.append(dict(dataset="SFMM", file=name, reason="split at %d gap(s) > %.0f s into %d segments" % (len(segs) - 1, GAP_S, len(segs)),
                             fall=bool(tr["is_fall"]), kind="split"))
        sid = "S%02d" % tr["subject"]
        tid = "S_%s" % name[:-4]
        n_kept = 0
        for k, (lo, hi, tt, aa, n_drop) in enumerate(segs):
            if tr["is_fall"] and not (lo <= peak < hi):
                excl.append(dict(dataset="SFMM", file=name, reason="fall: segment %d does not contain the impact peak (dropped)" % k, fall=True, kind="segment"))
                continue
            if len(tt) < 2 or tt[-1] - tt[0] < MIN_SEG_S:
                excl.append(dict(dataset="SFMM", file=name, reason="segment %d shorter than %.0f s (%.2f s)" % (k, MIN_SEG_S, (tt[-1] - tt[0]) if len(tt) > 1 else 0.0),
                                 fall=bool(tr["is_fall"]), kind="segment"))
                continue
            if n_drop:
                excl.append(dict(dataset="SFMM", file=name, reason="segment %d: %d non-increasing-timestamp samples dropped" % (k, n_drop), fall=bool(tr["is_fall"]), kind="samples"))
            fs = (len(tt) - 1) / float(tt[-1] - tt[0])
            grid = tt[0] + np.arange(int((tt[-1] - tt[0]) * fs) + 1) / fs
            xg = np.column_stack([np.interp(grid, tt, aa[:, i]) for i in range(3)])
            out.append(mk("SFMM", sid, tr["group"], tr["is_fall"], "A%02d" % tr["activity"], tid, k, xg, fs,
                          dict(native_rate=fs, n_gap_dropped=n_drop)))
            n_kept += 1
        if tr["is_fall"] and n_kept == 0:
            excl.append(dict(dataset="SFMM", file=name, reason="fall trial excluded: impact-peak segment unusable", fall=True, kind="trial"))
    return out


# ------------------------------------------------------------------ BITS
def build_bits(excl):
    """Preprocess every BITS file (acg, g); selection flags are stored, not applied here."""
    out = []
    for tr in W.bits_trials():
        raw = W.load_bits_raw(tr["path"])
        v = raw["acg"]["v"] / W.G
        t = raw["acg"]["t"]
        n = len(v)
        m = mag(v)
        rest = rest_g(m, 20)
        span = float((t[-1] - t[0]) / 1e9)           # timestamps assumed ns, 3 significant digits
        exp = n / 20.0
        out.append(mk("BITS", "B%02d" % tr["subject"], "adult", tr["is_fall"], ("fall%d" % tr["trial"]) if tr["is_fall"] else ("adl%d" % tr["trial"]),
                      "B_%s%d_u%02d" % ("fall" if tr["is_fall"] else "adl", tr["trial"], tr["subject"]), 0, v, 20.0,
                      dict(native_rate=20.0, rest_g=rest, rule4_pass=bool(0.9 <= rest <= 1.1),
                           ts_span_s=span, n_expected_s=exp,
                           rule5_pass=bool(abs(span - exp) / exp <= 0.10), n_raw=n)))
    return out


def main():
    excl = []
    res = {}
    for name, fn in (("weda", build_weda), ("sfmm", build_sfmm), ("bits", build_bits)):
        print("building", name, flush=True)
        res[name] = fn(excl)
        with open(os.path.join(CACHE, name + ".pkl"), "wb") as f:
            pickle.dump(res[name], f, protocol=4)
        print("  segments:", len(res[name]), "falls:", sum(r["is_fall"] for r in res[name]),
              " max ratio error: %.2e" % max(r["ratio_err"] for r in res[name]), flush=True)
    with open(os.path.join(RES, "exclusions.json"), "w") as f:
        json.dump(excl, f, indent=1)
    print("exclusion entries:", len(excl))


if __name__ == "__main__":
    main()
