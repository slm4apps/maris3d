# Release status

Date: 2026-11-07, product line updated 2026-11-12 (planner adapter, plan first, `maris3d update`). The v0.1.0 content is staged locally; the Hugging Face repo exists and is **private**; the GitHub repository is not created. Nothing is public until the open items below are closed.

## Decided (7 Nov 2026)
- Public name: **Maris3D-SLM-Blender-0.5B** (v0.1.0). The edit LoRA ships in v0.1 as a 5.6 MB adapter beside the q8_0 base (the product); a merged single file is the fallback.
- Hugging Face org: **slm4apps**; repo `slm4apps/Maris3D-Blender` (staged in `hf/Maris3D-Blender/`, five GGUFs and `MANIFEST.json`).
- Licence: **Apache-2.0** for code and weights (the Qwen base is Apache-2.0); Blender-side files that import `bpy` stay GPL-3.0-or-later. CC-BY is not applied.

## What exists
- Model: Maris3D-SLM-Blender-0.5B (0.5B; product = q8_0 base + edit LoRA adapter f16, plus the edit-merged q8_0 fallback and q4_k_m). Product on the 180 frozen requests: 49 pass / 87 partial / 44 fail (27.2% pass, 75.6% usable); merged fallback 35 / 104 / 41 (19.4%, 77.2%); strict mode (base + LoRA @0.7) 23.9% pass, 68.9% usable. See `CURRENT.json`.
- Plan first: planner adapter v3.1 (`maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf`) beside the base and the edit adapter; Auto in the add-on and `build_scene` over MCP plan, compile, build and check. Planner on 300 held-out sentences: relation 98.6%, placed-by 87.3% (98.5% on trained names).
- Detachable copilot (`src/maris3d/copilot`, `runtimes`, `executors`): native tool-call loop, per-request adapter scale, undo by replay, runs against our own Blender window or inside another Blender MCP.
- MCP server (`src/maris3d/mcp/server.py`): `build_scene`, `edit_scene`, `run_calls`, `scene_info`, `undo`, `look`. Checked end to end against a live Blender window with native calls.
- Extras (opt in, no packages): `extras/checks.py`, `extras/planner`, `extras/recipes`.
- Setup helpers: `python3 -m maris3d.setup check|serve-command|smoke`.

## Open before the public push
- Hosting contact details (which account e-mail and contact address the public pages use).
- Teacher-data terms: read the DeepSeek-V4.1-Flash licence and the host terms; the weights depend on them ([LICENSING.md](../docs/LICENSING.md)).
- Prompt licensing: the 165 AI-written benchmark prompts (authorship/provenance review open).
- Blender trademark naming review: the Foundation's trademark policy still needs reading ([LICENSING.md](../docs/LICENSING.md) section 5).
- Author line: the public author/commit identity to show on the release pages.
- The per-size promotion and model-card scripts (`scripts/promote.py`, `scripts/gen_model_cards.py`) still target the old JSON models; their tests are skipped until they are rewritten for the single-model `CURRENT.json`.
- `MODEL_CARD.md` and the promotion/model-card scripts still target the earlier JSON-format models (tracked debt; see above). `docs/PROMPT-FORMAT.md`, `EVALUATION.md` and `DATA-CARD.md` are kept as earlier-line reference pages, marked by status banners; the previous-generation figures (`ladder`, `pass-by-level`, `failure-categories`) remain from that line. `TECHNICAL-REPORT.md`, `docs/USAGE.md`, `FAQ.md`, `BENCHMARKS.md`, `SAFETY-AND-LIMITATIONS.md`, `LICENSING.md`, `PUBLIC-PRIVATE.md`, `release-v0.1.md` and the top-level release files are retargeted to Maris3D-SLM-Blender-0.5B.
