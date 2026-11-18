# SPDX-License-Identifier: Apache-2.0
"""Latency and memory probe for a local model served by Ollama, at several prompt sizes (llama-bench equivalent).

llama-bench is not needed: Ollama reports prompt and generation timings for every call. For each target prompt size the probe sends a
neutral filler text followed by a one-line Blender request, with the trained system prompt, greedy decoding and a fixed generation
cap, and records prompt tokens actually processed, prompt-processing speed, time to first token, generation speed, resident memory
of the model process, and whether the answer is still the correct tool call. Sizes above the context window show truncation and
the behaviour of a longer context setting.

    python3 eval/latency_probe.py --model TAG --sizes 512,2048,3800 --out FILE.json [--num-ctx 4096] [--repeat 2]
    python3 eval/latency_probe.py --model TAG --sizes 6000 --num-ctx 4096 --out beyond.json
    python3 eval/latency_probe.py --model TAG --sizes 6000 --num-ctx 8192 --out beyond8k.json

Run one model process at a time and only with enough free memory; the probe unloads the model when it finishes."""
import argparse, json, os, re, subprocess, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "src")]
from maris3d.dsl import tools as T   # noqa: E402

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
FILL = ("The workshop notes describe a plain scene with a table, a lamp and a few boxes that were moved between shelves during the week. "
        "Nothing in these notes is a request. ")
TASK = "Add a cube to the scene."


def runner_rss_mb():
    out = subprocess.run(["ps", "-axo", "rss,command"], capture_output=True, text=True).stdout
    # the worker process is called "ollama runner" in older Ollama versions and "llama-server" in newer ones
    tot = sum(int(l.split(None, 1)[0]) for l in out.splitlines() if "ollama runner" in l or "llama-server" in l)
    return round(tot / 1024)


def call(tag, user, num_ctx, num_predict=128):
    msgs = [{"role": "system", "content": T.SHORT}, {"role": "user", "content": user}]
    body = json.dumps({"model": tag, "messages": msgs, "stream": True, "format": "json", "keep_alive": "2m",
                       "options": {"temperature": 0, "num_ctx": num_ctx, "num_predict": num_predict}}).encode()
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(urllib.request.Request(OLLAMA + "/api/chat", body, {"Content-Type": "application/json"}), timeout=900)
    except urllib.error.HTTPError as e:
        # keep the server's reason (for example an input longer than the context window) instead of a bare "400 Bad Request"
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from None
    parts, first, last = [], None, {}
    for line in resp:
        if not line.strip():
            continue
        ch = json.loads(line)
        p = ch.get("message", {}).get("content", "")
        if p:
            first = first or time.time()
            parts.append(p)
        if ch.get("done"):
            last = ch
            break
    return "".join(parts), last, (first or time.time()) - t0, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", required=True); ap.add_argument("--sizes", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--num-ctx", type=int, default=4096); ap.add_argument("--repeat", type=int, default=2)
    a = ap.parse_args()
    rows = []
    for size in [int(s) for s in a.sizes.split(",")]:
        user = FILL * max(0, (size * 4) // len(FILL)) + "\n\nRequest: " + TASK if size > 40 else TASK
        for rep in range(a.repeat):
            try:
                text, last, ttft, wall = call(a.model, user, a.num_ctx)
            except RuntimeError as e:
                rows.append({"target_prompt_tokens": size, "num_ctx": a.num_ctx, "rep": rep, "error": str(e)})
                print(rows[-1], flush=True)
                break
            ok = bool(re.search(r'"shape"\s*:\s*"cube"', text))
            ev, ed, pc, pd = last.get("eval_count"), last.get("eval_duration"), last.get("prompt_eval_count"), last.get("prompt_eval_duration")
            rows.append({"target_prompt_tokens": size, "num_ctx": a.num_ctx, "rep": rep, "prompt_tokens_processed": pc,
                         "prompt_tok_s": round(pc / (pd / 1e9), 1) if pc and pd else None, "ttft_s": round(ttft, 2),
                         "gen_tokens": ev, "gen_tok_s": round(ev / (ed / 1e9), 1) if ev and ed else None, "wall_s": round(wall, 2),
                         "rss_mb": runner_rss_mb(), "correct_tool_call": ok, "answer_head": text[:120]})
            print(rows[-1], flush=True)
    json.dump(rows, open(a.out, "w"), indent=1)
    urllib.request.urlopen(urllib.request.Request(OLLAMA + "/api/generate", json.dumps({"model": a.model, "keep_alive": 0}).encode(),
                                                  {"Content-Type": "application/json"}), timeout=60).read()


if __name__ == "__main__":
    main()
