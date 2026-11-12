# Fall-Detection Model (Stage 1)

Training pipeline for the on-device IMU fall classifier.

- **Dataset:** SisFall, full 38 subjects, 4505 files, resampled to 52 Hz, 2 s windows. The raw dataset and derived feature matrices are not vendored here (regenerate via `src/features.py` / `src/features_v2.py` against the SisFall dataset — see `data/README.md`).
- **Features:** 9 magnitude/tilt features per window — see `include/FEATURES_SPEC.md`.
- **Model:** logistic regression (`v2`) — chosen over a decision tree for a better recall/false-alarm trade-off. Trial-level result: ~95% fall recall with a post-trigger stillness-confirmation rule (3.0 s window) to suppress false alarms. See `results/` for the full metrics (nested cross-validation folds, sweep tables, confusion matrix, recall-vs-false-alarm curve).
- **Export:** `src/export_c.py` / `src/export_final.py` export the trained model to C (`include/fall_model.h`); validated 1:1 against the Python reference via a host-side C test harness (`include/test_vectors.h`, `include/test_windows.h`) before porting to the XIAO. The deployed model lives alongside the firmware at `../../firmware/fall_imu/`.

## Layout

| Path | Contents |
|---|---|
| `src/` | Feature extraction (`features.py`, `features_v2.py`), training (`train.py`), evaluation (`eval_*.py`), C export (`export_c.py`, `export_final.py`) |
| `include/` | Exported model headers and the feature spec, shared with the firmware-side copy |
| `results/` | Metrics, sweep tables, nested-CV fold results, plots |
| `data/` | Dataset notes (raw SisFall data and derived feature CSVs are gitignored — regenerate locally) |
