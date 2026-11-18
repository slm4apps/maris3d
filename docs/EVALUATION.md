# Evaluation guide

## What is measured
- **Held-out sets** (BENCHMARKS.md section 2): sentences, names and change requests the adapter never trained on, each scored by outcome through the app's own code: the things named, the relation,
  the thing a part is placed by, whether a parts design parses and passes the app's rules, whether a word edit made the change asked for, whether a talk reply is right and whether it invents things
  that are not in the scene.
- **The 180-request yardstick** (BENCHMARKS.md section 1): 180 frozen Blender requests in seven modes (single objects, multipart objects, edits, animation, arrays and rings, parenting, geometry
  nodes). Each request is run in Blender and the finished scene is judged against a per-request checklist, not by whether the output parses. **Pass** = fully correct; **usable** = pass, or correct
  with small fixes. They are always reported separately, never blended. The request set stays with the maintainers while a public benchmark is prepared.
- **External benchmarks** (0.1 only, section 3).

## Rules for comparable numbers
1. Say what was used: the files and their sha256, the app version, the runtime, Blender version, the settings (temperature 0, context 8,192, repeat penalty 1.05).
2. Score the scene, not the text of the answer.
3. Do not tune on the benchmark; it was used to choose between our own models, so it is not a fresh test set.
4. Report pass and usable separately and say how many runs the figure comes from.

## Running the scripts
`eval/maris3d_eval/run_eval.py` is the runner for the earlier 206-prompt set and the tool-call format of 0.1; it does not drive the 0.2 words path. To judge 0.2, send requests through the app (the panel or
`scene_request` over MCP) and read the scene afterwards. `eval/result_schema.json` is the schema of a public result file.

## Known caveats
- A passing check means the scene has the requested things, counts and sizes, not that it looks good.
- One run per figure: the yardstick figures are single runs, so small differences are within noise.
- Most requests in the sets are machine-written, so their wording is more regular than real use.
