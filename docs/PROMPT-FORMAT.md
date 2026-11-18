# Prompt format and chat template

> Status, 7 Nov 2026: this page describes the earlier JSON-format models. v0.1 (Maris3D-SLM-Blender-0.5B) speaks native Qwen tool calls; see [README.md](../README.md) and [hf/Maris3D-Blender/README.md](../hf/Maris3D-Blender/README.md).

Documented once for the earlier JSON-format family; the old 0.5B and 1.5B models are identical in format.

For v0.1 there is no JSON document: the model emits the standard Qwen tool call `{"name": ..., "arguments": ...}` per turn, and the host returns the result as a `tool` message and loops (up to 20 calls per user turn). Any runtime that speaks Qwen tools can drive it — for example `llama-server --jinja` ([hf/Maris3D-Blender/SERVE.md](../hf/Maris3D-Blender/SERVE.md)).

## The turn

| Role | Content |
|---|---|
| system | `Output Blender tool calls as JSON: {"calls":[...]}.` (exactly; `maris3d.dsl.tools.SHORT`) |
| user | the request, plain English, for example `Add a UV sphere with radius 2 at the origin.` |
| assistant | one JSON object `{"calls":[{"tool":"...", ...}, ...]}` and then `<|im_end|>` |

The earlier models were fine-tuned on single-turn examples of exactly this shape. Every answer is a **complete scene document** for an empty scene: to change something, the user message must describe the whole
wanted scene again. Editing an existing scene turn by turn is not supported by these earlier models (the v0.1 default file edits: 26 of 30 edit requests usable, see [README.md](../README.md)).

## Chat template (ChatML, as in Qwen2.5)

```
<|im_start|>system
Output Blender tool calls as JSON: {"calls":[...]}.<|im_end|>
<|im_start|>user
Add a cube to the scene.<|im_end|>
<|im_start|>assistant
{"calls":[{"tool":"add_primitive","shape":"cube"}]}<|im_end|>
```

Stop tokens: `<|im_end|>` and `<|im_start|>`. The earlier Hugging Face repos ship the base model's `chat_template.jinja` unchanged; **always pass the system message**, otherwise the template inserts
the base model's default system prompt and the model was not trained for that. The earlier GGUF repos did the same with an Ollama `TEMPLATE` in a `Modelfile`; the v0.1 GGUF repo ships `SERVE.md` instead.

## Decoding

Temperature 0 (greedy), context 4096, at most 900 new tokens for the benchmark (the 40-call cap fits). `generation_config.json` in the safetensors repos still carries the base model's sampling defaults (temperature 0.7, top-p 0.8, top-k 20, repetition penalty 1.1);
override them: `do_sample=False`. JSON mode (or a grammar from `T.SCHEMA`) keeps the output parseable; the benchmark reference used a grammar.

## Longer prompt

`maris3d.dsl.tools.PROMPT` is a long tool-catalogue prompt. The MCP server and the bridge use it plus a short copilot addendum. The models were trained on the short prompt; the long one is not scored.

## Tool schema

The 26 tools and their arguments: [DSL.md](DSL.md) (generated from the code).
