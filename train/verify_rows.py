#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify teacher-written training rows by running them in headless Blender (provider-neutral).

Input  JSONL rows: {"id", "level", "prompt", "calls", "check"}   (check = a scene-check spec, see src/maris3d/engine/checks.py)
Output <out>/train.jsonl (kept: schema ok, compiles, executes, passes its own check) and <out>/rejects.jsonl (with the stage and reason).

    python3 train/verify_rows.py --rows candidates.jsonl --out rounds/round1 [--blender /path/to/blender]

A row is kept only when ALL of these hold: (1) the tool document has 1 to 40 calls and every call is valid for the tool schema,
(2) it compiles to a bpy script, (3) the script executes in Blender without error, (4) the scene satisfies the check written for the
prompt. This is the only place where a data row is admitted; there is no manual editing. Prompts that are near-duplicates of a
benchmark prompt must be removed BEFORE this step (see docs/DATA-CARD.md, decontamination)."""
import argparse, json, os, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "eval", "maris3d_eval"))
from maris3d.dsl.tools import compile_calls   # noqa: E402
from maris3d.engine.checks import check       # noqa: E402
from validate_tool_refs_lib import schema_errors  # noqa: E402

SCENE_DUMP = os.path.join(HERE, "..", "src", "maris3d", "blender", "scene_dump.py")


def verify(row, blender):
    errs = schema_errors(row["calls"])
    if errs:
        return "schema", "; ".join(errs[:3]), None
    try:
        code = compile_calls({"calls": row["calls"]})
    except Exception as e:  # noqa: BLE001
        return "compile", str(e)[:200], None
    with tempfile.TemporaryDirectory() as d:
        s, o = f"{d}/s.py", f"{d}/o.json"
        with open(s, "w") as f:
            f.write(code)
        try:
            subprocess.run([blender, "-b", "-P", SCENE_DUMP, "--", s, o], capture_output=True, timeout=120)
            with open(o) as f:
                scene = json.load(f)
        except Exception as e:  # noqa: BLE001
            return "execute", f"harness: {e}"[:200], None
    if not scene.get("executed"):
        return "execute", (scene.get("error") or "")[-200:], None
    fails = check(scene, row["check"])
    return ("check", "; ".join(fails)[:200], None) if fails else (None, None, scene)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--blender", default=os.environ.get("BLENDER_BIN") or "blender")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.rows) if l.strip()]
    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(lambda r: verify(r, a.blender), rows))
    os.makedirs(a.out, exist_ok=True)
    kept = rej = 0
    with open(os.path.join(a.out, "train.jsonl"), "w") as tf, open(os.path.join(a.out, "rejects.jsonl"), "w") as rf:
        for r, (stage, why, _) in zip(rows, results):
            if stage is None:
                tf.write(json.dumps({k: r[k] for k in ("id", "level", "prompt", "calls")}) + "\n")
                kept += 1
            else:
                rf.write(json.dumps({"id": r["id"], "stage": stage, "reason": why}) + "\n")
                rej += 1
    print(f"kept {kept}, rejected {rej} of {len(rows)} ({100 * kept / max(1, len(rows)):.1f}% verified-pass)")


if __name__ == "__main__":
    main()
