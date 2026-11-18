# Architecture (v0.1 draft)

## Pieces
- **Model**: Qwen2.5-Coder-0.5B-Instruct fine-tuned (merged GGUF q8_0), plus two small adapters (LoRA): the edit adapter and the planner. With no adapter or the edit adapter the model only ever emits the 26 native tool calls (`<tool_call>{"name","arguments"}</tool_call>`). It is never asked to write or run Blender code.
- **Copilot** (`src/maris3d/copilot`): no dependencies, no server, no Blender import. It offers the model the tools a request needs plus two fixed distractors, sends tool results as exactly `ok` or `error: <last 200 chars>`, appends a compact scene line to later turns, compiles the calls to Blender Python (`dsl/tools.py`) and runs them through an executor. Undo resets the scene and replays the accepted batches.
- **Runtimes** (`src/maris3d/runtimes`): llama-server (per-request adapter scale, always sent because adapters otherwise load at scale 1.0), Ollama (no per-request adapter: edit needs a second model entry), any OpenAI-style server such as LM Studio (plain model). Detection only looks; it never starts or downloads anything.
- **Executors** (`src/maris3d/executors`): our own Blender window over a local socket (`blender/live_server.py`), or inside another Blender MCP, where native calls are compiled to Python and sent through that MCP's execute tool.
- **MCP server** (`src/maris3d/mcp/server.py`, stdio, standard library only): `build_scene`, `edit_scene`, `run_calls`, `scene_info`, `undo`, `look`. No tool accepts Blender code.
- **Plan first** (`copilot/plan.py`, `compile_plan.py`, `describe_parts.py`, `recipes.py`): with the planner adapter on the server, Auto asks the planner for a list of things and their places in words (never a number), a parts table gives the parts of each thing, the compiler turns words into metres and tool calls, the edit adapter makes each part, and a check reads every part back and corrects it. A sentence that moves a thing the scene has, or orders a finish, is done by code alone.
- **Update** (`update.py`): `MANIFEST.json` names the current file of each role, the program version it needs and the planner's own prompt and answer format; a new adapter is fetched without the base, and a release for a newer program is refused untouched.
- **Extras** (opt in): `extras/checks.py` (scene checklist, edit guard), `extras/planner` and `extras/recipes` (recipe, API or self plan chain; offline by default).

## Flows
1. Host model drives: the host's own model sends native calls to `run_calls`, or plain requests to `build_scene`; the copilot compiles and runs them.
2. Embedded: the copilot sits inside another Blender MCP (`executors/mcp_forward.py`).
3. Model inside (optional): our model runs on its own llama-server behind `build_scene` and `edit_scene`; adapter off to build, on to edit, the planner alone to plan.

## What the model builds, and what the harness builds

A full scene take (the Christmas street) is **943 rows: 202 model turns and 741 copilot steps**.
The model authors *shapes* — a room's furniture, a house design, a tree, a car. The harness authors
*arrangement*: placement, cloning down the street, materials, grouping, gables, floor planks, the
glow cascade, snow, and the camera. Those are exactly the things a 0.5B model keeps getting wrong,
so they are code, not prompts, and each one has a gate.

**Batching rule (measured, 9 Nov 2026):** a prompt may ask for at most ~6 objects. Six parts (a
whole chair) came back as 6 correct calls in 5.9 s; sixteen parts (a whole dining set) came back as
42 calls in a repetition loop, with colliding names. Chunking at six turns the same work from 210
model turns into 47.

## Safety
Face budget per object and per scene in the live add-on, 60 s per call, a fixed screenshot path chosen by the server, one persistent timer on the Blender main thread, a lock around the socket, lazy reconnect.
