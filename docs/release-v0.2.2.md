# Maris3D 0.2.2: more change words, exact adds by code, voice input

Maris3D is a small Blender copilot that runs offline: a 0.5B model plus a Python app and a Blender add-on. You type (or now say) a sentence; the model answers in plain words; the app's
compiler turns the words into Blender tool calls and builds the scene. The model never writes a number: code computes every size and position. 0.2.2 needs no new base file: update the app, then `maris3d update`
fetches the new 23 MB adapter.

## What is new

- **A new adapter**, `maris3d-slm-blender-0.5b-v0.2.2-lora-f16.gguf` (23 MB), on the same 531 MB base. It knows more change words: camera (looks at a thing, from front, back, left, right or
  above), light (sun, lamp, spot or soft; dim, normal or bright), text, retext, attach, aim, finish (bevel, subdivide, thicken, wire, mirror, array, taper, bend, twist) and scene (background
  colour, length, frame rate). The app tells the model which cameras, lights and texts are in the scene, so a change can name them; `MARIS3D_KIT_WORDS=0` turns the new words off.
- **Exact adds are read by code.** "Add a cube named Path at -1, 0, 0 with a scale of 0.4, 2.0, 0.01" (and the same with a radius and depth, a major and minor radius, or a rotation) is built from
  the numbers as written, without asking the model. A sentence that asks for more than that still goes to the model.
- **Undo by voice or text:** "undo", "undo that", "go back" or "revert it" undoes the last request.
- **Voice input:** a mic button next to the prompt. Speech becomes text on your machine (whisper.cpp with a small English model). Set it up with `maris3d install --voice`; it needs a sound recorder
  (sox, ffmpeg, ALSA's `arecord`, or Windows' own).
- **Maris, the mascot,** behaves more like she lives in the scene: sized like a person, carries parts in from the edge of the ground, keeps facing what she placed, runs to a chair before she sits,
  carries a whole group when a request moves it. **Follow Maris** (off by default) lets the view drift after her.

## The numbers

Held-out sets the model never trained on, scored by outcome through the app's own code (0.2.2):

| What | Result |
|---|---|
| Plan from one sentence: the things named are right | 97.3 % (2,951 of 3,033 things in 716 held-out sentences) |
| the relation is right | 97.1 % |
| the thing it is placed by is right | 95.9 % |
| the whole sentence is planned right | 84.1 % (602 of 716) |
| Parts of a new thing: the answer parses | 99.9 % (1,268 held-out names) |
| the design passes the app's rules | 99.0 % |
| Word edits: the change asked for is the change made | 85.4 % (726 held-out change requests) |
| Talk: the reply is right | 96.1 % (152 turns); 96.5 % (231 turns, a second set) |
| Talk: things invented that are not in the scene | 0 in 383 turns |
| Long sentences that join several groups of things: the whole plan exact | 40.0 % (60 held-out sentences) |
| The 0.1 demo scene, its 204 exact adds through the 0.2.2 app (read by code): built exactly | 99.5 % (203 of 204) |

With the new change words in the prompt (150 held-out rows each): the whole sentence planned right 82.0 %, parts pass the app's rules 100 %, talk right 96.7 %.
Every set for 0.2.1 and 0.2.2 side by side, and what each test measures: [BENCHMARKS.md](BENCHMARKS.md).

## What it cannot do

The limits of 0.2 still hold; see [release-v0.2.md](release-v0.2.md) and [SAFETY-AND-LIMITATIONS.md](SAFETY-AND-LIMITATIONS.md). No lights, cameras or text from a plain request yet; from 0.2.2
a change to a built scene can add a camera, a light or a text.

## How to run it

Install in one command (no clone needed):

- macOS / Linux: `curl -fsSL https://raw.githubusercontent.com/slm4apps/maris3d/main/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/slm4apps/maris3d/main/install.ps1 | iex"`

Already on 0.2.x? Re-run the one-line install (or `pip install -U git+https://github.com/slm4apps/maris3d`) for the 0.2.2 app, then `maris3d update` for the 23 MB adapter. For voice input: `maris3d install --voice`. Then `maris3d serve start`, open the sidebar tab **Maris3D Copilot** in Blender's 3D View, type a sentence and
press **Run**, or press the mic button and say it. Weights: [slm4apps/Maris3D-Blender](https://huggingface.co/slm4apps/Maris3D-Blender). Details: [USAGE.md](USAGE.md).

0.2.1 stays at the GitHub tags `v0.2.1` / `v0.2.1.1` and at the `v0.2.1` revision of the Hugging Face repository; 0.1 at the GitHub tag `v0.1.2` and the `v0.1.0` revision ([release-v0.1.md](release-v0.1.md)).

## How you can help

Use it on real work and report where it breaks: send the sentence, what you expected and what the panel said. Failures from real work are worth more than another benchmark number.

Everything ships under Apache-2.0: code and weights (the Qwen base is Apache-2.0), docs included. The Blender add-on files that import `bpy` are GPL-3.0-or-later, because Blender's API is GPL.
