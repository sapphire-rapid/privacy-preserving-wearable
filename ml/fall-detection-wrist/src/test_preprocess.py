"""Unit tests for Step 2 (run: .venv/bin/python -I src/test_preprocess.py).
 1. |a| at rest ~ 1 g per dataset after conversion (26 and 52 Hz series).
 2. resample_to keeps a constant gravity vector constant all the way to the edges (padtype='line').
 3. Time-scale: a 3 Hz sine sampled at fs_in resamples to the same 3 Hz sine at fs_out.
"""
import os
import sys
import pickle
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import preprocess as P

CACHE = P.CACHE


def rest_stats(trials, fs):
    vals = []
    for r in trials:
        m = P.mag(r["x%d" % fs].astype(np.float64))
        v = P.rest_g(m, fs)
        if np.isfinite(v):
            vals.append(v)
    return np.asarray(vals)


def test_rest_one_g():
    out = {}
    for name in ("weda", "sfmm", "bits"):
        with open(os.path.join(CACHE, name + ".pkl"), "rb") as f:
            tr = pickle.load(f)
        for fs in P.RATES:
            v = rest_stats(tr, fs)
            med = float(np.median(v)); lo, hi = np.percentile(v, [5, 95])
            out[(name, fs)] = (med, lo, hi, len(v))
            assert 0.97 <= med <= 1.03, (name, fs, med)
            assert 0.9 <= lo and hi <= 1.15, (name, fs, lo, hi)
    for k, (med, lo, hi, n) in out.items():
        print("rest |a| %-5s @%2d Hz: median %.4f g  [5-95%%: %.3f, %.3f]  (%d trials)" % (k[0], k[1], med, lo, hi, n))


def test_constant_gravity():
    x = np.tile(np.array([[0.2, -0.3, 0.9]]), (200, 1))
    for fs_in in (20.0, 25.0, 31.25, 39.8, 49.7, 50.0):
        for fs in P.RATES:
            y, _ = P.resample_to(x, fs_in, fs)
            assert np.allclose(y, x[0], atol=1e-3), (fs_in, fs, np.abs(y - x[0]).max())
    print("constant-gravity edge test OK")


def test_sine_timescale():
    for fs_in in (20.0, 25.0, 39.8, 49.7, 50.0):
        t = np.arange(int(fs_in * 20)) / fs_in
        x = np.column_stack([np.sin(2 * np.pi * 3 * t)] * 3)
        for fs in P.RATES:
            y, rerr = P.resample_to(x, fs_in, fs)
            tt = np.arange(len(y)) / fs
            ref = np.sin(2 * np.pi * 3 * tt)
            sl = slice(2 * fs, -2 * fs)
            err = np.abs(y[sl, 0] - ref[sl]).max()
            # allowed: rational-ratio time-scale error accumulated over the 20 s record + filter ripple
            assert err < 3e-3 + 2 * np.pi * 3 * 20 * rerr, (fs_in, fs, err, rerr)
    print("sine time-scale test OK")


if __name__ == "__main__":
    test_constant_gravity()
    test_sine_timescale()
    test_rest_one_g()
    print("ALL TESTS PASSED")
