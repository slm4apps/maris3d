# Safety and limitations

## What can go wrong
- **Generated scenes run as Python inside Blender.** The model never writes code or numbers: it answers in words and the app's compiler writes the tool calls from a fixed tool set
  (see [DSL.md](DSL.md); unknown arguments are ignored). Blender still runs with the permissions of the user who starts it. Use a scratch session, do not run it where Blender can touch
  important files, and keep the MCP and live ports on localhost.
- **Resource use.** The tools can build large meshes (arrays, subdivision, booleans). The live add-on removes modifiers and objects that would push a scene past 100,000 faces per
  object or 400,000 in total.
- **No safety training.** The model was not trained to refuse; content is limited by what the tools can express.
- **A passed check is not a good-looking scene.** "Checked" means the scene satisfied the requested things, counts and sizes, not that it looks right.

## What it cannot do (0.2)
| Limit | Evidence |
|---|---|
| Fully correct on the 180-request yardstick: 23.3 %, usable 75.0 % (0.1: 28.3 % / 88.9 %); one run. 0.2 is not better than 0.1 on that set | [BENCHMARKS.md](BENCHMARKS.md) section 1 |
| Animation: 20 of 37 animation requests on the yardstick moved things as asked | same |
| A follow-up that adds a new thing to a scene that is already built often does nothing yet: 14 of 30 follow-up edits changed the scene | same |
| Word edits: 90.4 % of 726 held-out change requests did the change asked for | [BENCHMARKS.md](BENCHMARKS.md) section 2 |
| No lights, cameras or text from a plain request: a look-alike object or nothing (an animation that names a camera or a light gets a real one) | [FAQ.md](FAQ.md) |
| Not a general tool caller: it was trained for Blender scenes only (0.1 scored 49.25 % on BFCL v4 simple_python; 0.2 was not run on it) | [BENCHMARKS.md](BENCHMARKS.md) section 3 |
| No sculpting, rigging, simulation, node-based shaders beyond the basics, or file import | [DSL.md](DSL.md) |
| English only; Blender 5.2 LTS verified; a context of 8,192 tokens | [USAGE.md](USAGE.md) |

## Responsible use
Do not present generated scenes as manually crafted work if that matters in your setting, and check licences of any asset you combine with them.
Report vulnerabilities as described in [SECURITY.md](../SECURITY.md).
