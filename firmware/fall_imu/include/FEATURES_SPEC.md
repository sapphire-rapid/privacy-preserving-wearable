# FEATURES_SPEC.md

## 1. Source of the 9 features (verbatim from `src/features_v2.py`)

Constants (from `features_v2.py`):
```python
FS_IN = 200; UP, DOWN = 26, 100
WIN = 104; STRIDE = 26
G_FACTOR = (2 * 16) / (2 ** 13)

FEATURE_NAMES = ["max_mag", "min_mag", "mean_mag", "std_mag", "range_mag",
                 "max_jerk", "std_mag_post", "count_low", "tilt_deg"]
```

Helper `parse_file`:
```python
def parse_file(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip().rstrip(";").strip()
            if not line: continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3: continue
            rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
    arr = np.asarray(rows, dtype=float) * G_FACTOR
    out = np.column_stack([resample_poly(arr[:, i], UP, DOWN) for i in range(3)])
    return out
```

Helper `mag`:
```python
def mag(a): return np.sqrt((a ** 2).sum(axis=1))
```

Feature function `tilt_deg`:
```python
def tilt_deg(sig):
    m = mag(sig)
    peak = int(np.argmax(m))
    if peak >= 26:
        before = sig[peak - 26:peak]
    else:
        before = sig[:10]
    after = sig[-26:] if len(sig) >= 26 else sig
    u = before.mean(axis=0)
    v = after.mean(axis=0)
    nu = np.linalg.norm(u); nv = np.linalg.norm(v)
    if nu == 0 or nv == 0:
        return 0.0
    cos = np.clip(np.dot(u, v) / (nu * nv), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos)))
```

Feature function `features_of_window`:
```python
def features_of_window(w):
    m = mag(w)
    jerk = np.abs(np.diff(m))
    post = m[-52:] if len(m) >= 52 else m
    return [float(m.max()), float(m.min()), float(m.mean()), float(m.std()),
            float(m.max() - m.min()), float(jerk.max()) if len(jerk) else 0.0,
            float(post.std()), float((m < 0.5).sum()), tilt_deg(w)]
```

Notes:
- `mag(w)` returns |a| in g (float64).
- `jerk` is |diff(|a|)| per sample (g/sample).
- `post` = last 52 samples of |a| (1.0 s at 52 Hz).
- `count_low` = number of samples with |a| < 0.5 g.
- `tilt_deg` = angle (degrees) between mean accel vector over 0.5 s before the peak and mean accel vector over the last 0.5 s of the window.

## 2. Worked example: FIRST window in `include/test_windows.h`

Source trial: `F13_SA14_R05.txt` (fall, subject SA14, trial 5).
Resampled signal length: 780 samples @ 52 Hz.
Window start index: 189 (0-based), so window covers resampled samples [189, 293).
Impact peak index (global): 230, |a| = 3.0244258448708665 g.
Peak index within window: 41 (230 - 189), |a| = 3.0244258448708665 g.

Tilt computation:
- before segment: 26 samples immediately before the peak within the window, indices [15, 41) of the window (resampled global [204, 230)).
  before mean vector u = [0.3069280309664971, -0.5537392552514727, -0.676132493392285]
  |u| = 0.9262759457204397
- after segment: last 26 samples of the window, indices [78, 104) (resampled global [267, 293)).
  after mean vector v = [0.9742803362020575, 0.10280367959073299, 0.1374838081761493]
  |v| = 0.9892889201633689
- cos = (u . v) / (|u| |v|) = 0.16276477858875635 (clamped to [-1, 1]; no clamp needed here)
- angle = arccos(cos) in degrees = 80.63258955001758 deg

9 features (float64 during computation; stored as float32 in test_windows.h):
1. max_mag     = 3.024425745010376
2. min_mag     = 0.4813745617866516
3. mean_mag    = 1.0845192670822144
4. std_mag     = 0.3838688135147095
5. range_mag   = 2.543051242828369
6. max_jerk    = 1.15291166305542
7. std_mag_post= 0.09045233577489853
8. count_low   = 1.0
9. tilt_deg     = 80.6325912475586

Expected probability (final LR, threshold 0.93): 0.9889366879421754
Expected trigger: 1 (prob >= 0.93)

## 3. Dtype and edge-case notes

Dtype at each step:
- Raw ADC counts: integer (text), parsed as Python float then `np.asarray(rows, dtype=float)`.
- After `* G_FACTOR`: float64.
- After `resample_poly`: float64 (scipy returns float64 for float64 input).
- `mag()` result: float64.
- `features_of_window` returns Python `float` (float64); `tilt_deg` returns `float(...)` (float64).
- Stored in CSV (pandas): float64.
- Stored in `test_windows.h` / `fall_model.h`: float32 (written with `.9g` + `f` suffix).
- StandardScaler mean/scale and LR coef/intercept: float64 in Python, written as float32 in header.

Edge cases handled:
- `parse_file`: skips blank lines and lines with fewer than 3 columns; strips trailing `;`.
- `tilt_deg` peak near window start: if `peak < 26`, use the first 10 samples as the "before" segment (`before = sig[:10]`) instead of `sig[peak-26:peak]`.
- `tilt_deg` after segment: if `len(sig) < 26`, use the whole signal (`sig`) instead of the last 26 samples.
- `tilt_deg` zero-length/zero-norm guard: if `nu == 0` or `nv == 0`, return 0.0.
- `tilt_deg` arccos clamping: `cos` is clamped to [-1.0, 1.0] via `np.clip` before `np.arccos`.
- `features_of_window` jerk: if `len(jerk) == 0` (window shorter than 2 samples), `max_jerk = 0.0`.
- `features_of_window` post-impact std: if `len(m) < 52`, use the whole magnitude array (`m`) instead of the last 52.
- `count_low`: counts samples with |a| < 0.5 g.
- `G_FACTOR` for ADXL345: (2*16)/(2^13) = 32/8192 = 0.00390625 g per LSB.
## 4. Stillness / confirmation check (verbatim from `src/eval_confirm.py`)

```python
def trial_alarm(rec, prob_thr, std_thr, conf_len, conf_samples):
    # returns (alarm bool, latency_sec or None, n_past_end)
    past_end = 0
    for wi, prob in rec["windows"]:
        if prob < prob_thr:
            continue
        start = wi * STRIDE
        seg_start = start + WIN
        seg_end = seg_start + conf_samples
        magarr = rec["mag"]
        if seg_end > len(magarr):
            # cannot fully evaluate -> conservative confirmed
            past_end += 1
            return True, None, past_end  # alarm
        seg = magarr[seg_start:seg_end]
        if seg.std() < std_thr and abs(seg.mean() - 1.0) < 0.2:
            # confirmed
            end_sec = seg_end / 52.0
            peak_sec = rec["peak_idx"] / 52.0
            latency = end_sec - peak_sec
            return True, latency, past_end
    return False, None, past_end
```

Notes:
- `conf_samples` = `int(conf_len * 52)` (e.g. 3.0 s -> 156 samples).
- `seg_start` = end of the triggering window (`wi * STRIDE + WIN`); the confirmation segment is the `CONFIRM_LEN` seconds of |a| immediately AFTER the triggering window.
- `seg.std()` uses numpy default `ddof=0` (population std).
- Comparisons are strict: `seg.std() < std_thr` and `abs(seg.mean() - 1.0) < 0.2`.
- If the segment runs past the end of the trial (`seg_end > len(magarr)`), it is treated as confirmed (conservative) and counted in `past_end`.
- Final parameters: `prob_thr = 0.93`, `std_thr = 0.05`, `conf_len = 3.0 s`, mean tolerance `0.2 g` around `1.0 g`.

### Worked example: first stillness segment in `include/test_windows.h`

First `StillSeg` in `test_windows.h` (expected `is_still = 1`), 156 samples of |a|:
- std (ddof=0) = 0.010485771596369148
- mean = 0.9994771266858974
- std < 0.05 ? True (0.0105 < 0.05)
- abs(mean - 1.0) < 0.2 ? True (0.000523 < 0.2)
- Result: still (confirmed). min/max of segment = 0.967728794 / 1.0296849.
