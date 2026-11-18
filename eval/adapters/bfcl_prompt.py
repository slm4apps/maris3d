# SPDX-License-Identifier: Apache-2.0
"""BFCL (Berkeley Function Calling Leaderboard) subset in prompt mode: simple_python and multiple, as an honest floor.

The model is NOT a general function-calling model. It was trained to answer in one fixed format (a JSON tool document for Blender).
This adapter gives it the benchmark's function descriptions in the user message, asks for the benchmark's call format
`[func(arg=value)]`, and scores the answer with our own re-implementation of the AST check (function name, required and unknown
parameters, value in the accepted list with int-for-float tolerance and case/punctuation-insensitive strings). It is NOT the official
evaluator: the numbers are a floor and are not comparable with the public leaderboard.

    python3 eval/adapters/bfcl_prompt.py run   --data DIR --out FILE --model TAG [--cats simple_python,multiple] [--limit N]
    python3 eval/adapters/bfcl_prompt.py score --data DIR --in FILE --json FILE
"""
import argparse, ast, json, os, re, sys, time, urllib.request

OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
SYSTEM = ("You are an expert in composing functions. You are given a question and a set of possible functions. Based on the question, "
          "you will need to make one or more function/tool calls to achieve the purpose. If none of the functions can be used, point it out. "
          "If the given question lacks the parameters required by the function, also point it out. You should only return the function calls "
          "in your response.\nIf you decide to invoke any of the function(s), you MUST put it in the format of "
          "[func_name1(params_name1=params_value1, params_name2=params_value2...), func_name2(params)]\n"
          "You SHOULD NOT include any other text in the response.\nHere is a list of functions in JSON format that you can invoke.\n{functions}\n")


def load(data, cat):
    f = os.path.join(data, f"BFCL_v4_{cat}.json")
    return [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]


def answers(data, cat):
    f = os.path.join(data, "possible_answer", f"BFCL_v4_{cat}.json")
    return {j["id"]: j["ground_truth"] for j in map(json.loads, (l for l in open(f, encoding="utf-8") if l.strip()))}


def ask(tag, system, user):
    body = {"model": tag, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "stream": False,
            "keep_alive": "5m", "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 400}}
    r = json.load(urllib.request.urlopen(urllib.request.Request(OLLAMA + "/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=300))
    return r["message"]["content"], r.get("prompt_eval_count"), r.get("eval_count"), (r.get("eval_duration") or 0) / 1e9


def run(a):
    done = set()
    if os.path.exists(a.out):
        done = {json.loads(l)["id"] for l in open(a.out) if l.strip()}
    for cat in a.cats.split(","):
        items = load(a.data, cat)[:a.limit or None]
        for it in items:
            if it["id"] in done:
                continue
            q = it["question"][0][0]["content"]
            sysm = SYSTEM.replace("{functions}", json.dumps(it["function"]))
            try:
                out, ptok, etok, es = ask(a.model, sysm, q)
            except Exception as e:
                out, ptok, etok, es = f"ERROR {e}", None, None, 0
            with open(a.out, "a") as f:
                f.write(json.dumps({"id": it["id"], "cat": cat, "output": out, "prompt_tokens": ptok, "eval_tokens": etok, "eval_s": es}) + "\n")
            print(it["id"], (out or "")[:80].replace("\n", " "), flush=True)


def parse_calls(text):
    """Return list of (name, {param: value}) or None when the answer is not a parsable call list."""
    t = (text or "").strip()
    t = re.sub(r"^```\w*\n|\n```$", "", t).strip()
    if not t.startswith("["):
        t = "[" + t + "]"
    try:
        tree = ast.parse(t, mode="eval").body
    except Exception:
        return None
    if not isinstance(tree, ast.List):
        return None
    calls = []
    for e in tree.elts:
        if not isinstance(e, ast.Call):
            return None
        name = ast.unparse(e.func)
        try:
            kw = {k.arg: ast.literal_eval(k.value) for k in e.keywords if k.arg}
        except Exception:
            return None
        if e.args:
            return None  # positional args cannot be matched to names without the schema
        calls.append((name, kw))
    return calls


def norm(v):
    if isinstance(v, str):
        return re.sub(r"[\s,./\-_*^]", "", v).lower().replace("'", "").replace('"', "")
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    return v


def call_ok(call, gt_item):
    (gname, gparams), = gt_item.items()
    name, kw = call
    if name != gname:
        return "wrong_function"
    funcdoc_required = None
    for p, accepted in gparams.items():
        if p not in kw:
            if "" in accepted:      # optional parameter, omission allowed
                continue
            return "missing_required_param"
        if not any(norm(kw[p]) == norm(x) for x in accepted if x != "" or kw[p] == ""):
            return "wrong_value"
    for p in kw:
        if p not in gparams:
            return "unknown_param"
    return None


def score(a):
    rows = [json.loads(l) for l in open(a.inp) if l.strip()]
    res, per = [], {}
    for cat in sorted({r["cat"] for r in rows}):
        gt, fdocs = answers(a.data, cat), {i["id"]: i for i in load(a.data, cat)}
        for r in [r for r in rows if r["cat"] == cat]:
            calls = parse_calls(r["output"])
            if calls is None:
                cls = "unparsable_output"
            elif len(calls) != len(gt[r["id"]]):
                cls = "wrong_number_of_calls"
            else:
                cls = call_ok(calls[0], gt[r["id"]][0]) or "pass"
            res.append({"id": r["id"], "cat": cat, "class": cls, "prompt_tokens": r.get("prompt_tokens")})
    for cat in sorted({r["cat"] for r in res}):
        rs = [r for r in res if r["cat"] == cat]
        per[cat] = {"n": len(rs), "passed": sum(r["class"] == "pass" for r in rs),
                    "pass_pct": round(100 * sum(r["class"] == "pass" for r in rs) / len(rs), 1),
                    "classes": {c: sum(r["class"] == c for r in rs) for c in sorted({r["class"] for r in rs})}}
    toks = [r["prompt_tokens"] for r in res if r["prompt_tokens"]]
    out = {"per_category": per, "max_prompt_tokens": max(toks) if toks else None,
           "prompts_near_ctx_limit(>=3900)": sum(t >= 3900 for t in toks)}
    json.dump({"summary": out, "rows": res}, open(a.json, "w"), indent=1)
    print(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--data", required=True); r.add_argument("--out", required=True); r.add_argument("--model", required=True)
    r.add_argument("--cats", default="simple_python,multiple"); r.add_argument("--limit", type=int, default=0)
    s = sub.add_parser("score"); s.add_argument("--data", required=True); s.add_argument("--inp", "--in", dest="inp", required=True); s.add_argument("--json", required=True)
    a = ap.parse_args()
    run(a) if a.cmd == "run" else score(a)


if __name__ == "__main__":
    main()
