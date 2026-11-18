#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Memory-capped mlx_lm LoRA launcher for a small Apple-silicon Mac (8 GB). One training job at a time.

    python3 train/safe_train.py --name NAME --model Qwen/Qwen2.5-Coder-0.5B-Instruct --data build/mlx_data --iters 5000 \
        --lr 1e-4 --num-layers 16 --batch-size 2 --accum 1 --max-seq 1024 --save-every 1000

What it does: refuses to start when free memory is low or another LoRA run is active, caps MLX memory (4.5 GB) and its
cache (512 MB), resumes from the last saved adapter, logs the peak memory, and stops the run if macOS reports critical
memory pressure for 30 s. Everything unknown is passed on to `mlx_lm lora` unchanged. Output goes to build/adapters-NAME.
"""
import argparse, os, re, subprocess, sys, threading, time
from pathlib import Path

BUILD = Path(os.environ.get("MARIS3D_BUILD", "build"))
PY = os.environ.get("SLM_PY", sys.executable)
MEM_LIMIT = int(4.5 * 1024 ** 3)
CACHE_LIMIT = 512 * 1024 ** 2
MIN_FREE_PCT = 35  # macOS "System-wide memory free percentage"


def free_pct():
    out = subprocess.run(["memory_pressure"], capture_output=True, text=True).stdout
    m = re.search(r"free percentage:\s*(\d+)%", out)
    return int(m.group(1)) if m else 100


def critical():
    # kern.memorystatus_vm_pressure_level: 1 normal, 2 warn, 4 critical
    return subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"], capture_output=True, text=True).stdout.strip() == "4"


def log(f, msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    f.write(line + "\n")
    f.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--name", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--lr", default="1e-4")
    ap.add_argument("--num-layers", type=int, default=16)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--max-seq", type=int, default=512)
    ap.add_argument("--save-every", type=int, default=200)
    ap.add_argument("--no-pressure-check", action="store_true")
    a, extra = ap.parse_known_args()
    extra = [x for x in extra if x != "--"]
    adapters = BUILD / f"adapters-{a.name}"
    adapters.mkdir(parents=True, exist_ok=True)
    logf = open(BUILD / f"train-{a.name}.log", "a")
    if subprocess.run(["pgrep", "-f", "mlx_lm.* lora"], capture_output=True).returncode == 0:
        sys.exit("another mlx_lm lora run is active: one training job at a time")
    fp = free_pct()
    log(logf, f"free memory {fp}% (min {MIN_FREE_PCT}%)")
    if fp < MIN_FREE_PCT and not a.no_pressure_check:
        sys.exit(f"not starting: free memory {fp}% < {MIN_FREE_PCT}%. Close apps first.")
    resume = adapters / "adapters.safetensors"
    cmd = [PY, "-c", (
        "import sys,mlx.core as mx;"
        f"mx.set_memory_limit({MEM_LIMIT});mx.set_cache_limit({CACHE_LIMIT});"
        "from mlx_lm import lora;"
        "sys.argv=['mlx_lm.lora']+sys.argv[1:];"
        "import atexit;atexit.register(lambda:print('PEAK_MEMORY_GB %.2f'%(mx.get_peak_memory()/1024**3),flush=True));"
        "lora.main()")]
    cmd += ["--model", a.model, "--train", "--data", a.data, "--adapter-path", str(adapters),
            "--iters", str(a.iters), "--learning-rate", str(a.lr), "--num-layers", str(a.num_layers),
            "--batch-size", str(a.batch_size), "--grad-accumulation-steps", str(a.accum),
            "--max-seq-length", str(a.max_seq), "--grad-checkpoint", "--save-every", str(a.save_every)]
    if resume.exists():
        cmd += ["--resume-adapter-file", str(resume)]
        log(logf, f"resuming from {resume}")
    cmd += extra
    log(logf, "start: " + " ".join(cmd[3:]))
    p = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)
    stop = threading.Event()

    def watchdog():
        bad = 0
        while not stop.wait(10):
            bad = bad + 1 if critical() else 0
            if bad >= 3:
                log(logf, "memory pressure CRITICAL for 30 s: stopping (rerun to resume from the last save)")
                p.terminate()
                return
    threading.Thread(target=watchdog, daemon=True).start()
    rc = p.wait()
    stop.set()
    log(logf, f"finished rc={rc}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
