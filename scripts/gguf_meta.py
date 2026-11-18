#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read the general.* string metadata of a GGUF file with the standard library only (no llama.cpp needed).

    python3 scripts/gguf_meta.py model.gguf        # prints general.name, general.version, general.basename ...
"""
import struct, sys

_FIXED = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
_FMT = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}


def _str(f):
    (n,) = struct.unpack("<Q", f.read(8))
    return f.read(n).decode("utf-8", "replace")


def _skip(f, t):
    if t in _FIXED:
        f.read(_FIXED[t])
    elif t == 8:
        _str(f)
    elif t == 9:
        (et,) = struct.unpack("<I", f.read(4))
        (n,) = struct.unpack("<Q", f.read(8))
        if et in _FIXED:
            f.seek(n * _FIXED[et], 1)
        else:
            for _ in range(n):
                _skip(f, et)
    else:
        raise ValueError("unknown GGUF value type %d" % t)


def read_general(path, max_kv=200):
    """Return {key: str|number|bool} for every scalar key that starts with 'general.'. Arrays are skipped."""
    out = {}
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError("not a GGUF file")
        (ver,) = struct.unpack("<I", f.read(4))
        _tensors, kv = struct.unpack("<QQ", f.read(16))
        for _ in range(min(kv, max_kv)):
            key = _str(f)
            (t,) = struct.unpack("<I", f.read(4))
            if key.startswith("general.") and t == 8:
                out[key] = _str(f)
            elif key.startswith("general.") and t in _FMT:
                out[key] = struct.unpack(_FMT[t], f.read(_FIXED[t]))[0]
            else:
                if not key.startswith("general.") and not key.startswith(("qwen2.", "llama.", "GGUF")):
                    if key.startswith("tokenizer."):
                        break  # general.* always precedes the tokenizer block
                _skip(f, t)
    return out


_BIG_ARRAYS = ("tokenizer.ggml.tokens", "tokenizer.ggml.merges", "tokenizer.ggml.token_type", "tokenizer.ggml.scores")


def read_all(path, max_kv=500):
    """Every metadata key of a GGUF file -> value (str, number, bool, or a list of strings). The vocabulary
    arrays are skipped (no metadata in them); only the header is read, so a 1 GB model takes milliseconds."""
    out = {}
    with open(path, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError("not a GGUF file")
        struct.unpack("<I", f.read(4))
        _tensors, kv = struct.unpack("<QQ", f.read(16))
        for _ in range(min(kv, max_kv)):
            key = _str(f)
            (t,) = struct.unpack("<I", f.read(4))
            if t == 8:
                out[key] = _str(f)
            elif t in _FMT:
                out[key] = struct.unpack(_FMT[t], f.read(_FIXED[t]))[0]
            elif t == 9 and key not in _BIG_ARRAYS:
                (et,) = struct.unpack("<I", f.read(4))
                (n,) = struct.unpack("<Q", f.read(8))
                if et == 8:
                    out[key] = [_str(f) for _ in range(n)]
                elif et in _FIXED:
                    f.seek(n * _FIXED[et], 1)
                else:
                    for _ in range(n):
                        _skip(f, et)
            else:
                _skip(f, t)
    return out


if __name__ == "__main__":
    for k, v in read_general(sys.argv[1]).items():
        print("%s = %r" % (k, v))
