#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""gguf_clean.py -- copy a GGUF with release metadata: our name, our identity, nothing from the build machine.

    python3 scripts/gguf_clean.py IN.gguf OUT.gguf --name "Maris3D SLM Blender 0.5B"

The converters write what they find on the machine that ran them: general.name and basename guessed from the
training folder, general.base_model.* and general.tags made from the local base-model path, an "mlx" tag, and
the base model's chat template with its stock identity. This copy:
  * sets general.name;
  * removes general.base_model.*, general.basename, general.finetune, general.tags, general.url, general.source.*;
  * replaces the template's default system line with scripts/maris3d_identity.IDENTITY (model files only);
  * keeps every tensor and every other key unchanged.
Then it reads the copy back with scripts/scan_private.py and fails (deleting the copy) on any finding.
Needs the gguf package (pip install gguf==0.17.1).
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gguf_meta  # noqa: E402
import maris3d_identity as I  # noqa: E402
import scan_private as S  # noqa: E402

DROP_PREFIX = ("general.base_model.", "general.source.", "general.dataset.")
DROP = {"general.basename", "general.finetune", "general.tags", "general.url", "general.repo_url",
        "general.organization", "general.author", "general.base_model.count"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--name", required=True)
    ap.add_argument("--python", default=sys.executable, help="a python with the gguf package")
    a = ap.parse_args()
    if not a.name.startswith(I.NAME):
        sys.exit("the name must start with " + I.NAME)
    meta = gguf_meta.read_all(a.src)
    cmd = [a.python, "-m", "gguf.scripts.gguf_new_metadata", a.src, a.dst, "--general-name", a.name, "--force"]
    for k in meta:
        if k in DROP or k.startswith(DROP_PREFIX):
            cmd += ["--remove-metadata", k]
    if "tokenizer.chat_template" in meta:
        cmd += ["--chat-template", I.fix_template(meta["tokenizer.chat_template"])]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("gguf_new_metadata failed:\n" + r.stderr[-2000:])
    found = S.scan_file(a.dst, os.path.basename(a.dst))
    if found:
        os.remove(a.dst)
        sys.exit("still not clean, copy removed:\n" + "\n".join(x["rule"] for x in found))
    print("clean:", a.dst)


if __name__ == "__main__":
    main()
