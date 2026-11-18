# SPDX-License-Identifier: Apache-2.0
from ..dsl.tools import compile_calls


def compile_call(call):
    """One native call -> Blender Python. Returns (code, None) or (None, error). The model never writes this code."""
    try:
        return compile_calls({"calls": [call]}), None
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"[-200:]
