# SPDX-License-Identifier: Apache-2.0
"""One request: place, edit by words, or plan first -> design what is missing -> build by code."""
import json
from dataclasses import dataclass, field

from . import animate as AN
from . import apply_change as AC
from . import compile_plan as CP
from . import describe_parts as PARTS
from . import place as PLACE
from . import plan as PLAN
from . import vocabulary as V
from ..text import t

PARTS_TOKENS = 900        # one designed object: the longest training answer is 667 tokens
MAX_DESIGNED_PARTS = 24   # the longest training object has 11 parts
MAX_TOKENS = 2800  # output budget per ask; the scored engine uses the same value (engine/runtime.py)
EDIT_TOKENS = 400         # one word edit answer (the scorer's budget, eval_edit_words.py)
EDIT_PASSES = 3           # at most 3 passes, then the best guess / a plain answer


def _reply_text(message):
    """The model's text: llama-server --jinja may lift a <tool_call> into `tool_calls`; put it back."""
    text = message.get("content") or ""
    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                continue
        text = "<tool_call>\n" + json.dumps({"name": fn.get("name"), "arguments": args}) + "\n</tool_call>"
        break
    return text


@dataclass
class Result:
    calls: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    text: str = ""
    api_error: str = ""
    failures: list = field(default_factory=list)
    mode: str = ""            # build, plan, place, finish or change: what ran this turn
    plan: dict = None         # the validated plan
    plan_error: str = ""      # why the reply was not a usable plan
    built: dict = None        # a compiled plan: items, parts, how many the model got exact / the harness fixed
    moved: dict = None        # a placement request answered by the placer: what moved where
    finished: dict = None     # a finish order answered by code: what was smoothed, sharpened, merged
    changed: dict = None      # a change answer applied by code: the answer, what failed, what the read-back said
    animated: dict = None     # a motion written by code (animate.py): the motions, what moved, what was added
    show: list = field(default_factory=list)  # the model's `show` lines, checked: show.apply_lines actions

    @property
    def ok(self):
        return bool(self.calls) and not self.errors and not self.api_error and not self.failures


def _plan_words(items):
    """'2 things: station; 3 red bench next_to station' -- the planner's list, for the log."""
    out = []
    for i in items[:6]:
        n = int(i.get("count") or 1)
        bits = ([str(n)] if n > 1 else []) + [str(i.get("material") or ""), str(i.get("recipe") or i.get("id") or "?")]
        place = i.get("place") or {}
        if place.get("relation"):
            bits += [str(place.get("relation")).replace("_", " "), str(place.get("anchor") or "")]
        if i.get("arrange"):
            bits.append(t("say.planner.arranged", arrange=i["arrange"]))
        out.append(" ".join(b for b in bits if b))
    more = t("say.planner.list_more", count=len(items) - 6) if len(items) > 6 else ""
    head = t("say.planner.list_one") if len(items) == 1 else t("say.planner.list_many", count=len(items))
    return head + "; ".join(out) + more


def _said(answer):
    """What a word answer says, for the panel: its `say`, else the text of its show `say` lines."""
    if answer.get("say"):
        return str(answer["say"])
    lines = [str(x.get("text")) for x in answer.get("show") or []
             if isinstance(x, dict) and x.get("line") == "say" and x.get("text")]
    return " ".join(lines)


class Copilot:
    """runtime: object with chat(messages, tool_names, max_tokens, role) -> message dict.
    session: copilot.session.Session. router: optional fn(request, objects, turn) -> 'build'|'edit'
    (a change to what the scene has is never built as a new thing)."""

    def __init__(self, runtime, session, router=None, scene_cap=40):
        self.runtime, self.session, self.router = runtime, session, router
        self.scene_cap = scene_cap
        self.messages = []
        self.turn = 0
        # True: the parts planner designs EVERY item; the library is only what is used when its
        # design cannot be built.
        self.design_first = True
        # who did what, one line each (trace.Trace.say); None = silent. The add-on shows it.
        self.say = None
        # the scene show (copilot/show.py react): callables fn(name, info) told what the copilot
        # is doing: request, tool_call, part, done, error. A listener that raises is ignored.
        self.listeners = []

    def _say(self, who, text):
        say = getattr(self, "say", None)          # a Copilot made without __init__ has none
        if say is not None:
            try:
                say(who, text)
            except Exception:
                pass          # never lose the work over a log line

    def _emit(self, event, **info):
        for fn in tuple(getattr(self, "listeners", None) or ()):
            try:
                fn(event, info)
            except Exception:
                pass

    def _emit_done(self, result):
        """The end of a request: done (with what is still wrong, or the kind of a change answer)
        or error. A request that only had single tool errors but built things is still done."""
        if not getattr(self, "listeners", None):
            return
        err = result.api_error or (
            result.errors[0].get("error") if result.errors and not result.calls else "")
        if err:
            self._emit("error", text=str(err)[:200])
            return
        built = result.built or {}
        kind = ((result.changed or {}).get("answer") or {}).get("kind")
        self._emit("done", text=result.text or "", unfixed=int(built.get("unfixed") or 0) + len(result.failures),
                   kind=kind if kind in ("question", "cannot") else None)

    def _run_plan(self, request):
        """One ask with no tools: the outline prompt, answered as a plan. It is validated here and
        returned in Result.plan; nothing is applied to the scene. An unusable reply is an error:
        there is no other route to build with."""
        self.turn += 1
        self._say(t("speaker.planner"), t("say.planner.asked_build"))
        result = Result(mode="plan")
        self.messages = [{"role": "system", "content": V.OUTLINE_SYSTEM}, {"role": "user", "content": request}]
        try:
            message = self.runtime.chat(self.messages, [], max_tokens=MAX_TOKENS, role="planner")
        except Exception as error:  # infrastructure failure, never a model answer
            result.api_error = repr(error)[:300]
            return result
        reply = message.get("content") or ""
        result.text = reply
        self.messages.append({"role": "assistant", "content": reply})
        obj, reason = PLAN.parse_reply(reply)
        if reason is None:
            obj = PLAN.from_outline(obj)
            ok, reason = PLAN.check_items(obj)
        else:
            ok = False
        if ok:
            result.plan = obj
        else:
            result.plan_error = reason or "invalid plan"
        return result

    # ---- plan first: the planner's answer is compiled, not printed -------------
    def run_auto(self, request):
        """The flow below, told to the listeners: request, then done or error."""
        self._emit("request", text=str(request))
        try:
            result = self._run_auto(request)
        except Exception as error:
            self._emit("error", text=repr(error)[:200])
            raise
        self._emit_done(result)
        return result

    def _run_auto(self, request):
        """The whole flow for one sentence: edit by words, place, or plan -> compile -> build.

        Everyone hits plan first. A request to put a thing beside or next to another one is
        answered by the placer. So:
          1. a sentence that moves a thing the scene has, relative to another thing it has, is
             answered by the placer (words -> metres), no model;
          2. otherwise the planner is asked; if it names things, the plan is compiled into exact
             instructions and built by code (run_items);
          3. otherwise the answer says so (result.no_plan_built); nothing else runs.
        """
        exact = CP.is_exact_instruction(request)
        if exact:
            self._say(t("speaker.router"), t("say.router.exact_edit"))
        # a motion over time ("spin it once over one second", "a ball bouncing twice") is written by
        # code (animate.py): the edit adapter has no word for it and the compiler has the keyframes
        motions = [] if exact else AN.parse(request)
        if motions:
            animated = self.run_animate(request, motions)
            if animated is not None:
                return animated
        # the word edit adapter answers a change to the things the copilot built, and every
        # sentence that states its numbers
        if (exact or self.session.specs) and self._has_role("edit"):
            changed = self.run_change_words(request)
            if changed is not None and not self._change_fell_short(changed):
                return changed
            if changed is not None:
                # the edit answer did nothing (no calls, no question for the user): "add a cushion on the
                # seat", "make it look smooth" go on to the finish and the planner instead of ending here
                self._say(t("speaker.router"), t("say.router.edit_fell_through"))
        finished = self.run_finish(request)         # needs no model, so it works on any server
        if finished is not None:
            self._say(t("speaker.code"), t("say.code.finish_done", text=finished.text) if finished.text
                      else t("say.code.finish_done_bare"))
            return finished
        start = len(self.session.batches)
        self._mark_north()
        try:
            return self._auto(request)
        finally:
            self.session.merge_from(start)        # the marker and the request are one undo unit

    def run_animate(self, request, motions):
        """Keyframes for the motions, by code. On an empty scene the sentence's things are built first
        (planner, then a plain primitive / camera / light for a noun the build did not make).
        None when a follow-up names a thing the scene does not have (the flow goes on); a sentence that
        brings the thing in ("a ball bouncing twice" after other builds) builds it and animates it."""
        objects = self.session.objects()
        calls, notes, missing = AN.plan_calls(motions, objects, last=self._last_built())
        if (missing or not calls) and self.session.specs and not AN.introduces(request, missing):
            return None
        start = len(self.session.batches)
        result, added = None, []
        try:
            if missing or not calls:
                self._mark_north()
                result = self._auto(request)
                objects = self.session.objects()
                calls, notes, missing = AN.plan_calls(motions, objects, last=self._last_built())
                if missing or not calls:
                    added = AN.make_missing(missing or [m.noun for m in motions if m.noun], objects)
                    for call, (ok, err) in zip(added, self.session.apply(added) if added else []):
                        if not ok:
                            (result.errors if result else []).append({"tool": call.get("tool"), "error": err})
                    objects = self.session.objects()
                    calls, notes, missing = AN.plan_calls(motions, objects, last=self._last_built())
            result = result or Result(mode="animate")
            self.turn += 1 if result.mode == "animate" else 0
            result.calls.extend(added)
            for call, (ok, err) in zip(calls, self.session.apply(calls) if calls else []):
                if not ok:
                    result.errors.append({"tool": call.get("tool"), "error": err})
            result.calls.extend(calls)
            result.animated = {"motions": [m.kind for m in motions], "notes": notes, "added": [c.get("name") for c in added],
                               "missing": missing}
            if notes:
                self._say(t("speaker.code"), t("say.code.animated", text="; ".join(notes)))
                result.text = result.text or "; ".join(notes)
            return result
        finally:
            self.session.merge_from(start)

    @staticmethod
    def _change_fell_short(changed):
        """True when the word edit answer changed nothing and asked nothing: no calls, no
        infrastructure error, no error to show (an unreadable answer, a change that failed), and its kind is not a question / talk / look the panel must show."""
        if changed.calls or changed.api_error or changed.errors:
            return False
        kind = ((getattr(changed, "changed", None) or {}).get("answer") or {}).get("kind")
        return kind not in ("question", "talk", "look")

    def _apply_done(self, result, answer, done):
        """Run what a change answer came to (apply_change.Applied), read it back, fill `result`."""
        if done.say:
            result.text = done.say
            self._say(t("speaker.planner"), done.say)
        first_batch = len(self.session.batches)
        try:
            for call, (ok, err) in zip(done.calls, self.session.apply(done.calls) if done.calls else []):
                if not ok:
                    result.errors.append({"tool": call.get("tool"), "error": err})
        finally:
            self.session.merge_from(first_batch)
        if done.calls:
            self.session.specs = done.specs          # after apply: the batch kept the specs of before, for undo
            self._regroup()
        result.calls.extend(done.calls)
        for error in done.errors:
            result.errors.append({"tool": "change", "error": error["error"]})
            self._say(t("speaker.code"), t("say.code.not_applied", error=error["error"]))
        read = AC.check(answer, self.session.objects(), done) if done.calls else []
        result.changed = {"answer": answer, "errors": done.errors, "checked": read, "notes": done.notes}
        for row in read:
            if row["status"] == "wrong":
                result.failures.append(f"{row['do']} {row['object']}: {row['detail']}")
        return result

    def run_change_words(self, request, clarified=()):
        """The word-format edit adapter (role "edit") reads the scene in words
        (describe_scene.edit_input) and answers in words; code applies it (edit_words.apply_words).
        A `look` answer gets the parts of the things it names and is asked again: at most
        EDIT_PASSES passes. None when the answer is kind build (the flow for new things goes on).
        question / cannot: its `say` goes to the panel and nothing runs."""
        from . import describe_scene as DS
        from . import edit_words as EW
        result = Result(mode="change")
        focus = ()
        for _ in range(EDIT_PASSES):
            self.turn += 1
            text, notes = DS.edit_input(self.session.specs, request, focus=focus, last=self._last_built(),
                                        clarified=clarified)
            for note in notes:
                self._say(t("speaker.code"), note)
            self._say(t("speaker.edit"), t("say.edit.asked"))
            try:
                system = EW.EDIT_SYSTEM_EXACT
                message = self.runtime.chat([{"role": "system", "content": system},
                                             {"role": "user", "content": text}], [],
                                            max_tokens=EDIT_TOKENS, role="edit")
            except Exception as error:  # infrastructure failure, never a model answer
                result.api_error = repr(error)[:300]
                return result
            reply = _reply_text(message)
            result.text = reply
            answer = EW.unwrap(reply)
            if isinstance(answer, dict):
                # the panel and the scene show words, never the raw answer: its say, else its say lines
                result.text = _said(answer)
            if not isinstance(answer, dict) or answer.get("kind") not in EW.KINDS:
                result.errors.append({"tool": "change", "error": t("error.edit_unreadable")})
                self._say(t("speaker.edit"), result.errors[-1]["error"])
                return result
            if answer.get("kind") == "build":
                from . import show as SHOW
                self._show(result, SHOW.apply_lines(answer.get("show"), list(self.session.specs))[0])
                return None
            done = EW.apply_words(answer, self.session.specs, self.session.objects(), design=self._design_word)
            self._show(result, getattr(done, "show", None))
            if getattr(done, "kind", None) == "look":
                if done.look and tuple(done.look) != tuple(focus):
                    focus = tuple(done.look)
                    self._say(t("speaker.edit"), t("say.edit.looks_at", names=", ".join(focus)))
                    continue
                result.text = t("result.which_thing")
                self._say(t("speaker.edit"), result.text)
                return result
            return self._apply_done(result, answer, done)
        result.text = t("result.edit_passes", passes=EDIT_PASSES)
        self._say(t("speaker.edit"), result.text)
        return result

    def _show(self, result, actions):
        """The model's checked `show` lines: kept on the result and handed to `self.show` (the
        add-on's Messages builder), if there is one. Code only applies them."""
        if not actions:
            return
        result.show.extend(actions)
        self._say(t("speaker.show"), ", ".join(a["op"] for a in actions))
        hook = getattr(self, "show", None)
        if hook is not None:
            try:
                hook(actions)
            except Exception:
                pass          # never lose the work over a message

    def _design_word(self, what):
        """edit_words `add`: the parts planner's answer (a dict) for `what`, or None."""
        if not self._has_role("parts"):
            return None
        self.turn += 1
        self._say(t("speaker.parts_planner"), t("say.parts.asked", what=what))
        message = self.runtime.chat([{"role": "system", "content": PARTS.PARTS_SYSTEM_FINAL},
                                     {"role": "user", "content": str(what)}], [],
                                    max_tokens=PARTS_TOKENS, role="parts")
        answer, reason = PLAN.parse_reply(message.get("content") or "")
        return answer if reason is None and isinstance(answer, dict) else None

    def _last_built(self):
        return next(reversed(self.session.specs), None)

    def _regroup(self):
        """The groups (parent -> parts) follow the specs after a change."""
        groups = {k: v for k, v in (getattr(self.session, "groups", None) or {}).items() if k in self.session.specs}
        for thing, spec in self.session.specs.items():
            groups[thing] = [p["name"] for p in spec["parts"]]
        self.session.groups = groups

    def _mark_north(self):
        """One empty named SceneNorth at the origin, an arrow on the ground pointing +y, if the
        scene has none: "north" is then visible in the viewport and the same in a new session."""
        if any(o.get("name") == CP.NORTH_MARKER for o in self.session.objects()):
            return
        self.session.apply([{"tool": "add_empty", "name": CP.NORTH_MARKER, "location": [0.0, 0.0, 0.0],
                             "display": "SINGLE_ARROW", "rotation_deg": [-90.0, 0.0, 0.0]}])

    def _auto(self, request):
        moved = self.run_move(request)
        if moved is not None:
            self._say_moved(moved, t("speaker.placer"))
            return moved
        # What kind of request is it? The planner cannot say yet (it has no word for the kind of request yet): it
        # answers every sentence with things to build, so "make the chair red" built a second
        # chair. Until it can, the router's words decide: a change to what the scene has
        # goes to the edit model with the scene list, and is never compiled into a build.
        objects = self.session.objects()
        is_edit = bool(self.router and objects and self.router(request, objects, self.turn) == "edit")
        is_move = bool(CP.MOVE_VERB.search(str(request).lower()))
        if is_edit and not is_move:
            # a change the word edit adapter did not take: nothing builds a second copy of it
            self._say(t("speaker.router"), t("say.router.edit"))
            return self._which_thing()
        self._say(t("speaker.router"), t("say.router.move") if is_move else t("say.router.new"))
        planned = self._run_plan(request)
        if planned.api_error:
            # the model server did not answer: say so, never "I could not turn that into things"
            result = Result(mode="build")
            result.api_error = planned.api_error
            result.text = t("result.server_unreachable", error=planned.api_error[:120])
            self._say(t("speaker.router"), result.text)
            return result
        listed = CP.plan_items(planned.plan)
        if planned.plan_error:
            self._say(t("speaker.planner"), t("say.planner.no_plan", error=planned.plan_error[:80]))
        else:
            self._say(t("speaker.planner"), _plan_words(listed) if listed else t("say.planner.nothing"))
        placed = self._move_from_plan(request, [i for i in listed if CP.recipe_key(i.get("recipe"))])
        if placed is not None:
            placed.plan = planned.plan
            self._say_moved(placed, t("speaker.placer"))
            return placed
        if is_move and objects:
            # a move the placer and the planner could not turn into a place ("5 metres to the
            # left"): if its one item is a thing the scene has, it is an edit, not a new thing
            boxes = CP.scene_boxes(objects, dict(getattr(self.session, "groups", None) or {}))
            there = len(listed) == 1 and CP.find_anchor(listed[0].get("id") or listed[0].get("recipe"), boxes)[0] in boxes
            if is_edit or there:
                # the word edit adapter found nothing to change: nothing else may edit it
                placed = self._which_thing()
                placed.plan = planned.plan
                return placed
        designed, notes = self._design_missing(listed, request)
        for note in notes:
            self._say(t("speaker.parts_planner"), note)
        items = [i for i in listed if CP.recipe_key(i.get("recipe"), designed)]
        unknown = [str(i.get("recipe")) for i in listed if not CP.recipe_key(i.get("recipe"), designed)]
        if items and unknown:
            self._say(t("speaker.code"), t("say.code.skips", names=", ".join(unknown[:6])))
        if items:
            result = self.run_items(items, designed)
            b = result.built or {}
            self._say(t("speaker.code"), t("say.code.built", items=b.get("items", 0), parts=b.get("parts", 0))
                      + (t("say.code.still_off", count=b.get("unfixed")) if b.get("unfixed") else ""))
            if b.get("library"):
                self._say(t("speaker.code"), t("say.code.from_library", names=", ".join(b["library"][:6])))
            result.built["notes"] = notes + result.built["notes"]
            result.plan = planned.plan
            return result
        # no usable plan is said plainly: nothing else builds
        result = Result(mode="build")
        result.text = t("result.no_plan_built")
        self._say(t("speaker.router"), result.text)
        result.plan, result.plan_error = planned.plan, planned.plan_error
        return result

    def _which_thing(self):
        result = Result(mode="change")
        result.text = t("result.which_thing")
        self._say(t("speaker.edit"), result.text)
        return result

    def _say_moved(self, result, who):
        m = getattr(result, "moved", None) or {}
        place = m.get("place") or {}
        words = " ".join(str(place.get(k)).replace("_", " ") for k in ("relation", "anchor") if place.get(k))
        self._say(who, t("say.placer.moves", object=m.get("object"), words=words, by=m.get("by")) if m
                  else t("say.placer.moved"))

    def _has_role(self, role):
        has = getattr(self.runtime, "has_role", None)
        return bool(has and has(role))

    def _design_missing(self, items, request=None):
        """"make me a windmill": the library has no windmill, so the parts planner is asked for
        one (parts with sizes, places in words) and the answer becomes a recipe for this request.
        Returns ({word: recipe}, notes). Without the parts adapter nothing is asked."""
        designed, notes = {}, []
        if not self._has_role("parts"):
            return designed, notes
        for item in items:
            word = CP.word_key(item.get("recipe"))
            if not word or word in designed or (CP.recipe_key(item.get("recipe")) and not self.design_first):
                continue
            noun = word.replace("_", " ")
            said = f"{item['material']} {noun}" if item.get("material") in PARTS.PARTS_COLORS else noun
            ask = ("an " if said[0] in "aeiou" else "a ") + said
            if request and len(items) == 1 and not item.get("place") and int(item.get("count") or 1) == 1:
                # one thing, no place: the parts planner reads the user's own sentence, as it was
                # trained ("make me a small red chair"). The scene planner has no size field, so
                # rebuilt from its item the size word was lost (found in testing)
                ask = str(request).strip()
            self.turn += 1
            self._say(t("speaker.parts_planner"), t("say.parts.asked", what=ask))
            try:
                message = self.runtime.chat([{"role": "system", "content": PARTS.PARTS_SYSTEM_FINAL},
                                             {"role": "user", "content": ask}], [],
                                            max_tokens=PARTS_TOKENS, role="parts")
            except Exception as error:  # infrastructure failure, never a model answer
                notes.append(f"{noun}: the parts planner could not be asked ({repr(error)[:120]})")
                continue
            answer, reason = PLAN.parse_reply(message.get("content") or "")
            recipe, why = PARTS.to_recipe(answer) if reason is None else (None, reason)
            if recipe is None or len(recipe["parts"]) > MAX_DESIGNED_PARTS:
                if recipe is not None:
                    why = f"{len(recipe['parts'])} parts is more than {MAX_DESIGNED_PARTS}"
                # a fallback is never silent: the note says what builds it instead
                instead = t("note.parts.library_instead") if CP.recipe_key(item.get("recipe")) \
                    else t("note.parts.not_built")
                notes.append(t("note.parts.refused", noun=noun, why=why, instead=instead))
                continue
            designed[word] = recipe
            notes.append(f"{noun}: designed by the parts planner, {len(recipe['parts'])} parts")
        return designed, notes

    def run_items(self, items, designed=None):
        """Build a list of plan items: layout by words, one exact instruction per part, checked.

        The compiler's own call for each part is run, no model. Every part is checked after it
        ran; what is missing or misplaced is corrected and counted in Result.built.
        """
        result = Result(mode="build")
        groups = dict(getattr(self.session, "groups", None) or {})
        before = self.session.objects()
        instances, notes = CP.layout(items, CP.scene_boxes(before, groups), designed,
                                     taken=[o.get("name") for o in before])
        stats = {"items": len(instances), "parts": 0, "exact": 0, "moved": 0, "missing": 0,
                 "wrong_place": 0, "wrong_size": 0,      # what "moved" was: a part can be both
                 "wrong_shape": 0,                       # not run; the harness made the part (in "missing")
                 "unfixed": 0,                           # still not right AFTER the harness corrected it
                 "dropped": 0, "notes": notes, "built": [i["id"] for i in instances],
                 "by": "code",                           # who turned the parts into calls
                 "designed": sorted(i["id"] for i in instances if (designed or {}).get(i["recipe"])),
                 # built from the library recipe, not a model design: always said (summary, messages)
                 "library": sorted(i["id"] for i in instances if not (designed or {}).get(i["recipe"]))}
        first_batch = len(self.session.batches)
        try:
            for inst in instances:
                for _text, parts in CP.chunks(inst):
                    self.turn += 1
                    sub = Result(mode="build")
                    calls = [CP.part_call(inst, p) for p in parts]
                    for call, (ok, err) in zip(calls, self.session.apply(calls)):
                        if not ok:
                            sub.errors.append({"tool": call.get("tool"), "error": err})
                        self._emit("tool_call", tool=call.get("tool"),
                                   name=call.get("name") or call.get("object"), ok=ok)
                    sub.calls.extend(calls)
                    result.calls.extend(sub.calls)
                    result.errors.extend(sub.errors)
                    objects = self.session.objects()
                    fixes = []
                    verdicts = []
                    for part in parts:
                        verdict, calls = CP.check_part(inst, part, objects)
                        off_place, off_size = CP.part_faults(inst, part, objects)
                        stats["wrong_place"] += off_place
                        stats["wrong_size"] += off_size
                        stats[verdict] += 1
                        stats["parts"] += 1
                        fixes.extend(calls)
                        verdicts.append((part, verdict))
                    after = None
                    if fixes:
                        self.session.apply(fixes)
                        after = self.session.objects()         # a correction is checked too
                        stats["unfixed"] += sum(1 for part in parts
                                                if CP.check_part(inst, part, after)[0] != "exact")
                    for part, verdict in (verdicts if getattr(self, "listeners", None) else ()):
                        self._emit("part", name=part["name"], verdict=verdict,
                                   unfixed=after is not None and verdict != "exact"
                                   and CP.check_part(inst, part, after)[0] != "exact")
                self.session.apply(CP.finish_calls(inst))
                groups[inst["id"]] = [p["name"] for p in inst["parts"]]
                try:        # what a change answer is applied on; a recipe that cannot be said in words has none
                    self.session.specs[inst["id"]] = AC.spec_from_inst(inst)
                except (KeyError, ValueError, ZeroDivisionError, TypeError):
                    self.session.specs.pop(inst["id"], None)
        finally:
            self.session.merge_from(first_batch)      # one request = one undo unit
        self.session.groups = groups
        wanted = {p["name"] for i in instances for p in i["parts"]} | set(groups)
        had = {o["name"] for o in before}
        stats["strays"] = sorted(o["name"] for o in self.session.objects()
                                 if o["name"] not in had and o["name"] not in wanted)
        result.built = stats
        return result

    def _move_from_plan(self, request, items):
        """A move the word-parser could not read but the planner could: one item that names a
        thing the scene already has, with a place, in a sentence that moves rather than adds."""
        if len(items) != 1 or not items[0].get("place") or not CP.MOVE_VERB.search(str(request).lower()):
            return None
        groups = dict(getattr(self.session, "groups", None) or {})
        boxes = CP.scene_boxes(self.session.objects(), groups)
        subject, _box = CP.find_anchor(items[0].get("id") or items[0].get("recipe"), boxes)
        place = dict(items[0]["place"])
        anchor, _abox = CP.find_anchor(place.get("anchor"), boxes)
        if subject not in boxes or (anchor not in boxes and anchor != CP.SCENE) or subject == anchor:
            return None
        place["anchor"] = anchor
        place["relation"] = CP.relation_word(place.get("relation")) or "next_to"
        if anchor == CP.SCENE:
            place["relation"] = CP.scene_relation(place["relation"])
        if place.get("distance") not in PLACE.GAP:
            place["distance"] = "touching" if place["relation"] in ("on_top_of", "under", "against") else "small"
        return self.run_move(request, parsed=(subject, place))

    def run_finish(self, request):
        """"make the squirrel smooth", "merge the head and the body of the cat": a finish for
        things the scene has is done by code (measured recipes, compile_plan.smooth_calls /
        skin_calls), no model. None when the sentence orders no finish on a thing that is there."""
        objects = self.session.objects()
        if not objects or CP.MOVE_VERB.search(str(request).lower()) and not CP.MERGE_WORDS.search(str(request).lower()):
            return None
        orders = CP.parse_finish(request, objects, dict(getattr(self.session, "groups", None) or {}))
        if not orders:
            return None
        calls, notes = CP.finish_order_calls(orders, objects)
        result = Result(mode="finish")
        self.turn += 1
        for call, (ok, err) in zip(calls, self.session.apply(calls) if calls else []):
            if not ok:
                result.errors.append({"tool": call.get("tool"), "error": err})
        result.calls.extend(calls)
        result.finished = {"orders": [{"do": kind, "on": names} for kind, names in orders], "notes": notes}
        result.text = "; ".join(notes)
        return result

    def run_move(self, request, parsed=None):
        """"put the bench behind the station": the placer answers, or None if this is not that."""
        groups = dict(getattr(self.session, "groups", None) or {})
        objects = self.session.objects()
        boxes = CP.scene_boxes(objects, groups)
        for o in objects:                      # parts under a parent the session did not build itself
            if o.get("parent"):
                groups.setdefault(o["parent"], []).append(o["name"])
        parsed = parsed or CP.parse_move(request, boxes)
        if parsed is None:
            return None
        subject, place = parsed
        mine = {subject} | set(groups.get(subject, []))
        box = boxes[subject]
        # the scene, as an anchor, is everything except the thing being moved
        anchor = CP.scene_box(boxes, without=mine) if place["anchor"] == CP.SCENE else boxes[place["anchor"]]
        size = PLACE.box_extent(box)
        others = [b for n, b in boxes.items()
                  if n not in (subject, place["anchor"]) and n not in groups.get(subject, [])
                  and n not in groups.get(place["anchor"], [])]
        res = PLACE.resolve(place, anchor, size, obstacles=others)
        old = PLACE.box_centre(box)
        delta = [res["centre"][i] - old[i] for i in range(3)]
        handle = next((o for o in objects if o["name"] == subject), None)
        if handle is None:
            return None
        target = [round(handle["loc"][i] + delta[i], 4) for i in range(3)]
        result = Result(mode="place")
        call = {"tool": "set_transform", "object": subject, "location": target}
        self.turn += 1
        for ok, err in self.session.apply([call]):
            if not ok:
                result.errors.append({"tool": "set_transform", "error": err})
        result.calls.append(call)
        result.moved = {"object": subject, "place": place, "to": target,
                        "by": [round(v, 3) for v in delta]}
        return result

    def undo(self):
        return self.session.undo()
