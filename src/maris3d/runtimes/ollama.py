# SPDX-License-Identifier: Apache-2.0
import json
import os

from .base import Runtime, post_json


def history_for_send(messages):
    """History shape Ollama accepts. Its runner parses history tool calls strictly:
    arguments must be objects, not JSON strings, else the follow-up ask fails with
    HTTP 400 "can't find closing '}'". The copilot stores the scored wire format
    (arguments as string); convert at send time only, never mutate the caller's copy."""
    out = []
    for message in messages or []:
        if message.get("role") == "assistant" and message.get("tool_calls"):
            message = dict(message)
            fixed = []
            for call in message["tool_calls"]:
                call = dict(call)
                fn = dict(call.get("function") or {})
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        pass
                    fn["arguments"] = args
                call["function"] = fn
                fixed.append(call)
            message["tool_calls"] = fixed
        out.append(message)
    return out


class Ollama(Runtime):
    """Ollama /api/chat. No per-request LoRA: edit behaviour needs a second model entry (edit_model, built with ADAPTER).

    ``text_tools`` (env ``MARIS3D_OLLAMA_TEXT_TOOLS=1``) declares the tools in a system message
    instead of the API ``tools`` field. The rendered prompt is the same one the model was trained on,
    but the answer is parsed by our own tolerant parser: Ollama's runner fails the whole request with
    HTTP 500 when one call in a long answer is malformed, which drops otherwise usable rows."""
    name = "ollama"

    def __init__(self, model, base_url="http://127.0.0.1:11434", edit_model=None, text_tools=None):
        self.model, self.base_url, self.edit_model = model, base_url.rstrip("/"), edit_model
        if text_tools is None:
            text_tools = os.environ.get("MARIS3D_OLLAMA_TEXT_TOOLS", "") not in ("", "0", "false")
        self.text_tools = text_tools

    @staticmethod
    def tools_block(tool_names, schemas):
        """The Qwen tool preamble, as text. Mirrors the model's chat template so the model sees
        the same prompt whether the tools arrive in the API field or in this message."""
        lines = ["You are Maris, the Maris3D model by slm4apps. You build and change 3D scenes in Blender from plain words, offline.", "",
                 "# Tools", "", "You may call one or more functions to assist with the user query.", "",
                 "You are provided with function signatures within <tools></tools> XML tags:", "<tools>"]
        lines += [json.dumps(schema, separators=(",", ":")) for schema in schemas]
        lines += ["</tools>", "",
                  "For each function call, return a json object with function name and arguments within "
                  "<tool_call></tool_call> XML tags:", "<tool_call>",
                  '{"name": <function-name>, "arguments": <args-json-object>}', "</tool_call>"]
        return "\n".join(lines)

    def chat(self, messages, tool_names, lora_scale=None, max_tokens=1024):
        use = self.edit_model if (self.edit_model and lora_scale) else self.model  # lora_scale 1 = edit mode
        options = {"temperature": 0, "repeat_penalty": 1.0, "num_predict": max_tokens, "num_ctx": 8192}
        history = history_for_send(messages)
        body = {"model": use, "messages": history, "stream": False, "options": options}
        if self.text_tools and tool_names:
            if not (history and history[0].get("role") == "system"):
                body["messages"] = [{"role": "system", "content": self.tools_block(tool_names, self.tools_payload(tool_names))}] + history
        elif tool_names:  # Plan mode sends no tools; omitting the field is the text-only chat
            body["tools"] = self.tools_payload(tool_names)
        try:
            return post_json(self.base_url + "/api/chat", body)["message"]
        except RuntimeError as error:
            raise RuntimeError(f"{error} [ollama model={use}]") from None
