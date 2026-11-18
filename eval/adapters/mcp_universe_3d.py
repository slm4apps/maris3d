# SPDX-License-Identifier: Apache-2.0
"""Adapter: MCP-Universe 3D-design tasks (Blender domain) -> Maris3D -> tool DSL -> headless Blender -> the benchmark's own checker.

MCP-Universe (Apache-2.0) drives a Blender MCP server with a ReAct agent and a paid chat API, then checks the saved .blend file with
one checker script per task. This adapter keeps the tasks and the checkers and replaces the agent loop: the task text is sent once to
the local model (trained system prompt, JSON mode), the tool document is compiled and executed in a headless Blender that starts
from an empty scene, the result is saved as the .blend file the task names, and the task's checker script is run on that file.

Concessions (all reported with the numbers): one shot, no agent loop; the adapter, not the model, saves the file (the DSL has no
save tool); no Polyhaven or other network access (the DSL has no such tool); Blender version is the one installed here, not the
version the benchmark pins.

    python3 eval/adapters/mcp_universe_3d.py generate --tasks DIR --out DIR --model TAG
    python3 eval/adapters/mcp_universe_3d.py check --bench-root DIR --out DIR --blender PATH
"""
import argparse, glob, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "..", "src")]
from maris3d.dsl import tools as T                    # noqa: E402
from maris3d.engine import runtime as R               # noqa: E402

RUNNER = '''
import bpy, json, sys
src, blend = sys.argv[sys.argv.index("--") + 1:][:2]
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for m in list(bpy.data.meshes) + list(bpy.data.materials) + list(bpy.data.cameras) + list(bpy.data.lights):
    try: bpy.data.batch_remove([m])
    except Exception: pass
err = None
try:
    exec(compile(open(src).read(), src, "exec"), {"__name__": "__main__"})
except Exception as e:
    err = f"{type(e).__name__}: {e}"
bpy.ops.wm.save_as_mainfile(filepath=blend)
print("RUNNER_RESULT " + json.dumps({"error": err}))
'''


def task_files(d):
    return sorted(glob.glob(os.path.join(d, "blender_task_*.json")))


def generate(a):
    for f in task_files(a.tasks):
        tid = re.search(r"(\d+)\.json$", f).group(1)
        d = os.path.join(a.out, f"task_{tid}")
        if os.path.exists(os.path.join(d, "generate.json")):
            continue
        os.makedirs(d, exist_ok=True)
        q = json.load(open(f, encoding="utf-8"))["question"]
        q = q.replace("{{MCPUniverse_DIR}}", "benchmark")
        msgs = [{"role": "system", "content": T.SHORT}, {"role": "user", "content": q}]
        rec = {"task": tid, "question_chars": len(q), "est_prompt_tokens": R.est_tok(msgs)}
        try:
            content, ntok, gen_s, wall_s = R.ollama_chat(a.model, msgs, max_tokens=2800, temperature=0)
            doc = R.salvage_doc(content)
            rec.update(raw=content, tokens=ntok, gen_s=round(gen_s, 2), n_calls=len(doc["calls"]))
            if doc["calls"]:
                try:
                    code = T.compile_calls(doc); rec["status"] = "COMPILED"
                except Exception as e:
                    code = ""; rec.update(status="ADAPTER_COMPILE_ERROR", reason=str(e)[:200])
            else:
                code = ""; rec.update(status="ADAPTER_NO_CALLS", reason="no complete tool call in the answer")
        except Exception as e:
            code = ""; rec.update(status="ADAPTER_MODEL_ERROR", reason=f"{type(e).__name__}: {str(e)[:200]}")
        open(os.path.join(d, "script.py"), "w").write(code)
        json.dump(rec, open(os.path.join(d, "generate.json"), "w"), indent=1)
        print(tid, rec["status"], rec.get("n_calls"), flush=True)


def check(a):
    """Run one task: execute script, save blend, run the benchmark's checker on it. Writes <out>/task_N/check.json."""
    runner = os.path.join(a.out, "_runner.py")
    open(runner, "w").write(RUNNER)
    # The task files and out/ folders are zero-padded (0001); the benchmark's checker files and result names are not (tid_1_check.py).
    tid = str(int(a.task))
    d = os.path.join(a.out, f"task_{tid.zfill(4)}")
    gen = json.load(open(os.path.join(d, "generate.json")))
    res = {"task": tid, "generate": gen["status"], "executed": False, "file_saved": False, "pass": False, "reason": ""}
    blend = os.path.join(d, f"tid_{tid}.blend")
    if gen["status"] != "COMPILED":
        # still save an empty scene so the benchmark's own file/content checks report what they would for an empty result
        open(os.path.join(d, "script.py"), "w").write("pass\n")
    try:
        p = subprocess.run([a.blender, "-b", "--factory-startup", "--python", runner, "--", os.path.join(d, "script.py"), blend],
                           capture_output=True, text=True, timeout=120)
        m = re.search(r"RUNNER_RESULT (\{.*\})", p.stdout)
        err = json.loads(m.group(1))["error"] if m else "runner produced no result"
        res["executed"] = m is not None and err is None
        res["script_error"] = err
    except Exception as e:
        res["script_error"] = f"harness: {e}"
    res["file_saved"] = os.path.exists(blend)
    chk = os.path.join(a.bench_root, "mcpuniverse", "evaluator", "blender", "check_functions", f"tid_{tid}_check.py")
    resfile = os.path.join(a.bench_root, "mcpuniverse", "evaluator", "blender", "evaluated_results", f"tid_{tid}_results.json")
    if os.path.exists(resfile):
        os.remove(resfile)
    if res["file_saved"] and os.path.exists(chk):
        try:
            subprocess.run([a.blender, "--background", blend, "--python", chk], capture_output=True, text=True, timeout=60)
            if os.path.exists(resfile):
                v = json.load(open(resfile))
                res["pass"], res["reason"] = bool(v.get("pass")), v.get("reason", "")
                os.replace(resfile, os.path.join(d, "checker_result.json"))
            else:
                res["reason"] = "checker wrote no result file"
        except Exception as e:
            res["reason"] = f"checker failed: {e}"
    json.dump(res, open(os.path.join(d, "check.json"), "w"), indent=1)
    print(tid, "PASS" if res["pass"] else "FAIL", res["reason"][:100])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--tasks", required=True); g.add_argument("--out", required=True); g.add_argument("--model", required=True)
    c = sub.add_parser("check"); c.add_argument("--bench-root", required=True); c.add_argument("--out", required=True)
    c.add_argument("--blender", required=True); c.add_argument("--task", required=True)
    a = ap.parse_args()
    generate(a) if a.cmd == "generate" else check(a)


if __name__ == "__main__":
    main()
