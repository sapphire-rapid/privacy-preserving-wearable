"""Model-comparison costs, MEASURED: fit the final tree / MLP on the whole pool (like the final LR), generate C inference
code for each, compile with arm-none-eabi-gcc -Os (Cortex-M4F, the XIAO nRF52840 class) and read `arm-none-eabi-size`.
Reported sizes are object-file text+rodata (flash) of the classifier alone and of the shared 9-feature code; libm (exp/expf) is
not included.  Writes results/flash.json.
"""
import os
import sys
import json
import subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from eval_nested import Ctx, n_params
from export_final import flt

ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results")
BUILD = os.path.join(ROOT, "cache", "flash_build")
INC = os.path.join(ROOT, "include")
REPO = os.path.dirname(os.path.dirname(ROOT))
FW_INC = os.path.join(REPO, "firmware", "fall_imu", "include")
ARM = ["arm-none-eabi-gcc", "-mcpu=cortex-m4", "-mthumb", "-mfloat-abi=hard", "-mfpu=fpv4-sp-d16", "-Os", "-ffunction-sections", "-fdata-sections", "-c"]


def tree_c(clf):
    t = clf.tree_
    L = ["float model_prob(const float f[9])", "{"]

    def rec(n, ind):
        pad = "    " * ind
        if t.children_left[n] == -1:
            v = t.value[n][0]
            L.append(f"{pad}return {flt(v[1] / v.sum())};")
            return
        L.append(f"{pad}if (f[{t.feature[n]}] <= {flt(t.threshold[n])}) {{")
        rec(t.children_left[n], ind + 1)
        L.append(f"{pad}}} else {{")
        rec(t.children_right[n], ind + 1)
        L.append(f"{pad}}}")
    rec(0, 1)
    L.append("}")
    return "\n".join(L)


def mlp_c(model):
    W1, W2 = model.clf.coefs_
    b1, b2 = model.clf.intercepts_
    mean, scale = model.scaler.mean_, model.scaler.scale_
    s = ["#include <math.h>"]
    s.append("static const float MEAN[9] = {" + ", ".join(flt(v) for v in mean) + "};")
    s.append("static const float SCALE[9] = {" + ", ".join(flt(v) for v in scale) + "};")
    s.append(f"static const float W1[9][{W1.shape[1]}] = {{" + ", ".join("{" + ", ".join(flt(v) for v in r) + "}" for r in W1) + "};")
    s.append(f"static const float B1[{len(b1)}] = {{" + ", ".join(flt(v) for v in b1) + "};")
    s.append(f"static const float W2[{len(W2)}] = {{" + ", ".join(flt(v) for v in W2[:, 0]) + "};")
    s.append(f"static const float B2 = {flt(b2[0])};")
    s.append(f"""float model_prob(const float f[9])
{{
    float x[9], z = B2;
    for (int i = 0; i < 9; i++) x[i] = (f[i] - MEAN[i]) / SCALE[i];
    for (int j = 0; j < {W1.shape[1]}; j++) {{
        float h = B1[j];
        for (int i = 0; i < 9; i++) h += x[i] * W1[i][j];
        if (h > 0.0f) z += h * W2[j];
    }}
    return 1.0f / (1.0f + expf(-z));
}}""")
    return "\n".join(s)


def lr_c():
    return '#include "fall_features.h"\nfloat model_prob(const float f[9]) { return fall_lr_prob(f); }\n'


def feat_c():
    return '#include "fall_features.h"\nvoid features(const float xyz[][3], float out[N_FEATURES]) { fall_features(xyz, WIN_SAMPLES, out); }\n'


def size_of(src, name):
    c = os.path.join(BUILD, name + ".c"); o = os.path.join(BUILD, name + ".o")
    open(c, "w").write(src)
    r = subprocess.run(ARM + ["-I", BUILD, "-I", INC, c, "-o", o], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-600:])
    out = subprocess.run(["arm-none-eabi-size", o], capture_output=True, text=True).stdout.splitlines()[1].split()
    text, data, bss = int(out[0]), int(out[1]), int(out[2])
    return dict(flash_bytes=text + data, text_incl_rodata=text, data=data, bss=bss)


def main():
    os.makedirs(BUILD, exist_ok=True)
    import shutil
    shutil.copy(os.path.join(FW_INC, "fall_features.h"), os.path.join(BUILD, "fall_features.h"))
    ctx = Ctx(26)
    subj = set(ctx.tsub)
    res = {}
    res["features(shared)"] = dict(size_of(feat_c(), "features"), n_params=0)
    lr = ctx.fit("lr", subj)
    res["lr"] = dict(size_of(lr_c(), "lr"), n_params=n_params(lr), param_bytes_f32=4 * n_params(lr))
    tree = ctx.fit("tree", subj)
    res["tree"] = dict(size_of(tree_c(tree.clf), "tree"), n_params=n_params(tree), depth=int(tree.clf.get_depth()), leaves=int(tree.clf.get_n_leaves()))
    mlp = ctx.fit("mlp", subj)
    res["mlp"] = dict(size_of(mlp_c(mlp), "mlp"), n_params=n_params(mlp), hidden=16)
    res["note"] = "arm-none-eabi-gcc -Os -mcpu=cortex-m4 -mfloat-abi=hard object text+data (flash) excluding libm; LR uses the firmware's fall_lr_prob (double exp)."
    json.dump(res, open(os.path.join(RES, "flash.json"), "w"), indent=1)
    for k, v in res.items():
        print(k, v)


if __name__ == "__main__":
    main()
