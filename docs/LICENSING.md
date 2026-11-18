# Licensing: research, table and decisions

Status, 15 Nov 2026: **all licence questions for v0.1 are settled** (Apache-2.0 for code, weights and docs together; the Blender `bpy` files are GPL-3.0-or-later; CC-BY is not applied; the teacher terms, the benchmark prompts and the name were reviewed on 12-14 Nov 2026). Nothing here is legal advice. Every statement says what was read and what was not.
Evidence read locally (no network): the licence files that ship with the base models in the local Ollama library
(`ollama show qwen2.5-coder:0.5b|1.5b|3b --license`), the llama.cpp `LICENSE` of the checkout used for conversion, the
package metadata of mlx-lm, the licence set shipped with Blender 5.2.2, and the private usage log of the teacher calls
(model names per data round only; no costs are published).

## 1. Base models

| Item | What was read | SPDX | What it requires of us |
|---|---|---|---|
| Qwen2.5-Coder-0.5B-Instruct | licence file of the library model `qwen2.5-coder:0.5b` (11,344 bytes, header "Apache License Version 2.0", "Copyright 2024 Alibaba Cloud") | Apache-2.0 | Give recipients a copy of the licence; keep copyright and attribution notices; say that files were changed; keep any NOTICE content (none found in the file read); trademarks not granted |
| Qwen2.5-Coder-1.5B-Instruct | licence file of `qwen2.5-coder:1.5b`, byte-identical to the 0.5B file | Apache-2.0 | same |
| Qwen2.5-Coder-3B (not used) | licence file of `qwen2.5-coder:3b` is the **Qwen Research License Agreement** (not Apache) | other | **Do not release a 3B size without reading it.** The v0.1 release is 0.5B only |

The Hugging Face card of Qwen2.5-Coder-0.5B-Instruct says `license: apache-2.0` (read 12 Nov 2026). The 1.5B card was not read; no 1.5B model is released.

Weights decision (a): a LoRA fine-tune merged into an Apache-2.0 base is a derivative work. Apache-2.0 allows relicensing
our modifications under Apache-2.0 provided the notices above are kept. `NOTICE` and `LICENSES/Qwen2.5-Coder-Apache-2.0.txt` do that.
The training data terms (section 3) do not restrict this.

## 2. Tooling

| Tool | Role | Licence (read) | Obligation |
|---|---|---|---|
| llama.cpp / ggml | GGUF conversion (`convert_hf_to_gguf.py`), inference | MIT, "Copyright (c) 2023-2026 The ggml authors" (checkout `LICENSE`) | None for GGUF files made with it; nothing of it is redistributed here |
| mlx-lm | LoRA training and merge | MIT (package metadata) | none |
| Ollama | optional runtime | MIT | none (not redistributed) |
| Blender 5.2.2 | scene engine for evaluation | GPL-3.0-or-later (licence set inside the app) | see add-on split below |

## 3. Training data: provider and terms per source

Data rounds and teachers, read from the private usage log (not from memory). The terms of every teacher and host below were reviewed by the maintainer on 12 Nov 2026 and allow releasing models trained on their outputs.

| Source | Role | Provider and model | Terms that matter | Status |
|---|---|---|---|---|
| Round 1 prompts and tool calls | training data | DeepSeek-V4.1-Flash, plus gpt-oss-120b for 18 rows; both through a hosted European inference API | model licences and the host's terms on outputs | **ok** (reviewed 12 Nov 2026) |
| Round 2 prompts and tool calls | training data | same as round 1 | same | **ok** (reviewed 12 Nov 2026) |
| Round 3 | training data for later candidates | GLM-5.3 through the same host | licence of GLM-5.3 and the host terms | **ok** (reviewed 12 Nov 2026) |
| Round 4 | training data for later candidates | GLM-5.3 | same | **ok** (reviewed 12 Nov 2026) |
| Azure OpenAI deployments | other experiments only | OpenAI models via Azure OpenAI | OpenAI and Microsoft terms | **not used** in any released data or weights |
| Verification | all rows | our own headless Blender run and our own scene checks | none | **ok** |
| Benchmark prompts b001 to b041 | not training data | written by the pipeline author | none | **ok** |
| Benchmark prompts b042 to b206 | not training data | 165 prompts written by an AI agent | that provider's output terms | **ok** (reviewed; all 206 prompts are published) |
| Third-party company or customer data | not used | not used | none | **ok** |

No training data is published. The 206 benchmark prompts are published with the evaluation code.

## 4. The Blender add-on and GPL

The add-on and scene scripts (`src/maris3d/blender/`: `scene_dump.py`, `render_scene.py`, `live_server.py`) import `bpy`.
Treat them as part of a GPL-3.0-or-later work. Everything else stays Apache-2.0. Apache-2.0 is one-way compatible with GPLv3, so
the GPL files can sit in the same repository and the same wheel. The Apache-2.0 modules start Blender as a separate process
(`subprocess`, socket, JSON) and generate Python text; they do not import `bpy`. The weights are data, not Blender code, and stay
Apache-2.0. `LICENSES/README.md` shows the folder map and every file has an SPDX header.

## 5. The name and trademark

"Blender" is a registered trademark of the Blender Foundation. The Foundation asks third parties not to use "Blender" as
their product name; descriptive use that says what a product works with is fine when it does not suggest endorsement.
The product is therefore named **Maris3D**, and "SLM for Blender" / `slm-blender` only describes what the model is for (in the
model and file names and the tagline). The repo carries the not-affiliated disclaimer in `README.md`, `NOTICE` and the model
card, uses no Blender logo or artwork, and claims no endorsement. Version numbers live in release tags, not in names.

## Decisions

1. **Licence: the repository ships under Apache-2.0**: code, weights and docs together. The Blender add-on and `bpy` scripts stay **GPL-3.0-or-later**. CC-BY is **not applied** anywhere in this repository.
2. **Hosting:** Hugging Face organisation `slm4apps`, model repo `slm4apps/Maris3D-Blender` (versions are git tags, v0.1 is tag `v0.1.0`); code at https://github.com/slm4apps/maris3d .
3. **Training data** is not published. The teacher and host terms were reviewed and allow releasing the weights.
4. **Benchmark:** all 206 prompts are published.
5. **Name:** Maris3D; "Blender" is used only descriptively (section 5).
6. **Azure OpenAI outputs** are in no released data or weights.
7. **3B size:** not released (Qwen Research License).
