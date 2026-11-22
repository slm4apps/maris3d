# Data card (training data; not released)

The training data and the pipeline that makes it are private to the maintainers and are not part of this repository. This card says what kind of data the adapter learned from, so results can be judged.

## What a row is
A pair (user request or scene description, assistant answer) where the answer is in **words** in the 0.2 word language: an outline of things and their places, the parts of one new thing, a word edit,
or a reply to a question. Text-only conversations: no images and no code from Blender itself. The requests are synthetic and written in English; the Qwen base reads many languages: simple requests in Spanish, French, German and Chinese built the right things in the right number 8 times in 12 in a small test. (0.1's rows were tool calls with coordinates.)

## How it is judged
Each result in [BENCHMARKS.md](BENCHMARKS.md) section 2 comes from a held-out set: sentences, names and change requests the adapter did not train on, scored by outcome through the app's code.

## Known limitations of the data
- Mostly machine-written requests, not real users': wording is more regular than real use. Send failed prompts (issue form "Failed prompt"): they are the most useful input we get.
- A passing check means the scene has the requested things, counts and sizes, not that it looks good.
- Things outside the vocabulary (lights, cameras, text) are not in the data; asked for one, the model builds a look-alike object or does nothing.

## Personal data
No personal data is intended in the rows (they are synthetic requests).
