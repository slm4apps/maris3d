# Data card (training data; not released)

> Status, 7 Nov 2026: this page describes the earlier JSON-format models. v0.1 (Maris3D-SLM-Blender-0.5B) speaks native Qwen tool calls; see [README.md](../README.md) and [hf/Maris3D-Blender/README.md](../hf/Maris3D-Blender/README.md).

Status: **the dataset is not published** in this release. The terms of the teacher models that wrote the rows were checked ([LICENSING.md](LICENSING.md), section 3). This card describes how the data was made so results can be judged; it covers the data factory as a whole, both the earlier rounds and the rounds used by v0.1.

## What a row is
A pair (user request, assistant answer) where the answer is tool calls that build or edit a Blender scene (see [DSL.md](DSL.md)). For the earlier models the answer was a JSON document under the system prompt in [PROMPT-FORMAT.md](PROMPT-FORMAT.md); for v0.1 it is text-only tool-call conversations in the native Qwen format. No images, no code from Blender itself.
Single turn, empty starting scene.

## How rows were made
1. **Prompts**: topic and level lists expanded by a teacher model into varied requests (levels 1 to 4 as in the benchmark; round 2 added a level of requests that need the extra tools: text, constraints, shape keys, geometry nodes, mesh edits, duplicates, object settings, applied transforms).
2. **Teacher answers**: a large hosted model wrote the tool-call JSON for each prompt. Round 1: 3,798 kept rows by one model and 18 by a second; round 2: 3,988 and 12.
3. **Verification in headless Blender**: every answer was compiled and run (`src/maris3d/blender/scene_dump.py`), then the prompt's scene check was evaluated (`train/verify_rows.py`). Only rows whose script ran and whose check held were kept.
4. **Decontamination** against the benchmark: near-duplicate prompts (token-set similarity) and the same tool-call signature were dropped; duplicates inside the data were dropped.
5. **Quota per level** so no level dominates.

## Numbers (from the private data statistics files)
<!-- source: round-1 and round-2 stats.json of the private data factory (not published) -->

| | Round 1 | Round 2 |
|---|---|---|
| Raw prompts generated | 4,500 | 4,730 |
| Dropped: near-duplicate of a benchmark prompt / same signature / duplicate / malformed | 66 / 3 / 113 / 46 | 23 / 9 / 206 / 37 |
| Kept after decontamination | 4,272 | 4,455 |
| Rows used for training | 3,816 | 4,000 |
| Spare verified rows / rejected rows | 302 / 154 | 246 / 209 |
| Verification pass rate per level | L1 96.3%, L2 94.8%, L3 96.8%, L4 97.6% | L1 98.2%, L2 97.4%, L3 93.9%, L4 97.6%, extra-tool level 89.2% |
| Rows using the 8 added tools | 0 | 667 |

The earlier JSON-format models were trained on the first two rounds: 7,610 rows plus a 200-row validation split. Two later rounds (11,471 and about 4,000 more verified rows by a third teacher) exist; which rounds trained the v0.1 model is tracked in the private workspace, not in this card.

## Known limitations of the data
- Written by language models, not by Blender artists: wording is more regular than real users'. A small test on real marketplace listing text (3 items) failed on the earlier 0.5B model before it produced any geometry (it emits empties); see the earlier-line observations in [SAFETY-AND-LIMITATIONS.md](SAFETY-AND-LIMITATIONS.md).
- A passing check means the scene satisfies the requested counts, sizes and properties, not that it looks good.
- Verified against Blender 5.2.2 only.
- Prompts are English.
- The checks were written by the same people who wrote the benchmark; leakage from prompt wording is possible even after near-duplicate removal.

## Personal data
No personal data is intended in the rows (they are synthetic requests). A final scan for e-mail addresses, paths and names will run before any release of the data.

## Release conditions
The rows are not part of this release. The repository ships under Apache-2.0 ([LICENSING.md](LICENSING.md)). `train/verify_rows.py` and `train/make_mlx.py` let others rebuild a dataset from their own teacher.
