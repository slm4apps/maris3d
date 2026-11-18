# Maris (the Maris3D mascot)

A small low-poly girl who weaves a glowing gold thread into a little toy that is half done (the thread runs into the part she is weaving). There are 6 toys: 3 everyday ones (train, sailboat, teddy) and 3 Christmas ones (tree, snowman, gift). The add-on can fix one toy or pick at random, either a toy that fits the outfit (winter = Christmas) or any toy; a new random toy is picked each time she weaves. She is the face of Maris3D in the
add-on (optional) and on the
landing pages.

| File | What it is |
|---|---|
| `maris.json` | **The contract.** Version, object/rig/collection names, poses (and the still frame of each), faces, outfits, colour slots, skins, hairs. The add-on and the web pages read only this, never hard-coded names. |
| `build_maris.py` | Builds everything from `maris.json` plus the geometry and animation curves. |
| `maris.blend` | Rigged character, one action per pose (`maris_<pose>`), all outfit materials kept. |
| `maris.glb` | All meshes (every mouth and every outfit piece), the rig and all actions, for the web. |
| `*-sheet.png` | Pose, face, outfit, skin and hair sheets for review. |

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
shipped designs (`sea`, `winter`, `conductor`); `copilot/show.py` (`all_designs`,
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
3. `python3 -m unittest tests.test_maris_spec` (checks the spec against the build script).
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

Licence: GPL-3.0-or-later (the script) like the add-on; the produced files follow the add-on.
