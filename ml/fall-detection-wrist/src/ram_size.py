"""RAM cost of the deployed fall trigger, MEASURED where possible:
  * stack: arm-none-eabi-gcc -Os -mcpu=cortex-m4 -fstack-usage on the firmware's fall_features.h (new fall_model.h) -> .su file
  * static data: .bss/.data of that object (arm-none-eabi-size)
  * sample window buffer: WIN_SAMPLES x 3 floats owned by the caller (arithmetic from the header, not a measurement)
Writes results/ram.json.  The long-lie placeholder buffer (CONFIRM_SAMPLES floats) is listed separately and not part of the trigger."""
import os
import re
import json
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ROOT))
BUILD = os.path.join(ROOT, "cache", "ram_build")
INC = os.path.join(ROOT, "include")
FW = os.path.join(REPO, "firmware", "fall_imu", "include", "fall_features.h")
ARM = ["arm-none-eabi-gcc", "-mcpu=cortex-m4", "-mthumb", "-mfloat-abi=hard", "-mfpu=fpv4-sp-d16", "-Os", "-fstack-usage", "-c"]


def macro(name):
    return int(re.search(r"#define %s\s+(\d+)" % name, open(os.path.join(INC, "fall_model.h")).read()).group(1))


def main():
    os.makedirs(BUILD, exist_ok=True)
    shutil.copy(FW, os.path.join(BUILD, "fall_features.h"))
    src = os.path.join(BUILD, "ram.c")
    open(src, "w").write('#include "fall_features.h"\n'
                         'float trigger_prob(const float xyz[][3]) { float f[N_FEATURES]; fall_features(xyz, WIN_SAMPLES, f); return fall_lr_prob(f); }\n'
                         'int still(const float *m) { return fall_is_still(m, CONFIRM_SAMPLES); }\n')
    obj = os.path.join(BUILD, "ram.o")
    r = subprocess.run(ARM + ["-I", BUILD, "-I", INC, src, "-o", obj], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    su = {}
    for line in open(os.path.join(BUILD, "ram.su")):
        p = line.rstrip("\n").split("\t")
        su[p[0].split(":")[-1]] = int(p[1])
    sz = subprocess.run(["arm-none-eabi-size", obj], capture_output=True, text=True).stdout.splitlines()[1].split()
    win = macro("WIN_SAMPLES"); confirm = macro("CONFIRM_SAMPLES")
    out = dict(stack_bytes_trigger_prob=su.get("trigger_prob"), stack_bytes_still=su.get("still"), su_all=su,
               data_bytes=int(sz[1]), bss_bytes=int(sz[2]), window_buffer_bytes=win * 3 * 4,
               long_lie_placeholder_buffer_bytes=confirm * 4,
               note="stack from -fstack-usage (Cortex-M4F, -Os, static estimate by the compiler incl. callees only if inlined); window buffer = WIN_SAMPLES*3*4 B owned by the caller; libm exp/sqrt/atan2 stack not included")
    json.dump(out, open(os.path.join(ROOT, "results", "ram.json"), "w"), indent=1)
    print(out)


if __name__ == "__main__":
    main()
