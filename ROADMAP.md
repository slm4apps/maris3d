# Roadmap

Maris3D is the small language model (SLM) for Blender. The goal of the 0.x line is that you can do the things people do
in Blender by typing what you want, offline, with a small model.

How it is built:
- The model says *what* in words; code turns the words into numbers and Blender calls.
- Every version covers **every feature group** at some level. Each version deepens the groups and never drops one.
- Every group has its own held-out set of test prompts. Its numbers are published for every version, next to the
  earlier ones, including the numbers that went down.

Versions are git tags and Hugging Face revisions; each promotion adds a row to `release/HISTORY.md`.

## Feature groups by version

Level in each version (0.1 is released, the later columns are plans):

| Feature group | 0.1 (released) | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 -> 1.0 |
|---|---|---|---|---|---|---|
| **Objects** ("a wooden chair") | built from primitives by tool calls; about 40 named things built part by part from a plan | a planner designs any object as parts; code builds them | more shapes per part (tapered, turned, bent) | figures and animals as objects | your own objects used as parts | all common objects pass their test set |
| **Scene layout** ("a rug, a chair beside it, gifts stacked") | one sentence is planned into named things with places | scene words: room, stack of N, facing, against the wall, under, in the middle | rooms with walls, windows and doors | characters placed in the scene | big scenes in zones (a village, a whole station) | |
| **Edits** ("make the chair red, move it left") | an edit adapter fixes and changes the scene | edits in words, read back and checked; "a chair" adds, "the chair" changes | edits to looks, light and camera | edits to poses and motion | edits across zones | |
| **Materials and looks** ("brass", "old wood") | colour, roughness, metal, glow, see-through | 147 colour names, shade, finish, gradient | wood, metal, glass, fabric, knitted, stripes, dots (procedural materials) | | images as labels and decals | |
| **Lights and world** ("evening light") | point, sun, spot and area lights | lights as words (planner and edit) | moods: morning, evening, night, studio, lamp glow; sky colour | lights that follow the action | | |
| **Camera and render** ("a close-up of the chair") | add a camera, render settings | the view frames what was built | shots: wide, close-up, from above, orbit; render size and quality | camera follows a character | | |
| **Object animation** ("the gift spins") | keyframes on objects, frame range | keyframes as words (planner and edit) | spin, bob, sway, pulse, move to, follow a path, flicker | timelines of several steps ("then") | | |
| **Characters** ("a small doll in a teal dress") | not yet | not yet (test set recorded as a baseline) | still figures from parts: doll, snowman, teddy, cat, dog, simple person | rigged characters | | |
| **Character motion** ("she walks to the chair and sits") | not yet | not yet | | poses and actions: stand, sit on, wave, point, walk to, hop, dance, hold | | |
| **Shape tools** ("round the edges", "a row of 10") | modifiers, shape keys, edit mesh, join, duplicate | modifiers as words (planner and edit) | bevel, array, mirror, hollow, smooth | | cut a hole, extrude, inset, taper, twist | |
| **Curves, text, procedural** ("a rope from the lamp to the chair") | curves, text, geometry nodes, snow | as words (planner when making, edit when changing) | | | ropes, cables and pipes between things; text on things; scatter (grass, snow, stones) | |
| **Physics** ("drop the gifts on the floor") | not yet | not yet | | drop and settle, cloth over a thing, falling snow | | |
| **Your own things** ("use my model as the table") | works on the open scene (add-on, MCP) | the planner is told what the scene holds | | | your selected objects as parts or anchors; export glb / fbx / usd | |
| **Talk and help** ("what can you do?") | answers with tool calls only | short messages in the scene, asks back when a word is unknown | explains what it built | | | Blender how-to answers from an offline help index |
| **Big scenes** | small scenes (a street, a station) | | | | zones | |
| **Product** | add-on, MCP server, Ollama, GGUF files | one planner + one edit adapter; update from 0.1 | | | | model size reviewed with measured numbers (smaller is the aim) |

A blank cell means the level of the column before it carries on.

## v0.1 (released)

Qwen2.5-Coder-0.5B-Instruct with a build LoRA, an edit LoRA and a planner LoRA, as GGUF files. On the 180-request
benchmark: 27.2 % fully correct, 75.6 % usable (correct or small fixes). Limits are in the README.

## v0.2 (next; breaking change)

- One planner writes the outline and the parts of each thing; code builds the parts directly in Blender.
- Edits are words that are read back and checked.
- Any noun, not a fixed list of names.
- Scene words (room, stack of N, facing, against the wall, under, in the middle) and new test sets for scenes, edits and
  characters (characters as a baseline).
- No group falls below its v0.1 level: every v0.1 tool becomes words the planner and the edit adapter use; there is no separate build model.
- Ships only when it rebuilds the v0.1 demo scene; the 180-request numbers of 0.1 and 0.2 are published side by side.

## Benchmarks

Tables in [docs/BENCHMARKS.md](docs/BENCHMARKS.md). Still to do, in order:
1. MCP-Universe in an agent loop.
2. The benchmark as an Inspect task, so others can run it.
3. BlenderGym (edit tasks).

## Out of reach for a small offline model

Sculpting by hand, painting textures by hand, photoreal people, film-grade animation. The model card says so.
