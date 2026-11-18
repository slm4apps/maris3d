# Release history

One row per released model version, newest first.

| Date | Model | Release | Pass % (gate basis) | Usable % / Run % | GGUF sha256 (first 12) | Note |
|---|---|---|---|---|---|---|
| 2026-11-18 | Maris3D SLM Blender 0.5B | 0.2.1 | 23.3% (same weights as 0.2.0) | 75.0% usable | `1cde9c09daba` base, `0b0c7e80e73a` adapter | the 0.2.0 weights; the files carry the Maris3D name and identity |
| 2026-11-18 | Maris3D SLM Blender 0.5B | 0.2.0 | 23.3% (one run, base + one adapter) | 75.0% usable | `5604f0e2480c` base, `e78695a13228` adapter | the model answers in words, code writes the tool calls; held-out scores in the model card |
| 2026-11-07 | Maris3D SLM Blender 0.5B | 0.1.0 | 19.4% (default file, edit LoRA merged) | 77.2% usable | `2879a3014ccf` | first public release: the build model + edit LoRA, four GGUFs, now at tag v0.1.0 of `slm4apps/Maris3D-Blender`; 180-request yardstick (strict mode base + LoRA @0.7: 23.9% pass) |
| 2026-10-31 | Maris3D SLM Blender 0.5B (development) | unreleased | 63.1% (repair loop) | 95.1% run | `108abba2a4c2` | earlier development line that reused the name: different model, old JSON format, 206-prompt benchmark — not comparable |
| 2026-10-31 | Maris3D-SLM-Blender-1.5B (development) | unreleased | 72.33% (bare) | 96.6% run | `f73f0f510a15` | same earlier development line, 206-prompt benchmark — not comparable |
