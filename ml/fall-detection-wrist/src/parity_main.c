/* parity_main: run windows / stillness segments from binary files through the firmware's fall_features.h
 * (compiled against the NEW fall_model.h) and print the results as text for src/parity.py to compare with Python.
 *   parity_main <windows.bin> <segments.bin>
 *   windows.bin : int32 N, then N * (WIN_SAMPLES*3) float32  (x,y,z interleaved, g)
 *   segments.bin: int32 M, then M * CONFIRM_SAMPLES float32  (|a| in g)
 * stdout: "W <9 features> <prob> <trigger>" per window, "S <is_still>" per segment (%.9g floats). */
#include <stdio.h>
#include <stdlib.h>
#include "fall_features.h"

int main(int argc, char **argv)
{
    if (argc < 3) { fprintf(stderr, "usage: %s windows.bin segments.bin\n", argv[0]); return 2; }
    FILE *fw = fopen(argv[1], "rb");
    FILE *fs = fopen(argv[2], "rb");
    if (!fw || !fs) { fprintf(stderr, "cannot open inputs\n"); return 2; }
    int n = 0, m = 0;
    if (fread(&n, sizeof n, 1, fw) != 1 || fread(&m, sizeof m, 1, fs) != 1) { return 2; }
    static float xyz[WIN_SAMPLES][3];
    float feat[N_FEATURES];
    for (int i = 0; i < n; i++) {
        if (fread(xyz, sizeof(float), WIN_SAMPLES * 3, fw) != (size_t)(WIN_SAMPLES * 3)) { return 2; }
        fall_features(xyz, WIN_SAMPLES, feat);
        float p = fall_lr_prob(feat);
        printf("W");
        for (int j = 0; j < N_FEATURES; j++) { printf(" %.9g", (double)feat[j]); }
        printf(" %.9g %d\n", (double)p, fall_trigger(p));
    }
    static float mag[CONFIRM_SAMPLES];
    for (int i = 0; i < m; i++) {
        if (fread(mag, sizeof(float), CONFIRM_SAMPLES, fs) != (size_t)CONFIRM_SAMPLES) { return 2; }
        printf("S %d\n", fall_is_still(mag, CONFIRM_SAMPLES));
    }
    return 0;
}
