# SPDX-License-Identifier: Apache-2.0
"""Lets a file of plain `test_*` functions run under `python -m unittest` (no pytest needed).

    Plain = as_testcase(globals())                      # at the end of the test file
    Plain = as_testcase(globals(), before=clean_env)    # `before(monkeypatch)` runs first

A test that takes `monkeypatch` gets a small stand-in with setenv / delenv; what it changed is
put back after the test.
"""
import inspect
import os
import unittest


class Env:
    def __init__(self):
        self._was = []

    def setenv(self, key, value):
        self._was.append((key, os.environ.get(key)))
        os.environ[key] = value

    def delenv(self, key, raising=True):
        if raising and key not in os.environ:
            raise KeyError(key)
        self._was.append((key, os.environ.get(key)))
        os.environ.pop(key, None)

    def undo(self):
        for key, value in reversed(self._was):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._was = []


def as_testcase(namespace, before=None):
    def wrap(fn):
        def method(self):
            env = Env()
            self.addCleanup(env.undo)
            if before is not None:
                before(env)
            fn(env) if "monkeypatch" in inspect.signature(fn).parameters else fn()
        method.__doc__ = fn.__doc__
        return method
    tests = {name: wrap(fn) for name, fn in namespace.items()
             if name.startswith("test_") and inspect.isfunction(fn)}
    return type("Plain", (unittest.TestCase,), dict(tests, __module__=namespace["__name__"]))
