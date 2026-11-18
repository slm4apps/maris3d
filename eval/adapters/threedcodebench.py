# SPDX-License-Identifier: Apache-2.0
"""Thin adapter: 3DCodeBench text-to-3D prompts -> Maris3D -> tool DSL -> bpy script -> the benchmark's own export step.

3DCodeBench (MIT data, Apache-2.0 code, Blender 5.x, Infinigen-based categories) asks a model to write a Blender Python script
from a text description. Maris3D does not write Blender Python: it writes a JSON tool document that the engine compiles to a
bpy script. This adapter replaces only the model call of the benchmark's `text_to_3d` task, so the rest of the benchmark (GLB export,
Chamfer scoring) runs unchanged on the compiled script.

Steps (all paths are arguments; nothing is downloaded here):
  generate  read <bench>/<Category>_seed0/prompt_<type>.txt, ask the local model (same Ollama JSON-mode call as the MCP server
            and the bridge), compile the tool document, write <out>/<Category>_seed0/<Category>_seed0.py and generate.json.
  report    combine generate.json, <out>/<Category>_seed0/glb/export_log.json (written by the benchmark's export_glb.py) and an
            optional Chamfer file into one summary JSON.

The model gets its trained system prompt and the benchmark's description as the user message. It does NOT get the benchmark's
system prompt (that one asks for Blender Python and would be out of distribution for a DSL model).

    python3 eval/adapters/threedcodebench.py generate --bench DIR --out DIR --model TAG [--prompt-type description] [--offset N --limit N]
    python3 eval/adapters/threedcodebench.py report --bench DIR --out DIR [--chamfer FILE] --json summary.json
"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "..", "src")]
from maris3d.dsl import tools as T                    # noqa: E402
from maris3d.engine import runtime as R               # noqa: E402


def categories(bench):
    return sorted(d for d in os.listdir(bench) if os.path.isdir(os.path.join(bench, d)) and d.endswith("_seed0"))


def generate(a):
    cats = categories(a.bench)[a.offset:]
    if a.limit:
        cats = cats[:a.limit]
    for c in cats:
        d = os.path.join(a.out, c)
        if os.path.exists(os.path.join(d, "generate.json")) and not a.overwrite:
            continue
        os.makedirs(d, exist_ok=True)
        prompt = open(os.path.join(a.bench, c, f"prompt_{a.prompt_type}.txt"), encoding="utf-8").read().strip()
        msgs = [{"role": "system", "content": T.SHORT}, {"role": "user", "content": prompt}]
        rec = {"instance": c, "prompt_type": a.prompt_type, "model": a.model, "prompt_chars": len(prompt)}
        t0 = time.time()
        try:
            content, ntok, gen_s, wall_s = R.ollama_chat(a.model, msgs, max_tokens=a.max_tokens, temperature=0)
            rec.update(raw=content, tokens=ntok, gen_s=round(gen_s, 2), wall_s=round(wall_s, 2))
            doc = R.salvage_doc(content)
            rec["n_calls"] = len(doc["calls"])
            if not doc["calls"]:
                code, rec["status"], rec["reason"] = "raise RuntimeError('adapter: no usable tool calls')", "ADAPTER_NO_CALLS", "model output had no complete tool call"
            else:
                try:
                    code, rec["status"] = T.compile_calls(doc), "COMPILED"
                except Exception as e:
                    code, rec["status"], rec["reason"] = "raise RuntimeError('adapter: compile failed')", "ADAPTER_COMPILE_ERROR", f"{type(e).__name__}: {str(e)[:160]}"
        except Exception as e:
            code, rec["status"], rec["reason"] = "raise RuntimeError('adapter: model call failed')", "ADAPTER_MODEL_ERROR", f"{type(e).__name__}: {str(e)[:160]}"
            rec["wall_s"] = round(time.time() - t0, 2)
        with open(os.path.join(d, f"{c}.py"), "w", encoding="utf-8") as f:
            f.write(code)
        with open(os.path.join(d, "generate.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
        print(c, rec["status"], rec.get("n_calls"), flush=True)


def report(a):
    rows = []
    chamfer = {}
    if a.chamfer and os.path.exists(a.chamfer):
        j = json.load(open(a.chamfer))
        chamfer = {r["instance"]: r for r in j.get("per_instance", [])}
    for c in categories(a.bench):
        d = os.path.join(a.out, c)
        g = json.load(open(os.path.join(d, "generate.json"))) if os.path.exists(os.path.join(d, "generate.json")) else {"status": "NOT_GENERATED"}
        ep = os.path.join(d, "glb", "export_log.json")
        e = json.load(open(ep)) if os.path.exists(ep) else {"status": "NOT_EXPORTED"}
        ch = chamfer.get(c, {})
        rows.append({"instance": c, "generate": g.get("status"), "reason": g.get("reason"), "n_calls": g.get("n_calls"),
                     "tokens": g.get("tokens"), "gen_s": g.get("gen_s"), "export": e.get("status"), "n_meshes": e.get("n_meshes"),
                     "error": (e.get("error") or "")[:300], "cd": ch.get("cd"), "cd_yawmin": ch.get("cd_yawmin"), "chamfer_status": ch.get("status")})
    n = len(rows)
    ok = [r for r in rows if r["export"] == "OK"]
    cds = sorted(r["cd_yawmin"] for r in rows if r.get("cd_yawmin") is not None)
    summ = {"n": n, "adapter_could_not_run": sum(r["generate"] not in ("COMPILED",) for r in rows),
            "adapter_status": {s: sum(r["generate"] == s for r in rows) for s in sorted({r["generate"] for r in rows})},
            "executable": len(ok), "executability": round(len(ok) / n, 4) if n else None,
            "export_status": {s: sum(r["export"] == s for r in rows) for s in sorted({r["export"] for r in rows})},
            "chamfer_scored": len(cds), "chamfer_yawmin_median": cds[len(cds) // 2] if cds else None,
            "chamfer_yawmin_mean": sum(cds) / len(cds) if cds else None}
    json.dump({"summary": summ, "rows": rows}, open(a.json, "w"), indent=1)
    print(json.dumps(summ, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--bench", required=True); g.add_argument("--out", required=True); g.add_argument("--model", required=True)
    g.add_argument("--prompt-type", default="description", choices=["description", "instruction"])
    g.add_argument("--offset", type=int, default=0); g.add_argument("--limit", type=int, default=0)
    g.add_argument("--max-tokens", type=int, default=2800); g.add_argument("--overwrite", action="store_true")
    r = sub.add_parser("report")
    r.add_argument("--bench", required=True); r.add_argument("--out", required=True)
    r.add_argument("--chamfer"); r.add_argument("--json", required=True)
    a = ap.parse_args()
    generate(a) if a.cmd == "generate" else report(a)


if __name__ == "__main__":
    main()
