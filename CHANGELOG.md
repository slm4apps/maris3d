# Changelog

All notable changes. Release numbers are public versions (v0.1, v0.2 ...), kept as git tags and Hugging Face revisions.

## [0.1.2] - 2026-11-18
- The 0.1 code as released in 0.1.1, with maintainers' working notes taken out of comments and docs, and the
  maintainer-only release scripts left out. The app works as in 0.1.1 with the same 0.1 model
  (Hugging Face tag v0.1.0).

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
- First public release: **Maris3D-SLM-Blender-0.5B**, a Qwen2.5-Coder-0.5B-Instruct fine-tune that builds and edits Blender scenes through native Qwen tool calls on a fixed 26-tool Blender set.
- Five GGUF files (Hugging Face `slm4apps/Maris3D-Blender`): `maris3d-slm-blender-0.5b-q8_0.gguf` (the base) served with `maris3d-slm-blender-0.5b-edit-lora-f16.gguf` (5.6 MB edit adapter: scale 0 on a fresh prompt, 1.0 on a correction) is the product; `maris3d-slm-blender-0.5b-edit-q8_0.gguf` (edit LoRA merged) is the single-file fallback for hosts without adapter support; `maris3d-slm-blender-0.5b-q4_k_m.gguf` is a smaller build file.
- Product (base + adapter) on the 180-request yardstick: 27.2% fully correct, 75.6% usable (build half 24.0 / 73.3 on 150 rows, edit half 43.3 / 86.7 on 30 rows). Merged single-file fallback: 19.4% pass, 77.2% usable. Strict mode (adapter at 0.7): 23.9% pass, 68.9% usable.
- **Plan first.** A planner adapter (`maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf`, 5.6 MB) is loaded beside the base and the edit adapter. In the add-on's Auto and in the MCP tool `build_scene`, one sentence that names things and where they stand is planned in words, compiled by code into exact instructions for every part, made part by part by the edit adapter, read back from Blender and corrected; the panel says how many parts were exact and how many corrected. 40 things by name; moves by words ("move the snowman to the left of the tree") and finishes (smooth, one skin, hollow) are done by code. Planner on 300 held-out sentences: relation right 98.6%, placed-by right 87.3% (98.5% on trained names). The edit adapter copies a compiled part exactly in 283 of 448 cases; the check corrects the rest.
- `maris3d update`: fetches a new adapter version by `MANIFEST.json`, sha256-checked, without a new download of the base; a failed download leaves the old file serving.
- `demo/`: the train station built from one sentence and the Christmas street, each as `.blend`, `.glb` and `.fbx`, the street also one file per object.
- Licence: Apache-2.0 for code and weights (the Qwen base is Apache-2.0); Blender-side files that import `bpy` stay GPL-3.0-or-later.

## [0.2.0] - in development (breaking change)
- Compiled parts go straight to Blender; no model copies them. One planner writes the outline and the parts of a thing; the built-in parts table goes away. The build / edit model stays for the tools the compiler has no words for and as a fallback switch. 0.2 does not ship until it reproduces the 0.1 demo.

## Earlier development line, superseded by 0.1.0 and never released
- Repository prepared locally (layout, licensing research, Hugging Face staging, promotion gates, private-info scan). Nothing pushed.
- Earlier development models in the old JSON tool format, measured on the previous 206-prompt benchmark (not comparable with the 180-request yardstick above): Maris3D-SLM-Blender-1.5B at 149/206 (72.3%) and Maris3D-SLM-Blender-0.5B at 123/206 (59.7%). See `release/CURRENT.json`.
