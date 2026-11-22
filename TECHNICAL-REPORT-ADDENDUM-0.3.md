# Addendum to the technical report: Maris3D 0.2 to 0.3.0

This addendum builds on the [v0.1 technical report](TECHNICAL-REPORT.md), which stays as published. It covers what
changed from 0.2.0 to 0.3.0: the word language, the single adapter, the 0.2.2 adapter, code-read exact adds, picture
input and SLM4Apps SceneBench 1.0. Every number is measured on the released files; set sizes are given with each.

## 1. From tool calls to words (0.2.0)

In 0.1 the model wrote native tool calls with coordinates. Coordinates were its weakest output: asked for positions
directly, it placed 0 of 36 held-out items within 25 cm. 0.2 moves every number out of the model. The model answers in
a small word language: which things, how many, materials, relations (*behind*, *next to*, *on top of*) and relative
sizes (*half*, *double*). The app's compiler turns the words into the same 26-tool DSL as 0.1 and computes every size
and position. The copilot builds part by part, reads the scene back from Blender and corrects it, up to three passes.

One LoRA adapter on the 0.1 base does four jobs that 0.1 split across adapters: plan a sentence, design the parts of a
thing that has no recipe, apply word edits to a built scene, and talk about the scene. Animation (spin, bounce,
orbit, pulse) is written by code from the sentence. 0.2.1 kept the weights and cleaned the files (Maris3D name and
identity in the GGUF metadata and chat template, no build-machine metadata); answers were checked unchanged after
cleaning at temperature 0.

## 2. The 0.2.2 adapter

0.2.2 continues training the 0.2 adapter on a mix that adds camera, light, text, retext, attach, aim, finish (bevel,
subdivide, thicken, wire, mirror, array, taper, bend, twist) and scene words, with the app telling the model which
cameras, lights and texts are in the scene. Training is ordered (the mix in a fixed order), learning rate 5e-5,
gradient accumulation 4, sequences up to 1,800 tokens, a checkpoint every 250 updates, each checkpoint scored on held-out
sets. No single checkpoint was best on every job, so the released adapter is an exact blend of two checkpoints of the
same run (0.3 of updates 7,500 and 0.7 of updates 9,000), made by stacking their LoRA ranks: the delta is the weighted
sum of the two deltas, and the adapter file (23 MB) has twice the rank of either checkpoint.

Held-out results (0.2.2, scored by outcome through the app's own code):

| What | Result |
|---|---|
| Plan: the things named are right | 97.3 % (2,951 of 3,033 things in 716 sentences) |
| Plan: the whole sentence right | 84.1 % (602 of 716) |
| Parts: the answer parses / passes the app's rules | 99.9 % / 99.0 % (1,268 names) |
| Word edits: the change asked for is the change made | 85.4 % (726 change requests) |
| Talk: the reply is right | 96.1 % (152 turns); 96.5 % (231 turns) |
| Talk: things invented that are not in the scene | 0 in 383 turns |

## 3. Exact adds: model or code

An exact add is a request that already holds every number ("add a cylinder named Cup at 0.45, 0.15, 0.86 with a
radius of 0.10 and a depth of 0.18"). The 0.1 demo street has 204 of them. Copying the numbers through the model, the
0.2.2 adapter built 163 exactly (right thing, place and size). From 0.2.2 the app reads such a request with a parser
and builds it without the model: 203 of 204 exactly. A request that asks for more than one exact shape still goes to
the model.

We also trained the 0.2.2 adapter further on exact adds. The resulting adapter copied the numbers itself on 200 of
204, but scored lower than the 0.2.2 blend on held-out plans, parts, word edits and talk, and on the full demo replay.
Because the parser already reaches 203, 0.3.0 ships the 0.2.2 adapter unchanged. The general point: when code can do a
step exactly, training the model to do it competes with what the model is for.

## 4. Picture input (0.3.0)

Picture input is an optional module. A small vision model, SmolVLM-500M-Instruct (GGUF, run by llama.cpp's
`llama-mtmd-cli`), is downloaded at install from Hugging Face with a pinned sha256; it is not part of the Maris3D
files. A picture is not described in one long caption. The vision model is asked several short questions in separate
runs (what it is, which objects are in it, the main colour), and each run exits. Code composes the answers into a short request of
the kind Maris3D was trained on ("a red car", "3 yellow spheres"): it drops filler ("a 3D render of"), the floor or
background, colour-only items and bare numbers, and falls back to the noun phrase of a long description only when the
short answers give nothing. The request then runs through the normal flow.

Memory: the vision step peaks at about 1.35 GB. If the free memory is less than that plus a 1 GB margin, the copilot
stops its own llama-server for the picture step and starts it again before the request, so the two models never swap.
The picture step took 3.6 to 4.5 s on an Apple-silicon Mac and 5.6 to 6.8 s on a laptop CPU.

## 5. SLM4Apps SceneBench 1.0

SceneBench 1.0 joins every check into one frozen set: 4,269 items in 10 areas, each item with a gold answer, scored by
outcome through the app's code. The area score is the mean of the area's checks; the overall score is the mean of the
areas a version has a result for. 0.3.0 runs the 0.2.2 model, so its column is the 0.2.2 model with the 0.3.0 app.

| Area (items) | 0.2.1 | 0.3.0 |
|---|---|---|
| Make one thing (1,212) | 68.9 | 72.2 |
| Lay out a scene (1,031) | 22.2 | 29.6 |
| Place exactly (204) | 93.7 | 99.5 |
| Change what is there (841) | 58.8 | 65.4 |
| Camera, light, text, finish (377) | 6.8 | 96.6 |
| Make it move (30) | 53.3 | 43.3 |
| Blender tools (108) | 19.0 | 21.5 |
| Talk (344) | 85.7 | 96.4 |
| Picture to scene (24) | – | 66.7 |
| **Overall** | **51.0** (8 areas) | **65.7** (9 areas) |

Picture to scene uses 24 fixed reference pictures made in Blender (balls, trees, cars, a table, chairs, a snowman, a house, boxes, a bench, a lamp, a flower, a pumpkin, a dog, a vase and primitives in several colours and counts). An item is right when the built scene has the right thing,
count and colour: thing 75.0 %, count 66.7 %, colour 79.2 %, all three 66.7 %. The whole-scene items (the Christmas
street and the station) are covered by the demo replay: 51 requests through the 0.3.0 app in Blender, 0 failed.

## 6. Lessons

- **Give the model less to do.** Words for the model, numbers for code: placement went from 0 of 36 within 25 cm to a
  compiler that computes every position.
- **Score on what the model has not seen, by outcome.** Every number above applies the model's answer with the app's
  own code and compares the resulting scene, so equivalent answers count and invented names fail.
- **Check the scorer before the score.** One SceneBench area first read 0.0 for the 0.2.2 adapter. Its answers were
  right; that run had used a scorer that could not read the tool-call form. The same answers through the scorer used
  for every other version: 96.6.
- **A dead server is not a score.** One run of the exact-adds adapter reported 39 of 204; its server had died at row 40.
  The rerun gave 200.

## 7. Limitations

The limits in [docs/SAFETY-AND-LIMITATIONS.md](docs/SAFETY-AND-LIMITATIONS.md) hold. Seven of the 26 tools have no
path through the word language. A picture is read as one kind of thing; it does not copy a scene or its layout. The
model is trained on English requests; the Qwen base reads many languages. In a small test, 12 simple requests (a red cube,
a wooden table with four chairs, three yellow balls) in Spanish, French, German and Chinese through the 0.3.0 add-on built
the right things in the right number 8 times; object names came out in the request's language or garbled.
