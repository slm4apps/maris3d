<!-- Release write-up for Maris3D-SLM-Blender-0.5B v0.1 (decided 7 Nov 2026: name, org slm4apps, Apache-2.0). -->

# Maris3D-SLM-Blender-0.5B v0.1: a small Blender copilot model that runs offline on an 8 GB Mac

I have released an early version of a small language model that builds and edits Blender scenes by calling tools. It has 0.5 billion parameters. The main file is 531 MB, two 5.6 MB adapters sit beside it (one for edits, one planner that turns a whole sentence into a plan), and it uses about 0.58 GB of memory when it runs. I trained it on home hardware, and it runs on an ordinary 8 GB Mac with no network.

Type one sentence, such as "a small train station: a platform, a station building behind the platform, a track in front of it, a train on top of the track", and it builds the scene: a planner lays the things out in words, code works out every number, the model makes the parts, and a check puts right what the model misses. You can also ask for single shapes with exact numbers and steer every detail yourself. This is version 0.1: it knows 40 everyday things by name, and the numbers below show where it is strong and where it is not.

## What it is

The model is Qwen2.5-Coder-0.5B-Instruct with two LoRA fine-tune stages: first a build LoRA, merged into the weights, then an edit LoRA that ships as a separate 5.6 MB adapter. A third small LoRA, the planner, was trained apart from them on 4,000 sentences and ships as a second 5.6 MB adapter; it writes no tool calls, only one JSON object that lists things and where they stand, in words. One server loads the base and both adapters; a fresh request runs with no adapter, a correction with the edit adapter, a plan with the planner alone. It speaks the standard Qwen tool-call format. Any host that can drive Qwen tools, for example `llama-server --jinja`, can run it without custom prompt code.

It was trained on a fixed set of 26 Blender tools: add a primitive, transform, material, modifier, parent, keyframe, array, geometry nodes and so on. The host runs each call in Blender, returns the result, and the model decides the next call. With any other tool set it does not work well. Training rows are at most 2,048 tokens; serve it with an 8,192 context, because the 26 tool descriptions plus a conversation can overflow 4,096.

## Why I built it

Most copilots for 3D software send every request to a large cloud model. That has three costs, and they are the reasons this model exists.

- **Privacy.** Your prompts and your scene go to a third party. Some studios cannot do that, for example under an NDA. A model on your own machine sends nothing anywhere.
- **Cost.** Cloud models charge per request. A local model costs electricity.
- **Offline use.** No network, no copilot. A local model works on a train, in a studio with no internet, or when a service is down.

My question was narrow: how small can a model be and still build a correct Blender scene from a plain request, on an ordinary laptop? My long-term target is 80% of real requests ending in a correct scene; the numbers below are the starting point.

## The numbers

I test on 180 frozen Blender requests in seven modes: single objects, multipart objects, edits, animation, arrays and rings, parenting, and geometry nodes. Each request runs in an agent loop with native tool calls, one at a time, up to 20 calls. Every call is executed in Blender 5.2, and the finished scene is judged against a per-request checklist. The scorer judges the scene, not whether the tool calls parse.

v0.1 ships five model files. The product is the base with the edit adapter (and the planner adapter for whole sentences, below); the other rows are the single-file options (pass = fully correct; usable = pass or correct-with-small-fixes):

| Variant | Full pass | Usable |
|---|---|---|
| **Product: q8_0 base + edit adapter (0 fresh, 1.0 correction)** | 49/180 (27.2%) | 136/180 (75.6%) |
| Single-file fallback: edit LoRA merged, q8_0 | 35/180 (19.4%) | 139/180 (77.2%) |
| Strict mode: base + edit LoRA at scale 0.7 | 23.9% | 68.9% |
| Base alone, q8_0 | 39/180 (21.7%) | 124/180 (68.9%) |
| Base alone, q4_k_m | 18.3% | 67.2% |

The product row is two halves: 24.0% pass / 73.3% usable on the 150 build requests, 43.3% / 86.7% on the 30 edit requests. For the single-file rows, on the 30 edit requests (usable): merged 26, strict 24, base alone 14. On the 120 build requests (usable): merged 94 (78.3%), strict 82 (68.3%), base 87 (72.5%), q4_k_m 91 (75.8%). The untrained Qwen2.5-Coder-0.5B base passes 0 of the same 180 requests.

I report pass and usable separately and never blended. A training run once raised the pass count while the usable count fell, and a single blended number would have hidden that.

Public benchmarks, run 4 Nov 2026 with the same settings for every model (llama-server, greedy decoding, native tool calls):

| | This model | Plain Qwen2.5-Coder-0.5B | Qwen3.5-0.8B |
|---|---|---|---|
| 3DCodeBench scenes that run (of 212) | 212/212 | 0/212 | 0/212 |
| BFCL v4 simple_python (400) | 49.25% | 0.0% native (74.0% text-extracted, not official) | 76.0% |
| BFCL v4 multiple (200) | 39.5% | not measured | 71.0% |
| MCP-Universe 3D, one shot (19) | 0/19 | 0/19 | 0/19 |

Two points on the 212/212. It means every generated scene executes in Blender. It does not mean every scene is right. On 3DCodeBench shape error (Chamfer distance, lower is better, 165 comparable scenes) the model scores 0.1118. Frontier vision models score 0.059 to 0.095. So the shapes are still worse than theirs, and I make no claim of parity with them.

Speed on 4 threads: about 62 tokens per second generation and 289 tokens per second prompt processing. On the Mac, an answer takes about 0.6 seconds and a cold load takes 1.3 seconds.

## What it cannot do

This section matters more than the one above.

- **Editing is weak on the bare base but strong with the edit adapter.** The build base alone manages 14 of 30 edit requests; with the edit LoRA (as the adapter, or merged into the fallback file) that is 26 of 30. If your workflow is "change what is already there", run the adapter.
- **Steering fails.** In multi-turn sessions, where you ask for a change after each result, it usually stops acting after the first turn. It succeeded in 0 of 30 sessions. Multi-part requests are the weakest build mode.
- **It is not a general tool caller.** On the BFCL v4 simple_python benchmark it scores 49.25%, below Qwen3.5-0.8B at 76.0% (multiple: 39.5% vs 71.0%). It learned Blender's 26 tools, and that narrow training cost it general skill. On the MCP-Universe 3D tasks it solved 0 of 19.
- **It is not accurate enough to trust unattended.** 44 of 180 requests fail outright on the product (41 on the merged file). The partial results often have the right object with wrong dimensions, missing parts or wrong relations between parts.
- **It is not a frontier model.** The numbers above say so.

The per-mode failure behaviour is summarised in the model card's limits section. If you want to know whether your kind of request is likely to work, look there first.

## How to run it

The five GGUF files are on Hugging Face at [slm4apps/Maris3D-Blender](https://huggingface.co/slm4apps/Maris3D-Blender); the checksums are in the release.

With llama.cpp, the product (one server, the base plus the two adapters):

```
llama-server -m maris3d-slm-blender-0.5b-q8_0.gguf --jinja -c 8192 --temp 0 --repeat-penalty 1.0 --port 8080 \
  --lora maris3d-slm-blender-0.5b-edit-lora-f16.gguf --lora maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf \
  --lora-init-without-apply
```

Send OpenAI-style requests to `/v1/chat/completions` with `tools` set to the `TOOLS.json` from the release, and the strength for the turn: `"lora": [{"id": 0, "scale": 0.0}]` for a fresh request, `1.0` for a correction. Your host runs each call in Blender, returns the result as a `tool` message, and loops. I used a limit of 20 calls per request. `maris3d serve start` runs this server for you, and `maris3d install` puts the add-on into Blender; there you type the sentence and leave the switch on Auto.

Keep temperature 0 and repeat penalty 1.0. A tool call is repetition by design, and a penalty of 1.1 makes the model drop object names and, at worst, repeat one call until it runs out of tokens.

Strict-pass mode is the same server with `"scale": 0.7` on every request. It has a higher fully-correct rate than any single file (23.9%) at the cost of some usable scenes.

If your host cannot load an adapter, serve the merged file:

```
llama-server -m maris3d-slm-blender-0.5b-edit-q8_0.gguf --jinja -c 8192 --temp 0 --repeat-penalty 1.0 --port 8080
```

With Ollama, which cannot switch an adapter per request, use the merged file. A `Modelfile` ships beside the GGUFs:

```
FROM ./maris3d-slm-blender-0.5b-edit-q8_0.gguf
PARAMETER temperature 0
PARAMETER repeat_penalty 1.0
PARAMETER num_ctx 8192
PARAMETER num_predict 800
```

Then run `ollama create maris3d-slm-blender-0.5b -f Modelfile`. Two notes: the llama-server path is the one I scored with, and Ollama's default repeat penalty is 1.1, which its OpenAI-compatible endpoint cannot change, so there the value must come from the Modelfile. If you try it, please tell me what happens.

The fourth file, `maris3d-slm-blender-0.5b-q4_k_m.gguf`, is the smaller build-only file (398 MB). It is measured: 18.3% pass, 67.2% usable — a real quality cost for the size saving.

## What ships in v0.1, and what comes in v0.2

The weakest area of the build base was editing, so v0.1 ships an edit LoRA. It fixed editing (26 of 30, against 14 of 30 for the base). Loaded as an adapter and switched per request, it leaves the base's build results untouched, which is why base plus adapter is the product: 27.2% pass, 75.6% usable. Merged into one file it costs full passes on builds (19.4% overall) but needs no adapter support. Running the adapter at scale 0.7 on every request gives strict mode: 23.9% pass, 68.9% usable. That is the whole menu: the product, one merged fallback, one strict recipe, one smaller build-only file.

v0.1 also ships a second small adapter, a planner (5.6 MB). The model alone needs one primitive per prompt with its numbers; nobody wants to type a train station that way. With the planner loaded you type one sentence: "a platform, a station building behind the platform, a track in front of the platform, a train on top of the track". The planner answers in words only: which things, how many, beside what. Code turns the words into metres, the edit adapter makes each part from that exact instruction, and a check reads every part back from Blender and corrects it. The honest numbers: on 300 held-out sentences the planner gets the stated relation right in 98.6% and the thing it is placed by in 87.3% (98.5% when it trained on every name in the sentence); the edit adapter copies a part exactly in 283 of 448 cases and the check corrects the rest. It knows 40 things by name, from a built-in parts table, and designs nothing new. The `demo/` folder has the station built this way, with its counts and its files.

That table and that copying are what v0.2 removes, as a breaking change: compiled parts go straight to Blender with no model in between, and one planner writes the parts of a thing as well as the outline. v0.2 ships when it reproduces the v0.1 demo.

Also next is multi-turn steering (0 of 30 sessions today), so that you can correct a scene in conversation, and the public benchmark set.

## How you can help

The most useful thing you can do is use it on real work and tell me where it breaks.

- **Report failures.** If a request gives a wrong or empty result, send me the prompt, the tool calls and what you expected. Failures from real work are worth more than another benchmark number, because my 180 requests are my own guess at what people ask.
- **Try the tools.** The 26-tool set and the scoring rules are part of the release. The 206-prompt benchmark ships in `eval/benchmark/`; the frozen 180-request set stays private so it remains a fair test. Run your own requests and tell me whether the model behaves.

Everything ships under Apache-2.0: code and weights (the Qwen base is Apache-2.0), docs included. The Blender add-on files that import `bpy` are GPL-3.0-or-later, because Blender's API is GPL.

This is a first step: a model small enough to run offline on a modest Mac that builds real Blender scenes from a sentence. Version 0.2 is already in the works.

Zino Adidi
