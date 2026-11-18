# Usage

> Status note, 12 Nov 2026: updated for **Maris3D-SLM-Blender-0.5B v0.1** (native Qwen tool calls, plan first): see [README.md](../README.md), [docs/ARCHITECTURE.md](ARCHITECTURE.md) and [release/STATUS.md](../release/STATUS.md).

One release, five model files, one prompt format. The files come from the Hugging Face repository
[slm4apps/Maris3D-Blender](https://huggingface.co/slm4apps/Maris3D-Blender) and are staged for review in `hf/Maris3D-Blender/`.

| File | Bytes | Role |
|---|---|---|
| `maris3d-slm-blender-0.5b-q8_0.gguf` | 531,068,000 | **The base of the product**, served with the two adapters below |
| `maris3d-slm-blender-0.5b-edit-lora-f16.gguf` | 5,881,344 | Edit adapter: off on a fresh prompt, on for a correction and for compiled parts |
| `maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf` | 5,881,248 | Planner adapter: one sentence -> a plan in words (plan first) |
| `maris3d-slm-blender-0.5b-edit-q8_0.gguf` | 531,067,872 | Single-file fallback for hosts without adapter support (edit LoRA merged; no plan first) |
| `maris3d-slm-blender-0.5b-q4_k_m.gguf` | 397,807,712 | Smaller build-only file (18.3% pass / 67.2% usable, measured) |

`MANIFEST.json` lists the current file of each role (base, edit, planner) with its sha256; `SHA256SUMS` lists every file.

Requirements: Python 3.9+, Blender (benchmarked on 5.2.2; 4.x is untested; `BLENDER_BIN` points at the executable), and a runtime that
speaks Qwen tool calls. Memory: 0.58 GB resident on an 8 GB Mac; about 0.6 s per answer, 1.3 s cold load. The repository code uses only
the Python standard library.

## 0. The short way: install, one sentence, update

```sh
maris3d install          # add-on into Blender, base + edit adapter + planner adapter, llama-server, self-test
maris3d serve start      # one server on port 9931: the base with both adapters loaded, none applied
maris3d serve status     # says which adapters are loaded
```

Open Blender, 3D View, sidebar tab **Maris3D Copilot**, leave the switch on **Auto**, type one
sentence and press **Run**:

```
A small train station: a platform, a station building behind the platform, a track in front of
the platform, a train on top of the track, two benches on the platform and four lamp posts in
front of the platform, close to it
```

With the planner loaded, Auto plans first: the planner writes the things and their places in
words, code turns them into exact instructions, the edit adapter makes each part, a check reads
every part back and corrects it. The panel line says how many parts the model made exactly and how
many were corrected. The words it knows, the sentences that were run and the limits are in
[PROMPTING-GUIDE.md](PROMPTING-GUIDE.md), section 0. **Build** and **Edit** force the model alone;
the **Plan** switch shows the plan and builds nothing. One request is one **Undo**.

A new adapter version does not cost a new download of the 530 MB base:

```sh
maris3d update                     # reads MANIFEST.json from the Hugging Face repository
maris3d update --from <folder>     # or from a folder that holds MANIFEST.json and the files
maris3d serve stop && maris3d serve start
```

`update` keeps every file that is already there with the right sha256, fetches what is new or
different, checks its sha256 before it takes its place, and removes the file it replaced only if
`update` itself had fetched it. A download with a wrong sha256 leaves the old file serving.

## 1. llama.cpp (llama-server)

The product (q8_0 base + edit adapter, one server; 27.2% pass / 75.6% usable):

```sh
llama-server -m maris3d-slm-blender-0.5b-q8_0.gguf --jinja -c 8192 --temp 0 --repeat-penalty 1.0 --port 8090 \
  --lora maris3d-slm-blender-0.5b-edit-lora-f16.gguf --lora maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf \
  --lora-init-without-apply
```

The planner adapter is optional on this line: without it the server builds and edits as scored, and plan first is off.
A plan request sets the planner to 1.0 and the edit adapter to 0; the two never run together. The add-on finds each
adapter by its file name (`planner` in the name; `planner-v3` tells it which planner prompt to send), not by its position.

Each request carries the adapter strength for that turn: `"lora": [{"id": 0, "scale": 0.0}]` on a fresh prompt (build
weights), `1.0` on a correction (edit weights). `maris3d serve start` runs this server, and the add-on sets the strength
itself. Strict-pass mode is the same server with `"scale": 0.7` on every request (23.9% pass / 68.9% usable).

Single-file fallback for hosts without adapter support (edit LoRA merged; 19.4% / 77.2%):

```sh
llama-server -m maris3d-slm-blender-0.5b-edit-q8_0.gguf --jinja -c 8192 --temp 0 --repeat-penalty 1.0 --port 8090
```

Keep the repeat penalty at 1.0: a tool call is repetition by design, and at 1.1 the model drops object names and can repeat
one call until the token limit.

Then POST OpenAI-style requests to `/v1/chat/completions` with `tools` set to the `TOOLS.json` from the release (26 Blender tools).
Your host runs each call in Blender, returns the result as a `tool` message, and loops; up to 20 calls per user turn is what it was
trained for. Rows are at most 2,048 tokens, but the 26-tool manifest plus a conversation can overflow 4,096: serve with 8,192.

The setup helper prints the command for your runtime and file:
`python3 -m maris3d.setup check`, `python3 -m maris3d.setup serve-command <model.gguf> [edit-lora.gguf]`,
`python3 -m maris3d.setup smoke`.

## 2. Ollama

Ollama cannot switch an adapter per request, so it serves the merged fallback file. Use the `Modelfile` that ships beside the
GGUFs (`FROM ./maris3d-slm-blender-0.5b-edit-q8_0.gguf`, temperature 0, `repeat_penalty 1.0`, `num_ctx 8192`, `num_predict 800`), then
`ollama create maris3d-slm-blender-0.5b -f Modelfile`. Ollama's own default repeat penalty is 1.1, and its OpenAI-compatible endpoint
(`/v1/chat/completions`) has no field to change it, so the value has to come from the Modelfile. The llama-server path is the
one the benchmark tables were measured with.

## 3. MCP server (`src/maris3d/mcp/`)

A stdio MCP server, Python standard library only: `python3 -m maris3d.mcp.server` (console script `maris3d-mcp`). Tools:
`build_scene`, `edit_scene`, `run_calls` (native calls handed over by a host model), `scene_info`, `undo`, `look`. `build_scene` is
the panel's Auto: with the planner on the server the sentence is planned first, and the reply says how many parts were built, exact
and corrected; `edit_scene` does moves by words and finishes by code and sends the rest to the edit model. It attaches to, or
launches, a Blender window with the live add-on (`src/maris3d/blender/live_server.py`, port 9877; `BLENDER_LIVE_PORT` to change).

The copilot can also sit inside another Blender MCP (`executors/mcp_forward.py`): the native calls are compiled to Python and sent
through that MCP's execute tool.

Optional extras (no extra packages): `extras/checks.py` (scene checklist, edit guard), `extras/planner` and `extras/recipes`
(offline recipe plans by default).

## Notes
- Greedy decoding (temperature 0, repeat_penalty 1.0) is what the model was trained and scored with.
- Generated code is untrusted: run it in a scratch Blender session, and keep the MCP/live ports on localhost.
- The model knows the 26 tools it was trained on; other tools are guessed.
