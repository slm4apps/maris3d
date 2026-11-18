# Prompting guide: Maris3D 0.2

Type into **3D View > Sidebar > Maris3D Copilot**, press **Run**. For a long sentence use the expand button (it opens a text block; the box runs it when the line is empty). One request is one
**Undo**. You say what you want in plain words; you never type a coordinate. The words below are the closed lists the app reads (`src/maris3d/copilot/vocabulary.py`); a sentence that uses
other words can still work, but these are the ones that are checked.

## Build: name things and where they stand

```
A small train station: a platform, a station building behind the platform, a track in front of
the platform, a train on top of the track, two benches on the platform and four lamp posts in
front of the platform, close to it
```

- **Where:** in front of, behind, left of, right of, next to, between, on top of, under, against, around, in the centre of.
- **How far:** touching, tiny, small, medium, large, far, distant (a stated distance such as "2 metres away" is read as the nearest of these steps).
- **Several of one thing:** in a row, in a ring, in a grid, in a stack.
- **Colours and materials:** black, brass, brick, cream, green, metal, navy, oak, pine, red, rust, snow, teal, terra, timber, walnut, white, plus grey, blue, yellow, glass, orange, water, pink, brown for parts.
- **Size words:** tiny, small, large, big, giant, huge, tall, short, wide, narrow.
- **A thing the app does not know by name** is designed by the model as parts (a shape, a colour, a size and where each part sits on an earlier part: cube, cylinder, cone, ico, uv sphere, torus).
  The result can be rough: check it in the viewport.

## Change what is there

Say what to do to a thing by name:

| Do | Say |
|---|---|
| move | `move the lamp next to the sofa`, `shift the tree behind the house` |
| resize | `make the table bigger`, `half as tall as the tree`, `double the chair` |
| recolour | `make the table darker`, `make the bench red` |
| turn / tilt | `turn the chair a quarter left`, `face the tree`, `tilt the lamp slightly` |
| copy | `add another bench`, `copy the bench` |
| remove, rename | `remove the tree`, `rename the shed to hut` |
| add a part | `put a chimney on the house` |
| finish | `make the cup smooth`, `make the cup hollow` (an open-top box, cylinder or cone) |

Sizes go by words (`a bit bigger`, `bigger`, `much bigger`, `double`, `half`, `triple`) or by a number you typed (`50 percent bigger`, `3 cm to the left`).

## Ask

`how many chairs are there?`, `what is behind the sofa?`: the model answers from the scene. It does not invent things that are not there.

## Animate

Motion is read from the sentence and written by the app's code: spin, swing, bounce, grow, shrink, rise, move, orbit, pulse or flicker and a colour change. For example
`spin the fan once over one second`, `a ball bouncing twice`, `a moon going round a planet`, `make the door swing`. Time and counts can be words ("twice", "two seconds", "half a second").
24 frames per second. Animation moved things as asked in 20 of 37 requests on the yardstick, so check the timeline.

## What it will not do

- **Lights, cameras and text:** not from a plain request yet (you get a look-alike object or nothing). An animation that names one works: "a camera circling the cube", "a light pulsing".
- **A follow-up that adds a new thing to a scene that is already built** often does nothing yet. Build all the things in the first sentence, or press **Undo** and describe the whole scene again.
- It is a 0.5B model: check the result in the viewport. See [SAFETY-AND-LIMITATIONS.md](SAFETY-AND-LIMITATIONS.md) and [BENCHMARKS.md](BENCHMARKS.md).
