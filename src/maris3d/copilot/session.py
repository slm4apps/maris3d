# SPDX-License-Identifier: Apache-2.0
"""Executor contract and replay-log undo. No Blender import here."""


class Executor:
    """What the copilot needs from a Blender backend (live window, headless, or a test fake)."""

    def reset(self):
        raise NotImplementedError

    def run_call(self, call):
        """Run one native call. Return (ok, error_text_or_None)."""
        raise NotImplementedError

    def objects(self):
        """[{name, type, loc, material?}] of the current scene."""
        raise NotImplementedError


class Session:
    """Applies batches of calls and can undo whole batches by reset-and-replay.

    Replay is exact and needs no file copies: the log only holds calls that succeeded.
    """

    def __init__(self, executor):
        self.executor = executor
        self.batches = []
        self.groups = {}      # built items: parent name -> its part names (compile_plan)

    def apply(self, calls):
        done, results = [], []
        for call in calls:
            ok, err = self.executor.run_call(call)
            results.append((ok, err))
            if ok:
                done.append(call)
        if done:
            self.batches.append(done)
        self.last_results = results      # a checker reads these (repair needs the errors)
        return results

    def merge_from(self, start):
        """Join every batch added since index `start` into one, so undo reverts them together."""
        tail = self.batches[start:]
        if len(tail) > 1:
            self.batches[start:] = [[call for batch in tail for call in batch]]

    def undo(self):
        if not self.batches:
            return False
        self.batches.pop()
        self.executor.reset()
        for batch in self.batches:
            for call in batch:
                self.executor.run_call(call)
        return True

    def reset(self):
        self.batches.clear()
        self.executor.reset()

    def objects(self):
        return self.executor.objects()
