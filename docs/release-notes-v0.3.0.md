**Install in one command** (no clone needed):

- macOS / Linux: `curl -fsSL https://raw.githubusercontent.com/slm4apps/maris3d/main/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/slm4apps/maris3d/main/install.ps1 | iex"`

Already on 0.2.x? Re-run the one-line install (or `pip install -U git+https://github.com/slm4apps/maris3d`) for the 0.3.0 app. The model files are the same as 0.2.2, so there is nothing new to download for the model.

**Maris3D 0.3.0** is a new app on the 0.2.2 model. Changes:
- **Picture input (optional):** press the picture button, pick a picture; a small vision model (SmolVLM 500M, downloaded from Hugging Face, not shipped) answers a few short questions about it on your machine (what it is, which objects, the main colour), then Maris3D builds a short request made from the answers. `maris3d install --vision`.
- **Voice in many languages:** English only (the default) or a many-language speech model that detects the language as you speak. `maris3d install --voice --voice-lang multi`.
- **The one-line installers ask nothing** and set up voice and picture input, put `maris3d` on your PATH and start the server (`MARIS3D_ASK=1` to be asked).
- **Maris** keeps moving after an error in one of her moves, stays person-sized and on the ground, and her greetings fade by themselves.

On SLM4Apps SceneBench 1.0 (4,269 items in 10 areas): 65.7 overall; camera, light, text and finish 96.6 %, talk 96.4 %, exact adds built exactly 99.5 % (203 of 204), picture to scene 66.7 % (24 reference pictures). All areas: [BENCHMARKS.md](https://github.com/slm4apps/maris3d/blob/main/docs/BENCHMARKS.md).

0.2.2 stays at tag [v0.2.2](https://github.com/slm4apps/maris3d/releases/tag/v0.2.2) and in [slm4apps/Maris3D-Blender at v0.2.2](https://huggingface.co/slm4apps/Maris3D-Blender/tree/v0.2.2); 0.1 at [v0.1.2](https://github.com/slm4apps/maris3d/releases/tag/v0.1.2) and [v0.1.0 on Hugging Face](https://huggingface.co/slm4apps/Maris3D-Blender/tree/v0.1.0).

Model files: [slm4apps/Maris3D-Blender](https://huggingface.co/slm4apps/Maris3D-Blender). Details: [CHANGELOG.md](https://github.com/slm4apps/maris3d/blob/main/CHANGELOG.md).
