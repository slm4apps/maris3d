# Maris (the Maris3D mascot)

A small low-poly girl with a star wand, weaving a little glowing gold toy that is half done; the toy floats beside the wand's star (no thread ties them, so nothing stretches when she moves). There are 6 toys: 3 everyday ones (train, sailboat, teddy) and 3 Christmas ones (tree, snowman, gift). The add-on can fix one toy or pick at random, either a toy that fits the outfit (winter = Christmas) or any toy; a new random toy is picked each time she weaves. She is the face of Maris3D in the
add-on (optional) and on the
landing pages.

| File | What it is |
|---|---|
| `maris.json` | **The contract.** Version, object/rig/collection names, poses (and the still frame of each), faces, outfits, colour slots, skins, hairs. The add-on and the web pages read only this, never hard-coded names. |
| `build_maris.py` | Builds everything from `maris.json` plus the geometry and animation curves. |
| `maris.blend` | Rigged character, one action per pose (`maris_<pose>`), all outfit materials kept. |
| `maris.glb` | All meshes (every mouth and every outfit piece), the rig and all actions, for the web. |
| `*-sheet.png` | Pose, face, outfit, tool, skin and hair sheets for review. |

## Build

```
blender -b --factory-startup -P assets/maris/build_maris.py -- OUT_DIR [--render]
```

Run it on a machine with a free CPU (not the training machine). `--render` also writes one picture per
pose, per outfit and per face (Cycles, CPU, a few minutes). Copy `maris.blend`, `maris.glb` and the
sheets back here.

## How the add-on and the page use it

- **Poses**: play action `action_prefix + pose` on the rig `rig`.
- **Faces**: show the mouth object `prefix + "Mouth" + mouth`, hide the other mouths; move each
  brow `prefix + "BrowL/R"` by `lift` along its stored `face_up` axis and turn it by `tilt`
  degrees (mirrored for R) around `face_front`, from its stored `face_base`. Those three custom
  properties are on the brow objects.
- **Outfits**: every mesh has a `maris_slot` property (its colour slot). Wearing outfit `o` sets
  each mesh's material to `maris_<slot>.<o>` when `o` recolours that slot, else `maris_<slot>`;
  shows the meshes whose `maris_outfit` property is `o`; hides those listed in `o.hide`; hides
  every other outfit's pieces. The current choice is stored on the rig as `maris_outfit`.
- **Pose pieces** (`pose_parts`): some poses swap pieces. Seated pieces carry a `maris_pose`
  property (a comma list of poses) and show only in those poses; `sit` and `sit_seat` hide the
  standing `Dress` so the skirt drapes over the seat (`sit_seat`) or pools on the floor (`sit`).
  `carry`, `run`, `trip` and `crash` hide the wand (stick and star) and the toy; `place` also shows the tool.
  `copilot/show.py` `visible()` is the one rule for all of this.
- **Tools** (`tool` per outfit): the wand, cane, baton or sword she uses to set a carried part
  down. Tool meshes have a `maris_tool` property naming their outfit.
- **Sitting** (`sitting`): `seat_height` is how high the seat is under her hips, `lap_under` how
  far the lap sits below the hip bone. The add-on looks for a seat-like part (chair, bench, stool,
  sofa, ...) near her and sits on it, else she sits on the floor.

## Carry mode (on by default)

When a model adds a stand-alone part, Maris pops up where it appears, lifts it over her head and
dashes to its real spot (leaning forward, arms back), then sets it down with her outfit's tool.
On the way she sometimes phases through things (she flickers), trips over small parts or bumps
into big ones; she always stands on the ground and never ends inside a part. Parts that are
grouped, parented, too big, or arrive in a rush she only watches (turns to look). The switch is
**Carry parts** in the Maris panel. Turning it off, undo, save and load all put every part back
at once. The pure route logic lives in `copilot/show.py` (`carry_choice`, `dash_route`,
`free_spot`) and is tested in `tests/test_maris_carry.py`.

## Colours come from the planner's vocabulary

Every colour in `maris.json` is a colour *answer* the planner and edit model already use: a
vocabulary name (`navy`, `tinsel_gold`, `brass`, ...) with an optional `shade` and `look`, or a
hex. `maris3d.copilot.show.maris_material` turns an answer into the same material the
scene executor makes, so Maris never needs a colour the models cannot say.

- **Slots** (`slots`): skin, hair, brow, dress, bodice, band, gold, eye, cheek, wood, fur, brass.
  Each mesh's `maris_slot` names its slot.
- **Skins** (`skins`, default `light`): light, skin, peach, tan, caramel, mocha.
- **Hairs** (`hairs`, default `golden`): golden, wheat, honey, cinnamon, chocolate, charcoal,
  silver_grey. Each sets both the `hair` and the `brow` slot.

## Designs (what users pick and save)

A design is `{label, outfit, skin, hair, colours: {slot: answer}}`. The three outfits are the
shipped designs (`sea`, `winter`, `conductor`, `ninja`); `copilot/show.py` (`all_designs`,
`save_user_design`, `delete_user_design`) adds the user's own, kept in `maris-designs.json` in
the extension's user folder. A saved design never overwrites a shipped name.

In Blender the **Maris** sub-panel (collapsed by default) sits under the Copilot panel. Its
header checkbox is the on / off switch. Inside: the design picker, Say hi, Clear messages, the
switches (fun finish, effects, maris in renders, off by default), and a customise form (outfit,
skin, hair and any slot's colour, shade and look from the vocabulary) with Save, Undo changes
and Delete. The maris and messages are never saved into the user's file and never count as
scene content for the models.

## Upgrading (keep it boring)

1. Change `maris.json` for anything other code reads (a new pose name, face, outfit, skin,
   hair or slot colour). Colours must be vocabulary answers (see above).
   Change `build_maris.py` for geometry or animation curves (a new pose needs an entry in
   `SEQUENCES`, a new outfit piece needs a line in `build_outfits`).
2. Bump `version`: patch for looks only, minor for new poses / faces / outfits, major when a name
   the add-on or the page uses is renamed or removed.
3. `python3 -m unittest tests.test_maris_spec tests.test_maris_carry` (checks the spec against the build script).
4. Rebuild with `--render`, look at the sheets, then commit the spec, script, `.blend`, `.glb`
   and sheets together.

Never rename an existing pose, face, outfit or object in a minor version: old saved scenes and
recorded replays refer to them by name.

## Outfits

| Outfit | Look | Fits |
|---|---|---|
| `sea` (default) | dawn-teal dress, gold headband | everything |
| `winter` | red wool dress, white fur hem, pointed cap with a pom-pom | the Christmas library |
| `conductor` | navy coat, brass buttons, peaked cap with a badge | the station library |
| `ninja` | charcoal suit, hood and mask (eyes showing), crimson head band and sash, sword on her back; always restless when idle | everything |

Licence: GPL-3.0-or-later (the script) like the add-on; the produced files follow the add-on.
