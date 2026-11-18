# SPDX-License-Identifier: Apache-2.0
"""The 206-prompt Maris3D gate as an Inspect AI task (pip install inspect-ai).

Same path as the standalone runner: trained system prompt, local Ollama model in JSON mode (greedy, 4096 context), tool document
compiled to a bpy script, headless Blender, scene check. The model is called by the solver below, not through Inspect's provider
layer, because the specialist needs Ollama's JSON mode and the trained system prompt. The scorer runs Blender as a local process:
there is NO container sandbox here (the Blender run is a short, offline, throw-away process; a Docker sandbox is a drop-in later).

    OLLAMA_MODEL=<ollama tag> inspect eval eval/inspect_task/maris3d_gate.py --model mockllm/model --max-samples 1 --limit 20

(`--model mockllm/model` only satisfies Inspect's model argument; the solver ignores it.)
"""
import json, os, shlex, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "..", "src")]
from inspect_ai import Task, task                                     # noqa: E402
from inspect_ai.dataset import Sample                                 # noqa: E402
from inspect_ai.scorer import Score, Target, accuracy, scorer, stderr, CORRECT, INCORRECT   # noqa: E402
from inspect_ai.solver import Generate, TaskState, solver             # noqa: E402

from maris3d.dsl import tools as T                                # noqa: E402
from maris3d.engine import runtime as R                           # noqa: E402
from maris3d.engine.checks import check                           # noqa: E402
from maris3d.eval_data import load_benchmark                      # noqa: E402

BENCH = os.path.join(HERE, "..", "benchmark", "prompts.jsonl")
SCENE_DUMP = os.path.join(HERE, "..", "..", "src", "maris3d", "blender", "scene_dump.py")
BLENDER = os.environ.get("BLENDER_BIN") or "blender"


@solver
def local_specialist():
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        tag = os.environ["OLLAMA_MODEL"]
        msgs = [{"role": "system", "content": T.SHORT}, {"role": "user", "content": state.input_text}]
        content, ntok, gen_s, wall_s = R.ollama_chat(tag, msgs, max_tokens=900, temperature=0)
        state.metadata.update(tokens=ntok, gen_s=gen_s)
        state.output.completion = content
        return state
    return solve


@scorer(metrics=[accuracy(), stderr()])
def scene_check():
    async def score(state: TaskState, target: Target) -> Score:
        spec = state.metadata["check"]
        try:
            code = T.compile_calls(json.loads(state.output.completion))
        except Exception as e:
            code = "raise RuntimeError('bad tool JSON: %s')" % str(e)[:80]
        pre = os.environ.get("PRELAUNCH_CMD")        # optional: a command to run before every Blender launch (for example a free-memory check)
        if pre:
            subprocess.run(shlex.split(pre), check=False)
        with tempfile.TemporaryDirectory() as d:
            s, o = f"{d}/s.py", f"{d}/o.json"
            open(s, "w").write(code)
            try:
                subprocess.run([BLENDER, "-b", "-P", SCENE_DUMP, "--", s, o], capture_output=True, timeout=90)
                scene = json.load(open(o))
            except Exception as e:
                scene = {"executed": False, "error": f"harness: {e}", "objects": []}
        fails = check(scene, spec)
        return Score(value=CORRECT if not fails else INCORRECT, answer=state.output.completion[:300],
                     explanation="; ".join(fails) or "all checks held", metadata={"ran": bool(scene.get("executed")), "level": state.metadata["level"]})
    return score


@task
def maris3d_gate():
    samples = [Sample(id=p["id"], input=p["prompt"], target="", metadata={"level": p["level"], "check": p["check"]}) for p in load_benchmark(BENCH)]
    return Task(dataset=samples, solver=local_specialist(), scorer=scene_check())
