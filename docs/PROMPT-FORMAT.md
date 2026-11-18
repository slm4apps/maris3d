# Prompt format and chat template

Maris3D 0.2 does not speak tool calls or JSON documents of tool calls. The model answers in **words**: one small JSON object whose fields take words from closed lists
(`src/maris3d/copilot/vocabulary.py`). The app writes the prompt, reads the answer and compiles it; you normally never see either. This page is for people who call the model
directly.

## The answers
| Role | The model says |
|---|---|
| Outline | `kind` build, question or cannot; for a build the things, how many, what they stand by (`relation`: front_of, behind, left_of, right_of, next_to, between, on_top_of, under, against, around, centre_of), a distance word (touching ... distant), an arrangement (row, ring, grid, stack), size and material words |
| Parts | the parts of one new thing: shape, colour, size words, where each part sits on an earlier part (`on_top_of`, `under`, `inside`, ...) |
| Change | `kind` change, with changes such as `remove`, `recolor`, `scale`, `move`, `turn`, `tilt`, `add`, `copy`, `rename`, or a question, a cannot, or a look |
| Talk | a short reply in words, from the scene the app describes |

Sizes are words (`half`, `double`, `a_bit_bigger`) or a ratio word; a number appears only as the user typed it. Code turns every word into metres, degrees and tool calls
([DSL.md](DSL.md) lists the tools the compiler writes).

## Chat template and decoding

ChatML, as in Qwen2.5. From 0.2.1 the template's default system line (used only when a request has no system message) names the
model: "You are Maris, the Maris3D model by slm4apps. You build and change 3D scenes in Blender from plain words, offline." A request
that carries its own system message, as every app request does, renders exactly as before. Serve with temperature 0, a context of 8,192 and a repeat penalty of 1.05; the app sends the adapter
strength and these values on every request. The Hugging Face repository ships a `Modelfile` for Ollama with the same settings. The system and user prompts are written by the app
(`src/maris3d/copilot/`); they are not a stable public interface, so call the app or the MCP server rather than the model if you can.
