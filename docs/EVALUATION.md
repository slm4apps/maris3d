# Evaluation guide

> Status, 7 Nov 2026: this page describes the earlier JSON-format models. v0.1 (Maris3D-SLM-Blender-0.5B) speaks native Qwen tool calls; see [README.md](../README.md) and [hf/Maris3D-Blender/README.md](../hf/Maris3D-Blender/README.md).

The current v0.1 numbers (180-request yardstick, four variants, native tool calls in a real agent loop) are in [BENCHMARKS.md](BENCHMARKS.md); everything below describes the earlier 206-prompt setup and its runner.

## What is measured

206 prompts (`eval/benchmark/prompts.jsonl`, sha256 recorded in every result file), four levels: L1 single object (48 prompts), L2 several objects (58), L3 materials, modifiers, constraints (51), L4 multi-step scenes and animation (49).
Each prompt has a machine check (`check` field, evaluated by `maris3d.engine.checks`): object counts, bounding boxes, positions, materials, modifiers, animation data and so on.

- **Run %**: the compiled script executed in headless Blender without error.
- **Pass %**: the scene check held (the headline number).
- Also recorded: tok/s, median time to first token, deprecated-API hits (patterns for removed Blender APIs).

Gate used for promotion in the earlier line: run at least 80% and pass at least 60%. The v0.1 gate is different: beat the 21.7% baseline (base alone, q8_0) by 5 points — 26.7% pass on the 180-request yardstick ([ROADMAP.md](../ROADMAP.md)).

## Run it

```sh
export BLENDER_BIN=/path/to/blender              # 5.2.2 was used
# GGUF through llama-cpp-python (grammar-constrained, the reference setup)
python3 eval/maris3d_eval/run_eval.py --model maris3d-slm-blender-1.5b-Q8_0.gguf --backend llama --out results/run.json
# Ollama (JSON mode; set OLLAMA_FORMAT=schema|json|none to change the constraint)
python3 eval/maris3d_eval/run_eval.py --model maris3d-slm-blender-1.5b --backend ollama --out results/run.json
# retry loop: feed the failed check back, up to 2 times
python3 eval/maris3d_eval/run_eval.py ... --repair 2
# convert the raw output (contains generated code and local paths) to the public form
python3 scripts/import_result.py results/run.json --name Maris3D-SLM-Blender-1.5B --format gguf-q8_0 --file maris3d-slm-blender-1.5b-Q8_0.gguf --sha256 <hex> --out release/results/x.json
```
A full run takes about 1 to 2 hours on a laptop CPU. A run writes `<out>.partial` and resumes after an interruption. Schema of the public result: `eval/result_schema.json`.

External benchmark results (current: the 4 Nov 2026 native-format runs; the 31 Oct 2026 runs of this earlier line are a superseded appendix there) and why they are not comparable with leaderboards: [BENCHMARKS.md](BENCHMARKS.md).

## Rules for comparable numbers

1. Same 206 prompts in the same order, same short system prompt, greedy decoding, 4096 context, Blender 5.2.2.
2. Say what was used: file and its SHA-256, runtime (llama.cpp grammar, Ollama JSON mode ...), machine, repair on/off.
3. Do not tune on the benchmark. It was already used to choose between our own models, so it is not a fresh test set.
4. Add new prompts only at the end of the list (CONTRIBUTING.md); the old numbers stay comparable.

## Known caveats

- **Constrained decoding matters.** On the Ollama build used to prepare this release, the full JSON-schema `format` made the 1.5B model emit unrelated `add_empty` calls for "Add a cube", while plain JSON mode produced the correct call.
  The reference scores used llama.cpp grammar decoding. Scores through Ollama JSON mode were not measured.
- **Per-level breakdown differs between two runs of the same 1.5B file** (a Mac run and a CPU-server run both give 149/206 but different level splits in the private notes). The public result file uses the Mac run's rows; the two splits were not reconciled.
- The 0.5B per-prompt rows of the headline run are not in the repository (summary only, in `release/results/`). A second 0.5B run on a memory-starved Mac gave 34.5% and is not used.
- 165 of the 206 prompts were written by an AI agent, 41 by the pipeline author; see [LICENSING.md](LICENSING.md).
- Helper pack ablations (part planner, scene hints, retrieval) are described in TECHNICAL-REPORT.md; they are not part of the public runner.
