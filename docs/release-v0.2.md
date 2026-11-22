# Maris3D 0.2: the model plans in words, code builds the scene

Maris3D 0.2 is a small Blender copilot that runs offline: a 0.5B model plus a Python app and a Blender add-on. You type a sentence; the model answers in plain words (which things, how many, what they
are made of, where they stand); the app's compiler turns the words into Blender tool calls and builds the scene. The model never writes a number: code computes every size and position. It is a
breaking change from 0.1, which wrote tool calls with coordinates, so 0.2 needs the 0.2 app.

## What is new

- **Words, not numbers.** One small word language (things, relations such as *behind* or *on top of*, sizes such as *half* or *double*) replaces tool calls with coordinates.
- **One adapter** (12 MB) for planning, the parts of a new thing, word edits and talk, on the same 531 MB base as 0.1. 0.1 needed an edit adapter and a planner adapter.
- **Edits by words:** "make the table darker", "move the lamp next to the sofa". The model says what changes, code applies it and checks it.
- **Talk:** ask about the scene and it answers from what is there.
- **Animation** ("spin it once over one second", "a ball bouncing twice", "a moon going round a planet") is done by the app's code from your sentence, not by the model.

## The numbers

Held-out sets the model never trained on, scored by outcome through the app's own code:

| What | Result |
|---|---|
| Plan from one sentence: the things named are right | 97.3 % (3,033 things in 716 held-out sentences) |
| the relation is right | 97.0 % |
| the thing it is placed by is right | 95.8 % |
| Parts of a new thing: the answer parses | 99.9 % (1,268 held-out names) |
| the design passes the app's rules | 95.7 % |
| Word edits: the change asked for is the change made | 90.4 % (726 held-out change requests) |
| Talk: the reply is right | 95.8 % (118 held-out talk turns) |
| Talk: things invented that are not in the scene | 0 in 383 turns |

On the 180-request yardstick that 0.1 was scored on, one run: 0.2 is 23.3 % fully correct and 75.0 % usable, against 28.3 % and 88.9 % for 0.1. Animation moves things as asked in 20 of 37 requests.
Full table: [BENCHMARKS.md](BENCHMARKS.md).

## What it cannot do

- **Lights, cameras and text are not in 0.2.** No lights, cameras or text from a plain request yet: the model has no words for them, so it builds a look-alike object (a lamp for "a light", a sign with a blank panel for text) or does nothing. An animation that names a camera or a light ("a camera circling the cube", "a light pulsing") gets a real one from the app's animation code. They are planned for a later version.
- **A follow-up that adds a new thing to a scene that is already built often does nothing yet** (14 of 30 follow-up edits changed the scene in one test).
- **It is not a general tool caller** and is not accurate enough to trust unattended: check the scene in the viewport.
- Trained on English requests, not English only (the Qwen base reads many languages); Blender 5.2 LTS verified; serve with temperature 0, a context of 8,192 and a repeat penalty of 1.05.

More in [SAFETY-AND-LIMITATIONS.md](SAFETY-AND-LIMITATIONS.md).

## How to run it

```sh
git clone https://github.com/slm4apps/maris3d && cd maris3d
pip install -e .
maris3d install        # the add-on into Blender, the base and the adapter, a self-test
maris3d serve start    # one local server on port 9931
```

Then open the sidebar tab **Maris3D Copilot** in Blender's 3D View, type a sentence and press **Run**. Weights: [slm4apps/Maris3D-Blender](https://huggingface.co/slm4apps/Maris3D-Blender).
Details for llama.cpp, Ollama and MCP: [USAGE.md](USAGE.md). 0.1 stays reachable at the `v0.1.0` revision of the same Hugging Face repository and at the GitHub tag `v0.1.2`; see [release-v0.1.md](release-v0.1.md).

## How you can help

Use it on real work and report where it breaks: send the sentence, what you expected and what the panel said. Failures from real work are worth more than another benchmark number.

Everything ships under Apache-2.0: code and weights (the Qwen base is Apache-2.0), docs included. The Blender add-on files that import `bpy` are GPL-3.0-or-later, because Blender's API is GPL.
