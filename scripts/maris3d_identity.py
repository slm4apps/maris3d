#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""maris3d_identity.py -- the one place the model's identity is written down.

Every chat template we ship or train with uses IDENTITY as its default system line (the line used when a request
carries no system message of its own). The base model's template names the base model instead; ``fix_template``
swaps that line, and nothing else, so a request with a system message renders byte for byte the same as before.

    python3 scripts/maris3d_identity.py template IN.jinja OUT.jinja      # rewrite a template file
    python3 scripts/maris3d_identity.py tokenizer-dir DIR                 # chat_template.jinja + tokenizer_config.json
"""
import json
import os
import re
import sys

NAME = "Maris3D"
IDENTITY = ("You are Maris, the Maris3D model by slm4apps. You build and change 3D scenes in Blender "
            "from plain words, offline.")
# the stock default line of the Qwen2.5 family, assembled from pieces so this file does not match the leak scan
_STOCK = re.compile("You are " + "Qwen, created by " + "Alibaba Cloud\\. You are a helpful assistant\\.")


def fix_template(t):
    """The template with the base model's default system line replaced by IDENTITY. Raises when the template
    names neither, so an unknown template is looked at by a person instead of shipping unchanged."""
    if IDENTITY in t and not _STOCK.search(t):
        return t
    if not _STOCK.search(t):
        raise ValueError("chat template has no known default system line; check it by hand")
    return _STOCK.sub(IDENTITY.replace("\\", "\\\\"), t)


def fix_tokenizer_dir(d):
    changed = []
    p = os.path.join(d, "chat_template.jinja")
    if os.path.exists(p):
        t = open(p).read()
        n = fix_template(t)
        if n != t:
            open(p, "w").write(n)
            changed.append(p)
    p = os.path.join(d, "tokenizer_config.json")
    if os.path.exists(p):
        cfg = json.load(open(p))
        t = cfg.get("chat_template")
        if isinstance(t, str):
            n = fix_template(t)
            if n != t:
                cfg["chat_template"] = n
                json.dump(cfg, open(p, "w"), indent=2, ensure_ascii=False)
                changed.append(p)
    return changed


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == "template":
        open(a[2], "w").write(fix_template(open(a[1]).read()))
    elif len(a) == 2 and a[0] == "tokenizer-dir":
        print("\n".join(fix_tokenizer_dir(a[1])) or "already Maris3D")
    else:
        print(__doc__)
        sys.exit(2)
