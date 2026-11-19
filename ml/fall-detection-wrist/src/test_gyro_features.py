"""Vectorised gyro features == scalar reference on real windows; invariance of the gyro features to a fixed sensor rotation."""
import os
import sys
import pickle
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as F

CACHE = os.path.join(os.path.dirname(HERE), "cache")


def main():
    rng = np.random.default_rng(1)
    tr = [r for r in pickle.load(open(os.path.join(CACHE, "weda.pkl"), "rb")) + pickle.load(open(os.path.join(CACHE, "sfmm.pkl"), "rb")) if r.get("gyro_ok")]
    c = F.CFG26
    worst = np.zeros(6)
    for _ in range(300):
        r = tr[int(rng.integers(len(tr)))]
        xa = r["x26"].astype(np.float64); xg = r["g26"].astype(np.float64)
        if len(xa) < c.win:
            continue
        st = rng.integers(0, len(xa) - c.win + 1, size=4)
        vec = F.gyro_window_features(xa, xg, st, c)
        for k, s in enumerate(st):
            ref = np.array(F.gyro_features_of_window(xa[s:s + c.win], xg[s:s + c.win], c))
            worst = np.maximum(worst, np.abs(vec[k] - ref) / np.maximum(np.abs(ref), 1e-9) * (np.abs(ref) > 1e-9))
    print("max rel diff per gyro feature:", np.array2string(worst, precision=2))
    assert worst.max() < 1e-9
    # orientation invariance: rotate both accel and gyro by one fixed rotation -> all 6 features unchanged
    th = 0.7; R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    r = tr[10]; xa = r["x26"].astype(np.float64); xg = r["g26"].astype(np.float64); st = F.sliding_starts(len(xa), c)[:20]
    a = F.gyro_window_features(xa, xg, st, c); b = F.gyro_window_features(xa @ R.T, xg @ R.T, st, c)
    assert np.allclose(a, b, atol=1e-9)
    print("TEST GYRO FEATURES PASSED (vectorised == scalar; rotation-invariant)")


if __name__ == "__main__":
    main()
