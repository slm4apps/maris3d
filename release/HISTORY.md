# Promotion history

One row per size per promotion, appended by `scripts/promote.py`. Public release numbers only; the mapping to internal training runs is kept privately.

| Date | Model | Release | Pass % (gate basis) | Usable % / Run % | GGUF sha256 (first 12) | Note |
|---|---|---|---|---|---|---|
| 2026-11-07 | Maris3D-SLM-Blender-0.5B | 0.1.0 | 19.4% (default file, edit LoRA merged) | 77.2% usable | `2879a3014ccf` | first public release: the base fine-tune + edit LoRA, four GGUFs on `slm4apps/Maris3D-Blender`; 180-request yardstick (strict mode base + LoRA @0.7: 23.9% pass) |
| 2026-10-31 | Maris3D-SLM-Blender-0.5B (development) | unreleased | 63.1% (repair loop) | 95.1% run | `108abba2a4c2` | earlier development line that reused the name: different model, old JSON format, 206-prompt benchmark — not comparable |
| 2026-10-31 | Maris3D-SLM-Blender-1.5B (development) | unreleased | 72.33% (bare) | 96.6% run | `f73f0f510a15` | same earlier development line, 206-prompt benchmark — not comparable |
