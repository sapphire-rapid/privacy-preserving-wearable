"""Step 3: the 9 features, window grid and window labelling of features_v2.py, parameterised by sample rate.

Reference (SisFall, 52 Hz): WIN=104, STRIDE=26, tilt before = 26 samples (fallback: first 10), tilt after = last 26,
std_mag_post = last 52, label window for a fall = peak - int(0.4*WIN) clipped into [0, n-WIN], one window per fall trial;
ADL trials contribute every sliding window.  Here every constant scales with fs (26 Hz: 52/13/13/13/5/26, confirm 78).
`features_of_window` is the scalar reference (verbatim logic of features_v2.py); `trial_features` is the vectorised
equivalent and is unit-tested against it.
"""
from dataclasses import dataclass
from fractions import Fraction
import numpy as np
from scipy.signal import resample_poly

FEATURE_NAMES = ["max_mag", "min_mag", "mean_mag", "std_mag", "range_mag",
                 "max_jerk", "std_mag_post", "count_low", "tilt_deg"]
STRETCH = (0.95, 1.00, 1.05)
STD_GRID = (0.05, 0.065, 0.08)                      # as specified
STD_GRID_EXT = (0.05, 0.065, 0.08, 0.12, 0.2, 0.3)   # sensitivity: wider stillness tolerance (wrist is rarely this still)
MEAN_TOL = 0.2


@dataclass(frozen=True)
class Cfg:
    fs: int
    win: int
    stride: int
    tilt_pre: int
    tilt_post: int
    tilt_fallback: int
    post_std: int
    confirm: int
    label_off: int


def cfg_for(fs):
    win = 2 * fs
    return Cfg(fs=fs, win=win, stride=fs // 2, tilt_pre=fs // 2, tilt_post=fs // 2,
               tilt_fallback=int(round(10 * fs / 52)), post_std=fs, confirm=3 * fs,
               label_off=int(0.4 * win))


CFG26 = cfg_for(26)
CFG52 = cfg_for(52)
assert (CFG52.win, CFG52.stride, CFG52.tilt_pre, CFG52.tilt_fallback, CFG52.post_std, CFG52.confirm) == (104, 26, 26, 10, 52, 156)


def mag(a):
    return np.sqrt((a ** 2).sum(axis=1))


# ---------------------------------------------------------------- scalar reference (mirrors features_v2.py)
def tilt_deg(sig, c):
    m = mag(sig)
    peak = int(np.argmax(m))
    if peak >= c.tilt_pre:
        before = sig[peak - c.tilt_pre:peak]
    else:
        before = sig[:c.tilt_fallback]
    after = sig[-c.tilt_post:] if len(sig) >= c.tilt_post else sig
    u = before.mean(axis=0)
    v = after.mean(axis=0)
    nu = np.linalg.norm(u); nv = np.linalg.norm(v)
    if nu == 0 or nv == 0:
        return 0.0
    cos = np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos)))


def features_of_window(w, c):
    m = mag(w)
    jerk = np.abs(np.diff(m))
    post = m[-c.post_std:] if len(m) >= c.post_std else m
    return [float(m.max()), float(m.min()), float(m.mean()), float(m.std()),
            float(m.max() - m.min()), float(jerk.max()) if len(jerk) else 0.0,
            float(post.std()), float((m < 0.5).sum()), tilt_deg(w, c)]


# ---------------------------------------------------------------- vectorised equivalent
def window_features(x, starts, c):
    """x (N,3) float64 trial, starts int array of window starts -> (len(starts), 9) float64."""
    x = np.asarray(x, dtype=np.float64)
    starts = np.asarray(starts, dtype=np.int64)
    m = mag(x)
    idx = starts[:, None] + np.arange(c.win)[None, :]
    mw = m[idx]
    out = np.empty((len(starts), 9))
    out[:, 0] = mw.max(1)
    out[:, 1] = mw.min(1)
    out[:, 2] = mw.mean(1)
    out[:, 3] = mw.std(1)
    out[:, 4] = out[:, 0] - out[:, 1]
    out[:, 5] = np.abs(np.diff(mw, axis=1)).max(1)
    out[:, 6] = mw[:, -c.post_std:].std(1)
    out[:, 7] = (mw < 0.5).sum(1)
    # tilt
    pk = mw.argmax(1)                                   # first max, like np.argmax
    cs = np.vstack([np.zeros((1, 3)), np.cumsum(x, axis=0)])
    pa = starts + pk
    use_pre = pk >= c.tilt_pre
    b0 = np.where(use_pre, pa - c.tilt_pre, starts)
    b1 = np.where(use_pre, pa, starts + c.tilt_fallback)
    u = (cs[b1] - cs[b0]) / (b1 - b0)[:, None]
    a0 = starts + c.win - c.tilt_post
    v = (cs[starts + c.win] - cs[a0]) / c.tilt_post
    nu = np.linalg.norm(u, axis=1); nv = np.linalg.norm(v, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = np.clip((u * v).sum(1) / (nu * nv), -1.0, 1.0)
    ang = np.degrees(np.arccos(cos))
    ang[(nu == 0) | (nv == 0)] = 0.0
    out[:, 8] = ang
    return out


def sliding_starts(n, c):
    return np.arange(0, n - c.win + 1, c.stride) if n >= c.win else np.zeros(0, dtype=np.int64)


def fall_label_start(m, n, c):
    peak = int(np.argmax(m))
    s = peak - c.label_off
    return max(0, min(s, n - c.win)), peak


# ---------------------------------------------------------------- v3: orientation-invariant gyro features (dps, same 2 s window)
GYRO_NAMES = ["gyro_max", "gyro_mean", "gyro_std", "gyro_rot_win", "gyro_rot_peak", "gyro_peak_offset_s"]
FEATURE_NAMES_V3 = FEATURE_NAMES + GYRO_NAMES      # 15 features; first 9 are the unchanged accelerometer features


def gyro_features_of_window(wa, wg, c):
    """|w| max / mean / std; integrated rotation angle sum(|w|*dt) over the window [deg]; the same within +-0.5 s of the |a| peak;
    signed time offset (|w| peak - |a| peak) [s]."""
    m = mag(wa); wm = mag(wg)
    p = int(np.argmax(m))
    lo, hi = max(0, p - c.tilt_pre), min(len(wm), p + c.tilt_pre + 1)
    return [float(wm.max()), float(wm.mean()), float(wm.std()), float(wm.sum() / c.fs), float(wm[lo:hi].sum() / c.fs),
            float((int(np.argmax(wm)) - p) / c.fs)]


def gyro_window_features(xa, xg, starts, c):
    xa = np.asarray(xa, dtype=np.float64); xg = np.asarray(xg, dtype=np.float64)
    starts = np.asarray(starts, dtype=np.int64)
    idx = starts[:, None] + np.arange(c.win)[None, :]
    ma = mag(xa)[idx]; wm = mag(xg)[idx]
    p = ma.argmax(1)
    out = np.empty((len(starts), 6))
    out[:, 0] = wm.max(1); out[:, 1] = wm.mean(1); out[:, 2] = wm.std(1); out[:, 3] = wm.sum(1) / c.fs
    pos = np.arange(c.win)[None, :]
    near = (pos >= (p - c.tilt_pre)[:, None]) & (pos <= (p + c.tilt_pre)[:, None])
    out[:, 4] = (wm * near).sum(1) / c.fs
    out[:, 5] = (wm.argmax(1) - p) / c.fs
    return out


def stillness_stats(m, starts, c):
    """Per window: (evaluable, std, mean) of the CONFIRM samples following the window (std ddof=0)."""
    n = len(m)
    s0 = starts + c.win
    ev = (s0 + c.confirm) <= n
    sd = np.full(len(starts), np.nan); mu = np.full(len(starts), np.nan)
    if ev.any():
        idx = s0[ev][:, None] + np.arange(c.confirm)[None, :]
        seg = m[idx]
        sd[ev] = seg.std(1); mu[ev] = seg.mean(1)
    return ev, sd, mu


def stretch(x, f):
    """Time-stretch a trial by factor f (new length ~ f * old length) with resample_poly."""
    if f == 1.0:
        return x
    r = Fraction(f).limit_denominator(40)
    return resample_poly(np.asarray(x, dtype=np.float64), r.numerator, r.denominator, axis=0, padtype="line")


def trial_windows(x, is_fall, c, xg=None):
    """Windows used for TRAINING from one trial (ADL: all sliding; fall: the impact window).  xg given -> 15 features (v3)."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    nf = 9 if xg is None else 15
    if n < c.win:
        return np.zeros((0, nf)), np.zeros(0, dtype=int)
    if is_fall:
        s, _ = fall_label_start(mag(x), n, c)
        st, y = np.array([s]), np.ones(1, dtype=int)
    else:
        st = sliding_starts(n, c)
        y = np.zeros(len(st), dtype=int)
    X = window_features(x, st, c)
    if xg is not None:
        X = np.hstack([X, gyro_window_features(x, xg, st, c)])
    return X, y
