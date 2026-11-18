#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Release gates for the single-model v0.1 layout (replaces the per-size promote.py gates).

  python3 scripts/release_check.py [--models DIR]

Each gate is ok / fail / pending. `pending` means a decision or measurement is still open (name, edit-adapter numbers);
only `fail` makes the exit code non-zero. The model file is checked only when it is present in --models
(default hf/Maris3D-Blender); nothing is downloaded.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import namedtuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "src")]
Gate = namedtuple("Gate", "name status detail")


def load(root=ROOT):
    with open(os.path.join(root, "release", "CURRENT.json"), encoding="utf-8") as f:
        return json.load(f)


def gate_score(cur):
    """Both blocks must be internally consistent; the product figure is the adapter pair."""
    blocks = [k for k in ("score", "score_routed") if k in cur["current"]]
    for key in blocks:
        s = cur["current"][key]
        if s["pass"] + s["partial"] + s["fail"] != s["n"]:
            return Gate("score", "fail", f"{key}: pass+partial+fail != n")
        if (round(100 * s["pass"] / s["n"], 1) != s["pass_pct"]
                or round(100 * (s["pass"] + s["partial"]) / s["n"], 1) != s["usable_pct"]):
            return Gate("score", "fail", f"{key}: percentages do not match the counts")
    p = cur["current"].get("score_routed") or cur["current"]["score"]
    label = "adapter pair" if "score_routed" in cur["current"] else "single file"
    return Gate("score", "ok", f'{label}: {p["pass"]}/{p["n"]} pass, {p["usable_pct"]}% usable')


def gate_tools():
    from maris3d.copilot.protocol import tools_sha256
    from maris3d.setup import TOOLS_SHA256
    return Gate("tools manifest", "ok" if tools_sha256() == TOOLS_SHA256 else "fail", tools_sha256()[:12])


def gate_artifact(cur, models_dir):
    art = cur["current"]["artifacts"]["gguf-edit-q8_0"]  # the default shipping file
    path = os.path.join(models_dir, art["file"])
    if not os.path.exists(path):
        return Gate("model file", "pending", f"{art['file']} not in {models_dir}")
    if os.path.getsize(path) != art["bytes"]:
        return Gate("model file", "fail", f"size {os.path.getsize(path)} != {art['bytes']}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return Gate("model file", "ok" if h.hexdigest() == art["sha256"] else "fail", h.hexdigest()[:12])


def gate_open_decisions(cur):
    open_items = []
    if "TBD" in str(cur.get("hf_org", "")) or "TBD" in str(cur["current"].get("public_name", "")):
        open_items.append("public name / account")
    if "UNCONFIRMED" in str(cur.get("repo_url", "")):
        open_items.append("repo URL")
    if "planned" in str(cur["current"].get("edit_adapter", "")) or "chosen by measured" in str(cur["current"].get("edit_adapter", "")):
        open_items.append("edit adapter numbers")
    return Gate("open decisions", "pending" if open_items else "ok", ", ".join(open_items))


def gate_scan():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "scan_private.py")], capture_output=True, text=True)
    return Gate("private scan", "ok" if out.returncode == 0 else "fail", (out.stdout.strip().splitlines() or [""])[-1])


STAGING = os.path.join(ROOT, "hf", "Maris3D-Blender")


def gate_staging_checksums(staging=STAGING):
    """Every staged file must match SHA256SUMS and be listed there. This is the gate that
    caught a card edited after the sums were generated."""
    sums = os.path.join(staging, "SHA256SUMS")
    if not os.path.exists(sums):
        return Gate("staging checksums", "fail", "SHA256SUMS missing")
    want = {}
    with open(sums, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                digest, name = line.split(None, 1)
                want[name.strip()] = digest
    listed = set(want)
    on_disk = set()
    for base, _dirs, files in os.walk(staging):
        for name in files:
            rel = os.path.relpath(os.path.join(base, name), staging)
            if rel == "SHA256SUMS":
                continue
            on_disk.add(rel)
    missing = sorted(listed - on_disk)
    unlisted = sorted(on_disk - listed)
    weights_only = missing and not unlisted and all(m.endswith(".gguf") for m in missing)
    if weights_only:
        listed -= set(missing)   # a clone has no weights (they are on Hugging Face): check the rest, report pending
    elif missing or unlisted:
        return Gate("staging checksums", "fail",
                    f"missing {missing[:3]} / unlisted {unlisted[:3]}")
    bad = []
    for rel, digest in want.items():
        if rel not in listed:
            continue
        h = hashlib.sha256()
        with open(os.path.join(staging, rel), "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        if h.hexdigest() != digest:
            bad.append(rel)
    if bad:
        return Gate("staging checksums", "fail", f"sha256 mismatch: {bad[:3]}")
    if weights_only:
        return Gate("staging checksums", "pending",
                    f"{len(listed)} files verified; weights not here (a clone; they are on Hugging Face): {missing[:3]}")
    return Gate("staging checksums", "ok", f"{len(want)} files verified")


def gate_one_card():
    """v0.1 has exactly one public card. Stale templates must not be resurrected."""
    stale = [p for p in ("MODEL_CARD.md", os.path.join("internal", "release", "MODEL-CARD.md"))
             if os.path.exists(os.path.join(ROOT, p))]
    if stale:
        return Gate("one card", "fail", f"stale card(s) present: {stale}")
    card = os.path.join(STAGING, "README.md")
    return Gate("one card", "ok" if os.path.exists(card) else "fail",
                "hf/Maris3D-Blender/README.md" if os.path.exists(card) else "public card missing")


def gate_product_files():
    """The product is ONE base file plus the edit adapter; both must be staged."""
    need = ("maris3d-slm-blender-0.5b-q8_0.gguf", "maris3d-slm-blender-0.5b-edit-lora-f16.gguf")
    missing = [n for n in need if not os.path.exists(os.path.join(STAGING, n))]
    return Gate("product files", "pending" if missing else "ok",
                f"missing {missing}" if missing else "base + edit adapter staged")


def run(models_dir, root=ROOT):
    cur = load(root)
    return [gate_score(cur), gate_tools(), gate_artifact(cur, models_dir), gate_open_decisions(cur),
            gate_staging_checksums(), gate_one_card(), gate_product_files(), gate_scan()]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=os.path.join(ROOT, "hf", "Maris3D-Blender"))
    gates = run(ap.parse_args(argv).models)
    for g in gates:
        print(f"{g.status.upper():8} {g.name}: {g.detail}")
    return 1 if any(g.status == "fail" for g in gates) else 0


if __name__ == "__main__":
    sys.exit(main())
