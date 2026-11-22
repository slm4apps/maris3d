# FAQ

**Why words and not Python or tool calls?** Small models write broken Blender code and wrong numbers. Maris3D 0.2's model answers in a small word language (things,
relations such as "behind" or "on top of", sizes such as "half" or "double"); the app's compiler turns the words into correct Blender tool calls and
every size and position is computed by code. The model never writes a number. 0.1 wrote tool calls with coordinates; that is why 0.2 is a breaking change.

**Which files do I need?** The base `maris3d-slm-blender-0.5b-q8_0.gguf` (531 MB, same file as 0.1) and the adapter `maris3d-slm-blender-0.5b-v0.2.2-lora-f16.gguf` (23 MB).
`maris3d install` fetches both. There is one adapter for planning, the parts of a new thing, word edits and talk (0.1 had separate edit and planner adapters).

**Do I need Blender?** Yes, to build the scene (headless is fine). Blender 4.2 or newer; 5.2 LTS is the verified version.

**Can it edit my scene?** It edits scenes the app built: recolour, resize, move, turn, copy, remove, rename, add a part to a thing. Edit by words scored 85.4 % on 726
held-out change requests. One known gap: a follow-up that adds a new thing to a scene that is already built often does nothing yet (in one test
14 of 30 follow-up edits changed the scene). Say it as a new request or press **Undo** and describe the whole scene again.

**Can it animate, add lights, cameras or text?** Simple animation (spin, swing, bounce, grow, shrink, rise, move, orbit, pulse, colour change) is done by
the app's code from your sentence, not by the model. No lights, cameras or text from a plain request yet. From 0.2.2 a change to a built scene can add a camera, a light or a text. An animation that names a camera or a light ("a camera circling the cube", "a light pulsing") gets a real one from the app's animation code.
They are planned for a later version, with no date.

**Can it answer questions about the scene?** Yes, "talk": it answers from what is in the scene (96.1 % right on 152 held-out turns; it invented nothing
in 383 turns).

**Does it work with Blender 4.x?** The add-on needs 4.2 or newer. Only 5.2 LTS is verified.

**Where are the weights and data?** Weights: [slm4apps/Maris3D-Blender](https://huggingface.co/slm4apps/Maris3D-Blender). The training data is not released; see the [data card](DATA-CARD.md).

**Can I use it commercially?** The code and weights are Apache-2.0, like the base model. See [LICENSING.md](LICENSING.md).

**Why is the Blender add-on GPL?** Anything that imports Blender's Python API (`bpy`) is treated as part of a GPL work. Only `src/maris3d/blender/` and the add-on are affected.

**Is this affiliated with Blender?** No. Independent community project; "Blender" is a trademark of the Blender Foundation.

**Why do my results differ from the card?** Check the same files (compare the sha256), temperature 0, context 8,192, repeat penalty 1.05, and that you go
through the 0.2 app. See [BENCHMARKS.md](BENCHMARKS.md).

**Which route should I use: the app, llama-server, Ollama or MCP?** The app drives llama-server or Ollama; the MCP server wraps the same request for MCP clients. See [USAGE.md](USAGE.md).

**Does it work in languages other than English?** It is trained on English requests. The Qwen base reads many
languages: in a small test, simple requests in Spanish, French, German and Chinese built the right things in the right number 8 times in 12 in a small test; English is the most reliable. Voice
input uses an English-only speech model by default; `maris3d install --voice --voice-lang multi` sets up a
many-language one of the same size that detects the language as you speak.

**Can it build from a picture?** Yes, with the optional picture input (`maris3d install --vision`). A small vision
model (SmolVLM 500M) is asked a few short questions about the picture on your machine and closes after each one; the
answers become a short request ("a red ball", "5 brown chairs") that Maris3D builds. It works best on a picture of one
kind of thing; it does not copy a whole scene or its layout.
