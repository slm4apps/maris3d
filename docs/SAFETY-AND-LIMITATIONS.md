# Safety and limitations

> Status note, 7 Nov 2026: updated for **Maris3D-SLM-Blender-0.5B v0.1** (native Qwen tool calls). The 180-request yardstick numbers below are the current line; observations marked *earlier line* were measured on the superseded JSON-format models and were not rerun.

## What can go wrong
- **Model output runs as Python inside Blender.** The tool calls are compiled from a fixed 26-tool set rather than free code, and `compile_calls` ignores unknown arguments, but Blender still runs with the permissions of the user who starts it.
  Use a scratch session, do not run it where Blender can touch important files, and keep the bridge/MCP ports on localhost.
- **Resource use.** The tool set can build large meshes (arrays, subdivision, booleans). The live server removes modifiers and objects that would push a scene past 100,000 faces per object or 400,000 in total, but the headless benchmark runner does not.
  The benchmark runner has a 90 s timeout per scene.
- **No safety training.** The models only output Blender tool calls; they were not trained to refuse. Content is limited by what the 26 tools can express.
- **Hallucinated certainty.** A "check passed" message from the MCP server or the bridge means the scene satisfied the requested counts and sizes; it does not mean the scene looks right.

## What it cannot do (measured, v0.1, 180-request yardstick)
| Limit | Evidence |
|---|---|
| Early model: the product (q8_0 base + edit adapter) 49 of 180 fully correct (27.2%), 87 partially correct, 44 fail (75.6% usable); merged single-file fallback 35 / 104 / 41 (19.4% / 77.2%); strict mode 23.9% pass / 68.9% usable; base alone 21.7% / 68.9%; q4_k_m 18.3% / 67.2% | `release/CURRENT.json`, [BENCHMARKS.md](BENCHMARKS.md) |
| Editing: weak on the bare build base (14 of 30 edit requests usable), strong with the edit LoRA, as the adapter or merged into the fallback file (26 of 30) | same |
| Multi-turn steering: 0 of 30 sessions — the model usually stops acting after the first follow-up; top improvement target | same |
| Multi-part requests are the weakest build mode | model card limits |
| Plan first knows 40 things by name and designs none; a name the planner did not train on is often written wrong (the thing it is placed by: 87.3% right on 300 held-out sentences, 98.5% when every name was trained) | model card, plan first |
| The model copies a compiled part exactly in 283 of 448 cases; the check corrects the rest, and says so when a correction did not hold | model card, plan first |
| A change to the scene (recolour, resize) is not read back and checked | [PROMPTING-GUIDE.md](PROMPTING-GUIDE.md) section 0 |
| Not a general tool caller: BFCL v4 simple_python 49.25%, multiple 39.5% (Qwen3.5-0.8B: 76.0% / 71.0%); MCP-Universe 3D one-shot 0 of 19 | [BENCHMARKS.md](BENCHMARKS.md) |
| Fixed tool set: 26 Blender tools only; other tools are guessed; no sculpting, rigging, simulation, node-based shaders (beyond basics), file import | `docs/DSL.md` |
| 20 tool calls per user turn (agent-loop limit); longer scenes get truncated | [USAGE.md](USAGE.md) |
| Does not see the scene or images; English only, Blender 5.2.2 only; trained on rows up to 2,048 tokens (serve with 8,192) | benchmark |

### Earlier line (superseded JSON-format models, kept as observations; not rerun on v0.1)
- L3 and L4 (modifiers, constraints, multi-step scenes, animation) were the weakest levels on the old 206-prompt benchmark (per-level tables in the old cards).
- Scale: it did not know units from text such as "205 mm"; some builds came out metres too large.
- Real-world text: three real marketplace listings built by the old 0.5B model gave empties instead of geometry (0/3).
- Whole-scene and incremental edit-training attempts on the old line did not improve over the plain model; the v0.1 edit LoRA is the approach that worked.

**PROPOSED NOTE (quick probe, 3 prompts; not reviewed, not a benchmark; 31 Oct 2026, earlier line).** We ran three benchmark prompts (b001 cube, b034 table, b036 snowman) in English and in 10 languages the Qwen2.5 base lists (zh, es, fr, de, pt, it, ru, ja, ko, ar). The translations were made by Claude and were not checked by native speakers. Each prompt was run once through Ollama: Q8_0, trained short system message, plain JSON mode, greedy decoding, no repair, normal scene check. Results:
- **Simple requests carry over.** The 1.5B passed the cube in all 10 languages and the table in 7. The 0.5B passed the cube in 8 (failing ko and ar) and the table in 2 (zh, ar).
- **Multi-part requests do not.** The snowman passed in 3 of 10 languages for the 1.5B and 0 of 10 for the 0.5B.
- **Totals outside English:** 20/30 for the 1.5B and 10/30 for the 0.5B. In English the 0.5B passed 3/3 and the 1.5B 2/3: its snowman built 4 meshes, while the published run passed it.
- **How the 0.5B fails:** often a JSON answer cut off at the token cap (nothing runs) or extra objects.
- **How the 1.5B fails:** mostly too few objects (eyes or nose missing).

Reading: the base model's understanding of these languages partly carries over for short single-object requests, and drops quickly with request length and model size. The limit stays "English only" until a proper translated benchmark is run. Script and raw outputs are kept in the maintainers' private notes.

## Responsible use
Do not present generated scenes as manually crafted work if that matters in your setting, and check licences of any asset you combine with them.
Report vulnerabilities as described in [SECURITY.md](../SECURITY.md).
