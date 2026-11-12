import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                            f1_score, roc_auc_score, confusion_matrix)
import joblib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "features.csv")
RESULTS = os.path.join(ROOT, "results")
os.makedirs(RESULTS, exist_ok=True)

df = pd.read_csv(DATA)
FEATURES = ["max_mag", "min_mag", "mean_mag", "std_mag", "range_mag",
            "max_jerk", "std_mag_post", "count_low"]
X = df[FEATURES].values.astype(float)
y = df["label"].values.astype(int)
groups = df["subject"].values

gkf = GroupKFold(n_splits=5)

def eval_model(make_model, scaled=False):
    fold_metrics = []
    all_y_true = []
    all_y_pred = []
    all_y_prob = []
    elderly_fp = []
    elderly_n = []
    for tr, te in gkf.split(X, y, groups):
        scaler = StandardScaler() if scaled else None
        Xtr = scaler.fit_transform(X[tr]) if scaled else X[tr]
        Xte = scaler.transform(X[te]) if scaled else X[te]
        m = make_model()
        m.fit(Xtr, y[tr])
        pred = m.predict(Xte)
        if hasattr(m, "predict_proba"):
            prob = m.predict_proba(Xte)[:, 1]
        else:
            prob = pred.astype(float)
        cm = confusion_matrix(y[te], pred, labels=[0, 1])
        metrics = {
            "acc": accuracy_score(y[te], pred),
            "prec": precision_score(y[te], pred, zero_division=0),
            "rec": recall_score(y[te], pred, zero_division=0),
            "f1": f1_score(y[te], pred, zero_division=0),
            "auc": roc_auc_score(y[te], prob) if len(np.unique(y[te])) > 1 else float("nan"),
            "cm": cm,
        }
        fold_metrics.append(metrics)
        all_y_true.append(y[te]); all_y_pred.append(pred); all_y_prob.append(prob)
        # elderly FPR on ADL windows
        subj_te = np.array([str(s) for s in df["subject"].values[te]])
        mask = np.array([s.startswith("SE") for s in subj_te]) & (y[te] == 0)
        if mask.sum() > 0:
            elderly_fp.append(int((pred[mask] == 1).sum()))
            elderly_n.append(int(mask.sum()))
    return fold_metrics, elderly_fp, elderly_n


# Logistic Regression
print("===== LogisticRegression (scaled) =====")
lr_folds, lr_fp, lr_n = eval_model(lambda: LogisticRegression(class_weight="balanced", max_iter=1000), scaled=True)
for i, m in enumerate(lr_folds):
    print(f"fold {i}: acc={m['acc']:.4f} prec={m['prec']:.4f} rec={m['rec']:.4f} f1={m['f1']:.4f} auc={m['auc']:.4f}")
    print("  cm:\n", m["cm"])
lr_mean = {k: np.mean([m[k] for m in lr_folds]) for k in ["acc", "prec", "rec", "f1", "auc"]}
print("MEAN:", {k: round(v, 4) for k, v in lr_mean.items()})
print("elderly FPR:", sum(lr_fp), "/", sum(lr_n), "=", sum(lr_fp) / max(1, sum(lr_n)))

# Decision Trees
tree_results = {}
for depth in [3, 4, 5, 6]:
    print(f"\n===== DecisionTree max_depth={depth} =====")
    folds, fp, n = eval_model(lambda d=depth: DecisionTreeClassifier(max_depth=d, class_weight="balanced", random_state=42), scaled=False)
    for i, m in enumerate(folds):
        print(f"fold {i}: acc={m['acc']:.4f} prec={m['prec']:.4f} rec={m['rec']:.4f} f1={m['f1']:.4f} auc={m['auc']:.4f}")
        print("  cm:\n", m["cm"])
    mean = {k: np.mean([m[k] for m in folds]) for k in ["acc", "prec", "rec", "f1", "auc"]}
    print("MEAN:", {k: round(v, 4) for k, v in mean.items()})
    print("elderly FPR:", sum(fp), "/", sum(n), "=", sum(fp) / max(1, sum(n)))
    tree_results[depth] = (folds, fp, n, mean)

# pick shallowest tree reaching best F1 (max_depth<=5 preferred)
# prefer max_depth <= 5
pool = [d for d in tree_results if d <= 5]
best_f1 = max(tree_results[d][3]["f1"] for d in pool)
candidates = [d for d in pool if tree_results[d][3]["f1"] >= best_f1 - 1e-9]
pick = min(candidates)
print("\nBest F1 among trees:", round(best_f1, 4), "candidates:", candidates, "-> picked depth", pick)

# retrain final tree on all data at picked depth
final_tree = DecisionTreeClassifier(max_depth=pick, class_weight="balanced", random_state=42)
final_tree.fit(X, y)
joblib.dump(final_tree, os.path.join(ROOT, "data", "fall_tree.joblib"))
print("\nFinal tree rules:")
print(export_text(final_tree, feature_names=FEATURES))

# plots
# bar chart of mean F1/AUC by model
labels = ["LR"] + [f"DT{d}" for d in [3, 4, 5, 6]]
f1s = [lr_mean["f1"]] + [tree_results[d][3]["f1"] for d in [3, 4, 5, 6]]
aucs = [lr_mean["auc"]] + [tree_results[d][3]["auc"] for d in [3, 4, 5, 6]]
x = np.arange(len(labels))
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(x - 0.2, f1s, 0.4, label="F1")
ax.bar(x + 0.2, aucs, 0.4, label="AUC")
ax.set_xticks(x); ax.set_xticklabels(labels)
ax.set_ylim(0, 1); ax.legend(); ax.set_title("Mean CV metrics")
fig.tight_layout()
fig.savefig(os.path.join(RESULTS, "metrics_bar.png"))
plt.close(fig)

# confusion matrix for picked tree (aggregate)
# recompute aggregate cm for picked
folds, fp, n, mean = tree_results[pick]
# aggregate cm from last fold? instead compute pooled by re-running quickly
agg_cm = np.zeros((2, 2), dtype=int)
for tr, te in gkf.split(X, y, groups):
    m = DecisionTreeClassifier(max_depth=pick, class_weight="balanced", random_state=42)
    m.fit(X[tr], y[tr])
    pred = m.predict(X[te])
    agg_cm += confusion_matrix(y[te], pred, labels=[0, 1])
fig, ax = plt.subplots(figsize=(4, 4))
im = ax.imshow(agg_cm, cmap="Blues")
for i in range(2):
    for j in range(2):
        ax.text(j, i, agg_cm[i, j], ha="center", va="center")
ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
ax.set_xticklabels(["ADL", "FALL"]); ax.set_yticklabels(["ADL", "FALL"])
ax.set_xlabel("Pred"); ax.set_ylabel("True"); ax.set_title(f"DT depth {pick} pooled CM")
fig.tight_layout()
fig.savefig(os.path.join(RESULTS, "confusion_matrix.png"))
plt.close(fig)

# save chosen depth for export step
with open(os.path.join(ROOT, "data", "chosen_depth.txt"), "w") as f:
    f.write(str(pick))
print("\nSaved chosen depth", pick)
print("Plots saved to", RESULTS)
