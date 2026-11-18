#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Turn a raw run_eval.py output (summary + rows with generated code and local paths) into the public result form
(eval/result_schema.json): no code, no paths, tracebacks reduced to their last line.

    python3 scripts/import_result.py raw.json --name Maris3D-SLM-Blender-1.5B --format gguf-q8_0 --file maris3d-slm-blender-1.5b-Q8_0.gguf \
        --sha256 <hex> --blender 5.2.2 --out release/results/maris3d-1.5b-v0.1.json --source "description of origin"
"""
import argparse, hashlib, json, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PROMPTS = os.path.join(ROOT, "eval", "benchmark", "prompts.jsonl")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def last_line(err):
    if not err:
        return None
    line = [l for l in str(err).strip().splitlines() if l.strip()][-1]
    return re.sub(r"(/[\w.@-]+){2,}", "<path>", line)[:200]


def convert(raw, name, fmt, file, digest, blender, source):
    rows = [{"id": r["id"], "level": r["level"], "ran": bool(r["ran"]), "passed": bool(r["passed"]), "fails": list(r.get("fails") or []),
             "error": last_line(r.get("error")), "retries": r.get("retries", 0)} for r in raw["rows"]]
    s = raw["summary"]
    lv = {}
    for r in rows:
        a = lv.setdefault(str(r["level"]), [0, 0])
        a[0] += r["passed"]
        a[1] += 1
    n, passed, ran = len(rows), sum(r["passed"] for r in rows), sum(r["ran"] for r in rows)
    return {"schema": "maris3d-result/1",
            "model": {"family_name": name, "format": fmt, "file": file, "sha256": digest},
            "benchmark": {"n": n, "prompts_sha256": sha256(PROMPTS), "blender": blender},
            "settings": {"mode": s.get("mode"), "repair": s.get("repair"), "shots": s.get("shots"), "decoding": "greedy, 4096 ctx"},
            "summary": {"n": n, "passed": passed, "ran": ran, "run_pct": round(100 * ran / n, 2), "pass_pct": round(100 * passed / n, 2),
                        "by_level": {k: round(100 * v[0] / v[1], 1) for k, v in sorted(lv.items())},
                        "by_level_counts": {k: v for k, v in sorted(lv.items())},
                        "tok_s": s.get("tok_s"), "ttft_s_median": s.get("ttft_s_median"), "deprecated_hits": s.get("deprecated_hits")},
            "rows": rows, "source": {"note": source}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("raw")
    ap.add_argument("--name", required=True)
    ap.add_argument("--format", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--sha256")
    ap.add_argument("--blender", default="5.2.2")
    ap.add_argument("--source", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = convert(json.load(open(a.raw)), a.name, a.format, a.file, a.sha256, a.blender, a.source)
    if out["benchmark"]["n"] != 206:
        sys.exit("expected 206 rows, got %d" % out["benchmark"]["n"])
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print("wrote", a.out, out["summary"]["passed"], "/", out["summary"]["n"])


if __name__ == "__main__":
    main()
