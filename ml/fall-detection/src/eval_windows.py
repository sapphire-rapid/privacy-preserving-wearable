import os
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import (precision_score, recall_score, f1_score,
                            roc_auc_score, confusion_matrix)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "features.csv")
df = pd.read_csv(DATA)
FEATURES = ["max_mag", "min_mag", "mean_mag", "std_mag", "range_mag",
            "max_jerk", "std_mag_post", "count_low"]
X = df[FEATURES].values.astype(float)
y = df["label"].values.astype(int)
groups = df["subject"].values

gkf = GroupKFold(n_splits=5)

def run(make_model, scaled, name):
    print(f"\n========== {name} ==========")
    precs, recs, f1s, aucs = [], [], [], []
    for i, (tr, te) in enumerate(gkf.split(X, y, groups)):
        scaler = StandardScaler() if scaled else None
        Xtr = scaler.fit_transform(X[tr]) if scaled else X[tr]
        Xte = scaler.transform(X[te]) if scaled else X[te]
        m = make_model()
        m.fit(Xtr, y[tr])
        pred = m.predict(Xte)
        prob = m.predict_proba(Xte)[:, 1]
        cm = confusion_matrix(y[te], pred, labels=[0, 1])
        p = precision_score(y[te], pred, zero_division=0)
        r = recall_score(y[te], pred, zero_division=0)
        f = f1_score(y[te], pred, zero_division=0)
        a = roc_auc_score(y[te], prob)
        precs.append(p); recs.append(r); f1s.append(f); aucs.append(a)
        print(f"Fold {i}: precision={p:.4f} recall={r:.4f} f1={f:.4f} auc={a:.4f}")
        print(f"  confusion matrix (rows=true [ADL,FALL], cols=pred [ADL,FALL]):")
        print(f"  {cm.tolist()}")
    print(f"MEAN: precision={np.mean(precs):.4f} recall={np.mean(recs):.4f} "
          f"f1={np.mean(f1s):.4f} auc={np.mean(aucs):.4f}")

run(lambda: DecisionTreeClassifier(max_depth=5, class_weight="balanced", random_state=42),
    False, "DecisionTree depth=5")
run(lambda: LogisticRegression(class_weight="balanced", max_iter=1000), True, "LogisticRegression")
