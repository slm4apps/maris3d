# Usage

Maris3D 0.2 is two model files from [slm4apps/Maris3D-Blender](https://huggingface.co/slm4apps/Maris3D-Blender) plus the Maris3D app.

| File | Size | Role |
|---|---|---|
| `maris3d-slm-blender-0.5b-q8_0.gguf` | 531 MB | The base (Qwen2.5-Coder-0.5B-Instruct fine-tune), the same file as 0.1 |
| `maris3d-slm-blender-0.5b-v0.2.2-lora-f16.gguf` | 23 MB | One adapter: planning, the parts of a new thing, word edits and talk |

`MANIFEST.json` lists the current file of each role with its sha256, `SHA256SUMS` every file. 0.2 needs the 0.2 app; the 0.1 files stay at the `v0.1.0` revision of the same repository and the 0.1 app at the GitHub tag `v0.1.2`.

Requirements: Python 3.9+ and Blender 4.2 or newer (5.2 LTS verified; `BLENDER_BIN` points at the executable). The app uses only the Python
standard library.

## The short way

```sh
maris3d install          # the add-on into Blender, the base and the adapter (sha256-checked), a self-test
maris3d install --voice  # also voice input: whisper.cpp and a 60 MB speech model (sha256-checked)
maris3d install --voice --voice-lang multi  # voice in many languages (detected as you speak); default en
maris3d install --vision # also picture input: a 550 MB vision model (SmolVLM-500M, sha256-checked)
maris3d serve start      # one llama-server on port 9931: the base with the adapter loaded
maris3d serve status     # what is running
maris3d doctor           # checks Blender, the add-on, the server and the settings
```

In Blender open the 3D View, the sidebar tab **Maris3D Copilot**, type a sentence and press **Run**:

```
A small train station: a platform, a station building behind the platform, a track in front of
the platform, a train on top of the track, two benches on the platform and four lamp posts in
front of the platform, close to it
```

The model answers in words (which things, where they stand); the app's compiler turns the words into Blender tool calls and builds the scene,
reads it back and checks it. Later sentences change the scene ("make the bench red", "move the lamp next to the sofa") or ask about it
("how many chairs are there?"). One request is one **Undo**. With voice input set up, the mic button next to the prompt
records what you say (press it again to stop); whisper.cpp writes it down on your machine and the words run as the prompt. What you can say is in [PROMPTING-GUIDE.md](PROMPTING-GUIDE.md).

A new adapter does not cost a new download of the 531 MB base:

```sh
maris3d update                     # reads MANIFEST.json from the Hugging Face repository
maris3d update --from <folder>     # or from a folder that holds MANIFEST.json and the files
maris3d serve stop && maris3d serve start
```

`update` keeps every file that is already there with the right sha256, checks a download's sha256 before it takes its place, and a wrong
sha256 leaves the old file serving. A release that needs a newer app is refused untouched. `maris3d build-zip` builds the add-on zip.

## llama.cpp by hand

```sh
llama-server -m maris3d-slm-blender-0.5b-q8_0.gguf --lora maris3d-slm-blender-0.5b-v0.2.2-lora-f16.gguf --lora-init-without-apply \
  --jinja -c 8192 --temp 0 --port 9931
```

Use temperature 0, a context of 8,192 and a repeat penalty of 1.05; the app sends the adapter strength and the repeat penalty with each request. A
different repeat penalty changes the answers, so use the app's value if you call the server yourself. The app finds a running llama-server on
port 9931 or 8080, or Ollama.

## Ollama

The `Modelfile` in the Hugging Face repository loads the base and the adapter as the entry `maris3d-slm-blender-0.5b`:

```sh
ollama create maris3d-slm-blender-0.5b -f Modelfile
```

It sets temperature 0, repeat penalty 1.05 and a context of 8,192. Ollama's own default repeat penalty is 1.1, which is not what the adapter was
measured with, so keep the Modelfile's value. Then pick Ollama in the app's settings.

## MCP server

A stdio MCP server, Python standard library only: `python3 -m maris3d.mcp.server` (console script `maris3d-mcp`). Tools: `scene_request` (a request in
words, the same as the panel's **Run**), `run_calls` (tool calls from a host model, at most 20), `scene_info`, `undo`, `look` (a viewport
screenshot). It attaches to, or launches, a Blender window with the live add-on (port 9877; `BLENDER_LIVE_PORT` to change). No tool accepts
Blender code.

## Notes
- Generated scenes run as Python inside Blender with your permissions: use a scratch session and keep the MCP and live ports on localhost.
- The model answers in words, so it does not know your Blender's API; the compiler targets Blender 5.2.
