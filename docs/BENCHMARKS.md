# Benchmarks: Maris3D 0.2

Maris3D 0.2 answers in words and the app's code writes the Blender calls, so it is scored in two ways: held-out sets for each kind of answer (section 2), and the 180-request yardstick that
0.1 was also scored on (section 1). Section 3 holds the external benchmarks, which were run for 0.1 only.

## What each test measures

- **Plan** (716 held-out sentences, 3,033 things): one sentence in, the model's plan out. Each thing is checked: the right thing, count, relation, the thing it is placed by, distance, size, material. "Whole sentence right" means every thing in it is right.
- **Parts** (1,268 held-out names): the model designs a new thing from its parts. "Parses" = the answer can be read; "passes the rules" = the app's checks accept the design (parts exist before they are used, known size words, no name used twice).
- **Word edits** (811 held-out rows, 726 of them change requests): a scene and a request to change it. Right = the app, applying the answer, makes the change asked for.
- **Talk** (152 and 231 held-out turns, a few of them build or question turns): right = the reply is the right kind; "invented" counts things named that are not in the scene.
- **Sets with the new change words** (150 rows each): the same four jobs, with the 0.2.2 prompt that lists the scene's cameras, lights and texts.
- **Long sentences** (60 composites, 36 rooms, 24 scenes): long requests that join several groups of things. "Whole plan exact" = the things, the counts and every placement match.
- **Hard parts sets** (317 core names, 22 new names): parts designs for names outside the usual set.
- **The 0.1 demo scene** (204 requests): the exact adds typed to build the 0.1 demo street, run through the app's code with a stand-in for Blender that records each call's name, place and size; exact = the named object has the typed place and size (tolerance 0.01 m or 1 %).
- **The 180-request yardstick** (section 1): whole scenes built in Blender and judged against a checklist per request.

## 1. The 180-request yardstick

180 frozen Blender requests across seven modes: single objects, multipart objects, edits, animation, arrays and rings, parenting, geometry nodes. Each request is run in Blender and the finished
scene is judged against a per-request checklist, not by whether the output parses. Pass = fully correct; usable = pass or correct with small fixes. The request set stays with the maintainers while
the public benchmark is prepared. One run per row.

| | pass % | usable % |
|---|---|---|
| **0.2: base + one adapter, through the 0.2 app** | 23.3 | 75.0 |
| 0.1 product: base + edit adapter (and planner adapter) | 28.3 | 88.9 |

On this set 0.2 is below 0.1, and we report it as measured. By mode, 0.2 moved things as asked in 20 of 37 animation requests (done by the app's code). A related gap: a follow-up that adds a new thing to a scene
that is already built often does nothing yet (14 of 30 follow-up edits changed the scene).

### 0.1 variants on the same 180 requests

| Variant | pass % | usable % | edit requests usable (of 30) | build requests usable (of 120) |
|---|---|---|---|---|
| **product: q8_0 base + edit adapter, router per request (one run)** | **28.3** | **88.9** | 29 | 131 of 150 non-edit rows |
| merged single file: edit LoRA merged, q8_0 | 19.4 | 77.2 | 26 | 94 (78.3%) |
| strict: base + edit LoRA @0.7 | 23.9 | 68.9 | 24 | 82 (68.3%) |
| base alone, q8_0 | 21.7 | 68.9 | 14 | 87 (72.5%) |
| q4_k_m + edit LoRA @1.0 | 20.0 | 79.4 | 26 | 96 (80.0%) |

Untrained baselines on the same 180 requests, same agent loop and tool plumbing:

| Model (untrained) | pass % | usable % |
|---|---|---|
| Qwen2.5-Coder-0.5B | 0.0 | 0.0 |
| Qwen2.5-Coder-1.5B | 0.0 | 0.0 |
| Qwen3-1.7B | 5.0 | 12.8 |

## 2. Held-out sets (0.2)

Sentences, names and change requests the adapter never trained on, scored by outcome through the app's own code.

| What | Result |
|---|---|
| Plan from one sentence: the things named are right | 97.3 % (3,033 things in 716 held-out sentences) |
| the relation (behind, next to, on top of ...) is right | 97.0 % |
| the thing it is placed by is right | 95.8 % |
| Parts of a new thing: the answer parses | 99.9 % (1,268 held-out names) |
| the design passes the app's rules | 95.7 % |
| Word edits: the change asked for is the change made | 90.4 % (726 held-out change requests) |
| Talk: the reply is right | 95.8 % (118 held-out talk turns) |
| Talk: things invented that are not in the scene | 0 in 383 turns |

Serving: temperature 0, context 8,192, repeat penalty 1.05.

Measured on 0.2.0 (0.2.1 has the same weights). 0.2.1 and 0.2.2 on the same sets: section 2b, which scores both with the 0.2.2 app's code, so its 0.2.1 column differs slightly from this section.

## 2b. 0.2.1 and 0.2.2 on the same sets

Same rows, same scorer, temperature 0. Edit rows use the prompt without the new change words except the "New change words" rows.

| Set | Measure | 0.2.1 | 0.2.2 |
|---|---|---|---|
| Plan, 716 sentences | things right (of 3,033) | 97.3 % (2,952) | 97.3 % (2,951) |
| | relation right | 97.0 % (2,941) | 97.1 % (2,946) |
| | placed by the right thing | 95.8 % (2,906) | 95.9 % (2,908) |
| | whole sentence right (of 716) | 82.0 % (587) | 84.1 % (602) |
| Parts, 1,268 names | answer parses | 99.9 % | 99.9 % |
| | passes the app's rules | 95.1 % | 99.0 % |
| Word edits | change requests right (726) | 90.4 % | 85.4 % |
| | all rows right (811) | 88.4 % | 84.8 % |
| Talk, 152 turns | reply right | 85.5 % | 96.1 % |
| | talk turns right (118) | 94.9 % | 94.9 % |
| Talk, second set, 231 turns | reply right | 84.4 % | 96.5 % |
| | talk turns right (197) | 89.3 % | 95.9 % |
| Talk, both sets | things invented (383 turns) | 0 | 0 |
| New change words: plan, 150 | whole sentence right | 78.7 % (118) | 82.0 % (123) |
| | things right (of 642) | 97.2 % (624) | 97.2 % (624) |
| New change words: parts, 150 | passes the app's rules | 94.0 % | 100 % |
| New change words: edits, 150 | rows right | 64.7 % | 61.3 % |
| New change words: talk, 150 | reply right | 87.3 % | 96.7 % |
| Long sentences: composites, 60 | whole plan exact | 5.0 % | 40.0 % |
| Long sentences: rooms, 36 | whole plan exact | 0.0 % | 0.0 % |
| Long sentences: scenes, 24 | whole plan exact | 0.0 % | 0.0 % |
| Hard parts: 317 common names, outside the training set | passes the app's rules | 93.1 % | 99.1 % |
| Hard parts: 22 new names, outside the training set | passes the app's rules | 95.5 % | 90.9 % |
| 0.1 demo scene, 204 exact adds, answered by the model | built exactly | 96.1 % (196) | 79.9 % (163) |
| | the same, with the new change words | | 81.9 % (167) |
| | read by code (0.2.2 app) | | 99.5 % (203) |


## 3. External benchmarks (0.1 only)

Same settings for every model: llama-server, greedy decoding (temperature 0), native tool calls, context 4096 (0.1). The Maris3D column is the 0.1 merged single file (`maris3d-slm-blender-0.5b-edit-q8_0.gguf`), not the base + adapter product; the comparisons are plain Qwen2.5-Coder-0.5B and Qwen3.5-0.8B.

0.1 was a specialist trained on a fixed 26-tool Blender set, so the BFCL numbers are context on what the narrow training costs, not a leaderboard claim.

### BFCL v4 (Berkeley Function Calling Leaderboard)

| Category (items) | Maris3D 0.1 | plain Qwen2.5-Coder-0.5B | Qwen3.5-0.8B |
|---|---|---|---|
| simple_python (400) | 49.25% | 0.0% native (74.0% text-extracted, not official) | 76.0% |
| multiple (200) | 39.5% | 0.0% native | 71.0% |

The plain 0.5B's 74.0% comes from mechanically extracting calls from its text answers; it is not a native tool-call score and not an official BFCL number.

### 3DCodeBench (text track)

| Measure | Maris3D 0.1 | plain Qwen2.5-Coder-0.5B | Qwen3.5-0.8B |
|---|---|---|---|
| Executable scenes (of 212) | 212/212 | 0/212 | 0/212 |
| Chamfer distance (lower is better) | 0.1118 (165 comparable scenes) | not measured | not measured |

The 212/212 means every generated scene executes in Blender, not that every scene is right. For context, table A.1 of [arXiv:2606.01057](https://arxiv.org/abs/2606.01057) lists 12 frontier vision models between 0.059 (GPT-5.5) and 0.095 (Claude Haiku 4.5), averaged over text and image tracks — a different subset, tracks, Blender version and model class, so this is context, not a ranking; the shapes are still worse than theirs.

### MCP-Universe, 3D design (one shot, 19 tasks)

0 of 19 pass — for all three models. Context only: the published MCP-Universe results (table 3 of [arXiv:2508.14704](https://arxiv.org/abs/2508.14704)) are ReAct agents with large models over many turns (GPT-5 52.63%, Claude-4.0-Sonnet 26.32%, GPT-4o 26.32%, GLM-4.5 26.32%, GPT-OSS-120B 10.53%); the one-shot mode here is not comparable with them.

### Speed of 0.1 (4 threads; tg128 = generation, pp512 = prompt processing; tokens per second)

| Model | tg128 | pp512 |
|---|---|---|
| Maris3D 0.1 (base, q8_0) | 62.1 | 289.1 |
| plain Qwen2.5-Coder-0.5B | 62.8 | 266.5 |
| Qwen3.5-0.8B | 33.6 | 175.1 |

Runtime of 0.1 on an 8 GB Mac: 0.58 GB resident, about 0.6 s per answer, 1.3 s cold load.

## 4. What did not run, and why

| Item | Why |
|---|---|
| MCP-Universe in an agent loop | the 0/19 above is one-shot; the published mode is an agent loop with many turns |
| Chamfer for the comparison models | their 0/212 executable rate leaves nothing to compare |
| BlenderGym, Unity, Maya, Unreal, OpenDCC-Bench | not started, see [ROADMAP.md](../ROADMAP.md) |
