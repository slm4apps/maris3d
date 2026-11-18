# Benchmarks: Maris3D-SLM-Blender-0.5B v0.1 (native tool-call format)

Two generations of numbers live in this file. The current numbers (measured 4–6 Nov 2026) describe **Maris3D-SLM-Blender-0.5B**, the v0.1 release line: native Qwen tool calls driven through an agent loop, served with llama-server. The appendix holds the superseded runs of 31 Oct 2026, which measured the earlier development models in the old JSON format through Ollama; those numbers are history and are not comparable with anything above the appendix.

## 1. The 180-request yardstick (internal, frozen)

What it is: 180 frozen Blender requests across seven modes — single objects, multi-part objects, edits, animation, arrays and rings, parenting, geometry nodes. Each request runs in a real agent loop with native Qwen tool calls, one call at a time, up to 20 calls; every call is executed in Blender 5.2 and the finished scene is judged against a per-request checklist, not by whether the calls parse. Pass = fully correct; usable = pass or correct with small fixes. The frozen request set is kept with the maintainers for now; the public benchmark is in preparation.

| Variant | pass % | usable % | edit requests usable (of 30) | build requests usable (of 120) |
|---|---|---|---|---|
| default: edit LoRA merged, q8_0 | 19.4 | 77.2 | 26 | 94 (78.3%) |
| strict: base + edit LoRA @0.7 | 23.9 | 68.9 | 24 | 82 (68.3%) |
| base alone, q8_0 | 21.7 | 68.9 | 14 | 87 (72.5%) |
| q4_k_m + edit LoRA @1.0 | 20.0 | 79.4 | 26 | 96 (80.0%) |

Untrained baselines on the same 180 requests, same agent loop and tool plumbing:

| Model (untrained) | pass % | usable % |
|---|---|---|
| Qwen2.5-Coder-0.5B | 0.0 | 0.0 |
| Qwen2.5-Coder-1.5B | 0.0 | 0.0 |
| Qwen3-1.7B | 5.0 | 12.8 |

## 2. External benchmarks (4 Nov 2026)

Same settings for every model: llama-server, greedy decoding (temperature 0), native tool calls, context 4096. The Maris3D column is the merged single file (`maris3d-slm-blender-0.5b-edit-q8_0.gguf`), not the base + adapter product; the comparisons are plain Qwen2.5-Coder-0.5B and Qwen3.5-0.8B.

The model is a specialist trained on a fixed 26-tool Blender set, so the BFCL numbers are context on what the narrow training costs, not a leaderboard claim.

### BFCL v4 (Berkeley Function Calling Leaderboard)

| Category (items) | Maris3D-SLM-Blender-0.5B | plain Qwen2.5-Coder-0.5B | Qwen3.5-0.8B |
|---|---|---|---|
| simple_python (400) | 49.25% | 0.0% native (74.0% text-extracted, not official) | 76.0% |
| multiple (200) | 39.5% | 0.0% native | 71.0% |

The plain 0.5B's 74.0% comes from mechanically extracting calls from its text answers; it is not a native tool-call score and not an official BFCL number.

### 3DCodeBench (text track)

| Measure | Maris3D-SLM-Blender-0.5B | plain Qwen2.5-Coder-0.5B | Qwen3.5-0.8B |
|---|---|---|---|
| Executable scenes (of 212) | 212/212 | 0/212 | 0/212 |
| Chamfer distance (lower is better) | 0.1118 (165 comparable scenes) | not measured | not measured |

The 212/212 means every generated scene executes in Blender, not that every scene is right. For context, table A.1 of [arXiv:2606.01057](https://arxiv.org/abs/2606.01057) lists 12 frontier vision models between 0.059 (GPT-5.5) and 0.095 (Claude Haiku 4.5), averaged over text and image tracks — a different subset, tracks, Blender version and model class, so this is context, not a ranking; the shapes are still worse than theirs.

### MCP-Universe, 3D design (one shot, 19 tasks)

0 of 19 pass — for all three models. Context only: the published MCP-Universe results (table 3 of [arXiv:2508.14704](https://arxiv.org/abs/2508.14704)) are ReAct agents with large models over many turns (GPT-5 52.63%, Claude-4.0-Sonnet 26.32%, GPT-4o 26.32%, GLM-4.5 26.32%, GPT-OSS-120B 10.53%); the one-shot mode here is not comparable with them.

### Speed (4 threads; tg128 = generation, pp512 = prompt processing; tokens per second)

| Model | tg128 | pp512 |
|---|---|---|
| Maris3D-SLM-Blender-0.5B (default, q8_0) | 62.1 | 289.1 |
| plain Qwen2.5-Coder-0.5B | 62.8 | 266.5 |
| Qwen3.5-0.8B | 33.6 | 175.1 |

Runtime on an 8 GB Mac: 0.58 GB resident, about 0.6 s per answer, 1.3 s cold load.

## 3. What did not run, and why

| Item | Why |
|---|---|
| MCP-Universe in an agent loop | the 0/19 above is one-shot; the published mode is an agent loop with many turns |
| Chamfer for the comparison models | their 0/212 executable rate leaves nothing to compare |
| BlenderGym, Unity, Maya, Unreal, OpenDCC-Bench | not started, see [ROADMAP.md](../ROADMAP.md) |

## Appendix: superseded runs of 31 Oct 2026 (earlier JSON-format models, Ollama)

These runs measured the earlier development line — the old JSON tool-document format, including a development model that reused the name "Maris3D-SLM-Blender-0.5B", on the old 206-prompt benchmark — through a local Ollama (Q8_0 GGUF, greedy, context 4096 unless stated, Apple M3, 8 GB, Ollama 0.40.11, Blender 5.2.2). They are superseded by everything above and kept for history only.

### Result table (old format)

| Benchmark | Items | Result |
|---|---|---|
| Release benchmark (206 prompts, own) | 206 | 59.7% bare, 63.1% with 2 retries ([EVALUATION.md](EVALUATION.md)) |
| 3DCodeBench (text track) | 212 generated, 165 scored | executable export 212 of 212 (see caveat); Chamfer (4-yaw, conditional mean) 0.1136 on 165 |
| MCP-Universe, 3D design (one shot) | 19 | 0 of 19 pass |
| BFCL v4, prompt mode (simple_python + multiple) | 600 | 0 of 600 (all unparsable); a mechanical text conversion passes 4 to 14 of 600, not official |
| Latency, Ollama, Q8_0 | 9 timed calls | 114 to 132 tok/s generation up to 3163 prompt tokens, 3.3k to 5.5k tok/s prompt processing |
| Inspect gate (own task, 206 samples) | 6 logged | no result (stopped early) |

### Old-format notes
- 3DCodeBench, old run: all 212 generated and exported to a non-empty mesh; the reference mesh could be built for 165 categories. Conditional mean Chamfer 0.1136 with 4-yaw alignment (median 0.083), 0.1658 without. About half of the answers (104 of 212) were cut off in a repeated-call loop at the 40-call cap; they still exported a mesh because the adapter compiled the first complete calls, so the 100% executable rate is not comparable with the paper's.
- BFCL, old run: every answer started with `{` (the trained JSON format) and none used the call syntax; 207 of 600 were valid JSON. The correct function name appeared somewhere in the text in 414 of 600 answers (a lenient check, not the metric).
- MCP-Universe, old run: 19 of 19 produced a document; the scene script ran in 17 of 19; five tasks need a Polyhaven download, which cannot work offline, and about twelve need features outside the 26 tools, so a near-zero was expected.
- The old comparison with published BFCL leaderboard entries (Claude-Opus-4-5 96.50/95.50, Qwen3-1.7B 91.00/92.50, Hammer2.1-0.5b 83.25/81.00 and others, read 2026-10-31) is obsolete for this line: the v0.1 model scores natively instead (section 2 above).

### Old latency probe (Ollama, Q8_0, context 4096 unless stated)

| Prompt tokens | Prompt tok/s (cold) | Time to first token | Generation tok/s | Correct tool call |
|---|---|---|---|---|
| 32 | 1168 (includes warm-up) | 0.58 s | 128 | yes |
| 443 | 3309 | 0.14 s | 124 | yes |
| 1701 | 4012 | 0.43 s | 123 | yes |
| 3163 | 5457 | 0.59 s | 120 | yes |
| 4965 at context 8192 | 2583 | 2.5 s | 65 | yes |
| 4965 at context 4096 | request refused (HTTP 400) | - | - | - |

Memory was not measured in the old probe (it looked for the wrong process name); the 0.8 GB figure of that line came from an earlier CPU-server run.

### How the old adapters were rerun

```sh
python3 eval/adapters/mcp_universe_3d.py generate --tasks <3d_design task folder> --out <out> --model <ollama tag>
python3 eval/adapters/mcp_universe_3d.py check --bench-root <MCP-Universe checkout> --out <out> --blender <blender binary> --task 1   # per task
python3 eval/adapters/bfcl_prompt.py run --data <BFCL data folder> --out <rows.jsonl> --model <ollama tag>
python3 eval/adapters/bfcl_prompt.py score --data <BFCL data folder> --in <rows.jsonl> --json <score.json>
python3 eval/latency_probe.py --model <ollama tag> --sizes 20,512,2048,3800 --num-ctx 4096 --out <file.json>
```

Raw outputs and per-prompt failure analysis are kept outside this repository (private working space); only the numbers above are published.
