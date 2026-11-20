**Install in one command** (no clone needed):

- macOS / Linux: `curl -fsSL https://raw.githubusercontent.com/slm4apps/maris3d/main/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/slm4apps/maris3d/main/install.ps1 | iex"`

Already on 0.2.x? Re-run the one-line install (or `pip install -U git+https://github.com/slm4apps/maris3d`) for the 0.2.2 app, then `maris3d update` for the 23 MB adapter.

**Maris3D SLM Blender 0.5B 0.2.2** has a new adapter on the same base. Changes:
- **More change words:** camera, light, text, retext, attach, aim, finish (bevel, subdivide, thicken, wire, mirror, array, taper, bend, twist) and scene (background colour, length, frame rate). `MARIS3D_KIT_WORDS=0` turns them off.
- **Exact adds are read by code:** "Add a cube named Path at -1, 0, 0 with a scale of 0.4, 2.0, 0.01" is built from the numbers as written. The 204 exact adds of the 0.1 demo scene: 203 built exactly (99.5 %).
- **Voice input:** a mic button next to the prompt, speech turned into text on your machine by whisper.cpp. Set it up with `maris3d install --voice`.
- **Undo by voice or text:** "undo", "go back" or "revert it".
- **Maris** behaves more like she lives in the scene, and **Follow Maris** (off by default) lets the view drift after her.

On held-out sets: plan things right 97.3 % (3,033 things in 716 sentences), parts pass the app's rules 99.0 % (1,268 names), talk replies right 96.1 % (152 turns), 0 invented things in 383 turns. All sets: [BENCHMARKS.md](https://github.com/slm4apps/maris3d/blob/main/docs/BENCHMARKS.md).

0.2.1 stays at tags [v0.2.1](https://github.com/slm4apps/maris3d/releases/tag/v0.2.1) / [v0.2.1.1](https://github.com/slm4apps/maris3d/releases/tag/v0.2.1.1) and in [slm4apps/Maris3D-Blender at v0.2.1](https://huggingface.co/slm4apps/Maris3D-Blender/tree/v0.2.1); 0.1 at [v0.1.2](https://github.com/slm4apps/maris3d/releases/tag/v0.1.2) and [v0.1.0 on Hugging Face](https://huggingface.co/slm4apps/Maris3D-Blender/tree/v0.1.0).

Model files: [slm4apps/Maris3D-Blender](https://huggingface.co/slm4apps/Maris3D-Blender). Details: [CHANGELOG.md](https://github.com/slm4apps/maris3d/blob/main/CHANGELOG.md).
