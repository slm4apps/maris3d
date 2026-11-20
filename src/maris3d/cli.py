# SPDX-License-Identifier: Apache-2.0
"""maris3d — one command installs the Copilot add-on into Blender and wires the local model.

  maris3d install [--model q8_0|one-lora|all] [--from DIR] [--skip-model] [--express]
  maris3d serve start|stop|status
  maris3d update [--from DIR-or-URL]      new adapter versions, without a new download of the base
  maris3d doctor
  maris3d build-zip [--out dist]

No agent/MCP config is ever written. Standard library only.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request

from .net import urlopen

from . import addonbuild
from .text import t
from . import update as files
from .runtimes.detect import detect

CACHE = Path.home() / ".cache" / "maris3d"
SETTINGS = Path.home() / ".config" / "maris3d" / "settings.json"
HF_BASE = "https://huggingface.co/slm4apps/Maris3D-Blender"
HF_TAG = "v0.2.2"   # install reads this release's tagged files; `maris3d update` reads main (MANIFEST needs_app guards it)
MODELS = {"q8_0": "maris3d-slm-blender-0.5b-q8_0.gguf",                    # the base everything rides on
          "one-lora": "maris3d-slm-blender-0.5b-v0.2.2-lora-f16.gguf",           # outline plan, word edit, talk
          "parts-lora": "maris3d-slm-blender-parts-lora-f16.gguf"}       # parts designer add-on
PORT = 9931
# the product: ONE server (base q8_0) with the one adapter loaded; the copilot names a role on
# every turn and that adapter runs alone, so planning and editing share 512 MB.
PRODUCT = ("q8_0", "one-lora")
# a separate parts adapter (designs a thing the library lacks) is optional: 0.2 ships without one,
# and the one adapter answers the parts turns (runtimes.llama_server.ONE_ROLES).
OPTIONAL = ()   # 0.2 ships no optional adapter (the parts adapter was folded into the one adapter)


def _say(msg):
    print(msg, flush=True)


def _get(url, timeout=30):
    with urlopen(Request(url), timeout=timeout) as r:
        return r.read()


def download_model(variant="q8_0", sha_line=None):
    """GGUF from HF, sha256-verified against the release SHA256SUMS (never hardcoded)."""
    name = MODELS[variant]
    models = CACHE / "models"
    models.mkdir(parents=True, exist_ok=True)
    dest = models / name
    min_size = 1_000_000 if "lora" in name else 400_000_000
    if dest.exists() and dest.stat().st_size > min_size:
        return dest, t("cli.already_downloaded")
    if not sha_line:
        sums = _get(f"{HF_BASE}/resolve/{HF_TAG}/SHA256SUMS").decode()
        sha_line = next((l for l in sums.splitlines() if l.strip().endswith(name)), "")
        if not sha_line:
            raise RuntimeError(t("cli.error.not_listed", name=name))
    want = sha_line.split()[0]
    _say(t("cli.downloading", name=name, size=t("cli.size.adapter") if "lora" in name else t("cli.size.model")))
    h = hashlib.sha256()
    tmp = dest.with_suffix(".part")
    with open(tmp, "wb") as f:
        body = _get(f"{HF_BASE}/resolve/{HF_TAG}/{name}", timeout=1800)
        h.update(body)
        f.write(body)
    got = h.hexdigest()
    if got != want:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(t("cli.error.sha_mismatch", name=name, got=got[:16], want=want[:16]))
    tmp.rename(dest)
    return dest, want[:16]


# One tested llama.cpp build. "latest" is not usable: its newest release can carry no binaries, and the
# asset names change (win-cpu-x64.zip, macos-arm64.tar.gz). Bump LLAMA_BUILD after testing a newer one.
LLAMA_BUILD = "b12503"
LLAMA_EXE = "llama-server.exe" if sys.platform == "win32" else "llama-server"


def _llama_asset():
    import platform
    m = platform.machine().lower()
    arm = m in ("arm64", "aarch64")
    return {"darwin": f"macos-{'arm64' if arm else 'x64'}.tar.gz",
            "linux": f"ubuntu-{'arm64' if arm else 'x64'}.tar.gz",
            "win32": f"win-cpu-{'arm64' if arm else 'x64'}.zip"}.get(sys.platform)


def find_llama_server():
    """The one `maris3d install` unpacked (with its libraries), else the one on PATH."""
    import shutil
    for p in sorted((CACHE / "llama").glob(f"*/**/{LLAMA_EXE}"), reverse=True):
        if p.is_file():
            return str(p)
    old = CACHE / LLAMA_EXE          # where 0.2.1 and earlier put a lone binary
    if old.is_file():
        return str(old)
    return shutil.which("llama-server")


def download_llama_server():
    """Best-effort fetch of the pinned ggml-org build for this platform; the whole archive is unpacked so
    the server's libraries (DLLs on Windows) sit next to it. Returns the server's path or None."""
    kind = _llama_asset()
    if not kind:
        return None
    name = f"llama-{LLAMA_BUILD}-bin-{kind}"
    url = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/{name}"
    dest = CACHE / "llama" / LLAMA_BUILD
    try:
        arc = CACHE / "llama" / name
        arc.parent.mkdir(parents=True, exist_ok=True)
        if not arc.exists():
            part = arc.with_name(arc.name + ".part")
            part.write_bytes(_get(url, timeout=600))
            part.rename(arc)
        dest.mkdir(parents=True, exist_ok=True)
        if name.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(arc) as z:
                z.extractall(dest)
        else:
            import tarfile
            with tarfile.open(arc) as z:
                try:
                    z.extractall(dest, filter="data")
                except TypeError:        # Python < 3.12: refuse absolute and parent paths by hand
                    root = dest.resolve()
                    for mbr in z.getmembers():
                        if not (dest / mbr.name).resolve().is_relative_to(root):
                            raise RuntimeError(f"unsafe path in archive: {mbr.name}")
                    z.extractall(dest)
        arc.unlink()
    except Exception as e:
        _say(t("cli.install.llama_download_failed", error=e))
        return None
    for p in dest.glob(f"**/{LLAMA_EXE}"):
        if p.is_file():
            if sys.platform != "win32":
                p.chmod(0o755)
            return str(p)
    return None


# Voice input: one tested whisper.cpp build (binaries for Linux and Windows; macOS uses Homebrew's
# whisper-cpp, or builds from the same source tag) and one small English model, sha256-pinned.
WHISPER_BUILD = "b5454"
WHISPER_SRC_TAG = "v1.9.5"
WHISPER_MODEL = "ggml-base.en-q5_1.bin"
WHISPER_MODEL_SHA = "4baf70dd0d7c4247ba2b81fafd9c01005ac77c2f9ef064e00dcf195d0e2fdd2f"
WHISPER_MODEL_URL = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{WHISPER_MODEL}"


def _whisper_asset():
    import platform
    arm = platform.machine().lower() in ("arm64", "aarch64")
    return {"linux": f"ubuntu-{'arm64' if arm else 'x64'}.tar.gz",
            "win32": "win-cpu-arm64.zip" if arm else "x64.zip"}.get(sys.platform)


def _unpack(arc, dest):
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    if arc.name.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(arc) as z:
            for name in z.namelist():
                if not (dest / name).resolve().is_relative_to(root):
                    raise RuntimeError(f"unsafe path in archive: {name}")
            z.extractall(dest)
    else:
        import tarfile
        with tarfile.open(arc) as z:
            try:
                z.extractall(dest, filter="data")
            except TypeError:        # Python < 3.12
                for mbr in z.getmembers():
                    if not (dest / mbr.name).resolve().is_relative_to(root):
                        raise RuntimeError(f"unsafe path in archive: {mbr.name}")
                z.extractall(dest)


def download_whisper():
    """whisper.cpp's command-line program for this machine; returns its path or raises."""
    import shutil
    from .copilot import voice
    have = voice.find_whisper(CACHE)
    if have:
        return have
    kind = _whisper_asset()
    if kind:
        name = f"whisper-bin-{kind}"
        url = f"https://github.com/ggml-org/whisper.cpp/releases/download/{WHISPER_BUILD}/{name}"
        arc = CACHE / "whisper" / name
        arc.parent.mkdir(parents=True, exist_ok=True)
        part = arc.with_name(arc.name + ".part")
        part.write_bytes(_get(url, timeout=600))
        part.rename(arc)
        _unpack(arc, CACHE / "whisper" / WHISPER_BUILD)
        arc.unlink()
        got = voice.find_whisper(CACHE)
        if got and sys.platform != "win32":
            os.chmod(got, 0o755)
        if got:
            return got
        raise RuntimeError(f"no whisper-cli in {name}")
    if sys.platform == "darwin" and shutil.which("brew"):
        _say(t("cli.install.voice_brew"))
        subprocess.run(["brew", "install", "whisper-cpp"], check=True)
        got = voice.find_whisper(CACHE)
        if got:
            return got
    if shutil.which("cmake") and shutil.which("git"):    # build the same tag from source
        src = CACHE / "whisper" / "src"
        if not src.exists():
            subprocess.run(["git", "clone", "--depth", "1", "--branch", WHISPER_SRC_TAG,
                            "https://github.com/ggml-org/whisper.cpp", str(src)], check=True)
        out = CACHE / "whisper" / WHISPER_SRC_TAG
        subprocess.run(["cmake", "-S", str(src), "-B", str(out), "-DCMAKE_BUILD_TYPE=Release",
                        "-DWHISPER_BUILD_TESTS=OFF"], check=True)
        subprocess.run(["cmake", "--build", str(out), "-j", "--config", "Release", "--target", "whisper-cli"],
                       check=True)
        got = voice.find_whisper(CACHE)
        if got:
            return got
    raise RuntimeError("no whisper.cpp build for this machine (install whisper-cpp, or cmake + git)")


def download_whisper_model():
    """The small English speech model, sha256-checked."""
    dest = CACHE / "whisper" / WHISPER_MODEL
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == WHISPER_MODEL_SHA:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = _get(WHISPER_MODEL_URL, timeout=1200)
    got = hashlib.sha256(body).hexdigest()
    if got != WHISPER_MODEL_SHA:
        raise RuntimeError(t("cli.error.sha_mismatch", name=WHISPER_MODEL, got=got[:16], want=WHISPER_MODEL_SHA[:16]))
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.rename(dest)
    return dest


def setup_voice():
    """{"whisper": path, "model": path} or None (and says why)."""
    from .copilot import voice
    try:
        prog, model = download_whisper(), download_whisper_model()
    except Exception as e:
        _say(t("cli.install.voice_failed", error=e))
        return None
    _say(t("cli.install.voice_ready", path=prog))
    if voice.find_recorder() is None:
        _say(t("cli.install.voice_no_recorder"))
    return {"whisper": str(prog), "model": str(model)}


def selftest(blender_bin, live=False):
    """Run the assembled extension's headless self-test in blender -b."""
    import shutil as _sh
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ext = addonbuild.assemble(tmp)
        env = dict(os.environ)
        if live:
            env["MARIS3D_SERVER"] = f"http://127.0.0.1:{PORT}"
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
    tip = t("cli.ask.yes_default") if default else t("cli.ask.no_default")
    while True:
        ans = input(f"{prompt} {tip} ").strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print(t("cli.ask.again"))


def cmd_install(args):
    live = _interactive(args)
    blender = addonbuild.find_blender()
    if not blender:
        _say(t("cli.install.no_blender"))
        return 1
    ver = addonbuild.blender_version(blender)
    _say(t("cli.install.blender_found", version=ver, path=blender))
    if args.model == "all":
        _say(t("cli.install.product"))
    if live and not _ask_yes(t("cli.install.ask_addon")):
        _say(t("cli.install.addon_skipped"))
        return 1
    ext, where = addonbuild.install_into_blender(blender)
    _say(t("cli.install.addon_installed", path=ext))
    try:
        addonbuild.enable_in_blender(blender)
        _say(t("cli.install.addon_enabled"))
    except Exception as e:
        _say(t("cli.install.enable_failed", error=e))
    found = detect()
    runtime = None
    if found:
        use_it = True if not live else _ask_yes(t("cli.install.ask_use_server", name=found[0].name))
        if use_it:
            _say(t("cli.install.server_found", name=found[0].name))
            runtime = {"backend": found[0].name, "model": getattr(found[0], "model", "maris3d"),
                       "url": getattr(found[0], "base_url", "")}
        else:
            found = None
    if not found and not args.skip_model:
        want = True if not live else _ask_yes(t("cli.install.ask_download"))
        if want:
            variants = list(PRODUCT) if args.model == "all" else [args.model]
            gguFs = {}
            for v in variants:
                gguFs[v], note = download_model(v)
                _say(t("cli.install.model_ready", path=gguFs[v], note=note))
            if args.model == "all":
                for v in OPTIONAL:
                    try:
                        gguFs[v], note = download_model(v)
                        _say(t("cli.install.model_ready", path=gguFs[v], note=note))
                    except Exception as e:      # not published yet, or offline: no parts designer
                        _say(t("cli.install.no_parts", error=e))
            binary = find_llama_server() or download_llama_server()
            if binary:
                _say(t("cli.install.llama_server", path=binary))
                runtime = {"backend": "llama-server", "model": "maris3d",
                           "url": f"http://127.0.0.1:{PORT}", "binary": binary,
                           "gguf": str(gguFs.get(PRODUCT[0]) or gguFs[variants[-1]])}
                if PRODUCT[1] in gguFs:  # the product: one base file + the one adapter
                    runtime["lora"] = str(gguFs[PRODUCT[1]])
                    if OPTIONAL and OPTIONAL[0] in gguFs:
                        runtime["parts"] = str(gguFs[OPTIONAL[0]])
            else:
                _say(t("cli.install.no_llama"))
        else:
            _say(t("cli.install.model_skipped"))
    voice_cfg = None
    want_voice = getattr(args, "voice", False) or (live and _ask_yes(t("cli.install.ask_voice"), default=False))
    if want_voice:
        voice_cfg = setup_voice()
    else:
        _say(t("cli.install.voice_skipped"))
    if voice_cfg:
        try:
            addonbuild.configure_voice(blender, voice_cfg["whisper"], voice_cfg["model"])
        except Exception as e:
            _say(t("cli.install.voice_failed", error=e))
    ready, out = None, ""
    want_test = True if not live else _ask_yes(t("cli.install.ask_selftest"))
    if want_test:
        ready, out = selftest(blender, live=bool(runtime and runtime.get("backend") == "llama-server"))
        if ready:
            _say(ready)
        else:
            _say(t("cli.install.selftest_failed"))
            _say(out[-600:])
    else:
        _say(t("cli.install.selftest_skipped"))
    if runtime and runtime.get("backend") == "llama-server":
        try:
            ok = addonbuild.configure_addon(blender, runtime.get("url", ""), "maris3d")
            _say(t("cli.install.urls_set") if ok else t("cli.install.urls_failed"))
        except Exception as e:
            _say(t("cli.install.urls_skipped", error=e))
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps({"blender": str(blender), "blender_version": ver,
                                    "addon_dir": str(ext), "runtime": runtime or {},
                                    "voice": voice_cfg or {}}, indent=2))
    _say(t("cli.install.settings_saved", path=SETTINGS))
    if ready is None:
        _say(t("cli.install.done_untested"))
        return 0
    _say(t("cli.install.ready") if ready else t("cli.install.partial"))
    return 0 if ready else 2


def serve_command(binary, gguf, lora, port, parts=None):
    """The llama-server command line. Adapters are loaded once and NOT applied until a request
    asks: the one adapter first, the parts adapter second; the copilot reads the ids back by file
    name. The per-request settings (repeat penalty) come from the request, not from this line."""
    cmd = [binary, "-m", str(gguf), "--jinja", "-c", "8192", "--temp", "0",
           "--port", str(port), "--host", "127.0.0.1"]
    if lora:  # loaded once, not applied until a request names its role
        cmd += ["--lora", str(lora)]
        if parts:
            cmd += ["--lora", str(parts)]
        cmd += ["--lora-init-without-apply"]
    return cmd


def _log_has_text(path):
    try:
        return Path(path).stat().st_size > 0
    except OSError:
        return False


def _start_one(binary, gguf, lora, port, pid_path, log, parts=None):
    cmd = serve_command(binary, gguf, lora, port, parts)
    _say(" ".join(cmd))
    try:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        # Windows 11 Smart App Control (and other app-control policies) run only signed programs;
        # the llama.cpp builds are not signed. Ollama's installer is.
        if getattr(e, "winerror", None) in (4551, 1260):
            _say(t("cli.serve.blocked_by_windows"))
            return None
        raise
    pid_path.write_text(str(proc.pid))
    for _ in range(60):
        time.sleep(0.5)
        try:
            json.loads(_get(f"http://127.0.0.1:{port}/props", timeout=2))
            _say(t("cli.serve.up", port=port, pid=proc.pid, model=Path(gguf).name,
                   adapter=t("cli.serve.plus_adapter", name=Path(lora).name) if lora else ""))
            return proc.pid
        except Exception:
            if proc.poll() is not None:
                _say(t("cli.serve.exited", port=port, log=CACHE / "serve.log"))
                # Smart App Control may also let the program start, then block its unsigned DLLs: it exits
                # before writing a line (0xC0000428, invalid image hash).
                if sys.platform == "win32" and (proc.returncode in (-1073740760, 3221226536)
                                                or not _log_has_text(CACHE / "serve.log")):
                    _say(t("cli.serve.blocked_by_windows"))
                return None
    _say(t("cli.serve.slow", port=port))
    return proc.pid


def _stop_one(pid_path, port):
    if not pid_path.exists():
        return False
    try:
        os.kill(int(pid_path.read_text().strip()), 15)
        pid_path.unlink(missing_ok=True)
        _say(t("cli.serve.stopped", port=port))
        return True
    except Exception as e:
        _say(t("cli.serve.nothing_error", port=port, error=e))
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
            _say(t("cli.serve.status_up", model=props.get("model_path", "?").rsplit("/", 1)[-1]))
            adapters = _adapters(PORT)
            if adapters:
                names = [Path(a.get("path", "?")).name for a in adapters]
                _say(t("cli.serve.adapters", names=", ".join(names)))
                if not any("blender-one" in n for n in names):
                    _say(t("cli.serve.no_one_loaded"))
            else:
                _say(t("cli.serve.no_one_loaded"))
            return 0
        except Exception:
            _say(t("cli.serve.nothing", port=PORT))
            return 1
    if args.action == "stop":
        return 0 if _stop_one(pid, PORT) else 1
    # start
    s = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {"runtime": {}}
    rt = s.get("runtime", {})
    binary = find_llama_server()
    if not binary:
        _say(t("cli.serve.no_binary"))
        return 1
    now = _installed()          # what `maris3d update` last put in place wins over older settings
    gguf = args.gguf or now.get("base") or rt.get("gguf") or str(CACHE / "models" / MODELS["q8_0"])
    lora = args.lora or now.get("one") or rt.get("lora") or str(CACHE / "models" / MODELS["one-lora"])
    for path in (gguf, lora):
        if not Path(path).exists():
            _say(t("cli.serve.missing", path=path))
            return 1
    parts = None
    if not args.no_parts:
        parts = args.parts or now.get("parts") or rt.get("parts") or str(CACHE / "models" / MODELS["parts-lora"])
        if not Path(parts).exists():
            _say(t("cli.serve.parts_missing"))
            parts = None
    CACHE.mkdir(parents=True, exist_ok=True)
    log = open(CACHE / "serve.log", "ab", buffering=0)
    if _start_one(binary, gguf, lora, PORT, pid, log, parts) is None:
        return 1
    _say(t("cli.serve.one_server", model=Path(gguf).name, adapter=Path(lora).name))
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
    source = args.source or f"{HF_BASE}/resolve/main"
    models = CACHE / "models"
    try:
        report = files.update(source, str(models), log=_say)
    except Exception as e:
        _say(t("cli.update.failed", error=e))
        return 1
    _say(t("cli.update.report", release=report["release"], kept=len(report["kept"]), fetched=len(report["fetched"]),
           removed=len(report["removed"]), bytes=report["bytes_transferred"]))
    if report["failed"]:
        _say(t("cli.update.partial"))
        return 1
    if report["fetched"]:
        _say(t("cli.update.restart"))
    return 0


def cmd_doctor(_args):
    ok = True
    blender = addonbuild.find_blender()
    if blender:
        _say(t("cli.doctor.blender_ok", version=addonbuild.blender_version(blender), path=blender))
    else:
        ok = False
        _say(t("cli.doctor.no_blender"))
    if blender:
        ready, out = selftest(blender)
        _say(t("cli.doctor.selftest_ok", ready=ready) if ready else t("cli.doctor.selftest_fail"))
        if not ready:
            ok = False
            _say(out[-500:])
    found = detect()
    _say(t("cli.doctor.servers_ok", names=", ".join("%s (%s)" % (f.name, getattr(f, "model", "")) for f in found))
         if found else t("cli.doctor.servers_none"))
    if SETTINGS.exists():
        _say(t("cli.doctor.settings", path=SETTINGS))
    else:
        _say(t("cli.doctor.no_settings"))
    _say(t("cli.doctor.all_good") if ok else t("cli.doctor.attention"))
    return 0 if ok else 2


def cmd_build_zip(args):
    path = addonbuild.build_zip(args.out)
    _say(t("cli.built", path=path))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="maris3d", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    from . import __version__
    p.add_argument("--version", action="version", version=f"maris3d {__version__} (models {HF_TAG})")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install", help=t("cli.help.install"))
    i.add_argument("--model", choices=list(MODELS) + ["all"], default="all",
                   help=t("cli.help.model"))
    i.add_argument("--from", dest="from_dir", help=t("cli.help.from_dir"))
    i.add_argument("--skip-model", action="store_true", help=t("cli.help.skip_model"))
    i.add_argument("--voice", action="store_true", help=t("cli.help.voice"))
    i.add_argument("--express", action="store_true",
                   help=t("cli.help.express"))
    i.set_defaults(fn=cmd_install)
    s = sub.add_parser("serve", help=t("cli.help.serve"))
    s.add_argument("action", choices=["start", "stop", "status"], nargs="?", default="status")
    s.add_argument("--gguf", help=t("cli.help.gguf"))
    s.add_argument("--lora", help=t("cli.help.lora"))
    s.add_argument("--parts", help=t("cli.help.parts"))
    s.add_argument("--no-parts", action="store_true", help=t("cli.help.no_parts"))
    s.set_defaults(fn=cmd_serve)
    u = sub.add_parser("update", help=t("cli.help.update"))
    u.add_argument("--from", dest="source", help=t("cli.help.source"))
    u.set_defaults(fn=cmd_update)
    d = sub.add_parser("doctor", help=t("cli.help.doctor"))
    d.set_defaults(fn=cmd_doctor)
    z = sub.add_parser("build-zip", help=t("cli.help.build_zip"))
    z.add_argument("--out", default="dist")
    z.set_defaults(fn=cmd_build_zip)
    args = p.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
