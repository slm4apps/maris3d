# SPDX-License-Identifier: Apache-2.0
"""Assemble the Blender add-on: the addon/ sources + vendored core modules, one extension dir.

The vendored copies are produced FROM the real modules at install time — single
source of truth; the fidelity test fails the build if the assembly ever drifts
from the sources (missing rewrite anchors assert loudly)."""
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parent  # src/maris3d
EXT_NAME = "maris3d_copilot"
VERSION = "0.2.1"

_ADDON_FILES = ("__init__.py", "executor.py", "client.py", "summary.py", "selftest.py",
                 "routing.py", "show.py")
# Maris (built by assets/maris/build_maris.py): the contract and the rigged asset. The package carries a copy
# (addon/maris, so an installed wheel has it); a source checkout without it falls back to assets/maris.
_MARIS = SRC / "addon" / "maris"
if not (_MARIS / "maris.json").exists():
    _MARIS = Path(__file__).resolve().parents[2] / "assets" / "maris"
_MARIS_FILES = ("maris.json", "maris.blend")

# source module (under src/maris3d) -> vendored filename (under vendor/)
_VENDOR = {
    "dsl/tools.py": "dsl_tools.py",
    "copilot/protocol.py": "protocol.py",
    "copilot/plan.py": "plan.py",
    "copilot/place.py": "place.py",
    "copilot/recipes.py": "recipes.py",
    "copilot/compile_plan.py": "compile_plan.py",
    "copilot/animate.py": "animate.py",
    "copilot/apply_change.py": "apply_change.py",
    "copilot/describe_parts.py": "describe_parts.py",
    "copilot/size_words.py": "size_words.py",
    "copilot/edit_words.py": "edit_words.py",
    "copilot/describe_scene.py": "describe_scene.py",
    "copilot/loop.py": "loop.py",
    "copilot/policy.py": "policy.py",
    "copilot/session.py": "session.py",
    "copilot/framing.py": "framing.py",
    "copilot/trace.py": "trace.py",
    "copilot/show.py": "show.py",
    "copilot/colours.py": "colours.py",
    "copilot/vocabulary.py": "vocabulary.py",
    "text/__init__.py": "text.py",
    "runtimes/base.py": "runtime_base.py",
    "runtimes/llama_server.py": "llama_server.py",
    "runtimes/ollama.py": "ollama.py",
}
_REWRITES = {
    "runtimes/base.py": [("from ..copilot.protocol import load_tools", "from .protocol import load_tools")],
    "copilot/loop.py": [("from ..text import t", "from .text import t")],
    "runtimes/llama_server.py": [("from .base import Runtime, post_json",
                                  "from .runtime_base import Runtime, post_json")],
    "runtimes/ollama.py": [("from .base import Runtime, post_json",
                            "from .runtime_base import Runtime, post_json")],
}


def assemble(dest):
    """dest may be the parent dir (extension dir is created inside) or the extension dir itself."""
    dest = Path(dest)
    if dest.name != EXT_NAME:
        dest = dest / EXT_NAME
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    addon = SRC / "addon"
    for name in _ADDON_FILES:
        shutil.copyfile(addon / name, dest / name)
    shutil.copyfile(addon / "manifest.toml", dest / "blender_manifest.toml")
    vendor = dest / "vendor"
    (vendor / "data").mkdir(parents=True)
    (vendor / "__init__.py").write_text("# vendored single-source copies, assembled by maris3d.addonbuild\n",
                                        encoding="utf-8")
    for src, name in _VENDOR.items():
        text = (SRC / src).read_text(encoding="utf-8")
        for old, new in _REWRITES.get(src, []):
            if old not in text:
                raise RuntimeError(f"assemble: rewrite anchor missing in {src}: {old!r}")
            text = text.replace(old, new)
        (vendor / name).write_text(text, encoding="utf-8")
    shutil.copyfile(SRC / "copilot" / "data" / "TOOLS.json", vendor / "data" / "TOOLS.json")
    (vendor / "data" / "text").mkdir()
    for lang in (SRC / "text").glob("*.json"):
        shutil.copyfile(lang, vendor / "data" / "text" / lang.name)
    (dest / "maris").mkdir()
    for name in _MARIS_FILES:
        shutil.copyfile(_MARIS / name, dest / "maris" / name)
    return dest


def build_zip(out="dist"):
    out = Path(out) if Path(out).is_absolute() else Path.cwd() / out
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        ext = assemble(tmp)
        path = out / f"{EXT_NAME}-{VERSION}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(ext.rglob("*")):
                z.write(f, f.relative_to(ext.parent))
    return path


def find_blender():
    from .executors.live import _find_blender
    return _find_blender()


def blender_version(blender_bin):
    out = subprocess.run([blender_bin, "--version"], capture_output=True, text=True, timeout=90).stdout
    m = re.search(r"Blender\s+(\d+)\.(\d+)", out)
    if not m:
        raise RuntimeError(f"cannot parse Blender version from {blender_bin}")
    return f"{m.group(1)}.{m.group(2)}"


def addons_dir(blender_bin):
    """The user's legacy add-ons dir for this Blender (works 4.2 → 5.2, auto-enablable headlessly).
    Asked from Blender itself first: Blender decides it (BLENDER_USER_RESOURCES / BLENDER_USER_SCRIPTS, and on
    macOS it ignores $HOME), so a guessed path can differ from the one Blender loads add-ons from."""
    try:
        r = subprocess.run([blender_bin, "-b", "--factory-startup", "--python-expr",
                            "import bpy; print('COPT-ADDONS-DIR=' + bpy.utils.user_resource('SCRIPTS', path='addons'))"],
                           capture_output=True, text=True, timeout=120)
        m = re.search(r"COPT-ADDONS-DIR=(.+)", r.stdout)
        if m and m.group(1).strip():
            return Path(m.group(1).strip())
    except (OSError, subprocess.SubprocessError):
        pass
    ver = blender_version(blender_bin)
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support" / "Blender"
    elif sys.platform == "win32":
        base = home / "AppData" / "Roaming" / "Blender Foundation" / "Blender"
    else:
        base = home / ".config" / "blender"
    return base / ver / "scripts" / "addons"


def install_into_blender(blender_bin=None):
    """Assemble + copy into Blender's add-ons dir. Returns (ext_dir, addons_dir)."""
    blender_bin = blender_bin or find_blender()
    if not blender_bin:
        raise RuntimeError("Blender not found: set BLENDER_BIN or install Blender 4.2+ (5.2 LTS verified)")
    target = addons_dir(blender_bin) / EXT_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = assemble(tmp)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src, target)
    return target, target.parent


def configure_addon(blender_bin, server_url, model):
    """Point the add-on at the server the installer just set up (and save the prefs).
    One-command install must leave the panel working without the user typing URLs."""
    expr = ("import bpy; p = bpy.context.preferences.addons['%s'].preferences; "
            "p.server_url = %r; p.model = %r; "
            "bpy.ops.wm.save_userpref(); print('COPT-CONFIGURED', p.server_url)"
            % (EXT_NAME, server_url, model))
    r = subprocess.run([blender_bin, "-b", "--python-expr", expr], capture_output=True, text=True, timeout=300)
    return r.returncode == 0 and "COPT-CONFIGURED" in (r.stdout + r.stderr)


def enable_in_blender(blender_bin, module=EXT_NAME):
    """Enable the add-on persistently, headlessly (enables + SAVES the user prefs:
    a -b session never autosaves userpref.blend on quit, so without save_userpref
    the enable dies with the session)."""
    expr = (f"import addon_utils; addon_utils.enable('{module}', default_set=True, persistent=True); "
            "import bpy; bpy.ops.wm.save_userpref(); "
            f"print('COPT-ENABLED', addon_utils.check('{module}') if hasattr(addon_utils,'check') else 'ok', "
            "'SAVED')")
    r = subprocess.run([blender_bin, "-b", "--python-expr", expr],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or "Error" in (r.stdout + r.stderr):
        raise RuntimeError(f"enabling failed: {(r.stderr or r.stdout)[-400:]}")
    return True
