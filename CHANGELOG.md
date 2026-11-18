# Changelog

All notable changes. Release numbers are public versions (v0.1, v0.2 ...), kept as git tags and Hugging Face revisions.

## [0.2.1.1] - 2026-11-18
App only; the model files are unchanged (Hugging Face tag v0.2.1).
- **Windows installer fixed.** The one-line PowerShell install stopped before it made its private Python folder, and
  its last step passed the wrong arguments; both are fixed. The `maris3d` command now runs through a small
  `maris3d.cmd` and the signed `python.exe`, because Windows 11 Smart App Control blocks the unsigned launcher pip makes.
- **llama-server download fixed on every platform.** The install fetches one tested llama.cpp build (b12503) with its
  libraries, instead of the newest release, which no longer carries the program.
- When Windows blocks `llama-server.exe` or its libraries (Smart App Control runs only signed programs), `maris3d serve start` says so and
  points to Ollama.
- `python -m maris3d` works as the `maris3d` command.

## [0.2.1] - 2026-11-18
- **Same model, clean files.** The base and the adapter carry the 0.2.0 weights and give the same answers; the files now
  carry the Maris3D name and no metadata from the machine that built them. The adapter file is
  `maris3d-slm-blender-0.5b-v0.2.1-lora-f16.gguf`; `maris3d update` fetches both files again because their contents changed.
- **Identity.** The chat template's default system line, used only when a request has no system message of its own (the
  app always sends one), says the model is Maris, the Maris3D model by slm4apps. The Ollama `Modelfile` sets the same line.
- The 0.1.0 and 0.2.0 files on Hugging Face were rebuilt the same way at their tags; their sha256 values changed, the
  weights did not.
- Installer: no attempt to fetch the parts adapter, which 0.2 folded into the one adapter.
- The private-information scan reads GGUF metadata, wheels and large files; `scripts/gguf_clean.py` writes release
  metadata into a GGUF.

## [0.2.0] - 2026-11-18 (breaking change)
- **Maris3D SLM Blender 0.5B 0.2** (Hugging Face `slm4apps/Maris3D-Blender`): the same base file as 0.1 (`maris3d-slm-blender-0.5b-q8_0.gguf`, 531 MB) served with one adapter, `maris3d-slm-blender-0.5b-v0.2.0-lora-f16.gguf` (12 MB), which replaces 0.1's edit and planner adapters. 0.2 needs the 0.2 app; 0.1 stays at GitHub tag v0.1.1 and at revision `v0.1.0` of `slm4apps/Maris3D-Blender`.
- **Words, not numbers.** The model answers in plain words (things, counts, materials, relations, size words); the app's compiler writes the Blender tool calls and computes every size and position. 0.1 wrote tool calls with coordinates.
- **Plan, parts, edits, talk from one adapter.** On held-out sets: plan things right 97.3 % (3,033 things in 716 sentences), relation 97.0 %, placed-by 95.8 %; a new thing's parts parse 99.9 % (1,268 names) and pass the app's rules 95.7 %; word edits 90.4 % (726 requests); talk replies right 95.8 % (118 turns), 0 invented things in 383 turns.
- **Animation** is written by the app's code from the sentence (spin, bounce, move, rise, grow, shrink, swing, orbit, pulse, colour change), no model.
- An edit answer that changes nothing no longer ends the turn silently.
- Serving: temperature 0, context 8,192, repeat penalty 1.05; `llama-server --lora ... --lora-init-without-apply --jinja -c 8192`, or Ollama through the `Modelfile` (`maris3d-slm-blender-0.5b`).
- Not in 0.2: lights, cameras and text from a plain request (the model builds a look-alike object or does nothing; an animation that names a camera or a light gets a real one). A follow-up that adds a new thing to a built scene often does nothing yet.
- The 0.1 demo scene, its 204 requests replayed through the 0.2 app: 188 built exactly (92.2 %).
- Names: the Ollama model keeps 0.1's name, `maris3d-slm-blender-0.5b` (`:latest`, and `:0.2.0` for this version);
  adapter files carry their release version (`maris3d-slm-blender-0.5b-v0.2.0-lora-f16.gguf`). On Hugging Face, `main` is the
  latest release and each version is a tag.
- Kept from 0.1.1 and carried into 0.2: downloads without a certificate store, the one-line installers, new things stand on the
  ground (z = 0 or higher), `maris3d --version`, `maris3d-setup check` finds the installed llama-server, release checks on a fresh
  clone say PENDING for the weights. `maris3d install` reads the files of tag `v0.2.0`; `maris3d update` reads the newest release
  and refuses one that needs a newer app.

## [0.1.1] - 2026-11-15
- Installer and `maris3d update`: downloads work on a Python without its own certificate store (the python.org
  installer for macOS before its "Install Certificates" step): on a certificate error the download is tried once more
  with the system CA bundle, still verified. Same model files as 0.1.0.
- One-line install: `install.sh` (macOS, Linux) and `install.ps1` (Windows) make a private Python venv, install
  the package from the GitHub release and run `maris3d install`. Nobody needs to clone the repository.
- Edit mode keeps to what the sentence names: "Make Band red." had come back as paint-everything plus moves of the camera,
  the lamps and the car. When the sentence names things the scene has, "all" now means those things (or the parts under
  them) and edits aimed at anything else are not run; a sentence that names nothing keeps the camera and lights as they are.
- Plan first no longer sinks a new scene into the floor: Blender's default cube (bottom at -1 m) was taken as the ground.
  Things now stand on z = 0 or higher.
- `scripts/release_check.py` on a fresh clone: the weights are on Hugging Face, not in git, so their checks now say PENDING
  instead of FAIL. `maris3d-setup check` finds the llama-server that `maris3d install` unpacked. New: `maris3d --version`.

## [0.1.0] - 2026-11-12
- First public release: **Maris3D SLM Blender 0.5B**, a Qwen2.5-Coder-0.5B-Instruct fine-tune that builds and edits Blender scenes through native Qwen tool calls on a fixed 26-tool Blender set.
- Five GGUF files (Hugging Face `slm4apps/Maris3D-Blender`, revision `v0.1.0`): `maris3d-slm-blender-0.5b-q8_0.gguf` (the base) served with `maris3d-slm-blender-0.5b-edit-lora-f16.gguf` (5.6 MB edit adapter: scale 0 on a fresh prompt, 1.0 on a correction) is the product; `maris3d-slm-blender-0.5b-edit-q8_0.gguf` (edit LoRA merged) is the single-file fallback for hosts without adapter support; `maris3d-slm-blender-0.5b-q4_k_m.gguf` is a smaller build file.
- Product (base + adapter, router picks the adapter per request) on the 180-request yardstick, one run: 28.3% fully correct, 88.9% usable (51 pass / 109 partial / 20 fail; 3 requests hit a Blender error). Merged single-file fallback: 19.4% pass, 77.2% usable. Strict mode (adapter at 0.7): 23.9% pass, 68.9% usable.
- **Plan first.** A planner adapter (`maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf`, 5.6 MB) is loaded beside the base and the edit adapter. In the add-on's Auto and in the MCP tool `build_scene`, one sentence that names things and where they stand is planned in words, compiled by code into exact instructions for every part, made part by part by the edit adapter, read back from Blender and corrected; the panel says how many parts were exact and how many corrected. 40 things by name; moves by words ("move the snowman to the left of the tree") and finishes (smooth, one skin, hollow) are done by code. Planner on 300 held-out sentences: relation right 98.6%, placed-by right 87.3% (98.5% on trained names). The edit adapter copies a compiled part exactly in 283 of 448 cases; the check corrects the rest.
- `maris3d update`: fetches a new adapter version by `MANIFEST.json`, sha256-checked, without a new download of the base; a failed download leaves the old file serving.
- `demo/`: the train station built from one sentence and the Christmas street, each as `.blend`, `.glb` and `.fbx`, the street also one file per object.
- Licence: Apache-2.0 for code and weights (the Qwen base is Apache-2.0); Blender-side files that import `bpy` stay GPL-3.0-or-later.

## Earlier development line, superseded by 0.1.0 and never released
- Repository prepared locally (layout, licensing research, Hugging Face staging, promotion gates, private-info scan). Nothing pushed.
- Earlier development models in the old JSON tool format, measured on the previous 206-prompt benchmark (not comparable with the 180-request yardstick above): Maris3D-SLM-Blender-1.5B at 149/206 (72.3%) and Maris3D SLM Blender 0.5B at 123/206 (59.7%). See `release/CURRENT.json`.
