# SPDX-License-Identifier: Apache-2.0
"""Shared runtime helpers: talk to a local Ollama model, repair a cut-off tool document, compile and run it in headless
Blender, keep a conversation inside the 4096-token context. Pure standard library.

The names (BLENDER, OLLAMA, MAX_CALLS, COPILOT_SYS, fit, salvage_doc, run_blender, switch_to, swap_free_mb, swap_status,
last_error_line) are the surface used by the MCP server and the OpenAI-compatible bridge."""
import json, os, re, subprocess, tempfile, time, urllib.request

from maris3d.dsl import tools as T

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER = os.environ.get("BLENDER_BIN") or "blender"
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
MAX_CALLS = 40            # maxItems of the tool schema
CTX = 3600                # conservative guard for the 4096-token context
SWAP_REFUSE_MB, SWAP_WARN_MB = 250, 500

# The system prompt the models were fine-tuned with is T.SHORT. The long form T.PROMPT (tool catalogue) plus this
# paragraph is what the copilot/MCP flow sends so that the model can fix its own scene over several turns.
COPILOT_SYS = T.PROMPT + ("\nYou are a copilot working with a user over turns. After your calls run you are "
                          "told what the scene looks like; if the user or the facts point out a problem, fix it "
                          "in your next answer. Output only the JSON tool document.")


def parse_swap_free_mb(text):
    """Free swap in MB from `sysctl vm.swapusage` text (macOS); None when unparseable."""
    m = re.search(r"free = ([\d.]+)([MGK])", text or "")
    if not m:
        return None
    return float(m.group(1)) * {"K": 1 / 1024, "M": 1, "G": 1024}[m.group(2)]


def swap_free_mb():
    try:
        return parse_swap_free_mb(subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True).stdout)
    except Exception:
        return None


def swap_status(free_mb):
    """'refuse' under 250 MB, 'warn' under 500 MB, else 'ok' (unknown counts as ok)."""
    if free_mb is None:
        return "ok"
    return "refuse" if free_mb < SWAP_REFUSE_MB else "warn" if free_mb < SWAP_WARN_MB else "ok"


def last_error_line(scene):
    lines = [l for l in (scene.get("error") or "").strip().splitlines() if l.strip()]
    return lines[-1].strip()[:200] if lines else ""


def _post(path, payload, timeout=600):
    req = urllib.request.Request(OLLAMA + path, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def switch_to(model_tag):
    """One model process at a time: unload every other running Ollama model (keep_alive 0)."""
    try:
        running = [m["name"] for m in json.load(urllib.request.urlopen(OLLAMA + "/api/ps", timeout=10)).get("models", [])]
    except Exception:
        running = []
    for name in running:
        if name.split(":")[0] != model_tag:
            _post("/api/generate", {"model": name, "keep_alive": 0}, 60)


def salvage_doc(text, cap=MAX_CALLS):
    """Tool document from model text: the whole JSON when valid, else the complete call objects found in a cut-off
    or run-on document; always at most `cap` calls (the schema's maxItems). {"calls": []} when nothing usable."""
    try:
        d = json.loads(text)
        if isinstance(d, dict) and isinstance(d.get("calls"), list):
            return dict(d, calls=d["calls"][:cap])
    except Exception:
        pass
    calls, m = [], re.search(r'"calls"\s*:\s*\[', text or "")
    if m:
        i, dec = m.end(), json.JSONDecoder()
        while len(calls) < cap:
            while i < len(text) and text[i] in " \n\t\r,":
                i += 1
            if i >= len(text) or text[i] != "{":
                break
            try:
                o, i = dec.raw_decode(text, i)
            except Exception:
                break
            if isinstance(o, dict):
                calls.append(o)
    return {"calls": calls}


def est_tok(msgs):
    return sum(len(m["content"]) for m in msgs) // 3 + 4 * len(msgs)


def ctx_tok(msgs):
    """Conservative context estimate: JSON-heavy tool documents run about 2.4 characters per token."""
    return int(sum(len(m["content"]) for m in msgs) / 2.4) + 4 * len(msgs)


def compact(msgs):
    out = []
    for m in msgs:
        c = m["content"]
        if m["role"] == "assistant" and len(c) > 400:
            try:
                c = json.dumps(json.loads(c), separators=(",", ":"))
            except Exception:
                c = c[:400]
        out.append({"role": m["role"], "content": c})
    return out


def fit(msgs):
    """Keep the conversation inside the 4096-token context: compact JSON first, then shrink old assistant documents.
    Never drops messages: system, goal and the recent tail always survive intact."""
    if ctx_tok(msgs) <= CTX:
        return msgs
    out = compact(msgs)
    for cap in (1200, 800, 400, 200, 100):
        if ctx_tok(out) <= CTX:
            break
        out = [{"role": m["role"],
                "content": m["content"][:cap] if m["role"] == "assistant" and len(m["content"]) > cap else m["content"]}
               for m in out]
    return out


def ollama_chat(model_tag, msgs, max_tokens=2800, temperature=0, seed=None):
    """One streamed /api/chat call in JSON mode. Returns (content, tokens, gen_s, wall_s). The stream is cut as soon as
    a 41st call starts (the schema allows 40)."""
    t0 = time.time()
    opts = {"temperature": temperature, "num_ctx": 4096, "num_predict": max_tokens}
    if seed is not None:
        opts["seed"] = seed
    body = json.dumps({"model": model_tag, "messages": msgs, "stream": True, "format": "json", "keep_alive": "5m",
                       "options": opts}).encode()
    resp = urllib.request.urlopen(urllib.request.Request(OLLAMA + "/api/chat", body, {"Content-Type": "application/json"}), timeout=600)
    parts, n, first, last = [], 0, None, {}
    for line in resp:
        if not line.strip():
            continue
        ch = json.loads(line)
        piece = ch.get("message", {}).get("content", "")
        if piece:
            first = first or time.time()
            parts.append(piece)
            n += 1
            if "".join(parts).count('{"tool"') > MAX_CALLS:
                resp.close()
                break
        if ch.get("done"):
            last = ch
            break
    end = time.time()
    return "".join(parts), last.get("eval_count") or n, (end - (first or end)), end - t0


def run_blender(doc, prefix):
    """Compile calls, then run scene_dump and a Workbench render in ONE headless Blender.
    Returns (scene, blender_seconds, png_paths)."""
    try:
        code = T.compile_calls(doc) if doc.get("calls") else "raise RuntimeError('the model returned no usable tool calls')"
    except Exception as e:
        code = f"raise RuntimeError('bad tool JSON: {str(e)[:80]}')"
    t0 = time.time()
    with tempfile.TemporaryDirectory() as d:
        s, o = f"{d}/s.py", f"{d}/o.json"
        with open(s, "w") as f:
            f.write(code)
        try:
            subprocess.run([BLENDER, "-b", "-P", os.path.join(HERE, "..", "blender", "render_scene.py"), "--", s, o, prefix],
                           capture_output=True, timeout=240)
            with open(o) as f:
                scene = json.load(f)
        except Exception as e:
            scene = {"executed": False, "error": f"harness: {e}", "objects": []}
    pngs = [p for p in (scene.get("render") or {}).get("pngs", []) if os.path.exists(p)]
    return scene, time.time() - t0, pngs
