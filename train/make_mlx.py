#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Merge verified data rounds into one MLX-LM chat dataset (train.jsonl, valid.jsonl).

Each input row is {"id", "level", "prompt", "calls"}. It becomes
{"messages": [system SHORT, user prompt, assistant '{"calls":[...]}' (compact JSON)]}.
Rows are de-duplicated by id across rounds (first round wins), shuffled with a fixed seed (11) and split.

    python3 train/make_mlx.py --rounds round1,round2 --root path/to/rounds --out build/mlx_data --valid 200
"""
import argparse, json, os, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from maris3d.dsl.tools import SHORT  # noqa: E402


def build(round_dirs, valid=200, seed=11):
    seen, rows = set(), []
    for d in round_dirs:
        f = Path(d) / "train.jsonl"
        if not f.exists():
            raise FileNotFoundError(f)
        n = 0
        for line in open(f):
            r = json.loads(line)
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            n += 1
            rows.append({"messages": [{"role": "system", "content": SHORT},
                                      {"role": "user", "content": r["prompt"]},
                                      {"role": "assistant", "content": json.dumps({"calls": r["calls"]}, separators=(",", ":"))}]})
        print(f"{d}: +{n} (total {len(rows)})")
    if len(rows) <= valid:
        raise ValueError("too few rows for a validation split")
    random.Random(seed).shuffle(rows)
    return rows[valid:], rows[:valid]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=".", help="folder holding the round directories")
    ap.add_argument("--rounds", required=True, help="comma list of round directories, each with train.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--valid", type=int, default=200)
    a = ap.parse_args()
    train, valid = build([os.path.join(a.root, r) for r in a.rounds.split(",")], a.valid)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "train.jsonl").write_text("".join(json.dumps(r) + "\n" for r in train))
    (out / "valid.jsonl").write_text("".join(json.dumps(r) + "\n" for r in valid))
    print(f"wrote {out}: train {len(train)}, valid {len(valid)}")


if __name__ == "__main__":
    main()
