# FAQ

> Status note, 7 Nov 2026: updated for **Maris3D-SLM-Blender-0.5B v0.1** (native Qwen tool calls, 26 Blender tools): see [README.md](../README.md), [docs/USAGE.md](USAGE.md) and [release/STATUS.md](../release/STATUS.md). The earlier JSON-format models (0.5B v3, 1.5B v2) are history; their scores used a different 206-prompt benchmark.

**Why native tool calls and not Python code?** Small models write broken Blender Python (untuned Qwen2.5-Coder 0.5B and 1.5B scored 0% and 34% on a 41-prompt code test in our notes; the untuned 0.5B scores 0.0% on our 180-request yardstick). The model emits Blender tool calls in the standard Qwen tool-call format, and a small copilot compiles them to correct, current Blender 5.2 calls.

**Which file should I use?** v0.1 is a single 0.5B release with five model files, so the choice is by variant, not by size:
- The product, and what `maris3d install` fetches: the base `maris3d-slm-blender-0.5b-q8_0.gguf` served with the edit adapter `maris3d-slm-blender-0.5b-edit-lora-f16.gguf` and the planner adapter `maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf` (27.2% pass, 75.6% usable on the 180 requests; the planner adds plan first: one sentence builds several things).
- No adapter support on your host: the merged single file `maris3d-slm-blender-0.5b-edit-q8_0.gguf` builds **and** edits (19.4% pass, 77.2% usable; 26/30 edit requests usable). No plan first.
- Strict mode (base `maris3d-slm-blender-0.5b-q8_0.gguf` plus the edit LoRA `maris3d-slm-blender-0.5b-edit-lora-f16.gguf` at scale 0.7) for the highest fully-correct rate (23.9% pass), at the cost of usable scenes (68.9%).
- `maris3d-slm-blender-0.5b-q4_k_m.gguf` if you need the smaller file (18.3% pass, 67.2% usable — a measured quality cost).

**Do I need Blender?** To compile-and-run the calls: yes (headless is fine). To only get the tool calls: no.

**Can it edit my existing scene?** Yes, with the edit adapter loaded (the product setup) or on the merged fallback file: 26 of 30 edit requests either way. On the bare build base editing is weak (14 of 30). Multi-turn steering — asking for a change after each result — is still the weak point (0 of 30 sessions).

**Does it work with Blender 4.x?** Untested. The compiler targets the 5.2 API.

**Where are the weights and data?** Weights on Hugging Face: [slm4apps/Maris3D-Blender](https://huggingface.co/slm4apps/Maris3D-Blender) (five GGUF files). The training data is not released (see the data card).

**Can I use it commercially?** Yes: the code and weights are Apache-2.0, the same as the base model, and the teacher-data terms were reviewed. Details in [LICENSING.md](LICENSING.md); nothing there is legal advice.

**Why is the Blender add-on code GPL?** Anything that imports Blender's Python API (`bpy`) is treated as part of a GPL work. Only `src/maris3d/blender/` is affected.

**Is this affiliated with Blender?** No. Independent community project; "Blender" is a trademark of the Blender Foundation.

**Why do my results differ from the card?** Check: same GGUF file (compare the hash), greedy decoding (temperature 0), repeat penalty 1.0, the same 26-tool set, native tool calls, Blender 5.2.2. See [BENCHMARKS.md](BENCHMARKS.md).

**Which route should I use: llama-server, Ollama or the MCP server?** Any runtime that speaks Qwen tool calls works (llama-server, Ollama, LM Studio); the external benchmark tables were measured with llama-server. The MCP server wraps the same calls for MCP clients.
