# SPDX-License-Identifier: Apache-2.0
"""Where the copilot's compiled Python goes: our own Blender window, or another MCP's tools."""
from .compile import compile_call
from .live import LiveExecutor
from .mcp_forward import McpForwardExecutor, PROFILES

__all__ = ["compile_call", "LiveExecutor", "McpForwardExecutor", "PROFILES"]
