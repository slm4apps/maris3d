# SPDX-License-Identifier: Apache-2.0
"""Generic OpenAI-compatible planner.

Calls {base_url}/chat/completions with the planner prompt and the user's request text.
The key is read from an environment variable or a file at call time, sent only as a
Bearer header, and never stored on the instance, written to the package, or logged.
Only constructed and called when the config selects source "api" (see source.py).
Error reasons are fixed strings; server bodies and key values are never echoed.
"""
import json
import os
import urllib.error
import urllib.request

from . import plan as P
from . import validate

MAX_RESPONSE = 1 << 20


class PlannerError(Exception):
    """A plain, key-free reason the API planner gave no plan."""


class ApiPlanner:
    def __init__(self, base_url, model, key_env=None, key_file=None, timeout=30.0):
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise ValueError("api base_url must start with http:// or https://")
        if not model:
            raise ValueError("api model is required")
        if key_env and key_file:
            raise ValueError("set key_env or key_file, not both")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = float(timeout)
        self._key_env = key_env
        self._key_file = key_file

    def _key(self):
        """Read the key now. Returns None when no key source is configured (for example a local model)."""
        if self._key_env:
            value = os.environ.get(self._key_env, "").strip()
            if not value:
                raise PlannerError(f"key env var {self._key_env} is unset or empty")
            return value
        if self._key_file:
            try:
                with open(self._key_file, encoding="utf-8") as fh:
                    value = fh.read().strip()
            except OSError:
                raise PlannerError("key file cannot be read")
            if not value:
                raise PlannerError("key file is empty")
            return value
        return None

    def __call__(self, prompt):
        key = self._key()
        body = json.dumps({
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800,
            "messages": [{"role": "system", "content": P.PROMPT},
                         {"role": "user", "content": str(prompt)}],
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        request = urllib.request.Request(self.base_url + "/chat/completions", data=body,
                                         headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            raise PlannerError(f"api planner answered HTTP {exc.code}")
        except (urllib.error.URLError, OSError):
            raise PlannerError("api planner is unreachable")
        if len(raw) > MAX_RESPONSE:
            raise PlannerError("api planner reply is too large")
        try:
            content = json.loads(raw.decode("utf-8"))["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise PlannerError("api planner reply has no message content")
        ok, reason = validate.check(content)
        if not ok:
            raise PlannerError("api plan rejected: " + reason)
        return json.loads(content) if isinstance(content, str) else content
