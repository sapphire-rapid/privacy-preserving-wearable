import os
import numpy as np
import pandas as pd
import joblib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RESULTS = os.path.join(ROOT, "results")
os.makedirs(os.path.join(ROOT, "include"), exist_ok=True)
INC = os.path.join(ROOT, "include")

df = pd.read_csv(os.path.join(DATA, "features.csv"))
FEATURES = ["max_mag", "min_mag", "mean_mag", "std_mag", "range_mag",
            "max_jerk", "std_mag_post", "count_low"]
X = df[FEATURES].values.astype(float)
y = df["label"].values.astype(int)

model = joblib.load(os.path.join(DATA, "fall_tree.joblib"))
tree = model.tree_

# Map feature index -> name
def feat_name(i):
    return FEATURES[i]

# Generate nested if/else C code recursively
lines = []
def gen(node, indent):
    if tree.children_left[node] == tree.children_right[node]:  # leaf
        # majority class
        vals = tree.value[node][0]
        cls = int(np.argmax(vals))
        lines.append(f"{indent}return {cls};")
        return
    fi = tree.feature[node]
    thr = tree.threshold[node]
    lines.append(f"{indent}if (f[{fi}] <= {thr:.6f}f) {{  /* {FEATURES[fi]} */")
    gen(tree.children_left[node], indent + "    ")
    lines.append(f"{indent}}} else {{")
    gen(tree.children_right[node], indent + "    ")
    lines.append(f"{indent}}}")

body = []
gen(0, "    ")
body_str = "\n".join(lines)

header = f"""#ifndef FALL_TREE_H
#define FALL_TREE_H

#define N_FEATURES {len(FEATURES)}

/* Feature order:
 * 0: {FEATURES[0]}
 * 1: {FEATURES[1]}
 * 2: {FEATURES[2]}
 * 3: {FEATURES[3]}
 * 4: {FEATURES[4]}
 * 5: {FEATURES[5]}
 * 6: {FEATURES[6]}
 * 7: {FEATURES[7]}
 */

static inline int fall_predict(const float f[N_FEATURES]) {{
{body_str}
}}

#endif
"""
with open(os.path.join(INC, "fall_tree.h"), "w") as f:
    f.write(header)
print("wrote fall_tree.h")

# Python mirror of the generated if/else logic
def predict_mirror(vec):
    f = vec
    # exec via recursive eval using tree thresholds (same as generated)
    node = 0
    while tree.children_left[node] != tree.children_right[node]:
        fi = tree.feature[node]
        if f[fi] <= tree.threshold[node]:
            node = tree.children_left[node]
        else:
            node = tree.children_right[node]
    vals = tree.value[node][0]
    return int(np.argmax(vals))

# verify on ALL windows
sk = model.predict(X)
mir = np.array([predict_mirror(x) for x in X])
agreement = float((sk == mir).mean())
print(f"Mirror vs sklearn agreement on ALL windows: {agreement*100:.2f}% ({int((sk==mir).sum())}/{len(X)})")

# test vectors: ~20 (10 fall + 10 adl)
rng = np.random.default_rng(42)
fall_idx = np.where(y == 1)[0]
adl_idx = np.where(y == 0)[0]
chosen = list(rng.choice(fall_idx, 10, replace=False)) + list(rng.choice(adl_idx, 10, replace=False))
tv_lines = ["#ifndef TEST_VECTORS_H", "#define TEST_VECTORS_H", "", "#include \"fall_tree.h\"", "", "typedef struct { float f[N_FEATURES]; int expected; } TestVector;", "", "static const TestVector test_vectors[] = {"]
for i in chosen:
    vec = X[i]
    exp = int(model.predict(vec.reshape(1, -1))[0])
    vals = ", ".join(f"{v:.6f}f" for v in vec)
    tv_lines.append(f"    {{{{{vals}}}, {exp}}},")
tv_lines.append("};")
tv_lines.append(f"#define N_TEST_VECTORS {len(chosen)}")
tv_lines.append("")
tv_lines.append("#endif")
with open(os.path.join(INC, "test_vectors.h"), "w") as f:
    f.write("\n".join(tv_lines))
print("wrote test_vectors.h")

# header size
print("fall_tree.h size (bytes):", os.path.getsize(os.path.join(INC, "fall_tree.h")))
print("test_vectors.h size (bytes):", os.path.getsize(os.path.join(INC, "test_vectors.h")))
