# SPDX-License-Identifier: Apache-2.0
"""maris3d — one command installs the Copilot add-on into Blender and wires the local model.

  maris3d install [--model edit-q8_0|q4_k_m] [--from DIR] [--skip-model] [--express]
  maris3d serve start|stop|status
  maris3d update [--from DIR-or-URL]      new adapter versions, without a new download of the base
  maris3d doctor
  maris3d build-zip [--out dist]

No agent/MCP config is ever written. Standard library only.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request

from . import addonbuild
from . import update as files
from .net import urlopen
from .runtimes.detect import detect

CACHE = Path.home() / ".cache" / "maris3d"
SETTINGS = Path.home() / ".config" / "maris3d" / "settings.json"
HF_BASE = "https://huggingface.co/slm4apps/Maris3D-Blender"
HF_TAG = "v0.1.0"   # 0.1 reads its own tagged files; later releases replace the files on main
MODELS = {"q8_0": "maris3d-slm-blender-0.5b-q8_0.gguf",            # the base everything rides on
          "edit-lora": "maris3d-slm-blender-0.5b-edit-lora-f16.gguf",  # 5.6 MB edit adapter
          # 5.6 MB planner (one sentence -> a plan in words). The add-on reads the planner's
          # generation from this NAME (`planner-v3`): keep that in the name of every later file.
          "planner-lora": "maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf",
          "edit-q8_0": "maris3d-slm-blender-0.5b-edit-q8_0.gguf",  # merged, for hosts without adapters
          "q4_k_m": "maris3d-slm-blender-0.5b-q4_k_m.gguf"}       # 25% smaller, measured worse — warn
PORT = 9931
# the product: ONE server (base q8_0) with the edit adapter loaded; the copilot asks for
# scale 0 on a fresh prompt and 1.0 on a correction, so build and edit share 512 MB.
PRODUCT = ("q8_0", "edit-lora")
# Plan mode needs its own adapter (the base alone parses 0 of 75 plans). It is loaded beside the
# edit adapter and only ever runs alone, on a plan turn. Optional: a release without the file
# still installs and serves; Plan mode then says what is missing.
OPTIONAL = ("planner-lora",)


def _say(msg):
    print(msg, flush=True)


def _get(url, timeout=30):
    with urlopen(Request(url), timeout=timeout) as r:
        return r.read()


def _source(from_dir=None):
    """Where release files come from: an air-gapped bundle folder, or the Hugging Face repo."""
    return str(Path(from_dir).expanduser()) if from_dir else f"{HF_BASE}/resolve/{HF_TAG}"


def download_model(variant="edit-q8_0", source=None):
    """One GGUF from the release (HF or a bundle folder), streamed to disk and sha256-checked
    against the release SHA256SUMS. A file already in place is kept only when its hash matches."""
    name = MODELS[variant]
    source = source or _source()
    models = CACHE / "models"
    models.mkdir(parents=True, exist_ok=True)
    dest = models / name
    with files._open(source, "SHA256SUMS") as f:
        sums = f.read().decode()
    line = next((l for l in sums.splitlines() if l.split() and l.split()[-1] == name), "")
    if not line:
        raise RuntimeError(f"{name} not listed in the release SHA256SUMS")
    want = line.split()[0]
    if dest.exists() and files.sha256_of(str(dest)) == want:
        return dest, "already downloaded"
    _say(f"downloading {name} ({'~6 MB' if 'lora' in name else '~400-530 MB'}, sha-verified)...")
    files._fetch(source, {"file": name, "sha256": want}, str(models))  # streamed, checked, then moved in
    return dest, want[:16]


def find_llama_server(extra=()):
    """A llama-server this installer unpacked, one in a bundle folder, or one on PATH."""
    import shutil
    exe = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    for root in [Path(d).expanduser() for d in extra if d] + [CACHE / "llama"]:
        if root.is_dir():
            hit = next((q for q in sorted(root.rglob(exe)) if q.is_file()), None)
            if hit:
                return str(hit)
    if (CACHE / exe).is_file():               # where older installers put it
        return str(CACHE / exe)
    return shutil.which("llama-server")


def _llama_asset():
    """The release archive suffix for this machine (ggml-org/llama.cpp asset names, Nov 2026)."""
    import platform
    arm = platform.machine().lower() in ("arm64", "aarch64")
    if sys.platform == "darwin":
        return f"-bin-macos-{'arm64' if arm else 'x64'}.tar.gz"
    if sys.platform.startswith("linux"):
        return f"-bin-ubuntu-vulkan-{'arm64' if arm else 'x64'}.tar.gz"
    if sys.platform == "win32":
        return f"-bin-win-vulkan-{'arm64' if arm else 'x64'}.zip"
    return None


def download_llama_server():
    """Best-effort fetch of a ggml-org release build for this platform (Metal on Mac, Vulkan on
    Windows / Linux). The whole archive is unpacked: llama-server needs the libraries beside it."""
    import shutil
    want = _llama_asset()
    if not want:
        return None
    releases = json.loads(_get("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10", timeout=30))
    asset = next((a for rel in releases for a in rel.get("assets", []) if a["name"].endswith(want)), None)
    if not asset:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / asset["name"]
    if not archive.exists():
        part = archive.with_name(archive.name + ".part")
        with urlopen(Request(asset["browser_download_url"]), timeout=600) as r, open(part, "wb") as f:
            for block in iter(lambda: r.read(1 << 20), b""):
                f.write(block)
        part.rename(archive)
    out = CACHE / "llama"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    if archive.name.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(archive) as z:
            z.extractall(out)
    else:
        import tarfile
        with tarfile.open(archive) as t:
            t.extractall(out, filter="data")
    binary = find_llama_server()
    if not binary or not binary.startswith(str(out)):
        return None
    if not binary.endswith(".exe"):
        Path(binary).chmod(0o755)
    return binary


def selftest(blender_bin, live=None):
    """Run the assembled extension's headless self-test in blender -b. live: a llama-server URL
    for one real request through the loop (None: the canned leg only)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ext = addonbuild.assemble(tmp)
        env = dict(os.environ)
        if live:
            env["MARIS3D_SERVER"] = live
        r = subprocess.run([blender_bin, "-b", "--factory-startup", "--python", str(ext / "selftest.py")],
                           capture_output=True, text=True, timeout=600, env=env)
        out = r.stdout + r.stderr
        ready = next((l for l in out.splitlines() if "SELFTEST READY" in l), None)
        return ready, out


def _interactive(args):
    """Default = interactive when a human is at a terminal; --express or a non-tty
    stdin (scripts, CI, headless installs) never prompt and install everything
    missing automatically (the previous always-express behaviour)."""
    return not getattr(args, "express", False) and sys.stdin.isatty()


def _ask_yes(prompt, default=True):
    tip = "[Y/n]" if default else "[y/N]"
    while True:
        ans = input(f"{prompt} {tip} ").strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("please answer y or n")


def cmd_install(args):
    live = _interactive(args)
    blender = addonbuild.find_blender()
    if not blender:
        _say("Blender not found. Set BLENDER_BIN or install Blender 4.2+ (5.2 LTS is the verified version).")
        return 1
    ver = addonbuild.blender_version(blender)
    _say(f"Blender {ver} found: {blender}")
    if args.model == "q4_k_m":
        _say("note: q4_k_m is the measured-worse quantisation (see docs/BENCHMARKS.md); "
             "the q8_0 base + edit adapter is the default.")
    if args.model == "all":
        _say("installing the product: q8_0 base + the 5.6 MB edit adapter (512 MB, one server).")
    if live and not _ask_yes("1/4 install the Maris3D Copilot add-on into this Blender?"):
        _say("add-on stage skipped — nothing was changed. Re-run without answering n, or use --express.")
        return 1
    ext, where = addonbuild.install_into_blender(blender)
    _say(f"add-on installed: {ext}")
    try:
        addonbuild.enable_in_blender(blender)
        _say("add-on enabled (3D View > Maris3D Copilot tab)")
    except Exception as e:
        _say(f"auto-enable failed ({e}) — enable 'Maris3D Copilot' in Blender preferences once.")
    found = detect()
    runtime = None
    if found:
        use_it = True if not live else _ask_yes(f"2/4 a model server is already running ({found[0].name}) — use it?")
        if use_it:
            _say(f"model server found: {found[0].name}")
            runtime = {"backend": found[0].name, "model": getattr(found[0], "model", "maris3d"),
                       "url": getattr(found[0], "base_url", "")}
            if found[0].name == "ollama":
                runtime["url"] = getattr(found[0], "base_url", "") or "http://127.0.0.1:11434"
        else:
            found = None
    if not found and not args.skip_model:
        want = True if not live else _ask_yes(
            "3/4 download the model (512 MB, sha-verified: base + edit adapter) and the llama-server "
            "binary (~25 MB) so the copilot runs fully local?")
        if want:
            source = _source(args.from_dir)
            variants = list(PRODUCT) if args.model == "all" else [args.model]
            gguFs = {}
            if args.model == "all":
                # the product files come from the release MANIFEST (streamed, sha-checked, recorded
                # in installed.json so `maris3d update` and `serve start` agree on what is there)
                report = files.update(source, str(CACHE / "models"), log=_say)
                now = _installed()
                failed = {f["file"] for f in report["failed"]}
                if now.get("base"):
                    gguFs[PRODUCT[0]] = Path(now["base"])
                if now.get("edit"):
                    gguFs[PRODUCT[1]] = Path(now["edit"])
                if now.get("planner"):
                    gguFs[OPTIONAL[0]] = Path(now["planner"])
                if PRODUCT[0] not in gguFs or PRODUCT[1] not in gguFs:
                    _say(f"model download failed: {', '.join(sorted(failed)) or 'base or edit file missing'}")
                    return 1
                for v in gguFs:
                    _say(f"model ready: {gguFs[v]}")
                if OPTIONAL[0] not in gguFs:
                    _say("planner adapter not installed - build and edit are unaffected; Plan mode needs it")
            else:
                for v in variants:
                    gguFs[v], note = download_model(v, source)
                    _say(f"model ready: {gguFs[v]} ({note})")
            binary = find_llama_server([args.from_dir]) or (None if args.from_dir else download_llama_server())
            if binary:
                _say(f"llama-server: {binary}")
                runtime = {"backend": "llama-server", "model": "maris3d",
                           "url": f"http://127.0.0.1:{PORT}", "binary": binary,
                           "gguf": str(gguFs.get(PRODUCT[0]) or gguFs[variants[-1]])}
                if PRODUCT[1] in gguFs:  # the product: one base file + the edit adapter
                    runtime["lora"] = str(gguFs[PRODUCT[1]])
                    if OPTIONAL[0] in gguFs:
                        runtime["planner"] = str(gguFs[OPTIONAL[0]])
            else:
                _say("llama-server binary not found and the automatic download failed — "
                     "install llama.cpp or run: maris3d serve start (see SERVE.md in the HF repo).")
        else:
            _say("model download skipped — the add-on is installed; run `maris3d install` again "
                 "when you want the model, or point the copilot at an existing server.")
    ready, out = None, ""
    want_test = True if not live else _ask_yes("4/4 run the headless self-test now?")
    if want_test:
        ready, out = selftest(blender, live=(runtime or {}).get("url") if (runtime or {}).get("backend") == "llama-server" else None)
        if ready:
            _say(ready)
        else:
            _say("self-test did not report READY — inspect with: maris3d doctor")
            _say(out[-600:])
    else:
        _say("self-test skipped — verify later with: maris3d doctor")
    if runtime and runtime.get("backend") in ("llama-server", "ollama"):
        try:
            ok = addonbuild.configure_addon(blender, runtime.get("url", ""), runtime.get("model") or "maris3d",
                                            backend=runtime["backend"])
            _say("add-on pointed at the local server(s)" if ok else "could not set the add-on URLs — set them in the add-on preferences")
            if not ok:
                _say(getattr(addonbuild.configure_addon, "last_output", ""))
        except Exception as e:
            _say(f"add-on URL setup skipped ({e})")
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps({"blender": str(blender), "blender_version": ver,
                                    "addon_dir": str(ext), "runtime": runtime or {}}, indent=2))
    _say(f"settings saved: {SETTINGS}")
    if ready is None:
        _say("Install complete (self-test skipped). Open Blender: 3D View > Maris3D Copilot tab in the N-panel.")
        return 0
    _say("Ready. Open Blender, look for the Maris3D Copilot tab in the 3D View N-panel." if ready
         else "Partial install — run doctor to see what is missing.")
    return 0 if ready else 2


def serve_command(binary, gguf, lora, port, planner=None, more=()):
    """The llama-server command line. Adapters are loaded once and NOT applied until a request
    asks: edit first (id 0), planner second, then any other role the updater installed (build,
    parts); the copilot reads each id back by file name."""
    cmd = [binary, "-m", str(gguf), "--jinja", "-c", "8192", "--temp", "0",
           "--port", str(port), "--host", "127.0.0.1"]
    if lora:  # loaded once, not applied until a request asks for it (scale 0 = build)
        for path in [lora, planner, *more]:
            if path:
                cmd += ["--lora", str(path)]
        cmd += ["--lora-init-without-apply"]
    return cmd


def _start_one(binary, gguf, lora, port, pid_path, log, planner=None, more=()):
    cmd = serve_command(binary, gguf, lora, port, planner, more)
    _say(" ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    pid_path.write_text(str(proc.pid))
    for _ in range(60):
        time.sleep(0.5)
        try:
            json.loads(_get(f"http://127.0.0.1:{port}/props", timeout=2))
            _say(f"llama-server up on :{port} (pid {proc.pid}, model {Path(gguf).name}"
                 + (f" + {Path(lora).name}" if lora else "") + ")")
            return proc.pid
        except Exception:
            if proc.poll() is not None:
                _say(f"llama-server on :{port} exited at startup — see {CACHE / 'serve.log'}")
                return None
    _say(f"slow start on :{port}; still booting — check maris3d serve status")
    return proc.pid


def _stop_one(pid_path, port):
    if not pid_path.exists():
        return False
    try:
        os.kill(int(pid_path.read_text().strip()), 15)
        pid_path.unlink(missing_ok=True)
        _say(f"stopped :{port}")
        return True
    except Exception as e:
        _say(f"nothing on :{port} ({e})")
        return False


def _adapters(port):
    try:
        out = json.loads(_get(f"http://127.0.0.1:{port}/lora-adapters", timeout=3))
        return out if isinstance(out, list) else []
    except Exception:
        return []


def cmd_serve(args):
    pid = CACHE / "serve.pid"
    if args.action == "status":
        try:
            props = json.loads(_get(f"http://127.0.0.1:{PORT}/props", timeout=4))
            _say(f"llama-server up: {props.get('model_path', '?').rsplit('/', 1)[-1]}")
            adapters = _adapters(PORT)
            if adapters:
                names = [Path(a.get("path", "?")).name for a in adapters]
                _say("adapters loaded: " + ", ".join(names)
                     + " (build turns run none, edits the edit adapter, Plan the planner)")
                if not any("planner" in n for n in names):
                    _say("no planner adapter on this server - Plan mode will not produce plans")
            else:
                _say("no adapter loaded — one merged file serves build and edit")
            return 0
        except Exception:
            _say(f"nothing on :{PORT}")
            return 1
    if args.action == "stop":
        return 0 if _stop_one(pid, PORT) else 1
    # start
    s = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {"runtime": {}}
    rt = s.get("runtime", {})
    binary = find_llama_server()
    if not binary:
        _say("no llama-server binary — run: maris3d install (or install llama.cpp)")
        return 1
    now = _installed()          # what `maris3d update` last put in place wins over older settings
    gguf = args.gguf or now.get("base") or rt.get("gguf") or str(CACHE / "models" / MODELS["q8_0"])
    lora = None if args.no_adapter else (args.lora or now.get("edit") or rt.get("lora")
                                         or str(CACHE / "models" / MODELS["edit-lora"]))
    # a merged file already contains the edit weights: never stack the adapter on it
    if lora and Path(gguf).name != MODELS["q8_0"] and gguf != now.get("base"):
        _say(f"{Path(gguf).name} is not the base file — serving it without the adapter")
        lora = None
    for path in (gguf,) + ((lora,) if lora else ()):
        if not Path(path).exists():
            _say(f"file missing: {path} — run: maris3d install")
            return 1
    planner = None
    if lora and not getattr(args, "no_planner", False):
        planner = getattr(args, "planner", None) or now.get("planner") or rt.get("planner") \
            or str(CACHE / "models" / MODELS["planner-lora"])
        if not Path(planner).exists():
            _say("planner adapter not found - serving without it (Plan mode will not produce plans)")
            planner = None
    CACHE.mkdir(parents=True, exist_ok=True)
    log = open(CACHE / "serve.log", "ab", buffering=0)
    more = [now[r] for r in files.ROLES[3:] if lora and now.get(r)]   # build, parts: whatever update installed
    if _start_one(binary, gguf, lora, PORT, pid, log, planner, more) is None:
        return 1
    if lora:
        _say(f"one server, 512 MB: {Path(gguf).name} + {Path(lora).name}; "
             "the copilot switches it per request (build 0.0, edit 1.0)")
    return 0


def _installed(models=None):
    """{role: path} of the files the updater has recorded in the models folder, {} when none."""
    models = str(models or CACHE / "models")
    try:
        listed = files.read_installed(models).get("files", [])
    except Exception:
        return {}
    out = {e["role"]: os.path.join(models, e["file"]) for e in listed}
    return {role: path for role, path in out.items() if os.path.isfile(path)}


def cmd_update(args):
    """Bring the models folder to the release's MANIFEST.json: a file that is already there and
    right is kept (the 530 MB base is not fetched again), a new adapter replaces the old one."""
    source = args.source or f"{HF_BASE}/resolve/{HF_TAG}"
    models = CACHE / "models"
    try:
        report = files.update(source, str(models), log=_say)
    except Exception as e:
        _say(f"update failed: {e}")
        return 1
    _say(f"release {report['release']}: kept {len(report['kept'])}, fetched {len(report['fetched'])}, "
         f"removed {len(report['removed'])}, {report['bytes_transferred']:,} bytes transferred")
    if report["failed"]:
        _say("not everything was installed; what was there before keeps serving")
        return 1
    if report["fetched"]:
        _say("restart the server to load the new files: maris3d serve stop && maris3d serve start")
    return 0


def cmd_doctor(_args):
    ok = True
    blender = addonbuild.find_blender()
    if blender:
        _say(f"[ok] Blender {addonbuild.blender_version(blender)}: {blender}")
    else:
        ok = False
        _say("[fail] Blender not found (BLENDER_BIN?)")
    if blender:
        ready, out = selftest(blender)
        _say(f"[{'ok' if ready else 'fail'}] in-Blender self-test: {ready or 'no READY (see below)'}")
        if not ready:
            ok = False
            _say(out[-500:])
    found = detect()
    _say(f"[{'ok' if found else 'warn'}] model servers: "
         + (", ".join(f"{f.name} ({getattr(f, 'model', '')})" for f in found) or "none found — serve or install one"))
    if SETTINGS.exists():
        _say(f"[ok] settings: {SETTINGS}")
    else:
        _say("[warn] no settings yet — run: maris3d install")
    _say("[ok] all good" if ok else "[fail] something needs attention (install/serve)")
    return 0 if ok else 2


def cmd_build_zip(args):
    path = addonbuild.build_zip(args.out)
    _say(f"built {path}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="maris3d", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    from . import __version__
    p.add_argument("--version", action="version", version=f"maris3d {__version__} (models {HF_TAG})")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install", help="add-on + local model, self-tested")
    i.add_argument("--model", choices=list(MODELS) + ["all"], default="all",
                   help="all = base + edit adapter (default), or one file")
    i.add_argument("--from", dest="from_dir", help="air-gapped bundle dir (GGUF + llama-server + add-on)")
    i.add_argument("--skip-model", action="store_true", help="install the add-on only")
    i.add_argument("--express", action="store_true",
                   help="no prompts: install everything missing automatically "
                        "(also automatic when stdin is not a terminal, e.g. scripts/CI)")
    i.set_defaults(fn=cmd_install)
    s = sub.add_parser("serve", help="the private llama-server")
    s.add_argument("action", choices=["start", "stop", "status"], nargs="?", default="status")
    s.add_argument("--gguf", help="base model file (default: the q8_0 base)")
    s.add_argument("--lora", help="edit adapter (default: the shipped 5.6 MB edit LoRA)")
    s.add_argument("--planner", help="planner adapter for Plan mode (default: the shipped one, if installed)")
    s.add_argument("--no-planner", action="store_true", help="serve without the planner adapter")
    s.add_argument("--no-adapter", action="store_true", help="serve one merged file, no adapter")
    s.set_defaults(fn=cmd_serve)
    u = sub.add_parser("update", help="fetch new adapter versions; the base is kept")
    u.add_argument("--from", dest="source", help="a folder or URL that holds MANIFEST.json "
                                                 "(default: the Hugging Face repo)")
    u.set_defaults(fn=cmd_update)
    d = sub.add_parser("doctor", help="diagnose everything")
    d.set_defaults(fn=cmd_doctor)
    z = sub.add_parser("build-zip", help="package the add-on zip")
    z.add_argument("--out", default="dist")
    z.set_defaults(fn=cmd_build_zip)
    args = p.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
