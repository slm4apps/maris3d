#!/usr/bin/env python3
"""OpenAI-compatible bridge that makes the Maris3D models plain selectable models in OpenCode.

    OpenCode (model picker: maris3d/maris3d-slm-blender-0.5b)  --POST /v1/chat/completions-->  this bridge (127.0.0.1:11500)
        -> latest user message only (OpenCode's ~16k-token system prompt and tool list are IGNORED)
        -> blender_mcp.tool_build(): SLM through Ollama (:11434), tool calls run in the live Blender (:9877), harness check, screenshot
        -> a short plain chat answer (what was built, check PASS/FAIL, retries, screenshot path + markdown image)

No MCP tool call and no bigger model is involved. OpenCode's housekeeping calls (session title, summaries) get a short text
answer WITHOUT running the SLM or Blender. Python standard library only (plus the unchanged blender_mcp / harness code).

Usage: python3 -m maris3d.bridge.slm_bridge     (serve in the foreground; PYTHONPATH=src or pip install -e .)
Env:   SLM_BRIDGE_PORT (11500)  SLM_BRIDGE_RETRIES (2: extra tries with the next seed when the check fails)  SLM_BRIDGE_DEBUG=1 (full request log)
"""
import json, os, queue, re, sys, threading, time, traceback, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from maris3d.mcp import blender_mcp as B  # noqa: E402  (the working pipeline: MODELS map, tool_build, LIVE Blender launcher)

PORT = int(os.environ.get("SLM_BRIDGE_PORT", "11500"))
RETRIES = int(os.environ.get("SLM_BRIDGE_RETRIES", "2"))
TEMPERATURE = float(os.environ.get("SLM_BRIDGE_TEMPERATURE", "0.3"))  # the recorded demo's setting (0 repeats one answer)
FIRST_SEED = int(os.environ.get("SLM_BRIDGE_SEED", "3"))
HOLD_S = float(os.environ.get("SLM_BRIDGE_HOLD_S", "0.3"))
DEBUG = os.environ.get("SLM_BRIDGE_DEBUG") == "1"
LOGDIR = B.SHOTS
REQLOG = os.path.join(LOGDIR, "bridge-requests.jsonl")
BUILD_LOCK = threading.Lock()  # one Blender, one Ollama model at a time

# Models exposed in the picker: every SLM in the blender_mcp MODELS map (key -> Ollama tag). All of them use the harness's
# ChatML-template chat prompt (copilot COPILOT_SYS) that blender_mcp.ask_model sends, so one pipeline serves all.
LABELS = {"0.5b": "Maris3D-SLM-Blender-0.5B (Q8_0)", "1.5b": "Maris3D-SLM-Blender-1.5B (Q8_0)"}
BY_ID = {tag: key for key, tag in B.MODELS.items()}


def log(*a):
    print(time.strftime("%H:%M:%S"), "[slm_bridge]", *a, file=sys.stderr, flush=True)


def reqlog(rec):
    try:
        if os.path.exists(REQLOG) and os.path.getsize(REQLOG) > 20_000_000:
            os.replace(REQLOG, REQLOG + ".old")
        with open(REQLOG, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------ reading the OpenAI request
def text_of(content):
    """OpenAI message content: a string, or a list of parts ({type: text, text}). Non-text parts (images) are dropped."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") in (None, "text"))
    return ""


def split_request(body):
    msgs = body.get("messages") or []
    system = "\n".join(text_of(m.get("content")) for m in msgs if m.get("role") in ("system", "developer"))
    users = [text_of(m.get("content")) for m in msgs if m.get("role") == "user"]
    return system, users


# OpenCode's own non-task calls (prompts captured from opencode 2.1.4). The session-title call carries a ~1.8k-char system prompt
# "You name conversations ..." and a user message ending "Reply with only the title."; compaction/summary calls ask to summarise the
# conversation or update a checkpoint. A real chat turn carries the agent prompt (tens of thousands of chars) and a tool list.
TITLE_RE = re.compile(r"(you name conversations|reply with only the title|reply with a title for it|title generator|generate a (brief |short )?title)", re.I)
SUMMARY_RE = re.compile(r"(summari[sz]e (what was done in )?(the|this) (conversation|session|thread)|existing checkpoint|conversation-checkpoint|"
                        r"summari[sz]e only what the user and the assistant said)", re.I)


def housekeeping_kind(system, users, body):
    """'title', 'summary' or None. A request with tools and a big system prompt is a normal chat turn, never housekeeping."""
    if body.get("tools") and len(system) > 6000:
        return None
    last = users[-1] if users else ""
    if TITLE_RE.search(system) or TITLE_RE.search(last):
        return "title"
    if SUMMARY_RE.search(system) or SUMMARY_RE.search(last):
        return "summary"
    return None


def clean_prompt(t):
    """`opencode run "a b"` wraps a multi-word message in literal double quotes before sending it; the TUI does not. Strip one wrapping pair."""
    t = t.strip()
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"' and '"' not in t[1:-1].replace('\\"', ""):
        t = t[1:-1].replace('\\"', '"').strip()
    return t


def make_title(users):
    t = (users[0] if users else "")
    m = re.search(r"<message>(.*?)</message>", t, re.S)
    t = clean_prompt(m.group(1) if m else t)
    t = " ".join(re.sub(r"\s+", " ", t).split(" ")[:8]).rstrip(".!?,")
    return (t[:1].upper() + t[1:]) or "Blender session"


# ------------------------------------------------------------------ the pipeline
def one_line(r):
    objs = r.get("live_objects") or []
    kinds = {}
    for o in objs:
        kinds[o.get("type", "?")] = kinds.get(o.get("type", "?"), 0) + 1
    return len(objs), ", ".join(f"{n} {k.lower()}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]))


def ollama_up():
    try:
        urllib.request.urlopen(B.H.OLLAMA + "/api/tags", timeout=3).read()
        return True
    except Exception:
        return False


def build(key, prompt, emit):
    """Run the SLM + Blender pipeline for one request. Progress goes to the log only (the chat gets one short confirmation). Returns (final_text, usage)."""
    label = LABELS.get(key, key)
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if not ollama_up():
        return ("I could not reach Ollama on 127.0.0.1:11434, so nothing was built. Open the Ollama app (or run `ollama serve`) "
                "and send the request again."), usage
    log(f"asking {label}, building in Blender: {prompt[:80]!r}")
    attempts = []
    res = None
    for n in range(RETRIES + 1):
        seed = FIRST_SEED + n
        try:
            res = B.tool_build({"prompt": prompt, "model": key, "temperature": TEMPERATURE, "seed": seed, "hold_s": HOLD_S, "reset": True})
        except Exception as e:  # Blender launch failure, Ollama error, memory gate...
            log("build error", repr(e))
            traceback.print_exc(file=sys.stderr)
            tail = "" if not attempts else f" Earlier tries: {'; '.join(attempts)}."
            return (f"Nothing was built: {type(e).__name__}: {e}.{tail}"), usage
        usage["prompt_tokens"] += res.get("prompt_tokens") or 0
        usage["completion_tokens"] += res.get("tokens") or 0
        if res.get("blender_crashed"):
            return res["blender_notice"], usage
        chk = res["check"]
        if chk["passed"]:
            break
        why = B.CF.failure_reason(res["calls"], res["per_call_results"], chk) or "the check failed"
        attempts.append(why)
        if n < RETRIES:
            log(f"try {n + 1} (seed {seed}) did not work: {why}; retrying")
    chk = res["check"]
    passed = chk["passed"]
    text = B.CF.confirmation(label, res.get("scene_before") or [], res.get("scene_after") or res.get("live_objects") or [], calls=res["calls"],
                             per_call=res["per_call_results"], check=chk, tries=len(attempts) + (1 if passed else 0),
                             earlier_fails=attempts if passed else attempts[:-1])
    if res.get("blender_notice"):
        text += " " + res["blender_notice"]
    return B.CF.with_screenshot(text, res.get("screenshot")), usage


def handle_command(prompt):
    """Chat-level commands kept from the old agent: reset / screenshot. Returns text or None."""
    p = re.sub(r"[^a-z ]", "", prompt.lower()).strip()
    if p in ("reset", "clear", "empty the scene", "clear the scene", "reset the scene"):
        r = B.tool_reset({})
        return f"Blender scene emptied ({len(r['live'].get('objects', []))} objects left)." + (f" Note: {r['blender_notice']}" if r.get("blender_notice") else "")
    if p in ("screenshot", "take a screenshot"):
        r = B.tool_screenshot({})
        return f"Screenshot: {r['screenshot']}\n\n![Blender scene]({r['screenshot']})\n\nObjects in the scene: {len(r.get('live_objects') or [])}."
    return None


def answer(body, emit):
    """Returns (text, usage). The text has already been emitted in pieces through emit() for the progress parts."""
    key = BY_ID.get(body.get("model"), None)
    system, users = split_request(body)
    kind = housekeeping_kind(system, users, body)
    rec = {"t": time.strftime("%H:%M:%S"), "model": body.get("model"), "stream": bool(body.get("stream")), "n_messages": len(body.get("messages") or []),
           "system_chars": len(system), "n_tools": len(body.get("tools") or []), "approx_request_tokens": len(json.dumps(body)) // 4,
           "housekeeping": kind, "user": (users[-1] if users else "")[:300]}
    if DEBUG:
        rec["body"] = body
    if kind == "title":
        rec["reply"] = make_title(users)
        reqlog(rec)
        return rec["reply"], {"prompt_tokens": 0, "completion_tokens": 0}
    if kind == "summary":
        rec["reply"] = "Maris3D session: each request is built in the live Blender window; see the screenshots listed above."
        reqlog(rec)
        return rec["reply"], {"prompt_tokens": 0, "completion_tokens": 0}
    prompt = clean_prompt(users[-1] if users else "")
    if key is None:
        text, usage = f"Unknown model {body.get('model')!r}. Available: {', '.join(BY_ID)}.", {"prompt_tokens": 0, "completion_tokens": 0}
    elif not prompt:
        text, usage = "I got an empty message. Describe the 3D scene you want, for example: build a house.", {"prompt_tokens": 0, "completion_tokens": 0}
    else:
        with BUILD_LOCK:
            t0 = time.time()
            cmd = None
            try:
                cmd = handle_command(prompt)
            except Exception as e:
                cmd = f"Could not do that: {type(e).__name__}: {e}"
            if cmd is not None:
                text, usage = cmd, {"prompt_tokens": 0, "completion_tokens": 0}
            else:
                text, usage = build(key, prompt, emit)
            rec["wall_s"] = round(time.time() - t0, 1)
            rec["slm_prompt_tokens"] = usage["prompt_tokens"]
            rec["slm_user_text_sent"] = prompt
    rec["reply"] = text[:1500]
    reqlog(rec)
    return text, usage


# ------------------------------------------------------------------ HTTP
def chunk(cid, model, delta=None, finish=None, usage=None):
    c = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model,
         "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}
    if usage is not None:
        c["usage"] = usage
    return c


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        log(self.address_string(), fmt % a)

    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("/v1/models", "/models"):
            now = int(time.time())
            self._json(200, {"object": "list", "data": [{"id": tag, "object": "model", "created": now, "owned_by": "maris3d"} for tag in BY_ID]})
        elif path in ("/health", ""):
            self._json(200, {"ok": True, "models": list(BY_ID)})
        else:
            self._json(404, {"error": {"message": "not found", "type": "invalid_request_error"}})

    def do_POST(self):
        if self.path.split("?")[0].rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            return self._json(404, {"error": {"message": "not found", "type": "invalid_request_error"}})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._json(400, {"error": {"message": "invalid JSON", "type": "invalid_request_error"}})
        model, cid = body.get("model") or "maris3d", "chatcmpl-" + os.urandom(6).hex()
        try:
            if not body.get("stream"):
                pieces = []
                text, usage = answer(body, pieces.append)
                full = "".join(pieces) + text
                u = dict(usage, total_tokens=usage["prompt_tokens"] + usage["completion_tokens"])
                return self._json(200, {"id": cid, "object": "chat.completion", "created": int(time.time()), "model": model,
                                        "choices": [{"index": 0, "message": {"role": "assistant", "content": full}, "finish_reason": "stop"}], "usage": u})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            def sse(obj):
                self.wfile.write(b"data: " + (json.dumps(obj) if not isinstance(obj, str) else obj).encode() + b"\n\n")
                self.wfile.flush()

            q = queue.Queue()
            out = {}

            def work():
                try:
                    out["text"], out["usage"] = answer(body, lambda s: q.put(s))
                except Exception as e:  # never a stack trace in the chat
                    log("answer error", repr(e))
                    traceback.print_exc(file=sys.stderr)
                    out["text"], out["usage"] = f"The bridge hit an error: {type(e).__name__}: {e}", {"prompt_tokens": 0, "completion_tokens": 0}
                q.put(None)

            sse(chunk(cid, model, {"role": "assistant", "content": ""}))
            threading.Thread(target=work, daemon=True).start()
            while True:
                try:
                    item = q.get(timeout=10)
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")  # SSE comment: keeps idle timeouts away while the SLM and Blender work
                    self.wfile.flush()
                    continue
                if item is None:
                    break
                sse(chunk(cid, model, {"content": item}))
            sse(chunk(cid, model, {"content": out["text"]}))
            u = out["usage"]
            sse(chunk(cid, model, finish="stop", usage=dict(u, total_tokens=u["prompt_tokens"] + u["completion_tokens"])))
            sse("[DONE]")
        except (BrokenPipeError, ConnectionResetError):
            log("client went away")
        except Exception as e:
            log("handler error", repr(e))
            traceback.print_exc(file=sys.stderr)
            try:
                self._json(500, {"error": {"message": f"{type(e).__name__}: {e}", "type": "server_error"}})
            except Exception:
                pass


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    log(f"listening on http://127.0.0.1:{PORT}/v1 with models {', '.join(BY_ID)}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
