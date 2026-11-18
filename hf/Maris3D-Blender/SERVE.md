# Serving Maris3D-SLM-Blender-0.5B v0.1

## Files (sha256 verified against `SHA256SUMS`)
| File | Bytes | Role |
|---|---|---|
| maris3d-slm-blender-0.5b-q8_0.gguf | 531,068,000 | **Base** — the product, served with the adapter below |
| maris3d-slm-blender-0.5b-edit-lora-f16.gguf | 5,881,344 | **Edit adapter** — per-request scale 0 build / 1.0 edit |
| maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf | 5,881,248 | **Planner adapter** — optional; runs alone on a plan turn (one sentence -> a plan in words) |
| maris3d-slm-blender-0.5b-edit-q8_0.gguf | 531,067,872 | Merged single file, for hosts without adapter support |
| maris3d-slm-blender-0.5b-q4_k_m.gguf | 397,807,712 | Smaller build-only base |

## llama.cpp
```bash
# the product: ONE server, 518 MB. The adapters are loaded once and every request carries a
# scale — 0.0 for a fresh prompt (build weights), 1.0 for a correction (edit weights).
llama-server -m maris3d-slm-blender-0.5b-q8_0.gguf --jinja -c 8192 --temp 0 --repeat-penalty 1.0 --port 8090 \
  --lora maris3d-slm-blender-0.5b-edit-lora-f16.gguf --lora maris3d-slm-blender-0.5b-planner-v31-lora-f16.gguf \
  --lora-init-without-apply
# (leave the planner line out to serve build and edit only: plan first is then off)

# or let the CLI do exactly that (one process, pid in ~/.cache/maris3d/serve.pid)
maris3d serve start

# no adapter support (plain GGUF loaders): the merged file, one file for both modes
llama-server -m maris3d-slm-blender-0.5b-edit-q8_0.gguf --jinja -c 8192 --temp 0 --repeat-penalty 1.0 --port 8090
```

Then POST OpenAI-style `/v1/chat/completions` with your `tools` array (Qwen tool format)
**and the scale for the turn**:
```json
{"messages":[{"role":"user","content":"add a red cube named Box"}],
 "tools":[...], "temperature":0, "lora":[{"id":0,"scale":0.0}]}
```
With the planner loaded, list both adapters in every request so that neither stays at 1.0:
`"lora":[{"id":0,"scale":0.0},{"id":1,"scale":1.0}]` on a plan turn (no `tools`, the planner's own
system prompt), `{"id":1,"scale":0.0}` on every other turn. The add-on does this itself.
`GET /lora-adapters` lists the loaded adapters and their ids. Nothing is reloaded between
turns: the same process answers with scale 0 for a new scene and 1.0 for a change.
Measured: at 1.0 the adapter reproduces the merged edit file's verdicts row for row
(29/29 edit rows, same scorer), and at 0 the base is the build file. Strict-pass is the
same adapter at scale 0.7.

Measured on an 8 GB Mac: 0.58 GB resident, ~0.6 s per answer, 1.3 s cold load.

## Ollama
```bash
# local build from the staged files (a Modelfile ships alongside the GGUFs):
ollama create maris3d-slm-blender-0.5b -f Modelfile
```
Or pull straight from Hugging Face — **always with the `:Q8_0` tag**:
```bash
ollama run hf.co/slm4apps/Maris3D-Blender:Q8_0
```
The plain, untagged `hf.co/slm4apps/Maris3D-Blender` resolves to the **unmerged
base `q4_k_m` build** — not the release default; the `:Q8_0` tag picks the merged
edit-q8_0 file. An `hf.co` pull does not read this Modelfile. The repo therefore carries
two small files Ollama applies to such a pull: `params` (temperature 0, repeat_penalty 1.0,
num_ctx 8192, num_predict 800) and `system` (the identity line).

**repeat_penalty must be 1.0.** Ollama's default is 1.1, and a tool call is repetition by
design: the same keys, brackets and closing tags for every part. At 1.1 the model drops
object names and can repeat one call until the token limit, which the server reports as
`invalid tool call arguments ... unexpected end of JSON input` (measured on "a bar stool
with a seat, four legs and a footrest rail": seven named calls at 1.0, a runaway at 1.1).
Ollama's OpenAI-compatible endpoint (`/v1/chat/completions`) has no field for it, so there
the value comes only from `params` or a Modelfile; the native `/api/chat` takes it in
`options`. To pin the configuration yourself, use the remote-Modelfile recipe:
```bash
cat > maris3d.modelfile <<'EOF'
FROM hf.co/slm4apps/Maris3D-Blender:Q8_0
PARAMETER temperature 0
PARAMETER repeat_penalty 1.0
PARAMETER num_ctx 8192
PARAMETER num_predict 800
SYSTEM You are SLM4Blender-0.5B, a compact local model by slm4apps that builds and edits Blender scenes through tool calls.
EOF
ollama create maris3d-slm-blender-0.5b -f maris3d.modelfile
```
The shipped `Modelfile` sets `num_predict 800` — mandatory: Ollama's default generation
is unlimited, and plain questions (outside the trained tool-loop) then generate forever.
It also sets temperature 0 and repeat_penalty 1.0. **Always include the 26-tool `tools`
array in the request** — without it the model replies with a canned formula line instead
of an answer. Failure modes per bucket: `KNOWN-FAILURES.md`.

## Notes
- Temperature 0, repeat_penalty 1.0, up to 20 tool calls per user turn is what it was trained for.
- Context: use 8,192. Rows are at most 2,048 tokens, but the 26-tool manifest plus a
  conversation can overflow 4,096.
- The tool set (26 Blender tools) is in the main repo (`TOOLS.json`).
