#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Helpers for the hf/ staging folders: copy files in (APFS clone when possible), write and verify SHA256SUMS.

    python3 scripts/hf_stage.py sums  hf/maris3d-slm-blender-1.5b-GGUF       # (re)write SHA256SUMS
    python3 scripts/hf_stage.py check hf/maris3d-slm-blender-1.5b-GGUF       # verify SHA256SUMS, exit 1 on mismatch
    python3 scripts/hf_stage.py copy  SRC DEST_DIR [NAME]            # clone-copy one file into a staging folder
"""
import hashlib, os, shutil, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SUMS = "SHA256SUMS"
NOT_SUMMED = {SUMS, ".gitattributes", ".DS_Store"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def staged_files(folder):
    """Every file of the folder, also in sub-folders (figures/), as paths relative to it."""
    out = []
    for base, _dirs, names in os.walk(folder):
        out += [os.path.relpath(os.path.join(base, n), folder) for n in names if n not in NOT_SUMMED]
    return sorted(out)


def write_sums(folder):
    lines = ["%s  %s" % (sha256_file(os.path.join(folder, n)), n) for n in staged_files(folder)]
    with open(os.path.join(folder, SUMS), "w") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    return lines


def write_sums_from(folder, known=None):
    """Like write_sums, but use `known` {name: sha256} for files that are present or listed (avoids re-reading 3 GB weights when CURRENT.json
    already holds a verified hash). Weights listed in `known` but absent are still written (they are gitignored and staged locally)."""
    known = known or {}
    names = sorted(set(staged_files(folder)) | set(known))
    lines = []
    for n in names:
        if n == "README.md" or n not in known:
            lines.append("%s  %s" % (sha256_file(os.path.join(folder, n)), n))
        else:
            lines.append("%s  %s" % (known[n], n))
    with open(os.path.join(folder, SUMS), "w") as f:
        f.write("\n".join(lines) + "\n")
    return lines


def read_sums(folder):
    p = os.path.join(folder, SUMS)
    if not os.path.exists(p):
        return None
    out = {}
    for l in open(p):
        if l.strip():
            h, n = l.strip().split(None, 1)
            out[n.strip().lstrip("*")] = h
    return out


def check_sums(folder, allow_missing=False):
    """Return a list of problems (empty = every listed file exists, matches, and every staged file is listed).
    allow_missing=True tolerates listed-but-absent files (CI has no weights)."""
    sums = read_sums(folder)
    if sums is None:
        return ["%s missing" % SUMS]
    probs = []
    for n, h in sums.items():
        p = os.path.join(folder, n)
        if not os.path.exists(p):
            if not allow_missing:
                probs.append("%s listed but missing" % n)
        elif sha256_file(p) != h:
            probs.append("%s checksum mismatch" % n)
    probs += ["%s present but not in %s" % (n, SUMS) for n in staged_files(folder) if n not in sums and os.path.exists(os.path.join(folder, n))]
    return probs


def clone_copy(src, dest):
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    if sys.platform == "darwin":
        if subprocess.run(["cp", "-c", src, dest], capture_output=True).returncode == 0:
            return
    shutil.copyfile(src, dest)


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    if len(a) >= 2 and a[0] == "sums":
        print("\n".join(write_sums(a[1])))
    elif len(a) >= 2 and a[0] == "check":
        probs = check_sums(a[1])
        print("\n".join(probs) or "checksums ok")
        return 1 if probs else 0
    elif len(a) >= 3 and a[0] == "copy":
        clone_copy(a[1], os.path.join(a[2], a[3] if len(a) > 3 else os.path.basename(a[1])))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
