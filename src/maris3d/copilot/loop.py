# SPDX-License-Identifier: Apache-2.0
"""One request through the native tool loop: ask, run the calls, return results, ask again."""
import re
import json
from dataclasses import dataclass, field

from . import compile_plan as CP
from . import describe_parts as PARTS
from . import place as PLACE
from . import plan as PLAN
from . import policy as POLICY
from . import protocol as P

PARTS_TOKENS = 900        # one designed object: the longest training answer is 667 tokens
MAX_DESIGNED_PARTS = 24   # the longest training object has 11 parts
MAX_TOKENS = 2800  # output budget per ask; the scored engine uses the same value (engine/runtime.py)


REPEAT_LIMIT = 3     # the identical call may run this many times in one request, never more


@dataclass
class Result:
    calls: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    text: str = ""
    hit_cap: bool = False
    api_error: str = ""
    followup_error: str = ""  # server rejected a later step AFTER calls were applied: keep the work, say so
    failures: list = field(default_factory=list)
    repairs: int = 0          # how many correction turns the checker cost
    mode: str = ""            # build, edit or plan — the mode that actually ran this turn
    plan: dict = None         # plan mode only: the validated recipe plan
    plan_error: str = ""      # plan mode only: why the reply was not a usable plan
    planner: bool = False     # plan mode only: the planner adapter answered (not the base)
    repeated: int = 0         # calls dropped because the model sent the identical call again this turn
    built: dict = None        # a compiled plan: items, parts, how many the model got exact / the harness fixed
    moved: dict = None        # a placement request answered by the placer: what moved where
    finished: dict = None     # a finish order answered by code: what was smoothed, sharpened, merged

    @property
    def ok(self):
        return bool(self.calls) and not self.errors and not self.api_error and not self.failures


ASSIST = {
    # The rule: the router is always on, everything else is a column, not a
    # footnote. One word selects how much harness a run gets, so the published table can say
    # "assist=full" / "assist=route" instead of listing five switches.
    #   off   -> the raw model: one ask, no router, no retries (this is the "model only" row)
    #   route -> the product router only: mode -> adapter, 20 calls, no repair
    #   full  -> router + checker + repair loop + scene fixups (the shipped copilot)
    "off": dict(use_router=False, use_checker=False, repair_limit=0, max_calls=1, fixups=False),
    "route": dict(use_router=True, use_checker=False, repair_limit=0, max_calls=20, fixups=False),
    "full": dict(use_router=True, use_checker=True, repair_limit=2, max_calls=20, fixups=True),
}
DEFAULT_ASSIST = "route"


def make_checker():
    """The product checker: what a repair turn is allowed to complain about.

    Deliberately narrow and honest -- it reports a turn where *every* tool call failed, with the
    errors the tools actually returned. A scene-diff checker (does the result match the request)
    is the next step; until it exists this must not be described as one.
    """
    def check(objects, results=None):
        if not results:
            return []
        failed = [str(err) for ok, err in results if not ok and err]
        if failed and not any(ok for ok, _err in results):
            return ["nothing was built: " + "; ".join(failed[:3])]
        return []
    return check


def assist_settings(level=DEFAULT_ASSIST):
    """Map one assist level to Copilot kwargs. Unknown level -> the default, never silently full."""
    return dict(ASSIST.get(str(level or DEFAULT_ASSIST).lower(), ASSIST[DEFAULT_ASSIST]))


class Copilot:
    """runtime: object with chat(messages, tool_names, lora_scale) -> message dict.
    session: copilot.session.Session. router: optional fn(request, objects, turn) -> 'build'|'edit'.
    checker: optional fn(objects) -> list of failure strings. Repair is off (0) until measured on this model."""

    def __init__(self, runtime, session, router=None, checker=None, max_calls=20, repair_limit=0, scene_cap=40):
        self.runtime, self.session, self.router, self.checker = runtime, session, router, checker
        self.max_calls, self.repair_limit, self.scene_cap = max_calls, repair_limit, scene_cap
        self.messages = []
        self.turn = 0
        # True: the parts planner designs EVERY item and the library is only what is used when its
        # design cannot be built (the planners bring the whole spec; the library is
        # what we had before a model could). False until the parts planner has passed its gate.
        self.design_first = False
        # which model answers a compiled chunk when no build v2 adapter is loaded: 0.0 = the base
        # (build), 1.0 = the edit adapter. Measured on 448 parts: edit 283 exact (63.2 %),
        # the base 144 (32.1 %): the edit adapter answers compiled chunks.
        self.chunk_scale = 1.0
        # two switches for a compiled instruction: offer `add_primitive` alone instead of the
        # trimmed tool list with its two chance tools; and do not ask the model again after its
        # calls have run. Measured: both together are WORSE (edit 63.2 % -> 46.0 %, base
        # 32.1 % -> 25.2 %): they stay off.
        self.chunk_tools_only = False
        self.chunk_one_ask = False

    def run(self, request, mode=None):
        if mode == "plan":
            return self._run_plan(request)
        self.turn += 1
        objects = self.session.objects()
        if mode is None:
            mode = self.router(request, objects, self.turn) if self.router else ("edit" if self.turn > 1 and objects else "build")
        # the scene list goes with every later turn, and with an edit even on the first turn: the
        # panel starts a new copilot per request, so an edit of a scene that is there is always
        # "turn 1" and the model was never told what the scene holds
        bare = self.turn == 1 and not (mode == "edit" and objects)
        text = request if bare else P.followup_text(request, objects, self.scene_cap)
        # one ask per turn, like the scored protocol: the scene summary carries the state. Keeping the
        # previous turn's tool chatter makes the model continue its "Done — ..." text instead of calling.
        self.messages = [{"role": "user", "content": text}]
        names = P.trim_tools(request, mode)
        scale = 1.0 if mode == "edit" else 0.0
        result, step, repairs = Result(mode=mode), 0, 0
        first_batch = len(self.session.batches)
        try:
            self._loop(request, names, scale, result, step)
        finally:
            self.session.merge_from(first_batch)  # one request = one undo unit, however many model steps it took
        # Repair is a real second ask now: the checker names what is wrong, the model gets
        # one correction turn with that sentence, bounded by repair_limit. Before this it only
        # recorded the failures, so `assist=full` and `assist=route` scored the same by accident.
        if self.checker and not result.api_error:
            while repairs < self.repair_limit:
                try:
                    failures = list(self.checker(self.session.objects(),
                                                 getattr(self.session, "last_results", None)))
                except TypeError:
                    failures = list(self.checker(self.session.objects()))
                result.failures = failures
                if not failures:
                    break
                repairs += 1
                self.messages.append({"role": "user", "content":
                                      "That is not right yet: " + "; ".join(failures[:3]) +
                                      ". Fix only that with the tools."})
                self._loop(request, names, scale, result, step)
        result.repairs = repairs
        return result

    def _run_plan(self, request):
        """One ask with no tools: the model answers a recipe plan, never a tool call.
        It is validated here and returned in Result.plan; nothing is applied to the scene,
        and an invalid reply stays an error (there is no silent fallback to edit)."""
        self.turn += 1
        result = Result(mode="plan")
        # a server with the planner adapter loaded gets the adapter's own trained prompt and its
        # own vocabulary; any other server gets the plain instruction (base model, 0/75 parsed)
        planner = getattr(self.runtime, "planner_id", None) is not None
        v3 = planner and getattr(self.runtime, "planner_version", 1) == 3
        recipes = PLAN.PLANNER_RECIPES if planner else None
        result.planner = planner
        if v3:
            self.messages = PLAN.planner_v3_messages(request)
            if getattr(self.runtime, "planner_system", None):    # the installed planner's own prompt
                self.messages[0] = {"role": "system", "content": self.runtime.planner_system}
        else:
            self.messages = (PLAN.planner_messages(request) if planner
                             else [{"role": "user", "content": PLAN.plan_text(request)}])
        try:
            if planner:
                message = self.runtime.chat(self.messages, [], lora_scale=0.0,
                                            max_tokens=MAX_TOKENS, planner=True)
            else:
                message = self.runtime.chat(self.messages, [], lora_scale=0.0, max_tokens=MAX_TOKENS)
        except Exception as error:  # infrastructure failure, never a model answer
            result.api_error = repr(error)[:300]
            return result
        reply = message.get("content") or ""
        result.text = reply
        self.messages.append({"role": "assistant", "content": reply})
        obj, reason = PLAN.parse_reply(reply)
        if reason is None:
            ok, reason = PLAN.check_items(obj) if v3 else PLAN.check(obj, recipes)
        else:
            ok = False
        if ok:
            result.plan = obj
        else:
            result.plan_error = reason or "invalid plan"
        return result

    def _loop(self, request, names, scale, result, step):
        while True:
            try:
                # Same output budget as the scored engine (engine/runtime.py): 1024 truncates the tool-call
                # JSON on prompts that ask for many parts, which Ollama reports as invalid arguments.
                if getattr(self, "role", None):
                    message = self.runtime.chat(self.messages, names, lora_scale=scale, max_tokens=MAX_TOKENS,
                                                role=self.role)
                else:
                    message = self.runtime.chat(self.messages, names, lora_scale=scale, max_tokens=MAX_TOKENS)
            except Exception as error:  # infrastructure failure, never a model answer
                if step > 0:  # work already applied: do not call the whole request failed (a retry would duplicate it)
                    result.followup_error = repr(error)[:300]
                else:
                    result.api_error = repr(error)[:300]
                break
            calls = P.normalise_calls(message)
            # placement policy (see copilot/policy.py): in harness mode the authored coordinates
            # win and the model's own guess is dropped; this is what batching runs on, because a
            # batched reply places 37% exactly against 54% single and the median error is 0.28 m
            calls, _dropped_pos = POLICY.strip_placement(calls)
            if _dropped_pos:
                result.filtered = getattr(result, "filtered", 0) + _dropped_pos
            if scale == 1.0 and calls:
                # Edit mode: the adapter always opens with add_primitive for the object it was asked
                # to edit ("create + change" transcript shape). On an existing object that is a no-op
                # that Blender turns into Name.001 and it pollutes the scene. Drop it, keep the edit.
                existing = {o.get("name") for o in self.session.objects()}
                kept = [c for c in calls
                        if not (c.get("tool") == "add_primitive" and c.get("name") in existing)]
                dropped = len(calls) - len(kept)
                if dropped:
                    result.filtered = getattr(result, "filtered", 0) + dropped
                calls = kept
            only = getattr(self, "only_parts", None)
            if only is None and calls:
                calls = self._to_the_parts(calls)
            if only is None and scale == 1.0 and calls:
                calls, _off = self._edit_guard(request, calls)
                if _off:
                    result.filtered = getattr(result, "filtered", 0) + _off
            if only is not None:
                # a compiled chunk asks for named parts "and nothing else". The model sometimes adds
                # one more (SnowEye3), a second copy (Blender names it SnowEye2.001) or paints
                # everything grey; none of it was asked and there is no delete tool to undo it
                # (station demo run 3: two 1 m spheres in front of the track). Not run, counted.
                have = {o.get("name") for o in self.session.objects()}
                kept = []
                shapes = only if isinstance(only, dict) else {}
                for c in calls:
                    name = c.get("name")
                    if c.get("tool") == "add_primitive" and name in only and name not in have:
                        if shapes.get(name) and c.get("shape") != shapes[name]:
                            # a cube where a cylinder was asked has the right box and would pass
                            # as exact; there is no delete tool, so it is not run: the harness
                            # makes the part and it is counted as a wrong shape
                            result.wrong_shape = getattr(result, "wrong_shape", 0) + 1
                            continue
                        have.add(name)
                        kept.append(c)
                result.filtered = getattr(result, "filtered", 0) + len(calls) - len(kept)
                if calls and not kept:
                    result.text = ""
                    break
                calls = kept
            # A model that has lost its place sends the SAME call again and again (measured on
            # "a bar stool with a seat, four legs and a footrest rail": at repeat penalty 1.1 it wrote
            # one unnamed cube and then that identical call until the token limit). Twice or three
            # times can be meant ("three cubes"); past that it is a loop, and each repeat is one more
            # duplicate object on the same spot. The extras are dropped, and a reply made only of
            # extras ends the turn instead of feeding the loop.
            counts = {}
            for done in result.calls:
                key = json.dumps(done, sort_keys=True)
                counts[key] = counts.get(key, 0) + 1
            fresh = []
            for call in calls:
                key = json.dumps(call, sort_keys=True)
                if counts.get(key, 0) >= REPEAT_LIMIT:
                    result.repeated += 1
                    continue
                counts[key] = counts.get(key, 0) + 1
                fresh.append(call)
            if calls and not fresh:
                result.hit_cap = True
                result.text = "stopped: the model kept repeating a call it had already made"
                break
            calls = fresh
            if not calls:
                result.text = message.get("content") or ""
                self.messages.append({"role": "assistant", "content": result.text})
                break
            step += 1
            msg, ids = P.assistant_message(calls, self.turn, step)
            self.messages.append(msg)
            for cid, call, (ok, err) in zip(ids, calls, self.session.apply(calls)):
                if not ok:
                    result.errors.append({"tool": call.get("tool"), "error": err})
                self.messages.append({"role": "tool", "tool_call_id": cid, "content": P.format_result(ok, err)})
            result.calls.extend(calls)
            if only is not None and getattr(self, "chunk_one_ask", False):
                break                 # a compiled instruction: what is missing the copilot makes
            if len(result.calls) >= self.max_calls:
                result.hit_cap = True
                break

    def _to_the_parts(self, calls):
        """A built thing is an empty with its parts under it. Moving or turning the empty takes
        the parts along; painting it does nothing (an empty has no surface, the tool says ok).
        "Make the chair red" aimed at `Chair` is therefore sent to the parts of Chair."""
        if not any(c.get("tool") == "set_material" and c.get("object") for c in calls):
            return calls
        objects = self.session.objects()
        kind = {o.get("name"): str(o.get("type", "")).upper() for o in objects}
        parts = {}
        for o in objects:
            if o.get("parent"):
                parts.setdefault(o["parent"], []).append(o["name"])
        out = []
        for c in calls:
            name = c.get("object")
            if c.get("tool") == "set_material" and kind.get(name) == "EMPTY" and parts.get(name):
                c = dict({k: v for k, v in c.items() if k != "object"}, objects=list(parts[name]))
            out.append(c)
        return out

    EDIT_TOOLS = ("set_transform", "set_object", "set_material", "duplicate")

    def _edit_guard(self, request, calls):
        """Edit mode, 0.1 guard: "Make Band red." came back as
        set_material(object="all") on 68 objects plus moves of the camera, the lamps and the car.
        There is no delete tool and undo is the user's only way back, so when the sentence names
        things the scene has, only those things (and the parts under them) are edited: "all" is
        narrowed to them and edits aimed at anything else are not run, counted as filtered.
        A sentence that names nothing in the scene only keeps its hands off the camera and lights."""
        objects = self.session.objects()
        names = [o.get("name") for o in objects if o.get("name")]
        low = request.lower()
        words = set(re.findall(r"[a-z]+", low))

        def said(n):
            if re.search(r"(?<![a-z0-9_.])" + re.escape(n.lower()) + r"(?![a-z0-9_])", low):
                return True
            # a part is named by its last real word: RoofA -> roof, HouseWindow1 -> window
            parts = [w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", n.split(".")[0]) if len(w) > 1]
            head = parts[-1] if parts else ""
            return len(head) > 2 and (head in words or head + "s" in words or head + "es" in words)

        named = {n for n in names if said(n)}
        kind = {o.get("name"): str(o.get("type", "")).upper() for o in objects}
        if not named:
            # nothing named: only the camera and the lights are kept out of it, unless the
            # sentence is about them (the same run moved Camera and Light five times)
            if re.search(r"\b(camera|light|lights|lamp|lamps|sun)\b", low):
                return calls, 0
            out = [c for c in calls if not (c.get("tool") in self.EDIT_TOOLS
                                            and kind.get(c.get("object")) in ("CAMERA", "LIGHT"))]
            return out, len(calls) - len(out)
        children = {}
        for o in objects:
            if o.get("parent"):
                children.setdefault(o["parent"], []).append(o["name"])
        allowed, todo = set(), list(named)
        while todo:
            n = todo.pop()
            if n not in allowed:
                allowed.add(n)
                todo.extend(children.get(n, []))
        paintable = sorted(n for n in allowed if kind.get(n) != "EMPTY")
        made = {c.get("name") for c in calls if c.get("tool") == "add_primitive"}
        ok_names = allowed | made
        out, off = [], 0
        for c in calls:
            tool = c.get("tool")
            if tool not in self.EDIT_TOOLS:
                out.append(c)
                continue
            target = c.get("object")
            many = c.get("objects")
            if tool == "set_material" and (str(target).lower() == "all"
                                           or (isinstance(many, list) and "all" in [str(m).lower() for m in many])):
                if not paintable:
                    off += 1
                    continue
                c = dict({k: v for k, v in c.items() if k != "object"}, objects=paintable)
                out.append(c)
                continue
            if isinstance(many, list) and target is None:
                keep = [m for m in many if m in ok_names]
                if not keep:
                    off += 1
                    continue
                out.append(dict(c, objects=keep) if len(keep) != len(many) else c)
                continue
            if target is not None and target not in ok_names:
                off += 1
                continue
            out.append(c)
        return out, off

    # ---- plan first: the planner's answer is compiled, not printed -------------------
    def run_auto(self, request):
        """The whole flow for one sentence: place, or plan -> compile -> build, or the old path.

        Everyone should hit plan first, whether they are doing it manually or auto,
        and a request to put a thing beside or next to another one is answered by the placer. So:
          1. a sentence that moves a thing the scene has, relative to another thing it has, is
             answered by the placer (words -> metres), no model;
          2. otherwise the planner is asked; if it names recipes the library has, the plan is
             compiled into exact instructions and built (run_items);
          3. otherwise the request goes to Build/Edit exactly as before, with the plan attached.
        """
        if CP.is_exact_instruction(request):
            return self.run(request)                # it already states its numbers: straight to Build
        finished = self.run_finish(request)         # needs no model, so it works on any server
        if finished is not None:
            return finished
        if getattr(self.runtime, "planner_id", None) is None:
            # a server with no planner adapter (Ollama, a merged file): the request goes to the
            # model exactly as it did before
            return self.run(request)
        start = len(self.session.batches)
        self._mark_north()
        try:
            return self._auto(request)
        finally:
            self.session.merge_from(start)        # the marker and the request are one undo unit

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
            return moved
        # What kind of request is it? The planner cannot say yet (it has no word for the kind of request yet): it
        # answers every sentence with things to build, so "make the chair red" built a second
        # chair. Until it can, the router's words decide: a change to what the scene has
        # goes to the edit model with the scene list, and is never compiled into a build.
        objects = self.session.objects()
        is_edit = bool(self.router and objects and self.router(request, objects, self.turn) == "edit")
        is_move = bool(CP.MOVE_VERB.search(str(request).lower()))
        if is_edit and not is_move:
            return self.run(request, mode="edit")
        planned = self._run_plan(request)
        listed = CP.plan_items(planned.plan)
        placed = self._move_from_plan(request, [i for i in listed if CP.recipe_key(i.get("recipe"))])
        if placed is not None:
            placed.plan, placed.planner = planned.plan, planned.planner
            return placed
        if is_move and objects:
            # a move the placer and the planner could not turn into a place ("5 metres to the
            # left"): if its one item is a thing the scene has, it is an edit, not a new thing
            boxes = CP.scene_boxes(objects, dict(getattr(self.session, "groups", None) or {}))
            there = len(listed) == 1 and CP.find_anchor(listed[0].get("id") or listed[0].get("recipe"), boxes)[0] in boxes
            if is_edit or there:
                result = self.run(request, mode="edit")
                result.plan, result.planner = planned.plan, planned.planner
                return result
        designed, notes = self._design_missing(listed, request)
        items = [i for i in listed if CP.recipe_key(i.get("recipe"), designed)]
        if items:
            result = self.run_items(items, designed)
            result.built["notes"] = notes + result.built["notes"]
            result.plan, result.planner = planned.plan, planned.planner
            return result
        result = self.run(request)
        result.plan, result.plan_error, result.planner = planned.plan, planned.plan_error, planned.planner
        return result

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
            try:
                message = self.runtime.chat([{"role": "system", "content": PARTS.PARTS_SYSTEM},
                                             {"role": "user", "content": ask}], [], lora_scale=0.0,
                                            max_tokens=PARTS_TOKENS, role="parts")
            except Exception as error:  # infrastructure failure, never a model answer
                notes.append(f"{noun}: the parts planner could not be asked ({repr(error)[:120]})")
                continue
            answer, reason = PLAN.parse_reply(message.get("content") or "")
            recipe, why = PARTS.to_recipe(answer) if reason is None else (None, reason)
            if recipe is None:
                notes.append(f"{noun}: the parts planner's answer cannot be built ({why})")
                continue
            if len(recipe["parts"]) > MAX_DESIGNED_PARTS:
                notes.append(f"{noun}: {len(recipe['parts'])} parts is more than {MAX_DESIGNED_PARTS}")
                continue
            designed[word] = recipe
            notes.append(f"{noun}: designed by the parts planner, {len(recipe['parts'])} parts")
        return designed, notes

    def run_items(self, items, designed=None):
        """Build a list of plan items: layout by words, one exact instruction per part, checked.

        The model does the building (one ask per chunk of at most four parts of one object); what
        it leaves missing or misplaced is corrected by the harness and counted in Result.built, so
        a run always says who did what.
        """
        result = Result(mode="build")
        groups = dict(getattr(self.session, "groups", None) or {})
        before = self.session.objects()
        instances, notes = CP.layout(items, CP.scene_boxes(before, groups), designed)
        stats = {"items": len(instances), "parts": 0, "exact": 0, "moved": 0, "missing": 0,
                 "wrong_place": 0, "wrong_size": 0,      # what "moved" was: a part can be both
                 "wrong_shape": 0,                       # not run; the harness made the part (in "missing")
                 "unfixed": 0,                           # still not right AFTER the harness corrected it
                 "dropped": 0, "notes": notes, "built": [i["id"] for i in instances],
                 "designed": sorted(i["id"] for i in instances if (designed or {}).get(i["recipe"]))}
        # compiled chunks are exact instructions: a build v2 adapter, when the server has one, answers them;
        # a server without it answers with the base, as before
        self.role = "build" if self._has_role("build") else None
        first_batch = len(self.session.batches)
        try:
            for inst in instances:
                for text, parts in CP.chunks(inst):
                    self.turn += 1
                    self.messages = [{"role": "user", "content": text}]
                    sub = Result(mode="build")
                    self.only_parts = {p["name"]: CP.part_call(inst, p)["shape"] for p in parts}
                    try:
                        names = ["add_primitive"] if self.chunk_tools_only else P.trim_tools(text, "build")
                        self._loop(text, names, self.chunk_scale, sub, 0)
                    finally:
                        self.only_parts = None
                    stats["dropped"] += getattr(sub, "filtered", 0) or 0
                    stats["wrong_shape"] += getattr(sub, "wrong_shape", 0) or 0
                    result.calls.extend(sub.calls)
                    result.errors.extend(sub.errors)
                    result.repeated += sub.repeated
                    result.api_error = result.api_error or sub.api_error
                    objects = self.session.objects()
                    fixes = []
                    for part in parts:
                        verdict, calls = CP.check_part(inst, part, objects)
                        off_place, off_size = CP.part_faults(inst, part, objects)
                        stats["wrong_place"] += off_place
                        stats["wrong_size"] += off_size
                        stats[verdict] += 1
                        stats["parts"] += 1
                        fixes.extend(calls)
                    if fixes:
                        self.session.apply(fixes)
                        after = self.session.objects()         # a correction is checked too
                        stats["unfixed"] += sum(1 for part in parts
                                                if CP.check_part(inst, part, after)[0] != "exact")
                self.session.apply(CP.finish_calls(inst))
                groups[inst["id"]] = [p["name"] for p in inst["parts"]]
        finally:
            self.role = None
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
