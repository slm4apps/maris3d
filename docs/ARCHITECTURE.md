# Architecture (0.2)

## Pieces
- **Model**: Qwen2.5-Coder-0.5B-Instruct fine-tuned (`maris3d-slm-blender-0.5b-q8_0.gguf`, 531 MB) with ONE LoRA adapter (`maris3d-slm-blender-0.5b-v0.2.0-lora-f16.gguf`, 12 MB). The adapter is
  switched per request. The model answers in a small word language: which things, how many, what they are made of, where they stand, how a thing's parts fit together, what a change does,
  or a reply to a question. It never writes a number, a tool call or Blender code.
- **Copilot** (`src/maris3d/copilot`): no dependencies, no server, no Blender import. It asks the model for words, then code does the rest: `compile_plan.py` and `place.py` turn the words
  into metres and tool calls, `describe_parts.py` fits the parts of a thing, `edit_words.py` and `apply_change.py` turn a word edit into a change and apply it, `animate.py` writes keyframes for a
  motion sentence, and `describe_scene.py` gives the model the scene in words. After a build the scene is read back and checked. Undo resets the scene and replays the accepted batches.
- **Runtimes** (`src/maris3d/runtimes`): llama-server (adapter strength and repeat penalty sent with each request), Ollama (the `maris3d-slm-blender-0.5b` entry), any OpenAI-style server. Detection only looks;
  it never starts or downloads anything.
- **Executors** (`src/maris3d/executors`): our own Blender window over a local socket (`blender/live_server.py`), or inside another Blender MCP, where the compiled calls are sent through that MCP's
  execute tool.
- **MCP server** (`src/maris3d/mcp/server.py`, stdio, standard library only): `scene_request`, `run_calls`, `scene_info`, `undo`, `look`. No tool accepts Blender code.
- **Update** (`update.py`): `MANIFEST.json` names the current file of each role and the app version it needs; a new adapter is fetched without the base, and a release for a newer app is refused
  untouched.
- **Host-free core**: `copilot/`, `runtimes/`, `engine/` and `update.py` import no `bpy`. The Blender-only pieces are `dsl/tools.py`, `executors/`, `blender/`, `addon/` and `mcp/blender_mcp.py`.

## Flow of one request
1. You type a sentence; the app sends it, with the scene in words, to the model.
2. The model answers in words from closed lists (`copilot/vocabulary.py`).
3. The compiler turns the words into Blender tool calls and the executor runs them.
4. The scene is read back and checked; the panel says what was built or changed.

Lights, cameras and text have no words in the 0.2 vocabulary yet; such a request gets a look-alike object (a lamp, a sign with a blank panel) or nothing. The animation code adds a real camera or light when an animation names one.

## Safety
Face budget per object and per scene in the live add-on, a time limit per call, a fixed screenshot path chosen by the server, one persistent timer on the Blender main thread, a lock around the socket, lazy reconnect.
