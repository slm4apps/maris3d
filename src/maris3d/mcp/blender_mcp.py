#!/usr/bin/env python3
"""MCP server (stdio, pure Python standard library, no `mcp` package) that lets an OpenCode agent drive the
Maris3D models in a LIVE Blender window.

Tools: blender_build(prompt, model?, temperature?, seed?, check?, hold_s?, reset?), blender_reset(), blender_screenshot().

blender_build: the prompt goes VERBATIM to the local Ollama model with the harness's exact system prompt
(engine/runtime.py COPILOT_SYS) and format (JSON mode, num_ctx 4096, num_predict 2800, stream cut at the 41st call,
salvage_doc), the returned calls are compiled one at a time by the unchanged harness tools.compile_calls and run in the
open Blender window (blender_live.py socket add-on), then the harness check (checks.py on the whole document run
headless, as the harness does) is applied. Blender is launched once, with its UI, and stays open between calls.

Nothing is written to stdout except MCP JSON-RPC lines (stderr is free)."""
import json, os, re, socket, subprocess, sys, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER_BIN = os.environ.get("BLENDER_BIN") or "/Applications/Blender.app/Contents/MacOS/Blender"
PORT = int(os.environ.get("BLENDER_LIVE_PORT", "9877"))
SHOTS = os.environ.get("BLENDER_LIVE_SHOTS", os.path.expanduser("~/.cache/maris3d/live"))
MODELS = {"0.5b": "maris3d-slm-blender-0.5b", "1.5b": "maris3d-slm-blender-1.5b"}   # key -> local Ollama tag (see docs/USAGE.md)
DEFAULT_MODEL = "0.5b"
CHECKS = {  # named specs, same style as the 206-prompt gate (harness/blender/checks.py keys); same as scripts/gen.py
    "table-full": {"meshes": (5, 5), "bbox_z": (0.5, 1.5), "material": 5, "camera": 1, "type_count": {"LIGHT": (1, 3)}},
    "table": {"meshes": (5, 5), "bbox_z": (0.5, 1.5)},
    "chair": {"meshes": (6, 8), "material": 6, "bbox_z": (0.8, 2.5), "camera": 1, "type_count": {"LIGHT": (1, 3)}},
}

os.makedirs(SHOTS, exist_ok=True)
_real_stdout = sys.stdout
sys.stdout = sys.stderr  # any stray print from imported harness code goes to stderr, never into the protocol
from maris3d.engine import runtime as H   # noqa: E402  (switch_to, salvage_doc, run_blender, swap check, MAX_CALLS)
from maris3d.engine import runtime as D   # noqa: E402  (COPILOT_SYS, fit)
from maris3d.dsl import tools as T        # noqa: E402  (compile_calls)
from maris3d.engine import checks as C    # noqa: E402  (check)
from maris3d.mcp import confirm as CF     # noqa: E402  (plain-language confirmation text, shared with the bridge)
sys.stdout = _real_stdout


def log(*a):
    print("[blender_mcp]", *a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ live Blender
class Live:
    def __init__(self):
        self.sock = None
        self.f = None
        self.lock = threading.Lock()
        self.launch_lock = threading.Lock()
        self.proc = None
        self.pending = []

    def _connect(self):
        s = socket.create_connection(("127.0.0.1", PORT), timeout=3)
        s.settimeout(180)
        self.sock, self.f = s, s.makefile("rwb")

    def rpc(self, cmd, **kw):
        with self.lock:
            for attempt in (0, 1):
                try:
                    if self.f is None:
                        self._connect()
                    self.f.write((json.dumps(dict(kw, cmd=cmd)) + "\n").encode())
                    self.f.flush()
                    line = self.f.readline()
                    if not line:
                        raise ConnectionError("closed")
                    return json.loads(line)
                except Exception:
                    self.sock = self.f = None
                    if attempt:
                        raise
        raise RuntimeError("unreachable")

    def alive(self):
        try:
            r = self.rpc("ping")
            if r.get("ok") and r.get("pid"):
                self._remember(r["pid"])
            return bool(r.get("ok"))
        except Exception:
            return False

    # -- dead-Blender detection (works across MCP restarts: the last live pid is kept in a file)
    def _pidfile(self):
        return os.path.join(SHOTS, "blender-live.pid")

    def _remember(self, pid):
        try:
            open(self._pidfile(), "w").write(str(pid))
        except OSError:
            pass

    def _pid_alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _last_event(self):
        """Last line of the Blender-side event log (BEGIN/END of every command), to say what it was doing when it died."""
        try:
            with open(os.path.join(SHOTS, "blender-live-events.log"), "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 6000))
                lines = [l for l in f.read().decode("utf-8", "replace").splitlines() if " BEGIN " in l or " END " in l or " GUARD " in l]
            return lines[-1][:300] if lines else ""
        except OSError:
            return ""

    def death_notice(self):
        """Text saying that the previous Blender is gone (or None if there was none). Call it when the port does not answer."""
        pid = None
        try:
            pid = int(open(self._pidfile()).read().strip())
        except (OSError, ValueError):
            pass
        died = None
        if self.proc is not None and self.proc.poll() is not None:
            rc = self.proc.returncode
            died = f"exit status {rc}" + (" (killed by signal %d%s)" % (-rc, ", SIGKILL = most likely the macOS memory killer" if rc == -9 else "") if rc < 0 else "")
        elif pid and not self._pid_alive(pid):
            died = "the process is gone; no exit status and no crash report usually means it was killed for memory"
        if died is None:
            return None
        last = self._last_event()
        try:
            os.remove(self._pidfile())
        except OSError:
            pass
        self.proc = None
        return (f"Blender was no longer running ({died}) and had to be relaunched. The scene was lost with it: the new Blender "
                f"window starts empty. Last thing it was doing: {last or 'unknown'}. Log: {SHOTS}/blender-live-events.log")

    def take_notice(self):
        """The 'Blender had died, relaunched, scene lost' text, once (it is also kept if the pre-launch thread found it first)."""
        with self.launch_lock:
            n, self.pending = " ".join(self.pending), []
        return n or None

    def ensure(self, wait_s=120):
        """Attach to the open Blender, or launch ONE with its UI (detached, survives this server) and wait for it.
        If the previous Blender had died, the notice (scene lost) is queued for take_notice()."""
        with self.launch_lock:
            if self.alive():
                return
            notice = self.death_notice()
            if notice:
                log(notice)
                self.pending.append(notice)
            else:  # not dead, just not answering: never start a second Blender on the same port
                try:
                    pid = int(open(self._pidfile()).read().strip())
                except (OSError, ValueError):
                    pid = None
                if pid and self._pid_alive(pid):
                    raise RuntimeError(f"Blender (pid {pid}) is running but not answering on port {PORT}: it is busy or hung. "
                                       f"Wait for it, or close it and ask again (a new one is launched automatically).")
            log("launching Blender with UI")
            logf = open(os.path.join(SHOTS, "blender-launch.log"), "ab", buffering=0)
            env = dict(os.environ, BLENDER_LIVE_PORT=str(PORT), BLENDER_LIVE_SHOTS=SHOTS, PYTHONUNBUFFERED="1")
            self.proc = subprocess.Popen([BLENDER_BIN, "--factory-startup", "--window-geometry", "40", "60", "1280", "800", "--python", os.path.join(HERE, "..", "blender", "live_server.py")],
                                         stdout=logf, stderr=logf, stdin=subprocess.DEVNULL, start_new_session=True, env=env)
            t0 = time.time()
            while time.time() - t0 < wait_s:
                time.sleep(1.0)
                if self.alive():
                    subprocess.run(["osascript", "-e", 'tell application "Blender" to activate'], capture_output=True, timeout=10)
                    return
                if self.proc.poll() is not None:
                    raise RuntimeError(f"Blender exited at start-up with status {self.proc.returncode} (see {SHOTS}/blender-launch.log)")
            raise RuntimeError(f"Blender did not answer on port {PORT} within {wait_s}s (see {SHOTS}/blender-launch.log)")


LIVE = Live()


# ------------------------------------------------------------------ scene facts (for the before/after diff in the confirmation text)
_PROBE = """import bpy, json
def _col(o):
    for s in o.material_slots:
        m = s.material
        if m:
            n = m.node_tree.nodes.get("Principled BSDF") if m.use_nodes and m.node_tree else None
            return [round(float(v), 3) for v in (n.inputs["Base Color"].default_value[:3] if n else m.diffuse_color[:3])]
    return None
json.dump([{"name": o.name, "type": o.type, "loc": [round(v, 3) for v in o.location], "scale": [round(v, 3) for v in o.scale],
            "color": _col(o)} for o in bpy.data.objects], open(%r, "w"))
"""


def scene_facts():
    """Snapshot of the live scene (name, type, location, scale, colour) through the add-on's exec, so it also works with an older add-on."""
    path = os.path.join(SHOTS, "scene-facts.json")
    try:
        os.remove(path)
    except OSError:
        pass
    r = LIVE.rpc("exec", code=_PROBE % path)
    if r.get("error"):
        raise RuntimeError("scene probe failed: " + str(r["error"]))
    with open(path) as f:
        return json.load(f)


# ------------------------------------------------------------------ memory gate
def memory_gate():
    free = H.swap_free_mb()
    if H.swap_status(free) == "refuse":
        raise RuntimeError(f"free swap {free} MB is too low to load a model (harness refuses under 250 MB)")
    try:
        out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=20).stdout
        m = re.search(r"free percentage:\s*(\d+)%", out)
        if m and int(m.group(1)) < 10:
            raise RuntimeError(f"system memory free is {m.group(1)}% (under 10%), not loading a model")
    except subprocess.TimeoutExpired:
        pass
    return free


# ------------------------------------------------------------------ prompt-derived check spec
def auto_spec(prompt):
    """Generic harness-style spec derived from what the prompt literally asks for (the locked suite has per-ID specs,
    free prompts do not). Always: at least one object and one mesh."""
    p = prompt.lower()
    spec = {"objects_min": 1}
    meshes = None
    if "table" in p and re.search(r"(four|4) legs", p):
        meshes, spec["bbox_z"] = (5, 5), (0.5, 1.5)
    if meshes:
        spec["meshes"] = meshes
    else:
        spec["meshes"] = (1, 60)
    if "camera" in p:
        spec["camera"] = 1
    if re.search(r"\b(light|lamp|sun)\b", p):
        spec["type_count"] = {"LIGHT": (1, 3)}
    if re.search(r"material|colou?r", p):
        spec["material"] = meshes[0] if meshes and "every" in p else 1
    return spec


def jsonable(spec):
    return json.loads(json.dumps(spec))


# ------------------------------------------------------------------ model call (as scripts/gen.py)
def ask_model(tag, prompt, temperature, seed):
    H.switch_to(tag)  # one model at a time: unload any other running Ollama model (the harness does the same)
    msgs = [{"role": "system", "content": D.COPILOT_SYS}, {"role": "user", "content": prompt}]
    opts = {"temperature": temperature, "num_ctx": 4096, "num_predict": 2800}
    if seed is not None:
        opts["seed"] = seed
    body = json.dumps({"model": tag, "messages": D.fit(msgs), "stream": True, "format": "json", "keep_alive": "5m",
                       "options": opts}).encode()
    t0 = time.time()
    resp = urllib.request.urlopen(urllib.request.Request(H.OLLAMA + "/api/chat", body, {"Content-Type": "application/json"}), timeout=900)
    parts, last, cut = [], {}, False
    for line in resp:
        if not line.strip():
            continue
        ch = json.loads(line)
        piece = ch.get("message", {}).get("content", "")
        if piece:
            parts.append(piece)
            if "".join(parts).count('{"tool"') > H.MAX_CALLS:
                resp.close()
                cut = True
                break
        if ch.get("done"):
            last = ch
            break
    text = "".join(parts)
    ev, evd = last.get("eval_count"), last.get("eval_duration")
    if cut or not ev:  # stream was cut at the 41st call: Ollama sent no final stats, so count what we streamed
        ev = ev or len(parts)
    return {"text": text, "tokens": ev, "prompt_tokens": last.get("prompt_eval_count"), "gen_s": round((evd or 0) / 1e9, 2),
            "tok_per_s": round(ev / (evd / 1e9), 1) if ev and evd else None,
            "wall_s": round(time.time() - t0, 2), "cut_at_40_calls": cut, "options": opts}


# ------------------------------------------------------------------ tools
def crashed_result(tag, prompt, m, calls, per_call, err):
    """Blender died in the middle of a build: relaunch it (empty scene) and tell the chat plainly."""
    n_done = len(per_call)
    last = LIVE._last_event()
    LIVE.pending.clear()
    notice = LIVE.death_notice()
    relaunch_err = None
    try:
        LIVE.ensure()
    except Exception as e:
        relaunch_err = repr(e)
    LIVE.pending.clear()
    msg = (f"{'BLENDER CRASHED' if notice else 'BLENDER STOPPED ANSWERING'} while running this request (after {n_done} of {len(calls)} calls, "
           f"{('on call %d: %s' % (n_done + 1, calls[n_done].get('tool'))) if n_done < len(calls) else 'at the end'}; error seen: {type(err).__name__}: {err}). "
           + (notice or f"Last thing Blender was doing: {last or 'unknown'}. ")
           + (" Blender could NOT be relaunched: " + relaunch_err if relaunch_err else
              " Blender has been relaunched with an EMPTY scene: everything built before this (all earlier requests) is lost. "
              "The request was not completed; send it again to rebuild."))
    return {"blender_crashed": True, "blender_notice": msg, "report_line": msg, "model": tag, "prompt_sent_verbatim": prompt,
            "raw_model_json": m["text"], "n_calls": len(calls), "calls_in_order": [c.get("tool") for c in calls],
            "per_call_results": per_call, "live_objects": [], "screenshot": None}


def tool_build(a):
    prompt = a["prompt"]  # verbatim: no strip, no rewrite
    mkey = a.get("model") or DEFAULT_MODEL
    if mkey not in MODELS:
        raise ValueError(f"model must be one of {list(MODELS)}")
    tag = MODELS[mkey]
    temperature = float(a.get("temperature", 0.0))
    seed = a.get("seed")
    hold = float(a.get("hold_s", 0.6))
    free = memory_gate()
    LIVE.ensure()
    notice = LIVE.take_notice()  # set when the previous Blender had died: it was relaunched, the scene is empty
    if a.get("reset", False):  # keep building in the same scene; "reset" in chat clears it
        LIVE.rpc("reset")
    try:
        before = scene_facts()
    except Exception as e:
        log("scene_facts before failed", repr(e))
        before = None
    m = ask_model(tag, prompt, temperature, seed)
    LIVE.ensure()  # Blender may have died while the model was thinking
    notice = " ".join(x for x in (notice, LIVE.take_notice()) if x) or None
    doc = H.salvage_doc(m["text"])
    calls = doc["calls"]
    reuse = os.environ.get("MARIS3D_REUSE_MATERIALS", "1") == "1"
    per_call, t_live = [], time.time()
    try:
        for i, c in enumerate(calls, 1):
            try:
                code = T.compile_calls({"calls": [c]})
            except Exception as e:
                per_call.append({"i": i, "tool": c.get("tool"), "ok": False, "error": f"compile: {type(e).__name__}: {e}"})
                continue
            r = LIVE.rpc("exec", code=code, reuse_materials=reuse)
            per_call.append({"i": i, "tool": c.get("tool"), "ok": bool(r.get("ok")) and not r.get("error"),
                             "error": r.get("error") or (None if r.get("ok") else r.get("error")), "exec_s": r.get("exec_s")})
            time.sleep(hold)
        live_s = round(time.time() - t_live, 1)
        # frame the last thing that was built, by its kind (a house three-quarter, a chair level
        # with it, a wall square on); the old call framed the whole scene with one fixed angle
        built = next((c.get("name") for c in reversed(calls)
                      if c.get("tool") == "add_primitive" and c.get("name")), None)
        LIVE.rpc("frame", **({"subject": built} if built else {}))
        time.sleep(0.4)
        summary = LIVE.rpc("summary")
        try:
            after = scene_facts()
        except Exception as e:
            log("scene_facts after failed", repr(e))
            after = None
        shot = LIVE.rpc("screenshot", path=os.path.join(SHOTS, time.strftime("build-%Y%m%d-%H%M%S.png")))
    except (OSError, ValueError, ConnectionError) as e:
        if LIVE.alive():
            raise
        return crashed_result(tag, prompt, m, calls, per_call, e)
    # harness check: the whole document, run headless on an empty scene, then checks.check (as gen.py / the gate)
    chk = a.get("check", "auto")
    spec = CHECKS[chk] if chk in CHECKS else auto_spec(prompt)
    scene, bl_s, _ = H.run_blender(doc, os.path.join(SHOTS, "headless"))
    if scene.get("executed"):
        fails = C.check(scene, spec)
    else:
        fails = ["script did not execute: " + H.last_error_line(scene)]
    errs = [p for p in per_call if not p["ok"]]
    passed = bool(scene.get("executed")) and not fails and bool(calls)
    refused = [p for p in per_call if p.get("error") and "refused:" in p["error"]]
    generic = chk not in CHECKS and set(spec) <= {"objects_min", "meshes"}  # nothing in the prompt to check beyond "some meshes exist"
    facts_ok = before is not None and after is not None
    confirmation = CF.confirmation(mkey, before if facts_ok else [], after if facts_ok else summary.get("objects", []), calls=calls, per_call=per_call,
                                   check={"passed": passed, "fails": fails, "generic": generic})
    res = {
        "confirmation": confirmation,  # the plain sentence(s) to give the user (same text as the OpenCode bridge); screenshot goes on its own last line
        "scene_before": before, "scene_after": after, "calls": calls,
        "blender_notice": notice,
        "refused_by_guard": [{"i": p["i"], "tool": p["tool"], "why": p["error"]} for p in refused] or None,
        "report_line": ((f"NOTICE: {notice} " if notice else "") + f"{mkey}: {len(calls)} calls, {m['tokens']} tokens, {m['tok_per_s']} tok/s, {m['gen_s']} s generation; "
                        f"check {'PASS' if passed else 'FAIL'}" + ("" if passed else f" ({'; '.join(fails)[:200]})") +
                        f"; {len(errs)} call errors" + (f" ({len(refused)} refused by the safety guard to keep Blender alive: see refused_by_guard)" if refused else "") +
                        f"; live scene {len(summary.get('objects', []))} objects"),
        "model": tag, "prompt_sent_verbatim": prompt, "options": m["options"],
        "raw_model_json": m["text"], "n_calls": len(calls), "cut_at_40_calls": m["cut_at_40_calls"],
        "calls_in_order": [c.get("tool") for c in calls],
        "per_call_results": per_call,
        "tokens": m["tokens"], "prompt_tokens": m["prompt_tokens"], "tok_per_s": m["tok_per_s"], "generation_s": m["gen_s"], "model_wall_s": m["wall_s"],
        "live_build_s": live_s,
        "check": {"passed": passed, "fails": fails, "generic": generic, "spec": jsonable(spec), "spec_source": chk if chk in CHECKS else "auto (from the prompt words)",
                  "headless_objects": len(scene.get("objects", [])), "headless_s": round(bl_s, 1)},
        "live_objects": summary.get("objects"), "screenshot": shot.get("path"), "swap_free_mb_before": free,
    }
    return res


def tool_reset(a):
    LIVE.ensure()
    notice = LIVE.take_notice()
    LIVE.rpc("reset")
    return {"reset": True, "blender_notice": notice, "live": LIVE.rpc("summary")}


def tool_screenshot(a):
    LIVE.ensure()
    notice = LIVE.take_notice()
    r = LIVE.rpc("screenshot", path=os.path.join(SHOTS, time.strftime("shot-%Y%m%d-%H%M%S.png")))
    return {"screenshot": r.get("path"), "blender_notice": notice, "live_objects": LIVE.rpc("summary").get("objects")}


TOOLS = [
    {"name": "blender_build",
     "description": ("Send a 3D request VERBATIM to the local Maris3D model (Ollama), run the JSON tool calls it returns one by one in the "
                     "LIVE Blender window, run the harness check, and return the raw model JSON, per-call results, tokens, tok/s, generation time, "
                     "the check result and a screenshot path. The scene is emptied first (the model builds on an empty scene)."),
     "inputSchema": {"type": "object", "properties": {
         "prompt": {"type": "string", "description": "The user's request, exactly as the user wrote it. Do not rewrite or add detail."},
         "model": {"type": "string", "enum": list(MODELS), "description": "Optional. Default 0.5b. Use 1.5b only if the user asks for the 1.5B."},
         "temperature": {"type": "number", "description": "Optional. Default 0 (harness setting, deterministic). Use >0 with no seed to get a different answer on a retry."},
         "seed": {"type": "integer", "description": "Optional sampling seed."},
         "check": {"type": "string", "description": "Optional named check spec (table-full, table, chair). Default auto: derived from the words of the prompt."},
         "hold_s": {"type": "number", "description": "Optional pause in seconds after each call so the viewer can watch (default 0.6)."},
         "reset": {"type": "boolean", "description": "Empty the scene first (default false: each request adds to the current scene; say reset to clear)."}},
         "required": ["prompt"]}},
    {"name": "blender_reset", "description": "Empty the live Blender scene (objects, materials, data).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "blender_screenshot", "description": "Save a screenshot of the live Blender window and return its path.",
     "inputSchema": {"type": "object", "properties": {}}},
]
HANDLERS = {"blender_build": tool_build, "blender_reset": tool_reset, "blender_screenshot": tool_screenshot}


# ------------------------------------------------------------------ MCP stdio loop
def send(obj):
    _real_stdout.write(json.dumps(obj) + "\n")
    _real_stdout.flush()


def handle(msg):
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}},
            "serverInfo": {"name": "maris3d-blender", "version": "0.1"}}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        try:
            out = HANDLERS[name](args)
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": json.dumps(out, indent=1)}], "isError": False}})
        except Exception as e:
            log("tool error", name, repr(e))
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}})
    elif mid is not None:  # unknown request
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})
    # notifications (no id) need no answer


def main():
    # open Blender as soon as the TUI starts so the user sees the window; never blocks the protocol
    if os.environ.get("BLENDER_MCP_NO_PRELAUNCH") != "1":
        def prelaunch():
            try:
                LIVE.ensure()
            except Exception as e:
                log("prelaunch failed", repr(e))
        threading.Thread(target=prelaunch, daemon=True).start()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            handle(json.loads(line))
        except Exception as e:
            log("bad message", repr(e))


if __name__ == "__main__":
    main()
