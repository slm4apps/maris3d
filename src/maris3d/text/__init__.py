# SPDX-License-Identifier: Apache-2.0
"""The words Maris3D says to people, kept in one keyed file per language (`en.json` beside this
module). Code asks for a line by its key:

    t("say.router.edit")                     -> "a change to what the scene has: the edit model"
    t("say.code.built", items=3, parts=12)   -> "built 3 things, 12 parts"

A key missing from the chosen language falls back to English; a key missing from English is
returned as it is, so a typo shows up in the panel instead of breaking a run. The language comes
from `set_language()` (the add-on's setting) or the MARIS3D_LANG environment variable.
The prompts the models are trained on (`*_SYSTEM`) are never in these files: they stay English."""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
# the package keeps en.json beside this file; the add-on's vendored copy keeps it in data/text/
_DIRS = (_HERE, os.path.join(_HERE, "data", "text"))
FALLBACK = "en"
_cache = {}
_lang = os.environ.get("MARIS3D_LANG", "").strip().lower() or FALLBACK


def _table(lang):
    if lang not in _cache:
        table = {}
        for d in _DIRS:
            path = os.path.join(d, lang + ".json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    table = json.load(f)
                break
        _cache[lang] = table
    return _cache[lang]


def languages():
    """The languages that have a file, English first."""
    found = set()
    for d in _DIRS:
        if os.path.isdir(d):
            found.update(n[:-5] for n in os.listdir(d) if n.endswith(".json"))
    return [FALLBACK] + sorted(found - {FALLBACK})


def language():
    return _lang


def set_language(lang):
    """Choose the language of every later line; an unknown one still answers in English."""
    global _lang
    _lang = (str(lang or "").strip().lower()) or FALLBACK
    return _lang


def keys(lang=FALLBACK):
    return set(_table(lang))


def t(key, **values):
    text = _table(_lang).get(key)
    if text is None:
        text = _table(FALLBACK).get(key, key)
    return text.format(**values) if values else text
