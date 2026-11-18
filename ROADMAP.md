# Roadmap

Maris3D is the small language model (SLM) for Blender. The goal of the 0.x line is that you can do the things people do
in Blender by typing what you want, offline, with a small model.

How it is built:
- The model says *what* in words; code turns the words into numbers and Blender calls.
- Every version covers **every feature group** at some level and deepens it. The one exception is 0.2, which drops the
  0.1 tool-call route: lights, camera, curves, text and modifiers come back as words in 0.2.1.
- Every group has its own held-out set of test prompts. Its numbers are published for every version, next to the
  earlier ones, including the numbers that went down.

Versions are git tags and Hugging Face revisions; each promotion adds a row to `release/HISTORY.md`.

## Feature groups by version

Level in each version (0.1 and 0.2 are released, the later columns are plans):

| Feature group | 0.1 (released) | 0.2 (released) | 0.2.1 | 0.3 | 0.4 | 0.5 | 0.6 -> 1.0 |
|---|---|---|---|---|---|---|---|
| **Objects** ("a wooden chair") | built from primitives by tool calls; about 40 named things built part by part from a plan | the adapter designs any object as parts; code builds them |  | more shapes per part (tapered, turned, bent) | figures and animals as objects | your own objects used as parts | all common objects pass their test set |
| **Scene layout** ("a rug, a chair beside it, gifts stacked") | one sentence is planned into named things with places | scene words: room, stack of N, facing, against the wall, under, in the middle |  | rooms with walls, windows and doors | characters placed in the scene | big scenes in zones (a village, a whole station) | |
| **Edits** ("make the chair red, move it left") | an edit adapter fixes and changes the scene | edits in words, read back and checked; "a chair" adds, "the chair" changes | change words for lights, camera, motion, text and copies | edits to looks, light and camera | edits to poses and motion | edits across zones | |
| **Materials and looks** ("brass", "old wood") | colour, roughness, metal, glow, see-through | 147 colour names, shade, finish, gradient |  | wood, metal, glass, fabric, knitted, stripes, dots (procedural materials) | | images as labels and decals | |
| **Lights and world** ("evening light") | point, sun, spot and area lights | not in 0.2: the model says it cannot add lights yet | lights as words (planner and edit) | moods: morning, evening, night, studio, lamp glow; sky colour | lights that follow the action | | |
| **Camera and render** ("a close-up of the chair") | add a camera, render settings | the view frames what was built; no camera or render words yet | a camera as words; render size and quality as words | shots: wide, close-up, from above, orbit; render size and quality | camera follows a character | | |
| **Object animation** ("the gift spins") | keyframes on objects, frame range | by the app's code from the sentence: spin, bounce, move, rise, grow, shrink, swing, orbit, pulse, colour change | keyframes as words: spins, bounces, moves from A to B, grows | spin, bob, sway, pulse, move to, follow a path, flicker | timelines of several steps ("then") | | |
| **Characters** ("a small doll in a teal dress") | not yet | not yet (test set recorded as a baseline) |  | still figures from parts: doll, snowman, teddy, cat, dog, simple person | rigged characters | | |
| **Character motion** ("she walks to the chair and sits") | not yet | not yet |  | | poses and actions: stand, sit on, wave, point, walk to, hop, dance, hold | | |
| **Shape tools** ("round the edges", "a row of 10") | modifiers, shape keys, edit mesh, join, duplicate | sizes as words (bigger, smaller), copies of a thing in a plan | modifiers and copies as words (rounded edges, a row of N) | bevel, array, mirror, hollow, smooth | | cut a hole, extrude, inset, taper, twist | |
| **Curves, text, procedural** ("a rope from the lamp to the chair") | curves, text, geometry nodes, snow | not in 0.2 (snow only) | curves and text as words | | | ropes, cables and pipes between things; text on things; scatter (grass, snow, stones) | |
| **Physics** ("drop the gifts on the floor") | not yet | not yet |  | | drop and settle, cloth over a thing, falling snow | | |
| **Your own things** ("use my model as the table") | works on the open scene (add-on, MCP) | the planner is told what the scene holds |  | | | your selected objects as parts or anchors; export glb / fbx / usd | |
| **Talk and help** ("what can you do?") | answers with tool calls only | short messages in the scene, asks back when a word is unknown |  | explains what it built | | | Blender how-to answers from an offline help index |
| **Big scenes** | small scenes (a street, a station) | | |  | | zones | |
| **Hosts** (where it runs) | Blender (add-on, MCP) | Blender |  | the core runs as a local service; Blender is its first client | a second host in preview (Maya or Unity): "Maris3D for <host>" | | Blender, Maya, Unity, Unreal pass the same tests |
| **Product** | add-on, MCP server, Ollama, GGUF files | one LoRA file on the 0.1 base: plan, parts, edit and talk; add-on, MCP server, llama-server, Ollama (`maris3d-slm-blender-0.5b`); `maris3d update` | the same base; the adapter is retrained | | | | model size reviewed with measured numbers (smaller is the aim) |

A blank cell means the level of the column before it carries on.

## v0.1 (released)

Qwen2.5-Coder-0.5B-Instruct with a build LoRA, an edit LoRA and a planner LoRA, as GGUF files. On the 180-request
benchmark: 28.3 % fully correct, 88.9 % usable (correct or small fixes).

## v0.2 (released; breaking change)

- One LoRA file on the same base: it writes the outline plan, designs a new thing's parts, edits and talks, all in
  words. Code turns the words into numbers and builds every part in Blender.
- Edits are words that are read back and checked ("make the sofa red", "move the lamp next to the sofa", "make the rug
  bigger").
- Any noun, not a fixed list of names; scene words (room, stack of N, facing, against the wall, under, in the middle).
- Animation by the app's code from the sentence.
- 0.2 drops the 0.1 tool-call route, so lights, cameras, curves, text and modifiers are not in 0.2: the model says so
  instead of guessing. They come back as words in 0.2.1. On the 180-request benchmark 0.2 is below 0.1
  ([docs/BENCHMARKS.md](docs/BENCHMARKS.md)).
- Numbers per job on held-out prompts (outline plan, parts, edit, talk) and the 0.1 demo requests run through the 0.2
  app are in the model card.

## v0.2.1 (next)

- Lights, camera, render, curves, text, modifiers, copies and groups as words: the adapter uses them when making
  ("evening light", "the word Merry on the wall") and when changing ("warmer light", "make it a row of five"); code
  makes the Blender calls.
- One more training round of the adapter.
- Each new group gets its own held-out test prompts; the older numbers may not drop.

## Benchmarks

Tables in [docs/BENCHMARKS.md](docs/BENCHMARKS.md). Still to do, in order:
1. MCP-Universe in an agent loop.
2. The benchmark as an Inspect task, so others can run it.
3. BlenderGym (edit tasks).

## Out of reach for a small offline model

Sculpting by hand, painting textures by hand, photoreal people, film-grade animation. The model card says so.
