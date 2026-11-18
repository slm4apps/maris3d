# Prompting guide — Maris3D-SLM-Blender-0.5B v0.1

Read this before typing into the **3D View › Sidebar › Maris3D Copilot** panel. It lists what
this model + copilot can be asked for, one copy-pasteable example per capability, and — where the
repo measured a failure — the failure itself.

**Scope and honesty rule.** Every claim below carries the file that measured it. If a capability
exists in the tool schema but no run measured the model using it, the entry says **untested**. The
tool set is `src/maris3d/copilot/data/TOOLS.json` (26 tools, the exact manifest the model was
scored with — `copilot/protocol.py:44-49`). The model is 0.5B and early: 49/180 fully correct, 136/180 usable on the frozen yardstick with the shipped base + edit adapter (the merged single-file fallback: 35/180 and 139/180) (`README.md`, "Scores").

Prompts that name a recipe are the repo's canonical prompt text. Where the recipe applies scale or
rotation as a *separate deterministic row* (`gen_groups.py:658-662`), the example splits it into a
second prompt; that two-prompt form is the sidebar translation, not a verbatim run, and is labelled
where it matters.

Wording used below matches the panel: the prompt box, the **Run / Build / Apply edit** button, the
**Auto / Build / Edit** switch, the expandable `Copilot Prompt` text block, and one-step **Undo**
(`src/maris3d/addon/__init__.py:45, 201, 329-331, 390-396`).

**Two ways to ask.** Section 0 is the short way: a sentence about things and where they stand
(plan first). Sections 1 to 13 are the exact way: one primitive per prompt with its numbers, sent
to the model alone (the **Build** / **Edit** buttons, or a server without the planner). The "say
this, not that" table and the limits in section 13 describe the model alone.

Two behaviours of the harness matter more than any phrasing rule:

1. **One request = one undo step**, however many model calls it took (`copilot/loop.py:48-52`).
2. **Your words choose which tools are offered.** The request gets `add_primitive`, every tool whose
   keyword appears in the text, the four edit tools in Edit mode, and two random distractors — never
   all 26 (`copilot/protocol.py:18-40, 56-69`). If the needed word is absent, the needed tool may not
   be on the menu at all.

---

## 0. Plan first: one sentence builds a scene

This is what **Auto** does in the panel when the server has the planner adapter loaded (the
default after `maris3d install`), and what `build_scene` does over MCP. You name things and
say where they stand **in words**; nobody types a coordinate.

```
A small train station: a platform, a station building behind the platform, a track in front of
the platform, a train on top of the track, two benches on the platform and four lamp posts in
front of the platform, close to it
```

What happens to that sentence:

1. **The planner** (a 5.6 MB adapter, `maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf`) answers with a
   list of things in words only: which thing, how many, what it stands by, which side, how far. It
   never writes a number.
2. **Code** turns the words into metres: a built-in table gives the parts of each thing, the
   compiler places every part.
3. **The edit adapter** makes each part from that exact instruction (four parts per request).
4. **A check** reads every part back from Blender and corrects what the model got wrong. The
   panel then says what was built, for example `10 of 39 parts exact from the model, 29 corrected`
   (`still wrong` is shown when a correction did not hold).

Follow-up sentences that were run in the same scene:

| sentence | answered by |
|---|---|
| `a tree next to the station building` | planner, then build |
| `put a suitcase next to the bench, very close` | planner, then build |
| `a snowman in front of the track, 2 metres away` | planner, then build (the distance becomes a distance word) |
| `3 gifts next to the snowman in a row` | planner, then build |
| `a man and a woman next to him on the platform` | planner, then build |
| `move the snowman to the left of the tree, close to it` | code alone: a thing the scene has is moved by words, no model |
| `shift the tree behind the station building` | code alone |

### The words the planner knows

- **Things (40):** armchair, art, bench, bin, boy, bus, cabin, car, cat, chair, counter,
  floor_lamp, gift, house, kitchen_run, lamp, lamp_post, man, plant, platform, rug_group, shelf,
  sledge, snow_truck, snowman, sofa, squirrel, station_building, stove, suitcase, table,
  townhouse, track, train, tree, tv, van, waiting_lamp, woman, wreath. Say them as plain words
  ("a lamp post", "the station building").
- **Where:** in front of, behind, left of, right of, next to, between, on top of, under, against,
  around, in the centre of.
- **How far:** touching, very close, close, a medium distance, far (seven steps from `touching` to
  `distant`). A stated distance such as "2 metres away" is read as the nearest step, not as 2.00 m.
- **Arrangements for several of one thing:** in a row, in a ring, in a grid, in a stack.
- **Colours and materials:** black, brass, brick, cream, green, metal, navy, oak, pine, red, rust,
  snow, teal, terra, timber, walnut, white.

### Changes by words, done by code

- **Move:** `move the <thing> next to / behind / to the left of the <other thing>` (both must be
  in the scene).
- **Finish:** `make the <thing> smooth`, `merge the head and the body of the cat` (one skin over
  the parts), `make the cup hollow` (an open-top box, cylinder or cone only).
- Any other change (`make the bench red`, `scale the tree`) goes to the edit model as before:
  sections 6 and 9.

### Limits of plan first

- **Only the 40 things above.** The planner was measured on 300 held-out sentences: the stated
  relation is right in 98.6 %, the thing a part is placed by in 87.3 % (98.5 % when every name in
  the sentence is one it trained on). A name it did not train on is often written wrong
  (`cabin` became `cabine`); the request then falls back to the plain model and the panel says
  `no usable plan`.
- **The model copies parts imperfectly.** About 6 of 10 parts are exact as the edit adapter
  makes them (283 of 448 in the part-by-part test); the check corrects the rest. Read the panel
  line: `still wrong` means a part is not where the plan put it.
- **A change is not checked.** After a recolour, a resize or a move by the edit model nothing
  reads the scene back in v0.1.
- **It needs the planner on the server.** A merged single file or Ollama has no planner: Auto then
  sends the sentence to the model alone, and everything from section 1 on applies.
- A sentence that already states its numbers (`Add a cube named Seat at 0, 0, 0.45.`) skips the
  planner and goes straight to Build.

---

## Quick reference — say this, not that (the model alone)

| Say this | Not this | Because |
|---|---|---|
| `Add a cylinder named Cup at 0.45, 0.15, 0.86 with a radius of 0.10 and a depth of 0.18.` | `add a mug` | There is no "mug". Shape + radius + depth is the measured form: 43 rows, 0.93 ok (`PROMPT-PLAYBOOK.md`, "Overwhelmingly working") |
| `Add a cube named ChairSeat at -1.4, 0, 0.45.` then `Scale ChairSeat to 0.45, 0.45, 0.06.` | `Add a cube named ChairSeat at -1.4, 0, 0.45 with a scale of 0.45, 0.45, 0.06.` | A `scale` clause in a cube build makes the model emit `offset` instead of `location`: **0/78** correct, all at the origin |
| One object per prompt | `make a chair with four legs and a back` | 3+ verbs: **0/7** ok, median 20 calls, 12.0 s (`PROMPT-PLAYBOOK.md`, "How many verbs") |
| `Make Cup red.` in its own turn, object named | `Add a cylinder named Cup and make it red.` | Colour inside a build sentence rebuilds the object (`*.001`) or leaves it white; material=True rows 0.12 vs 0.38 |
| `Move Chair to 0, 1, 0.5.` | `put the chair by the table` | No spatial inference; "on the table" → every part at `0,0,0`; "between" failed four times |
| `Add a cylinder named Wheel1 at 1.95, -12.6, 0.28 with a radius of 0.28 and a depth of 0.2.` then `Rotate Wheel1 by 90 degrees around the Y axis.` | `lay the wheel on its side` | Rotation is numeric only; the angle lands (ledger "rotated part inside an item") but the rotate prompt leaves a duplicate |
| `Add an ico sphere named LampHead at -4.2, -6, 4.35 with a radius of 0.18.` | `Add a UV sphere named LampHead ...` | `uv_sphere` drops the name → object becomes `Sphere`, every later row misses |
| `Add a cube named Book1 at -0.45, 0.10, 0.80.` | `Add a cube named Box.` | No position = origin, and the default is a 2 m cube; two of them swallowed a still life |
| `Add a plane and scatter small stones on it with geometry nodes.` | `make it snow` | Scatter is measured to work; snow is not in the 26-tool set, and "make it snow" produced 65 cubes then 67 planes |
| `Add 5 cubes in a ring.` | `duplicate the chair 4 times down the road` | Ring array works; every clone phrasing failed on both machines, 6 asks |
| `Add the text SLM4 with an extrude of 0.05.` | `write SLM4 on the wall` | Text builds at the origin facing +Z; nothing snaps it to a wall |
| `Join PartA and PartB.` | `Join PartA and PartB into one object named Item1Mesh.` | Join keeps the active object's name; the requested name is ignored |
| `Add a camera at 0, -2.4, 1.55 with a lens of 32.` | `point the camera at the mug` | `add_camera` has no aim argument; the model's rotation misses the subject |
| `Hide Lamp from render.` | `delete the lamp` | There is no delete tool in the 26; "delete" routes to Edit mode but cannot be executed (`addon/routing.py:10-13`; `TOOLS.json`) |

---

## 1. One object per prompt

**The rule.** One build sentence, one object, in one request. Repeat the request for each part.

Why, measured:

| ask shape | result | evidence |
|---|---|---|
| 1 object, literal coordinates | median **1 call, ~2 s**, 0.38 ok over 192 one-verb rows | `PROMPT-PLAYBOOK.md` "How many verbs" |
| 2 verbs in one ask | 0.43 ok over 15 rows, 2.5 calls, 3.0 s — small sample | same |
| 3+ verbs in one ask | **0.0 ok** over 7 rows, median **20 calls, 12.0 s** | same |
| 6 parts, one whole chair (coherent) | 6 calls, 5.9 s, every part correct | measured on the batching run |
| 6 *mixed* parts (dining set) | **56 calls**, repetition loop | `harness/GUIDE.md` rule 1 |
| 6 mixed parts (kitchen) | 8 calls for 6 parts (two duplicates) | same |
| 16 parts, whole dining set | **42 calls**, `TableLeg` emitted 40×, names `.001`–`.041` | `FINDINGS-v1-to-v2.md` batching table |
| 5–8 parts in one turn (scene runs) | 59 and 64 calls, ended as one giant sphere / wrong shapes | |

The safe chunk is **3–4 parts, always exact**; 6 works only when the parts belong to one object;
past 6 the failure is length-like: it repeats the last item instead of stopping (`harness/GUIDE.md`
measured on the same runs).

**Example — the largest prompt that behaved (6 coherent parts, from the chair recipe):**

```
Build the whole chair in one go, all 6 parts in a single reply. Add a cube named ChairSeat at -2.0, -0.4, 0.45. Add a cylinder named ChairLeg1 at -2.245, -0.33, 0.22 with a radius of 0.03 and a depth of 0.45. Add a cylinder named ChairLeg2 at -2.07, -0.645, 0.22 with a radius of 0.03 and a depth of 0.45. Add a cylinder named ChairLeg3 at -1.93, -0.155, 0.22 with a radius of 0.03 and a depth of 0.45. Add a cylinder named ChairLeg4 at -1.755, -0.47, 0.22 with a radius of 0.03 and a depth of 0.45. Add a cube named ChairBack at -2.184, -0.502, 0.72.
```
*Produces:* six `add_primitive` calls, 6.1 s, names and positions exact (`harness/GUIDE.md` rule 1;
the take's own batched rows are in `prompts-take-batched.jsonl`, chunked at 4). *Provenance:* the
6-part chair was measured as "one whole chair"; this exact string is assembled from the take's
canonical part prompts, so treat its success as the measured shape, not a verbatim result.

**Example — the same object split the safe way (four prompts):**
```
Add a cube named ChairSeat at -2.0, -0.4, 0.45.
```
```
Add a cylinder named ChairLeg1 at -2.245, -0.33, 0.22 with a radius of 0.03 and a depth of 0.45.
```
```
Add a cylinder named ChairLeg2 at -2.07, -0.645, 0.22 with a radius of 0.03 and a depth of 0.45.
```
```
Add a cube named ChairBack at -2.184, -0.502, 0.72.
```
*Produces:* one call each, one undo step each. Repeat for legs 3 and 4.

**What not to do.** Do not write "then" and a second build in the same prompt. A build followed by
a build is the multi-part failure, and a repeated build is what creates `*.001`.

---

## 2. Naming — always "named X"

Every build prompt must contain `named <Name>`, and the name must be unique in the whole scene.

| name present? | measured effect | evidence |
|---|---|---|
| yes, for cube/cylinder/cone/torus/ico | name applied, later edits find it | 0.93 on cylinders; `gen_groups.py:651-659` |
| no name on `uv_sphere` | becomes `Sphere`; transform/material/parent rows silently miss | |
| no name on `cone` | becomes `Cone`; group gate failed with `missing: SnowNose, extra: Cone` | |
| no name at all | "the just-created object" is whatever is active; a repair can rename a neighbour instead | `harness/GUIDE.md` rule 3 |
| same name across objects | second becomes `Name.001`; later rows aim at the first | |
| re-issue a name in **Build** mode | `Name.001` is created at default size; v0.1 does **not** reject duplicate names | no rejection in `addon/executor.py` |
| re-issue a name in **Edit** mode | the leading add is filtered out **if the name already exists** | `copilot/loop.py:72-82` |

Naming rules that follow:

- Name by what a person would call it, and make it scene-unique: `HouseWindow1`, not `Window1`
  when a room already owns `Window1`.
- Name parts with an index: `ChairLeg1`…`ChairLeg4` (one shared name produced 40 collisions).
- Never name something `Lamp` if a light is nearby: the word `lamp` also adds `add_light` to the
  offered tools (`copilot/protocol.py:20`). `FloorLamp` was renamed for exactly this collision
  (`PLACEMENT-LAYERS.md` §3).
- If a round object matters, use `ico sphere` — it keeps `name`; `uv_sphere` does not.

**Example:**

```
Add an ico sphere named LampHead at -4.2, -6, 4.35 with a radius of 0.18.
```
*Produces:* `add_primitive(shape="ico_sphere", name="LampHead", location=[-4.2,-6,4.35], radius=0.18)`.

**Example (the name that breaks the next three prompts):**

```
Add a UV sphere named Sky at 0, 0, 40 with a radius of 40.
```
*Produces:* an object called `Sphere` (the `name` argument is dropped, plus `radius2`/`minor_radius`
noise). The follow-up `Make Sky blue.` then targets nothing.

---

## 3. Shapes and their parameters

`add_primitive.shape` accepts exactly: `cube`, `uv_sphere`, `ico_sphere`, `cylinder`, `cone`,
`torus`, `plane`, `monkey`, `circle`, `grid` (`TOOLS.json`). The vocabulary that was measured with
the model is smaller.

| shape | sizing words | what the number means | measured | use it for |
|---|---|---|---|---|
| `cube` | `scale` a, b, c | **half-extents** in metres: a 0.45,0.45,0.06 cube is 0.9 × 0.9 × 0.12 m | position-only 0.87 (21 rows); position **with** scale 0.0 (78 rows) | boxes, slabs, seats, walls, books |
| `cylinder` | `radius`, `depth` | radius in m; `depth` is the **full height** | **0.93** (43 rows, 1 call) | legs, poles, cups, table tops, wheels |
| `cone` | `radius`, `depth` | base radius, full height | 1.0 at exact coords (3 rows, small) | lamp shades, tree layers |
| `uv_sphere` | `radius` | radius | exact position ("a sphere at 2, 0, 1" → `[2,0,1]`) but **name dropped** | never for a named part |
| `ico_sphere` | `radius` (or `scale`) | radius; `scale` is dropped in some asks | position works; `scale` loss on ico is a recorded failure | round parts (lamp heads, leaves, fruit) |
| `torus` | `major_radius`, `minor_radius` | ring radius, tube radius | **0.0** (5 rows; every torus landed at the origin) | handles, rings, wreaths — expect to place it yourself |
| `plane` | `scale` | half-extents; z ignored | 1.0 at exact coords (3 rows, small) | rugs, ground, scatter beds |
| `text` | see `add_text` | `extrude`, `bevel_depth` | works (battery `text`, §2) | signs, greetings, graffiti |
| `monkey`, `circle`, `grid` | — | — | **untested** | — |

Three shape facts that cause most bad prompts:

1. **Cube `scale` is half-size, and the schema never says so** (`PLACEMENT-LAYERS.md` §5.6 "Scale
   grammar"). Twice the number you mean is the default mistake: `scale 1` is a 2 m cube.
2. **The scale clause in a cube sentence is the single biggest phrase-level failure**: 0/78 correct,
   because the model writes `offset` instead of `location`, and `offset` only shifts array copies —
   at `count=1` it does nothing (`dsl/tools.py:99-107`). Cylinders escape because their sizing
   words are `radius`/`depth`.
3. **Torus is the other shape whose sentence contains a sizing clause**: 0/5 landed, same cause
   (`PROMPT-PLAYBOOK.md` "The scale clause").

**Example — cube, two prompts (position, then scale):**

```
Add a cube named TableTop at 0, 0, 0.75.
```
*Produces:* one `add_primitive(cube)` at `[0,0,0.75]`, 2 m default until the next prompt.
```
Scale TableTop to 0.7, 0.5, 0.025.
```
*Produces:* `set_transform(object="TableTop", scale=[0.7,0.5,0.025])` — a 1.4 × 1.0 × 0.05 m slab.
*(The scale edit is measured to land in 1 call — `FINDINGS-v1-to-v2.md` §5.5, "scale 0.5: yes, 1
call". The exact two-prompt pair has not been run as a pair in the sidebar: **untested as a pair**.)*

**Example — cylinder (the one shape to use when you can):**

```
Add a cylinder named TableTop at 0, 0, 0.75 with a radius of 0.7 and a depth of 0.05.
```
*Produces:* `add_primitive(cylinder, radius=0.7, depth=0.05, location=[0,0,0.75])`, 1 call.

**Example — cone:**

```
Add a cone named LampShade at 1.7, 0, 1.6 with a radius of 0.18 and a depth of 0.22.
```
*Produces:* `add_primitive(cone, radius=0.18, depth=0.22)`; 3/3 at exact coordinates
(`PROMPT-PLAYBOOK.md`), but the name can fall back to `Cone`.

**Example — torus (say the numbers, expect to fix the position):**

```
Add a torus named CupHandle at 0.55, 0.15, 0.88 with a major radius of 0.06 and a minor radius of 0.015.
```
*Produces:* a torus, usually at `0,0,0` (0/5, playbook). Follow with `Move CupHandle to 0.55,
0.15, 0.88.` and `Rotate CupHandle by 90 degrees around the X axis.`

**Example — text:**

```
Add the text SLM4 with an extrude of 0.05.
```
*Produces:* `add_text(body="SLM4", extrude=0.05)` at the origin; measured to work (battery `text`,
`FINDINGS-v1-to-v2.md` §2). It arrives facing +Z and at `0,0,0`; you place it yourself. Watch the
bleed: an unasked `bevel_depth: 0.02` was added in one run.

---

## 4. Positioning

**The model's world.** Absolute metres, Z up, no units in the text. `location` is always
`[x, y, z]` and the origin of a primitive is its geometric centre, not its base.

The room the repo measures against (`gen_groups.py:262, 292-296`):

| reference | value | example prompt |
|---|---|---|
| floor plane | `z = 0` (the Floor slab is centred at `z = -0.05`, half-depth 0.05) | `Add a cube named Rug at 0, 0, 0.005.` |
| room extents | x `-4 … 4`, y `-1.5 … 2.6`, walls 2.8 m high, front (`-y`) open | — |
| back wall plane | centre `y = 2.68`, 0.12 m thick → inner face ≈ `2.62` | `Add a cube named Window1 at -2.5, 2.58, 1.4.` |
| wall-mounted things | ~0.03–0.10 m in front of the wall face: windows y 2.58, shelf y 2.35, frame y 2.50 | `Add a cube named Frame at 0.9, 2.42, 1.70.` |
| table top | table surface `z = 0.75 + 0.025 = 0.775`; a cup sits at its own half-height above that | `Add a cylinder named Cup at 0.45, 0.15, 0.86 with a radius of 0.10 and a depth of 0.18.` |

Floor contact means **centre z = half height**, not z = 0: a chair leg of depth 0.45 sits at
`z = 0.22` (`gen_groups.py:171-174`). That is the "everything placed on the ground sank by its centre
of mass" class of bug (`FINDINGS-v1-to-v2.md` §14).

**What happens when position is omitted.** The tool default is `[0, 0, 0]` (`dsl/tools.py:68`), so
the object lands at the world origin at **default size**: a 2 m cube, a radius-1 / depth-2 cylinder.
Measured: position-less cube rows 0/1 graded (`PROMPT-PLAYBOOK.md` "Shape × coordinates"); two
default-size 2 m cubes swallowed a still life; three 2 m ico spheres did the same.
There is no "place it sensibly" fallback.

**Example — absolute position (works):**

```
Add a cylinder named ChairLeg1 at -1.58, -0.18, 0.22 with a radius of 0.03 and a depth of 0.45.
```
*Produces:* the leg exactly there, within 2 cm; 43/43 measured (`PROMPT-PLAYBOOK.md`).

**Example — the position that silently disappears:**

```
Add a cube named ChairSeat at -1.4, 0, 0.45 with a scale of 0.45, 0.45, 0.06.
```
*Produces:* `add_primitive(cube, scale=[...], offset=[-1.4,0,0.45])` and **no `location`** → the seat
is at `0,0,0` (0/78). This is the prompt the take generator used plus a repair row; in the
sidebar there is no repair row, so do not type it.

**Example — wall plane:**

```
Add a cube named Window1 at -2.5, 2.58, 1.4.
```
*Produces:* a 2 m cube embedded in the back wall until you scale it; then
`Scale Window1 to 0.5, 0.025, 0.6.` gives the 1 × 0.05 × 1.2 m pane at the wall face
(`gen_groups.py:216`).

**Not supported, measured:** "on the table", "next to the door", "against the back wall",
"between each lamp". The model never queries existing positions and does no arithmetic — four
separate failures, and layer 4 of the placement stack is deliberately owned by
code, not the model (`PLACEMENT-LAYERS.md` §1).

---

## 5. Rotation

`rotation_deg` is **degrees**, XYZ Euler, right-handed, **Z up** (`dsl/tools.py:70` converts with
`math.radians`). Positive X tips the **+Y end up** — that sign is the roof bug. There is no
"face", "lay flat", "tilt", or "point at" argument on any build tool.

What is measured:

| ask | outcome | evidence |
|---|---|---|
| rotation supplied numerically on a transform row | lands: 90° and ±32° verified, wheels on their side, roof pitch correct | `CAPABILITY-LEDGER.md`, "rotated part inside an item" |
| `Rotate PartC by 90 degrees around the Z axis.` | right angle, but **`duplicate(PartC)` runs first**, leaving `PartC.001`; 21 `set_transform` calls | |
| `Rotate Item1 by 45 degrees around the Z axis.` (parented item) | **machine-dependent**: one machine rotated the empty, another built a new mesh named `Item1` and keyframed it | |
| "face the TV" / "make B face C" | no rotation at all: two `set_transform` + two `set_material` | ledger, "semantic facing" |

So: state the angle and the axis, name the object, and expect a leftover `PartC.001` — the duplicate
comes from `duplicate()`, not `add_primitive`, so the Edit-mode leading-add filter does **not** catch
it, and the repo's fix is a direct `rotation_deg` row, not a prompt. Do not ask for a semantic
orientation.

**Example — a wheel on its side.** A cylinder's axis is Z by default; rotating 90° about **Y** puts
the axis along X:

```
Add a cylinder named Wheel1 at 1.95, -12.6, 0.28 with a radius of 0.28 and a depth of 0.2.
```
```
Rotate Wheel1 by 90 degrees around the Y axis.
```
*Produces:* the wheel standing in the YZ plane with its axle along X, as authored in `gen_groups.py:250`.

**Example — a roof pitch.** Two slabs, opposite signs, pitch derived from span and rise
(half-span 2.2, rise 1.1 → 26.57°; `gen_groups.py:223-227`):

```
Add a cube named RoofA at 6.5, -1.1, 3.55.
```
```
Rotate RoofA by 26.57 degrees around the X axis.
```
```
Scale RoofA to 2.7, 1.233, 0.08.
```
*Produces:* the −Y panel with its eave down and ridge up. The +Y panel needs **−26.57**: swapping the
signs gives a valley with the eaves in the air. This is exactly why the guide tells you to
derive the sign, not to copy a "tilt" word.

**Example — a handle standing up.** A torus lies flat (ring in XY); 90° about X stands it in the
cup's vertical plane:

```
Add a torus named CupHandle at 0.56, 0.15, 0.88 with a major radius of 0.06 and a minor radius of 0.015.
```
```
Rotate CupHandle by 90 degrees around the X axis.
```
*Produces:* an upright ring beside the cup; the flat ring read as "a donut on the table"
(`gen_groups.py:160-163`).

---

## 6. Materials

`set_material` takes `color` (RGB **0–1**, not 0–255), `roughness` (0–1), `metallic` (0–1),
`emission_color` + `emission_strength`, and `alpha`. One material per part, in its own prompt, with
the object named.

Measured:

| ask | outcome | evidence |
|---|---|---|
| `Make Cup red.` (own turn, one object) | applies; battery "material" → `Red` on `Box` | `FINDINGS-v1-to-v2.md` §2 |
| `Make Base, Pillar and Roof grey stone.` | **builds three `*.001` cubes** instead of setting material | |
| `Make TableTop brown and make TableLeg brown.` | builds two default-size cubes + `set_material(object="all")` | |
| colour inside the build sentence | 0.12 ok over 8 graded rows vs 0.38 without | `PROMPT-PLAYBOOK.md` "Material in the same sentence" |
| recolour an already-coloured object | **appends a material slot**; slot 0 stays active, so it may still look red | `dsl/tools.py:199` appends, does not replace |
| emission on an existing object | **works twice** — warm emissive windows and all three lamp heads | ledger, "material emission on an existing object" |
| alpha / transparency | tool accepts it; no model run measured; no blend mode is set | **untested** |
| per-copy colour on clones | impossible before copying: clones share the source material | |

Rules:

- Name **one** object per material prompt. If several need the same colour, repeat the prompt; do
  not list them (that is the shape that triggers a rebuild).
- Material is a separate turn from the build. Inside a build sentence it either rebuilds the object or leaves it white.
- Recolouring is not idempotent: each `set_material` appends a slot. If a part must change colour,
  prefer Undo and re-apply, or accept that slot 0 still wins.
- Emission is a *look*, not illumination: it sets no light, so a "lit" street still casts no light. Ask for a light when you want light.

**Example — flat colour with roughness:**

```
Make Cup red.
```
*Produces:* `set_material(object="Cup", color=[1,0,0], ...)`. Better, with the values the repo uses:

```
Make Cup WhiteGloss with roughness 0.35.
```
*Produces:* `set_material(object="Cup", color=[0.92,0.92,0.90], roughness=0.35, name="WhiteGloss")`
(the palette is `gen_groups.py:12-26`).

**Example — metal:**

```
Make LampStand Brass with metallic 0.8 and roughness 0.35.
```
*Produces:* `set_material(object="LampStand", color=[0.55,0.42,0.18], metallic=0.8, roughness=0.35)`.

**Example — emission (measured to work):**

```
Make HouseWindow1 glow warm yellow.
```
*Produces:* a warm emissive material on the window; verified twice.
For a value, say it: `Make HouseWindow1 glow with emission strength 2.0.`

**Example — the same ask that rebuilds instead:**

```
Make TableTop brown and make TableLeg brown.
```
*Produces:* two new default-size cubes (`TableTop.001`, `TableLeg.001`) plus `set_material(all)`.
Split it into `Make TableTop brown.` then `Make TableLeg brown.`

**Not prompts, code.** Two material looks are produced by direct rows in the take because no prompt
was measured to make them: a **vertical gradient** (`"kind": "gradient"`, 6 rows,
`prompts-take.jsonl:812-814`) and **floor planks** (`"kind": "planks"`, `prompts-take.jsonl:198`).
Asking for "a gradient from brown to cream" or "wooden planks" in the sidebar is **untested**; the
model has only `set_material`, one flat colour at a time.

---

## 7. Batching, grouping and cloning

Three different things, with three different answers.

### 7.1 Asking for N parts in one reply

Allowed and measured to work up to **4 parts**, and up to **6 only when they are one object**; see
§1 for the table. The exact failure modes past that:

- **Repetition loop** — the last part is re-emitted instead of stopping: 16 parts → `TableLeg` 40×
  (`FINDINGS-v1-to-v2.md` batching table); 3+ verbs → 20 calls (`PROMPT-PLAYBOOK.md`).
- **Duplicates** — 8 calls for 6 parts, two names collided in the kitchen run (`harness/GUIDE.md`).
- **Runaway** — 59/64 calls in the scene runs, one giant sphere; the sidebar hard-stops at 20
  calls per request (`copilot/loop.py:30, 95-97`; `USAGE.md`).
- **Name collisions** — auto-suffixed `.001`…`.041`, so later fix rows rename the wrong object
  (`FINDINGS-v1-to-v2.md` batching table).

**Example — a batch that works (4 parts):**

```
Build the whole shelf in one go, all 4 parts in a single reply. Add a cube named ShelfL at 0.7, 2.35, 1.30. Add a cube named ShelfR at 1.3, 2.35, 1.30. Add a cube named ShelfTop at 1.0, 2.35, 1.60. Add a cube named ShelfMid at 1.0, 2.35, 1.40.
```
*Produces:* four `add_primitive` calls, four exact names (chunk-4 rows in `prompts-take-batched.jsonl`).
*Provenance:* the 4-part chunk is the measured unit (`harness/GUIDE.md` rule 1); this string is
assembled from the shelf recipe, not a verbatim run.

### 7.2 Parenting / grouping an existing set

An item is only an item when its parts are under one parent empty (`OBJECT-PIPELINE.md` §2.1). The
model's own grouping is the weakest area:

| ask | measured | evidence |
|---|---|---|
| parent one object | **works**: `Box` → `Rig` verified; call emitted **twice** | battery `parent`; ledger "parent one object" |
| parent several parts to one empty | **machine-dependent**: one machine parented all three; another chained A→B→C, left the empty unnamed, swapped order | |
| join several meshes | merged, but keeps `PartA` and ignores the requested name | |
| move parts into a collection | **works on both machines** | ledger |
| rotate a parented group | **machine-dependent**: one machine rotated `Item1`; another rebuilt it as a mesh | |

`parent` in shipped code preserves world position via `matrix_parent_inverse`, and
`add_empty_parent` exists for the deterministic path. The guide's advice: parent **one child per
prompt**, and create the empty first.

**Example — group an existing set (one child at a time):**

```
Add an empty named ChairRig at -2.0, -0.4, 0.45.
```
```
Parent ChairSeat to ChairRig.
```
```
Parent ChairBack to ChairRig.
```
*Produces:* `add_empty`, then one `parent` call each. The ledger measured `parent` emitted twice for
one target; with two targets expect re-issued calls. Multi-target parenting is **untested as a
reliable behaviour**.

**Example — join:**

```
Join PartA and PartB.
```
*Produces:* one mesh named `PartA` (the active object's name). Rename after: `Rename PartA to Item1Mesh.`
— tested as a copilot repair, not as a prompt pair (**untested as a pair**).

### 7.3 Cloning a piece down a line

This is the clearest "code, not prompt" in the repo. Six clone phrasings were run on both machines
and **all six failed**:

| prompt | what happened |
|---|---|
| `Duplicate Chair and move the copy to 1, 0, 0.5.` | moves the **original**, leaves the copy behind |
| `Make 3 more copies, 0.6 apart.` | **no tool call at all** |
| `Duplicate Chair and rotate the copy 45 degrees around the Z axis.` | rotation becomes `offset` z of 45 on one machine, 120 on another, + 19 `set_transform` |
| `Duplicate Chair as a linked copy at 0, 1, 0.5.` | 7 objects on one machine, no call on another |
| `Duplicate Item1 and place the copy at 0, 2.5, 0.` | invents a new cube named `Copy`/`Duplicate`; no empty, no children |
| `Duplicate it 3 times with an offset of 1.` | one primitive |

The tool `duplicate` also **cannot** express it: it copies one object (not children) with
`original + offset × (i+1)` and has no rotation. `clone_object` was written for this, copies the
subtree, and passes `test_clone_object.py` — but it is **not in `TOOLS.json`**, so the sidebar model
is never offered it. Clone tables in the repo are `"kind": "clone_table"` direct rows (38 of them).

**Example — what to type instead, for a loose row of cubes (the one measured array form):**

```
Add 5 cubes in a ring.
```
*Produces:* 5 cubes on a circle with auto names `Cube.001…` (battery `ring_array`; ledger
"repetition around a ring"). It is a ring, not a line, and the names are not yours.

**Example — the sentence that produces nothing:**

```
Make 3 more copies of Chair, 0.6 apart.
```
*Produces:* no tool call. If you need a line of items in v0.1, build them one at a time with
explicit coordinates, or use the harness's `clone_object` rows outside the sidebar.

---

## 8. Complex objects by decomposition

The model does not know "chair", "mug", "house". It knows shapes, numbers, and one call per step. So
the unit of work is a **recipe**: a base primitive plus a short chain of edits, one object at a time
(`FINDINGS-v1-to-v2.md` §5.1).

The full chain, and who owns each link:

```
human sentence        "make a chair"
      ↓               recipe (slots: shape, name, metres)      gen_groups.py:156-176
recipe
      ↓               canonical prompt                          gen_groups.base_prompt:588-601
build prompt          "Add a cube named ChairSeat at …"
      ↓               copilot, build mode, adapter scale 0.0    copilot/loop.py:45-46
model call            add_primitive(cube, name, location)
      ↓               deterministic fix row (not in the sidebar) gen_groups.py:658-662
placed object
      ↓               deterministic material row                 gen_groups.py:666-668
painted part
      ↓               empty + parent (world-preserving)          gen_groups.py:669-702
item
      ↓               edit prompt, edit mode, adapter scale 1.0  addon/routing.py:23-32
edit                  set_transform / set_material
```

Measured split of responsibility: the model supplies **one call per step** (battery 12/16); the
copilot supplies bookkeeping (names, placement, material, parenting); the planner/adapter supplies
sequence, and is not shipped (`FINDINGS-v1-to-v2.md` §5.2, §10). Asked for a *plan*, the base names
parts and picks shapes correctly — seat/back/legs, trunk/cones, body/pipe/door — but always emits
default `scale [1, 0.5, 0.5]` and `location [0, 0, z]` (maintainers' planner plan, measured). That is why you
supply the numbers.

### 8.1 Worked example: "make a chair"

**Step 0 — decompose it yourself.** Seat (a slab), four legs (cylinders), back (a slab). Six parts.
Do not ask for "a chair".

**Step 1 — seat.** Build at its centre, then scale (never both in one sentence):

```
Add a cube named ChairSeat at -2.0, -0.4, 0.45.
```
```
Scale ChairSeat to 0.45, 0.45, 0.06.
```
*Produces:* a 0.9 × 0.9 × 0.12 m seat at 0.45 m — the recipe in `gen_groups.py:170` with the scale
moved to its own turn.

**Step 2 — four legs.** One prompt each; all four are cylinders, so this shape is reliable at 0.93:

```
Add a cylinder named ChairLeg1 at -2.245, -0.33, 0.22 with a radius of 0.03 and a depth of 0.45.
```
```
Add a cylinder named ChairLeg2 at -2.07, -0.645, 0.22 with a radius of 0.03 and a depth of 0.45.
```
```
Add a cylinder named ChairLeg3 at -1.93, -0.155, 0.22 with a radius of 0.03 and a depth of 0.45.
```
```
Add a cylinder named ChairLeg4 at -1.755, -0.47, 0.22 with a radius of 0.03 and a depth of 0.45.
```
*Produces:* four exact legs; centre z 0.22 = half of 0.45, so they touch the floor.

**Step 3 — back.**

```
Add a cube named ChairBack at -2.184, -0.502, 0.72.
```
```
Scale ChairBack to 0.45, 0.06, 0.5.
```
*Produces:* a 0.9 × 0.12 × 1.0 m back standing from 0.22 to 1.22 m (`gen_groups.py:175`).

**Step 4 — one material per part.** Six prompts, same shape:

```
Make ChairSeat Walnut with roughness 0.8.
```
*Produces:* `set_material(object="ChairSeat", ...)`; repeat with `ChairLeg1`…`ChairBack`.

**Step 5 — make it one item.**

```
Add an empty named Chair at -2.0, -0.4, 0.45.
```
```
Parent ChairSeat to Chair.
```
…then one `Parent <part> to Chair.` per part.

**Result / cost:** 6 build prompts + 2 scale prompts + 6 material prompts + 7 grouping prompts ≈ 21
requests. The take does the same object with 6 model prompts and 14 direct rows (`prompts-take.jsonl`,
`g1-chair*`), because the copilot owns steps 4–5. `PROMPT-PLAYBOOK.md` calls the same shape "slot
filling, not vocabulary".

### 8.2 What decomposition buys, measured

| approach | result |
|---|---|
| 5–8 parts as one sentence | 59–64 calls, wrong shapes |
| per-part prompts, 3–4 per batch | exact every time (`harness/GUIDE.md`) |
| 6-part coherent chair in one reply | 6 calls, 5.9 s, all correct (same doc) |
| 16-part set in one reply | 42 calls, 40 collided names (`FINDINGS-v1-to-v2.md`) |

`gen_groups.py` is the vocabulary that actually works: `("Name", shape, [x,y,z], params, material,
fix?)`, with params `scale` for cube/ico/plane, `radius`+`depth` for cylinder/cone, `major`+`minor`
for torus. Copy its prompt builder, not a thesaurus.

---

## 9. Editing and transforming

The panel's **Auto** mode decides build vs edit with a keyword rule (`addon/routing.py:23-32`):

| your prompt starts with | mode | example |
|---|---|---|
| `Add`, `Create`, `Build`, `Generate`, `Make a…`, `Model`, `Spawn` | **build** | `Make a mug.` → build |
| `Make`, `Move`, `Rotate`, `Scale`, `Rename`, `Delete`, `Set`, `Give`, `Bevel`, `Smooth`, `Join`, `Parent`, `Hide`, … | **edit** | `Make the cube blue.` → edit |
| anything containing `the / this / that / it / selected / existing` **and** a change verb | **edit** | `turn it red` |

In Edit mode the copilot loads the edit adapter (scale 1.0) and **drops a leading `add_primitive`
whose name already exists**, because the adapter always opens by rebuilding the object it was asked
to edit (`copilot/loop.py:72-82`). Force the mode with the switch when Auto guesses wrong.

What each edit is worth:

| edit | prompt | measured |
|---|---|---|
| move | `Move Chair to 0, 1, 0.5.` | works — battery `cube_then_move` → `[0,2,1]` |
| rotate | `Rotate Wheel1 by 90 degrees around the Y axis.` | angle lands; leaves `PartC.001` |
| scale | `Scale ChairSeat to 0.45, 0.45, 0.06.` | works, 1 call (§5.5) |
| rename | `Rename PartA to Item1Mesh.` | tool exists (`set_object`); used as a repair; **untested as a prompt** |
| delete | — | **no delete tool** in the 26; cannot be executed |
| duplicate | `Duplicate Book1 three times with an offset of 0.25.` | fails: one primitive, or wrong-object move |
| material | `Make Cup red.` | works on a named object; appends a slot |
| hide | `Hide Lamp from render.` | `set_object(hide_render)` exists; **untested as a prompt** |
| bevel | `Bevel Box with a width of 0.05.` | works on a fresh object (battery); **silently does nothing in edit phrasing** |
| smooth | `Smooth Blob1.` | `shade_smooth` only; a real rounded shape needs the technique named |

Two edit-side facts the guide must repeat:

- **Every edit response may begin with a rebuild.** The filter catches it only when the name already
  exists; on a fresh name it creates a new object. After the filter, two new failure shapes
  appeared: a turn that emitted *only* the add (→ 0 calls, nothing happened) and turns that looped at
  95 calls (`FINDINGS-v1-to-v2.md` §5.5). The sidebar caps at 20.
- **Bevel in edit phrasing silently does nothing** — the call is emitted, no modifier appears.
  Subsurf works.

**Example — move an existing object:**

```
Move Chair to 0, 1, 0.5.
```
*Produces:* `set_transform(object="Chair", location=[0,1,0.5])`.

**Example — scale after a build (the safe way to size a cube):**

```
Scale Book1 to 0.17, 0.12, 0.03.
```
*Produces:* a 0.34 × 0.24 × 0.06 m book. Measured: scale edit lands in 1 call (§5.5).

**Example — the delete that cannot work:**

```
Delete the lamp.
```
*Produces:* Edit mode, then nothing — no tool in `TOOLS.json` can delete an object. Use Blender's own
selection and X, or Undo the request that created it.

---

## 10. Geometry nodes, scatter and snow

`add_geonodes` exists in the 26 with kinds `EMPTY`, `SUBDIVIDE`, `SCATTER`, `SET_POSITION`,
`UV_SPHERE`. It is not a general node editor: you cannot wire a graph from a prompt.

| capability | prompt | measured |
|---|---|---|
| scatter instances on a surface | `Add a plane and scatter small stones on it with geometry nodes.` | **works** — battery `scatter`; the take's playground uses `SCATTER` density 7.0 with a `GrassClump` instance (`prompts-take.jsonl:395`) |
| subdivide / smooth a solid | `soft rounded shape` / `subdivision or geometry nodes` / `melted wax, no hard edges` | **partial** — the first and third produce `shade_smooth` only; naming "subdivision or geometry nodes" produces a real `SUBDIVIDE` (8 → 26 evaluated verts, proven headless) but **all three rebuilt the cube first**, so the effect landed on a duplicate |
| snow | `Make it snow.` | **fails twice** — 65 cubes in a vertical column, then 67 stacked planes; no particles, no motion |
| a gable / triangle | `Close both ends of the roof with walls.` | **fails twice** — 20 + 21 wall cubes at one x, no triangle, ridge never reached |

Snow and gables are **not model capabilities in v0.1**:

- `snow(name, location, size, count, lifetime, frame_start, frame_end, flake)` exists in
  `dsl/tools.py:50` and is used as a single direct row (`prompts-take.jsonl:908`: 24,000 flakes, size
  140, lifetime 170, frames 700–900), but it is **not in `TOOLS.json`**, so the sidebar model cannot
  call it.
- `gable` is a harness direct row (`gen_groups.py:645-650`), a real 6-vert triangular prism; 28 street
  gables + 2 hero gables in the take. No primitive in the 26 is a triangle.

**Example — scatter (the one measured geonodes prompt):**

```
Add a plane and scatter small stones on it with geometry nodes.
```
*Produces:* `add_geonodes(object=<plane>, kind="SCATTER", ...)` plus instance objects. Works as a
battery check; the density/instance values are not inferred from "small stones" — say them if they
matter.

**Example — snow, if you are running the harness (not the sidebar):**

```
snow(name="SnowFall", location=[0,-60,20], size=140, count=24000, lifetime=170, frame_start=700, frame_end=900, flake=0.055)
```
*Produces:* one emitting plane with 24,000 flakes over frames 700–900 (`prompts-take.jsonl:908`).
Typed into the sidebar, "make it snow" produces geometry, not snow.

**Never ask the model for relative placement.** "Between each lamp", "next to the door", "round the
table" are layer-4 arithmetic; it failed four times, and the repo computes those
positions in the generator instead (`PLACEMENT-LAYERS.md` §1).

---

## 11. Camera, lights, animation, frames and text

These are staging. The repo's own rule is that they are **direct rows, not model turns**
(`FINDINGS-v1-to-v2.md` §9 "Stop doing"; §7 "Never train for the take"), because batching them costs
~0 model seconds and the model gets them wrong. Prompt them anyway if you are in the sidebar — the
tools exist — but expect to fix the framing by hand.

| row | prompt | measured |
|---|---|---|
| camera | `Add a camera at 0, -2.4, 1.55 with a lens of 32 and a rotation of 90, 0, 0.` | tool works; **aim misses the subject** — renders came out through the floor or into a wall. No `aim`/look-at argument exists |
| light | `Add an area light at -2.5, -2.0, 3.0 with an energy of 400.` | tool works (`Add a camera and a sun light.` battery); scenes still render near-black because world colour and light rotation are not set; that prompt shape graded 0.0 (1 row) |
| world | `Set the world colour to dusk blue.` | **0.0** — routed to `set_material` instead of `scene_settings` |
| keyframes (object) | `Add a cube named Box and animate its rotation over 60 frames.` | **works**, 4 calls (battery `animate`; `FINDINGS-v1-to-v2.md` §2) |
| camera animation | `Animate Camera from 0, -2.4, 1.55 to 0, -13, 4.2 over 120 frames.` | **fails** — invents a second camera `Cam` at the origin, keys identical values, travel 0.0 m; left `Camera` static |
| emission cascade | `Light the windows one by one.` | **fails twice** — invents `WindowL`/`WindowR` and keys location, then keys `energy` on a mesh; zero distinct onsets |
| frame end | `Set the frame end to 240.` | `set_frame_end`/`scene_settings` exist; the battery animate row used them (4 calls). **Untested as a standalone prompt** |
| text | `Add the text SLM4 with an extrude of 0.05.` | **works** (battery `text`); sits at the origin facing +Z, and can pick up an unasked `bevel_depth` |

`keyframe` accepts `property` ∈ `location | rotation_deg | scale | lens | energy | emission |
hide_render | color`, with `frame`, `value`/`amount`, `interpolation`. `keyframe(property="emission",
amount=…)` was added for the cascade and proven headless, but the model still did not produce a
cascade — a cascade is **N rows with increasing frame numbers**, never one sentence.

**Example — a camera you will have to aim yourself:**

```
Add a camera at 0, -2.4, 1.55 with a lens of 32.
```
*Produces:* `add_camera(location=[0,-2.4,1.55], lens=32, rotation_deg=[65,0,0])` — the default
rotation looks down at 65°, not at your subject. The take computes the look-at instead
(`"kind": "camera"` with a `target`, `prompts-take.jsonl:909`).

**Example — an object animation (the measured one):**

```
Add a cube named Box and animate its rotation over 60 frames.
```
*Produces:* a cube plus `keyframe(rotation_deg)` at the ends and a frame-end row, 4 calls. Note this
is a **build + animate** sentence that works; the failures are camera paths and material cascades,
not object rotation.

**Example — world colour, the way that fails:**

```
Set the world colour to dusk blue.
```
*Produces:* `set_material` on a mesh (playbook `set` 0.0, 1 row), not a world. Use Blender's World
properties, or the harness `scene_settings(world_color=[0.02,0.03,0.08])` row.

**Example — text on a wall (needs three prompts):**

```
Add the text Merry Christmas with an extrude of 0.012.
```
```
Move Merry Christmas to 3.98, 0.55, 1.72.
```
```
Rotate Merry Christmas by 90 degrees around the X axis.
```
*Produces:* extruded text at a wall position, rotated to face the room (the take's own row is
`prompts-take.jsonl:906`). Text orientation is Euler; there is no "face the wall".

---

## 12. What the model gets wrong

Each row is a measured failure, the prompt that fails, and the prompt that works instead. Issue
numbers are `FINDINGS-v1-to-v2.md`; verdicts are "fails on at least one of two runs"
(`CAPABILITY-LEDGER.md`).

| # | what fails | failing prompt | use instead |
|---|---|---|---|
| 1 | spatial language → all parts at `0,0,0` | `a mug, books and a plant on the table` | `Add a cylinder named Cup at 0.45, 0.15, 0.86 with a radius of 0.10 and a depth of 0.18.` |
| 2 | cube + scale clause → `offset`, lands at origin (0/78) | `Add a cube named ChairSeat at -1.4, 0, 0.45 with a scale of 0.45, 0.45, 0.06.` | `Add a cube named ChairSeat at -1.4, 0, 0.45.` then `Scale ChairSeat to 0.45, 0.45, 0.06.` |
| 3 | torus sizing clause → origin (0/5) | `Add a torus named MugHandle at 0.55, 0.15, 0.88 with a major radius of 0.06 and a minor radius of 0.015.` | build it, then `Move MugHandle to 0.55, 0.15, 0.88.` |
| 4 | `uv_sphere` loses its name → `Sphere` | `Add a UV sphere named Sky at 0, 0, 40 with a radius of 40.` | `Add an ico sphere named Sky at 0, 0, 40 with a radius of 40.` |
| 5 | `cone` name can fall back to `Cone` | `Add a cone named SnowNose at -5.4, -9.8, 1.0 with a radius of 0.04 and a depth of 0.2.` | `Add a cylinder named SnowNose ...` (the recipe's workaround), or repair the name |
| 6 | multi-name material ask → rebuilds `*.001` cubes | `Make Base, Pillar and Roof grey stone.` | `Make Base grey.` / `Make Pillar grey.` / `Make Roof grey.` |
| 7 | colour inside a build sentence → rebuild or white | `Add a cylinder named Cup and make it red.` | `Add a cylinder named Cup ...` then `Make Cup red.` |
| 8 | rotate a single object → duplicate left behind, 21 calls | `Rotate PartC by 90 degrees around the Z axis.` | no prompt form was reliable; the measured path is the copilot's direct `rotation_deg` row. In the sidebar, delete `PartC.001` by hand |
| 9 | rotate a parented group → machine-dependent; may rebuild the empty as a mesh | `Rotate Item1 by 45 degrees around the Z axis.` | rotate the parts before parenting, or use the deterministic row |
| 10 | clone any item → moves original / no call / 45 m offset / invented `Copy` | `Duplicate Chair and move the copy to 1, 0, 0.5.` | build each item at explicit coordinates, or harness `clone_object` |
| 11 | `duplicate` never used for a count | `Add a cube named Box, then duplicate it 3 times with an offset of 1.` | one prompt per cube, or `Add 5 cubes in a ring.` for a circle |
| 12 | multi-part in one prompt → 59–64 calls, wrong shapes | `make a chair with four legs and a back` | six separate part prompts (§8.1) |
| 13 | camera aim → misses subject, black frames | `point the camera at the mug` | `Add a camera at 0, -2.4, 1.55 with a lens of 32.` then aim by hand |
| 14 | world/dark scene | `Set the world colour to dusk blue.` | World properties, or `scene_settings(world_color=[...])` in the harness |
| 15 | camera path → a second camera, 0 m travel | `Animate Camera from 0, -2.4, 1.55 to 0, -13, 4.2 over 120 frames.` | key the camera by hand, or a `keyframe_transform` row |
| 16 | emission cascade → one frame, wrong property | `Light the windows one by one.` | one `keyframe(property="emission", amount=…, frame=N)` row per window |
| 17 | snow → a cube column, then a plane stack | `Make it snow.` | harness `snow(...)` only; not available in the sidebar |
| 18 | relative placement → its own objects at the origin, nothing between | `put a tree between each lamp` | compute the midpoint and give coordinates |
| 19 | gable / triangle → 41 wall cubes, void still open | `the roof is a V shape and both ends are open, close both ends with walls` | harness `gable` row, or two correctly signed slabs |
| 20 | "smooth" → rebuilds the object, smooths the duplicate | `soft rounded shape` / `Smooth Blob1.` | name the technique *and* the target, in Edit mode: `Add subdivision to Blob1.`; expect a duplicate |
| 21 | join name ignored | `Join PartA and PartB into one object named Item1Mesh.` | `Join PartA and PartB.` then `Rename PartA to Item1Mesh.` |
| 22 | per-clone colour impossible before copying | `paint each car a different colour` | paint after copying; clones share the source material |
| 23 | re-add an existing name in Build mode → `Name.001` at default size | `Add a cube named TableTop at 0, 0, 1.5.` (TableTop exists) | edit it: `Move TableTop to 0, 0, 1.5.` (Edit mode) |
| 24 | default size when position is omitted | `Add a cube named Box.` | always give `at x, y, z` — otherwise 2 m at the origin |

Two more measured caveats that are not prompts:

- **The same prompts behave differently on two machines** — parenting and group rotation passed on
  one machine and failed on another. Any single success is a hint, not a guarantee.
- **Scene-level pass ≠ model-level pass**: in the four group scenes all checks passed while the
  model's own cube accuracy was 0/64, hidden by the copilot's `set_transform` (§12 of FINDINGS).
  In the sidebar there is no `set_transform` row after your prompt — which is why §3 and §4 exist.

---

## 13. What this model does not do

From the tool schema (`TOOLS.json`), the docs' measured limits (`docs/SAFETY-AND-LIMITATIONS.md`)
and the failure log:

- **No sculpting, rigging, simulation, texture painting, file import, or node-graph authoring.**
  Fixed set of 26 Blender tools; other tools are guessed.
- **No deletion.** No tool removes an object. `delete` routes to Edit mode and stops there.
- **No scene vision.** It does not see the viewport, renders, or images; it sees only the text and
  the `[Scene objects: …]` line the copilot appends (`copilot/protocol.py:78-95`).
- **No spatial reasoning in the model alone.** No "on", "under", "next to", "between", "facing",
  "against", "centred in the room": four measured failures. Plan first (section 0) reads these
  words for the 40 things it knows.
- **No arithmetic.** No midpoints, divisions, counts derived from a distance, or "space them evenly".
- **No semantic shapes in the model alone.** No chair, mug, house, tree, wheel, handle, roof,
  gable. Only primitives, curves, text and modifiers; complex objects come from your decomposition
  (§8) or from the 40 things of plan first (section 0).
- **No per-copy variation.** Clones share the source material; materials are flat, not
  gradients.
- **No camera aim or camera path.** No `aim`, no look-at; animation of a named camera failed.
- **No material animation cascade** in one sentence.
- **No particles or snow through the sidebar**; snow is a harness-only row.
- **No multi-turn conversation.** v0.1 starts a fresh conversation per request (`README.md`); the
  scene summary travels with follow-ups inside one request, but the next request starts clean. 0/30
  multi-turn sessions were usable.
- **English only; Blender 5.2.2 verified; rows trained up to 2,048 tokens.** 20 tool calls per user
  turn is the trained loop limit.
- **No free design.** Plan first builds the 40 things it has a parts table for; it does not design
  a thing it has never seen. The **Plan** switch in the panel shows the planner's answer and builds
  nothing.

---

## Appendix A — tool → prompt

Every tool in `src/maris3d/copilot/data/TOOLS.json` (26), the prompt that should trigger it, and
whether the model was measured doing it. "Untested" means the tool exists and is offered, but no run
in this repo graded that prompt.

| # | tool | prompt that should trigger it | status |
|---|---|---|---|
| 1 | `add_primitive` | `Add a cylinder named Cup at 0.45, 0.15, 0.86 with a radius of 0.10 and a depth of 0.18.` | **works** for cylinder/cone/plane (0.93 / 1.0); cube only without a scale clause (0.87); torus 0.0 |
| 2 | `add_geonodes` | `Add a plane and scatter small stones on it with geometry nodes.` | **works** for `SCATTER`; `SUBDIVIDE` partial |
| 3 | `add_text` | `Add the text SLM4 with an extrude of 0.05.` | **works**; may add unasked `bevel_depth` |
| 4 | `set_transform` | `Move Chair to 0, 1, 0.5.` | **works** (battery `cube_then_move`) |
| 5 | `add_curve` | `Add a bezier curve with a bevel depth of 0.05.` | **works** (battery `curve_ribbon`) |
| 6 | `add_camera` | `Add a camera at 0, -2.4, 1.55 with a lens of 32.` | builds; **aim fails** |
| 7 | `scene_settings` | `Set the world colour to dusk blue.` | **fails** — routed to `set_material` |
| 8 | `add_empty` | `Add an empty named ChairRig at -2.0, -0.4, 0.45.` | works as part of a grouping ask (create+parent, 2 rows) |
| 9 | `edit_mesh` | `Inset the top face of Box by 0.02.` | **untested** |
| 10 | `add_light` | `Add an area light at -2.5, -2.0, 3.0 with an energy of 400.` | tool works (`Add a camera and a sun light.`); lighting result fails; 0 graded rows |
| 11 | `set_frame_end` | `Set the frame end to 240.` | **untested** as a standalone prompt (used in battery `animate`, 4 calls) |
| 12 | `join` | `Join PartA and PartB.` | works; **requested name ignored** |
| 13 | `keyframe` | `Add a cube named Box and animate its rotation over 60 frames.` | **works** for object rotation; camera/emission cascades fail |
| 14 | `parent` | `Parent Box to Rig.` | **works** one child; call emitted twice; multi-target machine-dependent |
| 15 | `new_collection` | `Create a collection named Tableware and put PartC in it.` | **works on both machines** |
| 16 | `duplicate` | `Duplicate Book1 three times with an offset of 0.25.` | **fails** |
| 17 | `add_modifier` | `Bevel Box with a width of 0.05.` | **works** on a fresh object; bevel in edit phrasing is silent |
| 18 | `add_constraint` | `Make Camera track Empty.` | **untested** |
| 19 | `add_shape_key` | `Add a shape key named Smile to Sphere.` | **untested** |
| 20 | `uv_unwrap` | `Unwrap Box with smart project.` | **untested** |
| 21 | `set_material` | `Make Cup red.` | **works** named/one object; multi-name rebuilds; recolour appends a slot |
| 22 | `add_empty_parent` | `Add an empty named Chair and parent the seat and back to it.` | **untested** as a prompt; the copilot uses it as a direct row |
| 23 | `set_object` | `Rename PartA to Item1Mesh.` | **untested** as a prompt; proven as a repair |
| 24 | `shade_smooth` | `Smooth Blob1.` | works as *shading only*; a rounded shape needs `SUBDIVIDE` |
| 25 | `apply_modifier` | `Apply the bevel on Box.` | **untested** |
| 26 | `apply_transform` | `Apply the scale on PlayGround.` | **untested** as a prompt; used as a direct row (`prompts-take.jsonl:393`) |

Not in `TOOLS.json`, therefore not askable in the sidebar: `clone_object` and `snow` (both in
`dsl/tools.py`, harness only), and the `gable`/`planks`/`gradient`/`clone_table` direct-row kinds
(`gen_groups.py`, `gen_take.py`). Those are code paths, not model capabilities.

---

## Appendix B — where each claim comes from

File names cited in this guide that are not in this repository (`PROMPT-PLAYBOOK.md`, `CAPABILITY-LEDGER`, `gen_groups.py` and the other maintainers' notes below) are the maintainers' working files: the measurements were taken from them and they are not published.

| source | what it settles |
|---|---|
| maintainers' prompt playbook (not published) | phrasing pass rates, call counts, seconds, scale-clause effect (217 labelled turns) |
| maintainers' capability ledger (not published) | per-capability verdict: model vs copilot, both machines |
| maintainers' v1-to-v2 findings log (not published) | issue log, batching table, per-object recipe, edit-chain measurement |
| maintainers' known-failures log (not published) | 180-prompt guard run: 39 PASS / 85 PARTIAL / 56 FAIL; edit is the weakest mode (15/30 unparsed) |
| maintainers' internal results note (not published) | internal-only arms; not public, not used for any claim here |
| maintainers' harness guide (not published) | chunk size 4, sweep/miss behaviour, direct rows |
| maintainers' planner plan (not published) | base names parts/shapes but invents no size or position |
| maintainers' object pipeline checklist (not published) | per-object checklist, 13-row verification matrix |
| maintainers' placement layers note (not published) | the five placement layers, scale-as-half-extents gap, corrections |
| maintainers' prompt generator (not published) | the prompt template and the recipe numbers used in every example |
| maintainers' take prompt sequence (not published) | the actual prompt/direct-row sequence of the take |
| `src/maris3d/copilot/data/TOOLS.json` | the 26-tool ground truth, parameters and enums |
| `src/maris3d/copilot/protocol.py` | tool trimming by keyword, scene summary, 20-call budget |
| `src/maris3d/copilot/loop.py` | edit filter, adapter scale 0/1, one-request-one-undo |
| `src/maris3d/addon/routing.py` | Auto build/edit keyword rule |
| `src/maris3d/dsl/tools.py` | parameter semantics (`scale` half-extents, `offset` dead at count 1, material append) |
| `README.md`, `docs/SAFETY-AND-LIMITATIONS.md`, `docs/USAGE.md` | scores, hard limits, 26 tools, 20 calls/turn, English only |

**Claims deliberately marked untested:** alpha/transparency from a prompt; the cube
"build-then-scale" pair as a run pair; rename/hide/constraint/shape-key/UV/edit-mesh/apply-modifier
prompts; compass words ("north of") in plan first; per-copy material variation through a prompt.
