"""Vectorised window_features == scalar features_of_window (mirror of features_v2.py), on real windows at 26 and 52 Hz."""
import os
import sys
import pickle
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as F

CACHE = os.path.join(os.path.dirname(HERE), "cache")


def main():
    rng = np.random.default_rng(0)
    trials = []
    for name in ("weda", "sfmm"):
        trials += pickle.load(open(os.path.join(CACHE, name + ".pkl"), "rb"))
    for fs, c in ((26, F.CFG26), (52, F.CFG52)):
        worst = np.zeros(9); n_tot = 0
        for _ in range(400):
            r = trials[int(rng.integers(len(trials)))]
            x = r["x%d" % fs].astype(np.float64)
            if len(x) < c.win:
                continue
            st = rng.integers(0, len(x) - c.win + 1, size=5)
            vec = F.window_features(x, st, c)
            for k, s in enumerate(st):
                ref = np.array(F.features_of_window(x[s:s + c.win], c))
                worst = np.maximum(worst, np.abs(vec[k] - ref) / np.maximum(np.abs(ref), 1e-9))
                n_tot += 1
        print("fs=%d  windows=%d  max rel diff per feature:" % (fs, n_tot), np.array2string(worst, precision=2))
        assert worst.max() < 1e-6, worst
    # label-window rule sanity
    x = trials[0]["x26"].astype(np.float64)
    m = F.mag(x); s, pk = F.fall_label_start(m, len(x), F.CFG26)
    assert 0 <= s <= len(x) - F.CFG26.win
    print("TEST FEATURES PASSED")


if __name__ == "__main__":
    main()
