# Licences in this repository

Every file carries (or inherits from its folder) one SPDX identifier. The decision is made: the repository ships under Apache-2.0 —
code, weights and docs together (see [docs/LICENSING.md](../docs/LICENSING.md)). CC-BY is not applied.

| Part | Where | SPDX | Why |
|---|---|---|---|
| Code: DSL, checker, runtime, MCP server, bridge, eval runner, training scripts, tests | `src/maris3d/` (except `blender/`), `eval/maris3d_eval/`, `train/`, `scripts/`, `tests/` | `Apache-2.0` | Matches the base models; patent grant; permissive |
| Blender-side code (imports `bpy`, runs inside Blender) | `src/maris3d/blender/` | `GPL-3.0-or-later` | Blender is GPL-3.0-or-later; code that imports its API is treated as part of a GPL work. Apache-2.0 code may be combined into a GPLv3 work (one-way compatible), so the two live side by side. The Apache-2.0 code only starts Blender as a separate process and talks to it over a socket or stdout/JSON |
| Model weights (merged safetensors, GGUF) | Hugging Face repos, staged in `hf/` | `Apache-2.0` | Fine-tuned derivatives of Apache-2.0 base models; attribution in `NOTICE`. The training-data terms were reviewed (LICENSING.md section 3) |
| Benchmark prompts and checks | `eval/benchmark/` | `Apache-2.0` (part of the repository licence) | All 206 prompts are published (LICENSING.md section 3) |
| Documentation and figures | `docs/`, `*.md` | `Apache-2.0` (part of the repository licence; code snippets likewise) | |
| Training data | not published | none | Teacher-written; not part of the release |

Texts: `Apache-2.0.txt`, `GPL-3.0-or-later.txt` (copied from the licence set shipped with Blender 5.2.2),
`Qwen2.5-Coder-Apache-2.0.txt` (the base models' own licence file).
