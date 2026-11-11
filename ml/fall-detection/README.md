# Fall-Detection Model (Stage 1)

Training pipeline for the on-device IMU fall classifier.

- Dataset: SisFall, full 38 subjects, 4505 files, resampled to 52 Hz, 2 s windows.
- Features: 9 magnitude/tilt features per window (see FEATURES_SPEC.md once added).
- Model: logistic regression — chosen over a decision tree for a better recall/false-alarm trade-off; trial-level result ≈ 95% fall recall with a post-trigger stillness-confirmation rule (3.0 s window) to suppress false alarms.
- Export: validated 1:1 against the Python reference via a host-side C test harness before porting to the XIAO.

> Populate this folder with the training scripts, FEATURES_SPEC.md, and the exported model header from the FallDetect pipeline.
