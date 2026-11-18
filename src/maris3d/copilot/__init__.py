# SPDX-License-Identifier: Apache-2.0
"""Detachable copilot core: no dependencies, no server, no Blender import.

It turns a model's native tool calls into Blender Python (dsl.tools.compile_calls),
runs them through an executor, checks the result and can undo. Any host can embed it.
"""
from .protocol import (load_tools, trim_tools, scene_summary, format_result,
                       normalise_calls, assistant_message)

__all__ = ["load_tools", "trim_tools", "scene_summary", "format_result",
           "normalise_calls", "assistant_message"]
