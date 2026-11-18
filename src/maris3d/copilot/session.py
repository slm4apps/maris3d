# SPDX-License-Identifier: Apache-2.0
"""Executor contract and replay-log undo. No Blender import here."""
import copy


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
        # what each built thing is, in the parts planner's words + metres (apply_change.spec_from_inst):
        # thing name -> spec. A change answer is applied on these. `_before` keeps the specs as
        # they were before each batch, so undo gives them back with the scene.
        self.specs = {}
        self._before = []

    def apply(self, calls):
        done, results = [], []
        for call in calls:
            ok, err = self.executor.run_call(call)
            results.append((ok, err))
            if ok:
                done.append(call)
        if done:
            self._before.append(copy.deepcopy(self.specs))
            self.batches.append(done)
        self.last_results = results      # a checker reads these (repair needs the errors)
        return results

    def merge_from(self, start):
        """Join every batch added since index `start` into one, so undo reverts them together."""
        tail = self.batches[start:]
        if len(tail) > 1:
            self.batches[start:] = [[call for batch in tail for call in batch]]
            self._before[start:] = [self._before[start]]

    def undo(self):
        if not self.batches:
            return False
        self.batches.pop()
        if self._before:
            self.specs = self._before.pop()
        self.executor.reset()
        for batch in self.batches:
            for call in batch:
                self.executor.run_call(call)
        return True

    def reset(self):
        self.batches.clear()
        self._before.clear()
        self.specs = {}
        self.executor.reset()

    def rebind(self, executor):
        """Keep this session for the next request on a new executor (the add-on makes one per
        request). What it built stays known, so "make the sofa red" reaches the edit adapter. A
        thing none of whose objects is in the scene any more (deleted by hand, a Blender undo) is
        forgotten."""
        self.executor = executor
        names = {o.get("name") for o in executor.objects()}
        gone = [k for k, spec in self.specs.items()
                if k not in names and not any(p.get("name") in names for p in spec.get("parts", []))]
        for k in gone:
            del self.specs[k]
        self.groups = {k: v for k, v in self.groups.items() if k in names or any(n in names for n in v)}
        return gone

    def forget_last(self):
        """The host already undid the last request (Blender's own undo): drop its batch and give
        the specs back as they were, without running anything again."""
        if not self.batches:
            return False
        self.batches.pop()
        if self._before:
            self.specs = self._before.pop()
        return True

    def objects(self):
        return self.executor.objects()
