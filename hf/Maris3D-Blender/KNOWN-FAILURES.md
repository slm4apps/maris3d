# Maris3D-SLM-Blender-0.5B v0.1 — known failures (merged single-file fallback)

Measured on the merged single-file fallback `maris3d-slm-blender-0.5b-edit-q8_0.gguf` (edit LoRA merged),
not on the default product (base + edit adapter, 27.2 / 75.6). The per-bucket table below is
for the fallback only.
Benchmark: 180 requests, 7 buckets (single 42; edit, multipart and animation 30 each;
arrays_rings 18; parenting 18; geonodes 12), Blender 5.2.2, temperature 0, context 4096.
Measured 7 Nov 2026. A row can fail several aspects; the "primary" reason is the first
failed aspect of the row.

Overall: **35 PASS / 104 PARTIAL / 41 FAIL** — 19.4% fully correct, 77.2% usable
(pass + partial).

## The 41 FAIL rows — two causes
| Primary cause | Rows | Meaning |
|---|---|---|
| `runs` — output never parsed | 20 | the model produced no usable tool call for the request |
| `right_object` — ran, built the wrong thing | 21 | the scene changed but did not match the request |

One further row ends in a Blender execution error. FAILs by bucket: multipart 11,
animation 9, single 8, arrays_rings 6, edit 4, parenting 3. The unparsed 20 spread:
multipart 6; single, animation, arrays_rings and edit 3 each; parenting 2
(ids include s06, s11, s17, a02, a20, a25, r05, r10, r18, pa03).

## The 104 PARTIAL rows — mostly one miss
101 ran, 3 ended in a Blender execution error. 61 of them fail exactly one aspect,
21 fail two, 18 fail three, 4 fail all four. Primary misses: **parts 27, relations 21**,
right_object 20, request 14, dimensions 11, animation 9, colour 2. 41 rows overall build
a wrong object somewhere in the scene; most of those rows are still partially usable.

## Strong vs weak
| Bucket | fully correct | Note |
|---|---|---|
| edit | 13/30 | the merged file's purpose. 3 of its 4 failures are unparsed (e19, e21, e26), 1 wrong object (e01) |
| geonodes | 5/12 | small bucket, simple node setups |
| animation | 5/30 | |
| single | 4/42 | mostly PARTIAL, not FAIL — right object, small misses |
| parenting | 4/18 | relations are the usual miss |
| arrays_rings | 3/18 | |
| multipart | 1/30 | **weakest mode** — 6 of its 11 failures are unparsed |

## Practical guidance
- At v0.1, 76% of requests give a usable scene routed (27% fully correct on the first
  try); if yours is one of the rest, the guidance below usually recovers it.
- When a request fails: rephrase it (name objects explicitly), split multi-part requests
  into steps, and retry once — the unparsed failures are often phrasing-sensitive.
- Judge results by the scene, not by the model's closing text: with tools present it
  finishes with a short formula line ("Done — completed 1 tool call.") that can misstate
  what actually ran. The scene state is the ground truth.
