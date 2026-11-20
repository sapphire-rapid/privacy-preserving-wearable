# C parity (Step 6)

Firmware `fall_features.h` sha256[:16] `9ec8875932bda914` (`fall_features.h` itself is unmodified; it is copied byte-identically to a build dir so that its quoted include picks up the new `fall_model.h`). Exported operating point: mode `trig90`, thr 0.835, std 0.08, tol 0.2 (provisional=False).

- `host_test.c` built with gcc against the new headers: compile rc=0; run rc=0; last lines:

```
4     0          PASS  
5     0          PASS  

RESULT: ALL PASS (12 windows, 6 still segments)
```

- 1000 random train windows (800 random sliding + 200 fall-impact) through the C feature code vs Python float64 on the same float32 inputs; PASS needs every feature within 0.0001 relative:

| feature | max rel err | max abs err | windows over 1e-4 |
|---|---|---|---|
| max_mag | 8.98e-08 | 4.07e-07 | 0 |
| min_mag | 9.39e-08 | 9.40e-08 | 0 |
| mean_mag | 4.12e-07 | 5.10e-07 | 0 |
| std_mag | 4.28e-06 | 2.19e-07 | 0 |
| range_mag | 1.76e-05 | 5.48e-07 | 0 |
| max_jerk | 9.90e-06 | 6.01e-07 | 0 |
| std_mag_post | 1.95e-05 | 1.53e-07 | 0 |
| count_low | 0.00e+00 | 0.00e+00 | 0 |
| tilt_deg | 6.98e-05 | 2.50e-05 | 0 |

- probability: max |C − Python| = 3.77e-07
- trigger decisions at the exported threshold 0.835: **0 mismatches** of 1000 (203 triggers; 1 windows within 1e-4 of the threshold)
- same comparison at other thresholds: 0.003: 0 mismatches (980 triggers); 0.5: 0 mismatches (292 triggers); 0.671: 0 mismatches (249 triggers); 0.93: 0 mismatches (164 triggers)
- stillness decisions on 1000 random 3 s segments (std<0.08, |mean−1|<0.2): **0 mismatches** (131 still)

**RESULT: PASS** (features≤1e-4: True, decisions identical: True, host_test: True)
