"""Step 6: C parity.
 (a) gcc-build firmware/fall_imu/host/host_test.c against the NEW headers and run it;
 (b) 1000 random TRAIN-pool windows (800 random sliding windows + 200 fall impact windows) and 1000 random confirm segments
     through the firmware's fall_features.h (compiled with the new fall_model.h) vs the Python reference.
PASS = every feature within 1e-4 relative (count_low exact) AND identical trigger / stillness decisions.
The firmware include dir is NOT modified: fall_features.h is copied byte-identically into a build dir so that its
`#include "fall_model.h"` (quoted include => same directory first) resolves to the NEW header.
Writes results/parity.json and results/PARITY.md.
"""
import os
import re
import sys
import json
import pickle
import hashlib
import shutil
import subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as F

ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ROOT))
INC = os.path.join(ROOT, "include")
RES = os.path.join(ROOT, "results")
BUILD = os.path.join(ROOT, "cache", "parity_build")
FW_INC = os.path.join(REPO, "firmware", "fall_imu", "include")
FW_HOST = os.path.join(REPO, "firmware", "fall_imu", "host")
C = F.CFG26
REL_TOL = 1e-4


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    os.makedirs(BUILD, exist_ok=True)
    shutil.copy(os.path.join(FW_INC, "fall_features.h"), os.path.join(BUILD, "fall_features.h"))
    assert sha(os.path.join(BUILD, "fall_features.h")) == sha(os.path.join(FW_INC, "fall_features.h"))
    op = json.load(open(os.path.join(RES, "exported_operating_point.json")))
    fm = json.load(open(os.path.join(RES, "final_model.json")))
    mean, scale, coef, b = np.array(fm["mean"]), np.array(fm["scale"]), np.array(fm["coef"]), fm["intercept"]
    thr = float(np.float32(op["thr"])); std_thr = float(np.float32(op["std"])); tol = float(np.float32(op["mean_tol"]))
    out = {"firmware_fall_features_sha": sha(os.path.join(FW_INC, "fall_features.h")), "op": op}

    # ---- (a) firmware host_test.c against the new headers
    exe_a = os.path.join(BUILD, "host_test_new")
    r = sh(["gcc", "-O2", "-Wall", "-I", BUILD, "-I", INC, os.path.join(FW_HOST, "host_test.c"), "-lm", "-o", exe_a])
    out["host_test_compile"] = dict(rc=r.returncode, stderr=r.stderr[-800:])
    if r.returncode == 0:
        r2 = sh([exe_a])
        out["host_test"] = dict(rc=r2.returncode, tail="\n".join(r2.stdout.strip().splitlines()[-4:]))
    print("host_test.c:", out.get("host_test", out["host_test_compile"]))

    # ---- (b) 1000 random windows + 1000 random segments
    pool = []
    for name in ("weda", "sfmm"):
        pool += pickle.load(open(os.path.join(ROOT, "cache", name + ".pkl"), "rb"))
    pool = [r for r in pool if len(r["x26"]) >= max(C.win, C.confirm)]
    rng = np.random.default_rng(2024)
    W = []
    falls = [r for r in pool if r["is_fall"]]
    while len(W) < 800:
        r = pool[int(rng.integers(len(pool)))]
        st = int(rng.integers(0, len(r["x26"]) - C.win + 1))
        W.append(r["x26"][st:st + C.win])
    while len(W) < 1000:
        r = falls[int(rng.integers(len(falls)))]
        x = r["x26"]; s, _ = F.fall_label_start(F.mag(x.astype(np.float64)), len(x), C)
        W.append(x[s:s + C.win])
    W = np.stack(W).astype(np.float32)
    S = []
    while len(S) < 1000:
        r = pool[int(rng.integers(len(pool)))]
        mg = F.mag(r["x26"].astype(np.float64))
        st = int(rng.integers(0, len(mg) - C.confirm + 1))
        S.append(mg[st:st + C.confirm])
    S = np.stack(S).astype(np.float32)
    wbin, sbin = os.path.join(BUILD, "windows.bin"), os.path.join(BUILD, "segments.bin")
    with open(wbin, "wb") as f:
        f.write(np.int32(len(W)).tobytes()); f.write(np.ascontiguousarray(W).tobytes())
    with open(sbin, "wb") as f:
        f.write(np.int32(len(S)).tobytes()); f.write(np.ascontiguousarray(S).tobytes())
    exe_b = os.path.join(BUILD, "parity_main")
    r = sh(["gcc", "-O2", "-Wall", "-I", BUILD, "-I", INC, os.path.join(HERE, "parity_main.c"), "-lm", "-o", exe_b])
    assert r.returncode == 0, r.stderr
    run = sh([exe_b, wbin, sbin])
    assert run.returncode == 0, run.stderr
    cw = [l.split()[1:] for l in run.stdout.splitlines() if l.startswith("W")]
    cs = [int(l.split()[1]) for l in run.stdout.splitlines() if l.startswith("S")]
    Cf = np.array([[float(v) for v in l[:9]] for l in cw]); Cp = np.array([float(l[9]) for l in cw]); Ct = np.array([int(l[10]) for l in cw])
    # python reference on the very same float32 inputs
    Pf = np.array([F.features_of_window(w.astype(np.float64), C) for w in W])
    Pz = (Pf - mean) / scale @ coef + b
    Pp = 1.0 / (1.0 + np.exp(-Pz))
    rel = np.abs(Cf - Pf) / np.where(np.abs(Pf) > 0, np.abs(Pf), 1.0)
    per_feat = {n: dict(max_rel=float(rel[:, j].max()), n_over=int((rel[:, j] > REL_TOL).sum()),
                        max_abs=float(np.abs(Cf[:, j] - Pf[:, j]).max())) for j, n in enumerate(F.FEATURE_NAMES)}
    # python decisions use the same prob definition evaluated on PYTHON features; C decides on its own float32 prob
    Pt = (Pp >= thr).astype(int)
    dec_mismatch = int((Pt != Ct).sum())
    extra = {}
    for t in (0.003, 0.5, 0.671, 0.93):
        extra[str(t)] = dict(mismatch=int(((Pp >= t) != (Cp >= t)).sum()), n_trigger_py=int((Pp >= t).sum()))
    near = int((np.abs(Pp - thr) < 1e-4).sum())
    Sm = S.astype(np.float64)
    Pstill = ((Sm.std(1) < std_thr) & (np.abs(Sm.mean(1) - 1.0) < tol)).astype(int)
    still_mismatch = int((Pstill != np.array(cs)).sum())
    out["windows"] = dict(n=len(W), n_fall_impact=200, per_feature=per_feat, max_abs_prob_diff=float(np.abs(Cp - Pp).max()),
                          trigger_mismatch_at_exported_thr=dec_mismatch, n_trigger_py=int(Pt.sum()), n_near_thr=near, extra_thresholds=extra)
    out["segments"] = dict(n=len(S), still_mismatch=still_mismatch, n_still_py=int(Pstill.sum()))
    feat_ok = all(v["n_over"] == 0 for v in per_feat.values())
    out["PASS_features_1e-4"] = bool(feat_ok)
    out["PASS_decisions"] = bool(dec_mismatch == 0 and still_mismatch == 0)
    out["PASS_host_test"] = bool(out.get("host_test", {}).get("rc") == 0)
    out["PASS"] = bool(out["PASS_features_1e-4"] and out["PASS_decisions"] and out["PASS_host_test"])
    json.dump(out, open(os.path.join(RES, "parity.json"), "w"), indent=1)

    L = ["# C parity (Step 6)\n", f"Firmware `fall_features.h` sha256[:16] `{out['firmware_fall_features_sha']}` (copied unmodified to a build dir; firmware include dir untouched). "
         f"Exported operating point: mode `{op['op_mode']}`, thr {op['thr']}, std {op['std']}, tol {op['mean_tol']} (provisional={op['provisional']}).\n",
         f"- `host_test.c` built with gcc against the new headers: compile rc={out['host_test_compile']['rc']}; run rc={out.get('host_test', {}).get('rc')}; last lines:\n\n```\n{out.get('host_test', {}).get('tail', '')}\n```\n",
         f"- {len(W)} random train windows ({len(W)-200} random sliding + 200 fall-impact) through the C feature code vs Python float64 on the same float32 inputs; PASS needs every feature within {REL_TOL:g} relative:\n",
         "| feature | max rel err | max abs err | windows over 1e-4 |", "|---|---|---|---|"]
    for n, v in per_feat.items():
        L.append(f"| {n} | {v['max_rel']:.2e} | {v['max_abs']:.2e} | {v['n_over']} |")
    L.append(f"\n- probability: max |C − Python| = {out['windows']['max_abs_prob_diff']:.2e}")
    L.append(f"- trigger decisions at the exported threshold {op['thr']}: **{dec_mismatch} mismatches** of {len(W)} ({int(Pt.sum())} triggers; {near} windows within 1e-4 of the threshold)")
    L.append("- same comparison at other thresholds: " + "; ".join(f"{k}: {v['mismatch']} mismatches ({v['n_trigger_py']} triggers)" for k, v in extra.items()))
    L.append(f"- stillness decisions on {len(S)} random 3 s segments (std<{std_thr:.4g}, |mean−1|<{tol:.4g}): **{still_mismatch} mismatches** ({int(Pstill.sum())} still)")
    L.append(f"\n**RESULT: {'PASS' if out['PASS'] else 'FAIL'}** (features≤1e-4: {out['PASS_features_1e-4']}, decisions identical: {out['PASS_decisions']}, host_test: {out['PASS_host_test']})")
    open(os.path.join(RES, "PARITY.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L[4:]))


if __name__ == "__main__":
    main()
