# SPDX-License-Identifier: Apache-2.0
"""Picture input, offline (bpy-free, so it is tested without Blender): an optional module, like voice.

`maris3d install` sets it up (express: always; interactive: asked; `--vision`: always). It downloads a small vision
model, SmolVLM 500M Instruct (Apache-2.0, ggml-org's GGUF build), from Hugging Face into ~/.cache/maris3d/vision,
sha256-checked. The weights are never part of the repository, the wheel or the add-on.

When the user gives a picture, `describe()` starts llama-mtmd-cli ONCE: the vision model loads, writes a detailed
description, and the process exits, so nothing stays in memory. The words then go to our own model as a normal
request (`to_request`), and the rest of the flow (plan, compile, build, check) is unchanged.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

VISION_REPO = "https://huggingface.co/ggml-org/SmolVLM-500M-Instruct-GGUF"
# name -> (sha256 of the file on the repository, bytes)
VISION_FILES = {
    "SmolVLM-500M-Instruct-Q8_0.gguf": ("9d4612de6a42214499e301494a3ecc2be0abdd9de44e663bda63f1152fad1bf4", 436806912),
    "mmproj-SmolVLM-500M-Instruct-Q8_0.gguf": ("d1eb8b6b23979205fdf63703ed10f788131a3f812c7b1f72e0119d5d81295150", 108783360),
}
MODEL_FILE, MMPROJ_FILE = tuple(VISION_FILES)
EXE = "llama-mtmd-cli.exe" if sys.platform == "win32" else "llama-mtmd-cli"
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
# The prompt that gave the most usable descriptions on our renders: an open "describe for a 3D artist"
# question. Lists and worked examples made the small vision models loop or copy the example back.
PROMPT = ("Describe this picture in detail for a 3D artist who must rebuild it: name every object, its colour, "
          "its rough size, how many there are, and where each one stands compared with the others.")
MAX_TOKENS = 200
REPEAT_PENALTY = 1.15        # prose, not tool calls: stops the small model repeating a line
MAX_CHARS = 600              # what goes on to our model: the first sentences, whole
TIMEOUT = 180                # seconds; the process is killed when it runs longer
_EXTRA_BIN = ("/opt/homebrew/bin", "/usr/local/bin")   # a GUI Blender on macOS does not see the shell PATH


def vision_dir(cache):
    return Path(cache) / "vision"


def find_mtmd_cli(cache, which=shutil.which, extra=_EXTRA_BIN):
    """The copy unpacked next to llama-server by `maris3d install`, else PATH, else the usual Homebrew places."""
    for p in sorted((Path(cache) / "llama").glob(f"*/**/{EXE}"), reverse=True):
        if p.is_file():
            return str(p)
    got = which("llama-mtmd-cli")
    if got:
        return got
    for d in extra:
        p = Path(d) / EXE
        if p.is_file():
            return str(p)
    return None


def vision_ready(cache):
    d = vision_dir(cache)
    return all((d / n).is_file() and (d / n).stat().st_size == size for n, (_, size) in VISION_FILES.items())


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download_vision(cache, fetch, say=print, local=()):
    """Both files into <cache>/vision, sha256-checked. `fetch(url) -> bytes` is injected. `local` lists folders that
    may already hold the files (for example a Hugging Face cache): a copy there with the right checksum is used."""
    d = vision_dir(cache)
    d.mkdir(parents=True, exist_ok=True)
    for name, (want, _size) in VISION_FILES.items():
        dest = d / name
        if dest.is_file() and _sha(dest) == want:
            continue
        tmp = dest.with_suffix(".part")
        found = next((Path(x) / name for x in local if (Path(x) / name).is_file() and _sha(Path(x) / name) == want), None)
        if found:
            try:
                os.link(found, tmp)            # same disk: no second copy of the weights
            except OSError:
                shutil.copyfile(found, tmp)
        else:
            say(f"downloading {name}")
            body = fetch(f"{VISION_REPO}/resolve/main/{name}")
            got = hashlib.sha256(body).hexdigest()
            if got != want:
                raise RuntimeError(f"{name}: checksum {got[:16]} does not match {want[:16]}")
            tmp.write_bytes(body)
        os.replace(tmp, dest)   # also over a stale file on Windows
    return d


def hf_cache_dirs(home=None):
    """Snapshot folders of an earlier Hugging Face download of the same repository, if any."""
    root = Path(home or Path.home()) / ".cache" / "huggingface" / "hub" / "models--ggml-org--SmolVLM-500M-Instruct-GGUF"
    return sorted((root / "snapshots").glob("*")) if root.is_dir() else []


def build_command(exe, cache, image, prompt=PROMPT, max_tokens=MAX_TOKENS, threads=None):
    d = vision_dir(cache)
    cmd = [exe, "-m", str(d / MODEL_FILE), "--mmproj", str(d / MMPROJ_FILE), "--image", str(image),
           "-p", prompt, "-n", str(max_tokens), "--temp", "0", "--repeat-penalty", str(REPEAT_PENALTY), "-ngl", "0"]
    if threads:
        cmd += ["-t", str(threads)]
    return cmd


_NOISE = ("ggml_", "llama_", "clip_", "mtmd", "load_", "main:", "build:", "encoding image", "image slice",
          "decoding image", "image decoded", "print_info", "common_", "system_info")


def clean_description(text, max_chars=MAX_CHARS):
    """stdout -> plain description: log lines and markdown dropped, repeated sentences dropped, whole sentences
    kept up to max_chars. Text clean-up only; the description itself is the vision model's."""
    lines = [l.strip() for l in (text or "").splitlines()]
    lines = [l for l in lines if l and not l.lower().startswith(_NOISE)]
    kept = []
    for l in lines:
        l = re.sub(r"\*\*|__|#+", "", l)
        l = re.sub(r"^\s*(?:[-*]|\d+\.)\s*", "", l)             # list marks
        l = re.sub(r"^[^.:]{1,40}:\s*", lambda m: "" if len(m.group(0).split()) <= 6 else m.group(0), l)  # "Objects Present: "
        l = re.sub(r"Here is (?:a|the) detailed description(?: and analysis)?\s*:?", "", l, flags=re.I).strip()
        if l:
            kept.append(l)
    body = re.sub(r"\s+", " ", " ".join(kept)).strip()
    out, seen, size = [], set(), 0
    for s in re.split(r"(?<=[.!?])\s+", body):
        key = re.sub(r"[^a-z ]", "", s.lower()).strip()
        if not key or key in seen:
            continue
        if size + len(s) > max_chars and out:
            break
        seen.add(key)
        out.append(s)
        size += len(s) + 1
    return " ".join(out).strip()


# Several short questions beat one long description: our 0.5B model is trained on short requests ("a red table with
# four chairs"), and a 500M vision model answers a narrow question far better than an open one. Each question is its
# own run (the model loads, answers, exits); the answers are put together into one short request.
PASSES = (
    ("name", "What is shown in this picture? Answer with a short phrase of two to six words.", 16),
    ("objects", "Name the objects in this picture, separated by commas.", 30),
    ("colour", "What is the main colour of the biggest object? Answer with one word.", 6),
)
COLOURS = ("red", "orange", "yellow", "green", "blue", "purple", "pink", "brown", "black", "white", "grey", "gray")
_LEADS = ("a", "an", "the", "one", "two", "three", "four", "five", "six", "some", "many")


def _run_once(exe, cache, image, prompt, max_tokens, run, timeout, max_chars=MAX_CHARS):
    r = run(build_command(exe, cache, image, prompt, max_tokens), capture_output=True, text=True, timeout=timeout)
    return clean_description(r.stdout, max_chars) if r.returncode == 0 else ""


_FILLER = re.compile(r"\b(?:3d|three[- ]dimensional)\s+(?:model|render|image)s?\s+of\s+(?:a|an|the)?\s*|"
                     r"\b(?:a\s+)?(?:picture|image|render)\s+of\s+(?:a|an|the)?\s*", re.I)
_EMPTY_WORDS = set(COLOURS) | {"3d", "shape", "shapes", "object", "objects", "thing", "things", "model", "models",
                               "geometric", "simple", "small", "large", "big", "and", "of", "with", "on", "i", "background"} | set(_LEADS)
_FLOOR = re.compile(r"^(?:(?:\d+|a|the|one|small|large|big)\s+)*(?:gr[ae]y|white|dark)\s+(?:square|plane|floor|ground|surface|background)$",
                    re.I)


_SETTING = re.compile(r"\s+(?:on|against|in front of|over)\s+(?:a|an|the)?\s*(?:[a-z]+\s+)?(?:background|surface|floor|ground|plane)\b.*$",
                      re.I)
_LONG_THING = re.compile(r"\b(?:is|depicts|shows|of)\s+(an?\s+[a-z ]{3,40}?)(?=\s+(?:with|placed|on|that|which|in|and|sitting|standing)\b|[,.]|$)",
                         re.I)


def _from_long(text):
    """The thing named in a long description ("The image depicts a large orange sphere placed on ..."), as a short
    request; the whole sentence when no such phrase is found."""
    m = _LONG_THING.search(text or "")
    return _phrase(m.group(1)) if m and _phrase(m.group(1)) else _phrase(text)


def _phrase(text):
    """A usable short answer: it names a thing (not a bare number, a list index, a colour or a filler word like
    "3D shapes"); "3D model of" is dropped, and so is the trailing dot."""
    t = re.sub(r"\s+", " ", (text or "").strip()).rstrip(".").strip()
    t = _SETTING.sub("", _FILLER.sub("", t)).strip()
    words = [w.strip(",.").lower() for w in t.split()]
    if not any(w.isalpha() and len(w) >= 3 and w not in _EMPTY_WORDS for w in words):
        return ""
    return t


def _items(text):
    """The object list split into items: commas, "2." list numbers and run-on capitals ("Black sphere Gray cube").
    The floor of the picture ("gray square") and items that name nothing are left out."""
    t = re.sub(r"(?:^|[\s,])\d+\.\s+", ", ", (text or "").strip())
    t = re.sub(r"(?<=[a-z]) (?=[A-Z])", ", ", t)
    out = []
    for part in t.split(","):
        p = _phrase(part)
        if p and not _FLOOR.match(p):
            out.append(p)
    return out


def compose(answers):
    """The short request from the pass answers: the name (or the first item of the object list), with the colour put
    in when the name has none. Falls back to the long description. Returns "" when nothing usable came back."""
    items = _items(answers.get("objects"))
    name = _phrase(answers.get("name")) or (items[0] if items else "")
    if not name:
        return _from_long(answers.get("long"))
    words = name.split()
    colour = (_phrase(answers.get("colour")).split() or [""])[0].lower().strip(",")
    if not _phrase(answers.get("colour")):
        colour = re.sub(r"[^a-z]", "", (answers.get("colour") or "").lower())
    if colour in COLOURS and not any(w.lower().strip(",") in COLOURS for w in words):
        lead = words[0].lower()
        if lead == "1":
            words[0] = "a"
        if lead in _LEADS or lead.isdigit():
            words.insert(1, colour)
        else:
            words = ["a", colour] + [words[0].lower()] + words[1:]
    elif words[0] == "1":
        words[0] = "a"
    elif words[0].lower() not in _LEADS and not words[0].isdigit():
        words = (["a"] if not words[0].lower().endswith("s") else []) + [words[0].lower()] + words[1:]
    return " ".join(words)


def describe(image, cache, prompt=None, run=subprocess.run, which=shutil.which, timeout=TIMEOUT, exe=None):
    """One picture in, one short description out. The vision model is loaded for each question only and exits after
    it. With a prompt: that one question. Returns (text, None) or (None, reason). Never raises."""
    exe = exe or find_mtmd_cli(cache, which)
    if not Path(str(image)).is_file():
        return None, "picture not found"
    if not vision_ready(cache):
        return None, "picture input is not set up: run  maris3d install --vision"
    if not exe:
        return None, "llama-mtmd-cli was not found: run  maris3d install --vision"
    try:
        if prompt:
            text = _run_once(exe, cache, image, prompt, MAX_TOKENS, run, timeout)
        else:
            answers = {k: _run_once(exe, cache, image, q, n, run, timeout) for k, q, n in PASSES}
            if not _phrase(answers["name"]) and not _phrase(answers["objects"]):
                answers["long"] = _run_once(exe, cache, image, PROMPT, MAX_TOKENS, run, timeout, max_chars=200)
            text = compose(answers)
    except subprocess.TimeoutExpired:
        return None, f"the picture took longer than {timeout} s"
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"the picture step could not start: {e}"
    if not text:
        return None, "the picture step gave no description"
    return text, None


# ---- memory: no swapping -----------------------------------------------------------------------------------------
# The vision model is up only for a few seconds per question. When the machine has room for it (its measured peak
# plus a margin), our model server stays up. When it has not, the picture step stops our server (started by
# `maris3d serve start`, which writes serve.pid and serve.cmd), asks its questions, and starts it again from the
# same command, so the two models never push the machine into swap. A server started some other way (no
# serve.cmd) is left running.
VISION_PEAK = 1_350_000_000    # bytes: llama-mtmd-cli with the 500M files, measured on the Mac
MEMORY_MARGIN = 1_000_000_000  # bytes kept free on top of that
SERVER_STOP_WAIT = 15      # seconds for the server to exit
SERVER_START_WAIT = 90     # seconds for it to answer again


def _alive(pid):
    if sys.platform == "win32":     # os.kill on Windows ends the process; ask tasklist instead
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                                 timeout=10).stdout
            return str(pid) in out
        except (OSError, subprocess.SubprocessError):
            return False
    try:                            # a server we started ourselves lingers as a zombie until it is reaped
        if os.waitpid(pid, os.WNOHANG)[0] == pid:
            return False
    except (ChildProcessError, OSError):
        pass
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def available_memory():
    """Bytes the system can give a new process without swapping, or None when it cannot be read."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=10).stdout
            page = int(re.search(r"page size of (\d+)", out).group(1))
            pages = {m.group(1): int(m.group(2)) for m in re.finditer(r"Pages (\w+)[^:]*:\s+(\d+)", out)}
            return page * sum(pages.get(k, 0) for k in ("free", "inactive", "speculative", "purgeable"))
        if sys.platform == "win32":
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = _Status()
            st.dwLength = ctypes.sizeof(_Status)
            return int(st.ullAvailPhys) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)) else None
        with open("/proc/meminfo") as f:
            m = re.search(r"MemAvailable:\s+(\d+) kB", f.read())
        return int(m.group(1)) * 1024 if m else None
    except Exception:
        return None


def room_for_vision(free=None):
    """True when the vision model fits next to what is running; an unreadable figure counts as no room."""
    free = available_memory() if free is None else free
    return free is not None and free >= VISION_PEAK + MEMORY_MARGIN


def _answers(port, timeout=2):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def pause_server(cache, alive=_alive, kill=os.kill, sleep=None):
    """Stop our model server for the picture step. Returns its command line (to start it again), or None when
    none of ours is running."""
    import json
    import signal
    import time
    sleep = sleep or time.sleep
    pid_p, cmd_p = Path(cache) / "serve.pid", Path(cache) / "serve.cmd"
    try:
        pid, cmd = int(pid_p.read_text().strip()), json.loads(cmd_p.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(cmd, list) or not alive(pid):
        return None
    kill(pid, signal.SIGTERM)
    for _ in range(SERVER_STOP_WAIT * 10):
        if not alive(pid):
            break
        sleep(0.1)
    return cmd


def resume_server(cache, cmd, popen=subprocess.Popen, ready=_answers, sleep=None):
    """Start the server again from its own command line; True once it answers."""
    import time
    sleep = sleep or time.sleep
    if not cmd:
        return True
    port = cmd[cmd.index("--port") + 1] if "--port" in cmd else "8080"
    with open(Path(cache) / "serve.log", "ab", buffering=0) as log:
        proc = popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    (Path(cache) / "serve.pid").write_text(str(proc.pid))
    for _ in range(SERVER_START_WAIT * 4):
        if ready(port):
            return True
        if proc.poll() is not None:
            return False
        sleep(0.25)
    return False


def describe_alone(image, cache, room=room_for_vision, **kw):
    """describe() without swapping: our model server stays up when there is room for the vision model next to it;
    otherwise it is stopped for the time the questions take and started again before this returns (a failed
    restart shows up on the next request as the usual server-down message)."""
    if room():
        return describe(image, cache, **kw)
    cmd = pause_server(cache)
    try:
        return describe(image, cache, **kw)
    finally:
        if cmd:
            resume_server(cache, cmd)


def to_request(description, typed=""):
    """The words our model gets: the user's own request first (if any), then what the picture shows, kept short
    like the requests the model was trained on."""
    typed = (typed or "").strip().rstrip(".")
    return f"{typed}: {description}" if typed else description
