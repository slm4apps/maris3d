# SPDX-License-Identifier: Apache-2.0
"""Run the 206-prompt Maris3D benchmark against a local model and write a result JSON.

    python3 eval/maris3d_eval/run_eval.py --model path/to/model-Q8_0.gguf --backend llama --out results/x.json
    python3 eval/maris3d_eval/run_eval.py --model maris3d-slm-blender-1.5b --backend ollama --out results/x.json

The model gets the system prompt it was trained with (dsl.tools.SHORT by default) and the benchmark prompt, answers with a
JSON tool document {"calls": [...]}, the document is compiled to a bpy script (dsl.tools.compile_calls), the script is run in
headless Blender (blender/scene_dump.py) and the scene is scored by the prompt's own check (engine/checks.py).

Metrics: run % (script executed), pass % (scene check held), tok/s, median time to first token, peak model memory, deprecated
API hits, pass % per level. Output schema: eval/result_schema.json. Optional --repair N gives the model N retries with the
failed check (or the last traceback line) as feedback. Greedy decoding, 4096 context, 900-token cap on the JSON answer.

This public runner covers the bare model and the repair loop. The helper-pack variants (part planner, scene hints, retrieval)
that were tried internally are not included: they did not help (see TECHNICAL-REPORT.md, ablations)."""
import argparse, json, os, re, resource, subprocess, sys, tempfile, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "..", "src")]
from prompts import P                                    # noqa: E402
from maris3d.dsl import tools as T                   # noqa: E402
from maris3d.engine.checks import check              # noqa: E402

SCENE_DUMP = os.path.join(HERE, "..", "..", "src", "maris3d", "blender", "scene_dump.py")
BLENDER = os.environ.get("BLENDER_BIN") or "blender"
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
DEPRECATED = [r"use_auto_smooth", r"view_align", r"\bbgl\b", r"\.use_nodes", r"object\.select\s*=", r"scene\.objects\.link",
              r"scene\.update\(\)", r"bpy\.context\.scene\.objects\.active", r"\.show_x_ray",
              r"primitive_\w+_add\([^)]*enter_editmode=True"]
_LLM = {}


def est_tok(msgs):
    return sum(len(m["content"]) for m in msgs) // 3 + 4 * len(msgs)


def chat_llama(gguf, msgs, schema):
    """llama.cpp in-process (llama-cpp-python), JSON-schema constrained like the reference runs."""
    from llama_cpp import Llama
    if gguf not in _LLM:
        _LLM[gguf] = Llama(model_path=gguf, n_ctx=4096, n_threads=int(os.environ.get("LLM_THREADS", "4")), verbose=False)
    t0, first, n, parts = time.time(), None, 0, []
    for ch in _LLM[gguf].create_chat_completion(
            messages=msgs, temperature=0, max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "900")), stream=True,
            response_format={"type": "json_object", "schema": schema}):
        piece = ch["choices"][0]["delta"].get("content")
        if piece:
            first = first or time.time()
            n += 1
            parts.append(piece)
    end = time.time()
    # ru_maxrss is bytes on macOS and kilobytes on Linux
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024)
    _LLM["peak_mb"] = rss
    return {"content": "".join(parts), "eval_count": n, "eval_s": end - (first or end), "ttft_s": (first or end) - t0}


def chat_ollama(tag, msgs, schema):
    # OLLAMA_FORMAT: "json" (default, plain JSON mode), "schema" (full JSON-schema constraint) or "none". On the Ollama build used for this
    # preparation the full schema constraint produced degenerate answers (see docs/EVALUATION.md); the reference numbers used llama.cpp grammar decoding.
    fmt = os.environ.get("OLLAMA_FORMAT", "json")
    body = {"model": tag, "messages": msgs, "stream": False,
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": int(os.environ.get("LLM_MAX_TOKENS", "900"))}}
    if fmt != "none":
        body["format"] = schema if fmt == "schema" else "json"
    req = urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=600))
    return {"content": r["message"]["content"], "eval_count": r.get("eval_count", 0),
            "eval_s": r.get("eval_duration", 0) / 1e9, "ttft_s": (r.get("load_duration", 0) + r.get("prompt_eval_duration", 0)) / 1e9}


def model_mem_mb(backend):
    if backend == "llama":
        return _LLM.get("peak_mb", 0)
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout.splitlines()[1:]
    tot = 0.0
    for l in out:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(GB|MB)", l)
        if m:
            tot += float(m.group(1)) * (1024 if m.group(2) == "GB" else 1)
    return tot


def run_blender(code):
    with tempfile.TemporaryDirectory() as d:
        s, o = f"{d}/s.py", f"{d}/o.json"
        with open(s, "w") as f:
            f.write(code)
        try:
            subprocess.run([BLENDER, "-b", "-P", SCENE_DUMP, "--", s, o], capture_output=True, timeout=90)
            with open(o) as f:
                return json.load(f)
        except Exception as e:
            return {"executed": False, "error": f"harness: {e}", "objects": []}


def summarize(model, repair, rows, peak, system_prompt):
    n = len(rows)
    levels = sorted({r["level"] for r in rows})
    return {"model": os.path.basename(model), "mode": "tools", "repair": repair, "system_prompt": system_prompt,
            "shots": 0, "rag": 0, "scene_hints": False, "parts": False,
            "prompt_tok_est_max": max(r["prompt_tok_est"] for r in rows), "n": n,
            "run_pct": 100 * sum(r["ran"] for r in rows) / n, "pass_pct": 100 * sum(r["passed"] for r in rows) / n,
            "tok_s": sum(r["tokens"] for r in rows) / max(1e-9, sum(r["gen_s"] for r in rows)),
            "ttft_s_median": sorted(r["ttft_s"] for r in rows)[n // 2], "peak_model_mem_mb": round(peak),
            "deprecated_hits": sum(bool(r["deprecated"]) for r in rows),
            "by_level": {str(l): round(100 * sum(r["passed"] for r in rows if r["level"] == l) /
                                       max(1, sum(1 for r in rows if r["level"] == l)), 1) for l in levels}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", required=True, help="GGUF path (--backend llama) or Ollama tag (--backend ollama)")
    ap.add_argument("--backend", choices=["llama", "ollama"], default="llama")
    ap.add_argument("--repair", type=int, default=0)
    ap.add_argument("--long-prompt", action="store_true", help="use the long tool catalogue prompt instead of the trained short one")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--levels", help="comma list, e.g. 1,2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    chat = chat_llama if a.backend == "llama" else chat_ollama
    system = T.PROMPT if a.long_prompt else T.SHORT
    items = [p for p in P if not a.levels or str(p["level"]) in a.levels.split(",")][:a.limit]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    part, rows, peak = a.out + ".partial", [], 0
    if os.path.exists(part):  # resume after an interrupted run
        rows = [json.loads(l) for l in open(part) if l.strip()]
    done = {r["id"] for r in rows}
    for p in items:
        if p["id"] in done:
            continue
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": p["prompt"]}]
        acct = {"toks": 0, "gen_s": 0.0, "ttft": None}

        def ask(m):
            r = chat(a.model, m, T.SCHEMA)
            acct["toks"] += r["eval_count"]
            acct["gen_s"] += r["eval_s"]
            acct["ttft"] = r["ttft_s"] if acct["ttft"] is None else acct["ttft"]
            return r["content"]

        ptok, tries, content = est_tok(msgs), 0, ask(msgs)
        while True:
            peak = max(peak, model_mem_mb(a.backend))
            try:
                code = T.compile_calls(json.loads(content))
            except Exception as e:
                code = "raise RuntimeError('bad tool JSON: %s')" % str(e)[:80]
            sc = run_blender(code)
            fails = check(sc, p["check"])
            if not fails or tries >= a.repair:
                break
            tries += 1
            err = (sc.get("error") or "").strip().splitlines() or ["script failed"]
            feedback = "That failed: " + (fails[0] if sc["executed"] else err[-1][:200]) + "\nFix it. Output only the corrected JSON."
            msgs = msgs + [{"role": "assistant", "content": content}, {"role": "user", "content": feedback}]
            ptok = max(ptok, est_tok(msgs))
            content = ask(msgs)
        dep = [d for d in DEPRECATED if re.search(d, code)]
        row = {"id": p["id"], "level": p["level"], "ran": sc["executed"], "passed": not fails, "fails": fails,
               "error": sc.get("error"), "deprecated": dep, "retries": tries, "prompt_tok_est": ptok,
               "tokens": acct["toks"], "gen_s": acct["gen_s"], "ttft_s": acct["ttft"], "code": code}
        rows.append(row)
        with open(part, "a") as f:
            f.write(json.dumps(row) + "\n")
        print(p["id"], "L%d" % p["level"], "PASS" if not fails else ("RAN" if sc["executed"] else "ERR"), (fails[0] if fails else "")[:90], flush=True)
    summ = summarize(a.model, a.repair, rows, peak, "long" if a.long_prompt else "short")
    print(json.dumps(summ, indent=1))
    with open(a.out, "w") as f:
        json.dump({"summary": summ, "rows": rows}, f, indent=1)


if __name__ == "__main__":
    main()
