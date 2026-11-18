# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) Maris3D contributors. Runs inside Blender, so it is GPL-3.0-or-later.
"""Maris3D Copilot — the model lives inside Blender.

N-panel ("Maris3D Copilot" tab): type the prompt, press **Run**. By default the
copilot decides whether a request builds or edits (its own routing, the shipped
behaviour); the Auto / Build / Edit switch is an optional override for when you want
to force one. The Edit / Plan switch in the same panel chooses what kind of answer the
prompt asks for: Edit is the shipped tool-call path, Plan asks for one JSON recipe plan
and executes nothing. The page icon expands the prompt into a real multi-line text area in the
Text Editor — Blender panels have no multi-line widget; when the one-line box is empty,
the text block's content runs.

Live per-call progress, a one-line result built from the real scene diff (never from
the model's words), and one Undo per request.

Single-shot prompts only in v0.1 (multi-turn steering is a known weakness: the
honest UX is fresh prompt + undo). No MCP, no free-form code execution — only the
26 fixed tools, translated by the same compiler the model was benchmarked with.

Importable without Blender (packaging/tests): registration is a no-op then.
"""
import json
import os
import sys

bl_info = {"name": "Maris3D Copilot", "author": "Maris3D contributors",
           "version": (0, 1, 1), "blender": (4, 2, 0), "location": "3D View > Maris3D Copilot",
           "category": "View 3D", "description": "Build and edit scenes from a prompt with a local model"}

_HAS_BPY = "bpy" in sys.modules or __import__("importlib.util", fromlist=["x"]).find_spec("bpy") is not None

if not _HAS_BPY:
    # outside Blender: metadata only, so packaging and tests can import this module
    def register():
        pass

    def unregister():
        pass

else:
    import bpy

    from . import executor, routing

    _STATE = {"running": False, "n": 0, "progress": "", "result": "", "error": "",
              "ping": "", "note": "", "dirty": False}

    PROMPT_NAME = "Copilot Prompt"
    SEED_PROMPT = "add a red cube named Box\n"  # a ready-to-run first prompt

    def _prompt_string():
        blk = bpy.data.texts.get(PROMPT_NAME)
        return blk.as_string().strip() if blk else ""

    def _current_prompt(context):
        """The one-line input wins; when it is empty the expanded text-area
        block (Copilot Prompt) runs instead — the panel hint says which."""
        one = context.window_manager.copt_prompt.strip()
        return one or _prompt_string()

    def _ensure_prompt_block():
        """Data-only: create the prompt text block (the expandable text area).
        Safe at any time, including register() — unlike the sidebar toggle."""
        try:
            blk = bpy.data.texts.get(PROMPT_NAME)
            if blk is None:
                blk = bpy.data.texts.new(PROMPT_NAME)
                blk.write(SEED_PROMPT)
        except Exception:
            pass

    def _mode(context):
        """None = Auto: let the copilot route the request itself (the default).
        BUILD/EDIT are explicit overrides."""
        choice = context.window_manager.copt_mode
        return {"BUILD": "build", "EDIT": "edit"}.get(choice)  # AUTO -> None

    def _reveal_sidebar():
        """Open the N-panel sidebar so the Copilot tab is easy to find.

        CRASH NOTE: setting space.show_region_ui fires an RNA update
        (ED_region_visibility_change_update -> WM_window_get_active_workspace)
        that SEGFAULTS Blender when the window/workspace is not fully
        constructed — calling it from register() or a load handler crashed
        every GUI launch (seen in crash reports). Therefore this
        runs ONLY from deferred timers, and only with a complete context."""
        try:
            wm = bpy.context.window_manager
            if bpy.app.background or not wm.windows:
                return None
            if bpy.context.window is None:  # UI not constructed yet — retry a few times
                tries = _STATE.get("_reveal_tries", 0) + 1
                _STATE["_reveal_tries"] = tries
                return 1.0 if tries < 5 else None
            _STATE["_reveal_tries"] = 0
            for window in list(wm.windows):
                try:
                    if getattr(window, "workspace", None) is None:
                        continue  # the exact NULL that segfaulted Blender
                    for area in window.screen.areas:
                        if area.type == "VIEW_3D":
                            for space in area.spaces:
                                if space.type == "VIEW_3D":
                                    space.show_region_ui = True
                except Exception:
                    continue
        except Exception:
            pass
        return None  # one-shot

    @bpy.app.handlers.persistent
    def _on_file_load(_dummy=None):
        # New files reset the layout: re-point the prompt block now (data-only),
        # and re-open the sidebar a beat AFTER the load has fully completed.
        _ensure_prompt_block()
        try:
            bpy.app.timers.register(_reveal_sidebar, first_interval=0.75)
        except Exception:
            pass

    def _redraw_views():
        try:
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "VIEW_3D":
                        area.tag_redraw()
        except Exception:
            pass

    def _tick():
        """Redraw the panel while a request runs so progress actually moves."""
        try:
            if _STATE["running"] or _STATE["dirty"]:
                _redraw_views()
                if not _STATE["running"]:
                    _STATE["dirty"] = False
                return 0.25
        except Exception:
            pass
        return 0.5

    def _wrap(text, width=62, lines=3):
        text = text or ""
        out, cur = [], ""
        for word in text.split():
            if cur and len(cur) + 1 + len(word) > width:
                out.append(cur); cur = word
            else:
                cur = f"{cur} {word}".strip()
            if len(out) == lines:
                out[-1] = out[-1] + "…"; return out
        if cur:
            out.append(cur)
        return out or [""]

    def _settings():
        prefs = bpy.context.preferences.addons[__package__].preferences
        return {"backend": prefs.backend, "server_url": prefs.server_url, "model": prefs.model,
                "ollama_url": prefs.ollama_url, "ollama_model": prefs.ollama_model,
                "assist": prefs.assist, "view_cam": prefs.view_cam}

    def _worker(prompt, settings, mode):
        try:
            from . import client, summary
            from .vendor import plan as plan_mod
            from .vendor.loop import Copilot, assist_settings, make_checker
            from .vendor.session import Session
            rt = client.make_client(settings)
            if not getattr(rt, "has_adapter", True):
                _STATE["note"] = "no edit adapter on this server — the merged file serves build and edit"
            ex = executor.QueueExecutor(on_call=lambda call: _STATE.update(
                progress=f"step {_STATE['n'] + 1}: {call.get('tool')}", n=_STATE["n"] + 1))
            before = list(ex.objects())
            _STATE["progress"] = "asking the model…"
            # one switch for how much harness a turn gets (EVAL-PROTOCOL-2026-11-10.md):
            # route = router only, full = router + checker + repair. The router itself is the
            # caller (routing.resolve), so it is always on.
            level = str(settings.get("assist") or "route").lower()
            cfg = assist_settings(level)
            sess = Session(ex)
            checker = make_checker() if cfg["use_checker"] else None
            cop = Copilot(rt, sess, checker=checker, max_calls=cfg["max_calls"],
                          repair_limit=cfg["repair_limit"],
                          router=lambda req, objs, _turn: routing.resolve(req, bool(objs), "AUTO"))
            # Auto = plan first (everyone should hit plan first, whether they are
            # doing it manually or auto): the placer, or planner -> compile -> build, or -- for
            # an exact instruction or a server without the planner -- the request as before.
            res = cop.run_auto(prompt) if mode is None else cop.run(prompt, mode=mode)
            print(f"COPT-TURN mode={res.mode or mode or 'auto'} prompt={prompt[:80]!r}", flush=True)
            if mode == "plan":
                _STATE["note"] = "plan only — nothing was executed"
                if res.api_error:
                    _STATE["error"] = f"server: {res.api_error}"
                elif res.plan_error:
                    _STATE["error"] = f"plan rejected: {res.plan_error}"
                elif res.plan:
                    _STATE["result"] = f"[plan] {plan_mod.describe(res.plan)}"
                    print(f"COPT-PLAN {json.dumps(res.plan, sort_keys=True)}", flush=True)
                else:
                    _STATE["error"] = "plan: the model returned no plan"
                return
            after = ex.objects()
            if getattr(res, "plan_error", None):
                # Auto asked the planner and could not use its answer: the request went to the
                # model without a plan (the old path). Say so; before, this was silent.
                _STATE["note"] = f"no usable plan ({str(res.plan_error)[:60]}) — built without one"
            if res.api_error:
                _STATE["error"] = f"server: {res.api_error}"
            elif res.followup_error:
                _STATE["error"] = f"work kept, a later step failed: {res.followup_error}"
            # a compiled plan can change the scene with no model call kept (the model answered
            # nothing usable and the copilot made every part): that is still a result and an undo step
            changed = bool(res.calls) or bool(getattr(res, "built", None) and res.built.get("parts"))
            # (a finish order done by code has calls too; its line comes from summary.built_line)
            if changed:
                executor.submit(("undo_push", f"Copilot: {prompt[:60]}"))
                _STATE["result"] = f"{summary.scene_diff(before, after, res)} ({len(res.calls)} calls)"
                did = summary.built_line(res)
                if did:
                    _STATE["result"] += f" — {did}"
                if settings.get("view_cam") == "FOLLOW" and not _STATE.get("external_camera"):
                    # follow the build: look at what this request made (new objects first, else
                    # whatever its calls touched), from an eye the scene says can see it
                    had = {o["name"] for o in before}
                    made = [o["name"] for o in after if o["name"] not in had]
                    made = made or [c.get("name") or c.get("object") for c in res.calls
                                    if c.get("name") or c.get("object")]
                    if made:
                        try:
                            executor.submit(("follow", made))
                        except Exception:
                            pass        # never lose the work over a camera move
            elif not _STATE["error"]:
                notes = "; ".join((getattr(res, "built", None) or {}).get("notes") or [])
                _STATE["result"] = (notes or res.text or "The model did not call any tools.")[:160]
        except Exception as e:
            try:
                import traceback
                traceback.print_exc()  # full detail in the Blender console; the panel shows one line
            except Exception:
                pass
            _STATE["error"] = f"{type(e).__name__}: {e}"[:200]
        finally:
            _STATE.update(running=False, progress="", n=0, dirty=True)

    def _ping_worker(settings):
        try:
            from . import client
            _STATE["ping"] = client.ping(settings)
        except Exception as e:
            _STATE["ping"] = f"{type(e).__name__}: {e}"[:120]
        _STATE["dirty"] = True

    class COPT_OT_run(bpy.types.Operator):
        bl_idname, bl_label = "copt.run", "Run"
        bl_description = ("Run the prompt as Edit (tool calls, applied) or Plan "
                          "(one validated JSON recipe plan, executed not at all)")

        @classmethod
        def poll(cls, context):
            return not _STATE["running"] and bool(_current_prompt(context))

        def execute(self, context):
            prompt = _current_prompt(context)
            if not prompt:
                self.report({"WARNING"}, "Type a prompt first")
                return {"CANCELLED"}
            prefs = bpy.context.preferences.addons[__package__].preferences
            has_objects = bool(executor.scene_objects())  # main-thread safe (no queue)
            if prefs.plan_mode == "PLAN":
                mode = "plan"
            else:
                # Auto = None: the copilot routes the request itself (run_auto: placer, planner ->
                # compile -> build, or the edit model). Before, this line resolved Auto to
                # build / edit here, so run_auto was never reached from the panel.
                mode = _mode(context)
                if mode == "edit" and not has_objects:
                    _STATE.update(result="", dirty=True,
                                  error="Edit mode needs an existing scene — switch to Auto or Build, "
                                        "or add an object first.")
                    self.report({"WARNING"}, "Nothing to edit in an empty scene")
                    return {"CANCELLED"}
            settings = _settings()
            if not settings["server_url"] and settings["backend"] == "LLAMA_SERVER":
                _STATE.update(result="", dirty=True, error="Set the llama-server URL in the add-on preferences.")
                self.report({"WARNING"}, "llama-server URL is empty")
                return {"CANCELLED"}
            _STATE.update(running=True, n=0, progress="starting…", result="", error="",
                          note="", dirty=True)
            import threading
            threading.Thread(target=_worker, args=(prompt, settings, mode), daemon=True).start()
            return {"FINISHED"}

    class COPT_OT_undo(bpy.types.Operator):
        bl_idname, bl_label = "copt.undo", "Undo"
        bl_description = "Revert the last Copilot request (one Blender undo step)"

        @classmethod
        def poll(cls, context):
            return not _STATE["running"]

        def execute(self, context):
            try:
                bpy.ops.ed.undo()  # each request was committed as one named step
            except Exception as e:
                self.report({"WARNING"}, f"nothing to undo ({e})")
            return {"FINISHED"}

    class COPT_OT_test(bpy.types.Operator):
        bl_idname, bl_label = "copt.test", "Test server"
        bl_description = "Ping the configured model server"

        def execute(self, context):
            import threading
            _STATE["ping"] = "pinging…"
            _STATE["dirty"] = True
            threading.Thread(target=_ping_worker, args=(_settings(),), daemon=True).start()
            return {"FINISHED"}

    class COPT_OT_open_editor(bpy.types.Operator):
        bl_idname, bl_label = "copt.open_editor", "Expand prompt"
        bl_description = ("Expand: move the prompt into a real multi-line text area "
                          "(Text Editor) beside the 3D view — it runs when the "
                          "one-line input is empty")

        def execute(self, context):
            blk = bpy.data.texts.get(PROMPT_NAME)
            if blk is None:
                blk = bpy.data.texts.new(PROMPT_NAME)
                blk.write(SEED_PROMPT)
            # expanding carries what you typed: the one-liner moves into the text area
            one = context.window_manager.copt_prompt.strip()
            if one and (not blk.as_string().strip() or blk.as_string().strip() == SEED_PROMPT.strip()):
                blk.clear()
                blk.write(one + "\n")
                context.window_manager.copt_prompt = ""
            # reuse any existing text editor, else turn the Outliner (or the largest
            # non-3D area) into one — pure data ops, no fragile context-dependent operators
            target = None
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "TEXT_EDITOR":
                        target = area
                        break
                    if area.type == "OUTLINER" and target is None:
                        target = area
                if target is not None and target.type == "TEXT_EDITOR":
                    break
            if target is None or target.type != "TEXT_EDITOR":
                best = -1
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type != "VIEW_3D" and area.width * area.height > best:
                            best, target = area.width * area.height, area
            if target is None:
                self.report({"WARNING"}, "Only a 3D view exists — split an area first, then retry")
                return {"CANCELLED"}
            target.type = "TEXT_EDITOR"
            for space in target.spaces:
                if space.type == "TEXT_EDITOR":
                    space.text = blk
                    try:
                        space.show_word_wrap = True
                    except Exception:
                        pass
            return {"FINISHED"}

    class COPT_PT_main(bpy.types.Panel):
        bl_label = "Maris3D Copilot"
        bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", "Maris3D Copilot"

        def draw(self, context):
            col = self.layout.column(align=True)
            if bpy.app.version < (4, 2, 0):
                col.label(text="Needs Blender 4.2+ (5.2 LTS verified)", icon="ERROR")
                return
            prefs = bpy.context.preferences.addons[__package__].preferences
            wm = context.window_manager
            col.label(text=f"{prefs.model or prefs.ollama_model}", icon="SETTINGS")
            if _STATE["error"]:
                box = col.box()
                for line in _wrap(_STATE["error"]):
                    box.label(text=line, icon="ERROR")
            col.separator()
            # Send as: Edit is the shipped tool-call path; Plan asks for one recipe plan
            col.label(text="Send as")
            col.prop(prefs, "plan_mode", expand=True)
            if prefs.plan_mode == "EDIT":
                # Auto is the shipped behaviour; Build/Edit are explicit overrides
                col.prop(wm, "copt_mode", expand=True)
            row = col.row(align=True)
            row.prop(wm, "copt_prompt", text="", icon="SHADERFX")
            row.operator("copt.open_editor", text="", icon="FILE_TEXT")
            row = col.row(align=True)
            row.scale_y = 1.3
            run_label = ("Plan" if prefs.plan_mode == "PLAN"
                         else {"AUTO": "Run", "BUILD": "Build", "EDIT": "Apply edit"}[wm.copt_mode])
            row.operator("copt.run", text=run_label, icon="PLAY")
            row.operator("copt.undo", text="Undo", icon="LOOP_BACK")
            if _STATE["running"]:
                col.label(text=_STATE["progress"] or "working…", icon="RENDER_RESULT")
            elif not wm.copt_prompt.strip():  # the expanded text area runs when the line is empty
                blk = bpy.data.texts.get(PROMPT_NAME)
                if blk is not None and blk.as_string().strip():
                    for ln in [l for l in blk.as_string().strip().split("\n") if l.strip()][:2]:
                        col.label(text=ln[:48], icon="SHADERFX")
                    col.label(text="↑ the text-area prompt runs (box is empty)", icon="INFO")
                elif not _STATE["result"] and prefs.plan_mode == "EDIT":
                    col.label(text="Auto: the copilot decides build or edit", icon="INFO")
            if prefs.plan_mode == "PLAN" and not _STATE["running"]:
                col.label(text="Plan: one recipe plan, nothing is executed", icon="INFO")
            if _STATE["result"]:
                col.separator()
                for line in _wrap(_STATE["result"]):
                    col.label(text=line)
            if _STATE["note"]:
                col.label(text=_STATE["note"], icon="INFO")
            if _STATE["ping"]:
                col.separator()
                for line in _wrap(_STATE["ping"]):
                    col.label(text=line, icon="INFO")

    VIEW_PATH = os.path.expanduser("~/.maris3d/view.json")

    def _write_policy(prefs):
        """Expose the build policy as user settings, not environment variables.

        Measured on the take's own rows (place_probe.py): build + single places a part exactly
        54% of the time with a 0.0000 m median; adding batching drops that to 37% and 0.28 m, and
        batching with the model placing would be worse still. So batch mode hands placement to
        the harness -- the authored coordinates decide, the model only chooses shapes.
        """
        os.environ["MARIS3D_PLACEMENT"] = prefs.placement.lower()
        os.environ["MARIS3D_BATCH"] = "1" if prefs.batch_parts else "0"

    def _write_view_config(prefs):
        """Persist the look where the maintainers' take driver and harness read it.

        The maintainers' take driver (not part of this repository) loads this file as its base and
        lets --cam/--beat/--no-log override it, so the same settings cover every scene: the
        camera mode, the pan beats and which columns are on screen.
        """
        try:
            os.makedirs(os.path.dirname(VIEW_PATH), exist_ok=True)
            data = {
                "mode": {"FOLLOW": "follow", "AREA": "area", "OFF": "off"}[prefs.view_cam],
                "showcase": bool(prefs.view_showcase),
                "idle_s": float(prefs.view_idle),
                "beat_s": float(prefs.view_beat),
                "panels": {"log": bool(prefs.view_log),
                           "outliner": bool(prefs.view_outliner),
                           "sidebar": bool(prefs.view_sidebar)},
            }
            with open(VIEW_PATH, "w") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            _STATE["view"] = VIEW_PATH
        except Exception as e:                       # never break a session over a preference
            _STATE["view_error"] = str(e)

    class COPT_preferences(bpy.types.AddonPreferences):
        bl_idname = __package__
        backend: bpy.props.EnumProperty(items=[("LLAMA_SERVER", "llama-server", "The scored path (ctx 8192, temp 0)"),
                                               ("OLLAMA", "Ollama", "Use an already-installed Ollama")],
                                        default="LLAMA_SERVER")
        server_url: bpy.props.StringProperty(name="llama-server URL", default="http://127.0.0.1:9931")
        model: bpy.props.StringProperty(name="model name", default="maris3d",
                                        description="the -m alias your llama-server was started with")
        ollama_url: bpy.props.StringProperty(name="Ollama URL", default="http://127.0.0.1:11434")
        ollama_model: bpy.props.StringProperty(name="Ollama model",
                                                default="hf.co/slm4apps/Maris3D-Blender:Q8_0")
        assist: bpy.props.EnumProperty(
            name="Assist",
            description="How much the harness does for the model. Route = the router only; "
                        "Full adds the checker and one repair turn when the scene is wrong",
            items=[("ROUTE", "Route", "Router only: mode -> adapter, no repair (the benchmark default)"),
                   ("FULL", "Full", "Router + checker + repair turn (the shipped copilot)"),
                   ("OFF", "Off", "Model only: one ask, no router, no repair")],
            default="ROUTE")
        plan_mode: bpy.props.EnumProperty(
            name="Send as",
            description="Edit sends the prompt as native tool calls and applies them; "
                        "Plan asks for one JSON recipe plan and executes nothing",
            items=[("EDIT", "Edit", "Send the prompt as a native tool call and apply it (the shipped behaviour)"),
                   ("PLAN", "Plan", "Ask for one JSON recipe plan; validate and show it, execute nothing")],
            default="EDIT")
        view_cam: bpy.props.EnumProperty(
            name="Camera",
            description="Where the 3D view looks while the copilot builds. Follow turns the view to "
                        "what each request just made, from an angle that can see it; Area keeps "
                        "one framing per room (takes only); Off never moves your view",
            items=[("FOLLOW", "Follow", "After each request, look at what it built"),
                   ("AREA", "Area", "One framing per room area, slow sweep (the old behaviour)"),
                   ("OFF", "Off", "No automatic camera")],
            default="FOLLOW", update=lambda self, ctx: _write_view_config(self))
        view_showcase: bpy.props.BoolProperty(
            name="Idle pan", default=True,
            description="After the idle time, pan the piece left / back / right / back / top / back",
            update=lambda self, ctx: _write_view_config(self))
        view_idle: bpy.props.IntProperty(
            name="Idle before pan (s)", default=6, min=0, max=120,
            update=lambda self, ctx: _write_view_config(self))
        view_beat: bpy.props.IntProperty(
            name="Beat length (s)", default=6, min=1, max=60,
            update=lambda self, ctx: _write_view_config(self))
        view_log: bpy.props.BoolProperty(
            name="Show prompt log", default=True,
            description="Keep the live prompt/response column on the left of the take window",
            update=lambda self, ctx: _write_view_config(self))
        view_outliner: bpy.props.BoolProperty(
            name="Show object list", default=True,
            description="Keep the scene collection column on the right of the take window",
            update=lambda self, ctx: _write_view_config(self))
        view_sidebar: bpy.props.BoolProperty(
            name="Show transform bar", default=False,
            description="Blender's N-panel. Off by default: the numbers are noise in a recording",
            update=lambda self, ctx: _write_view_config(self))

        placement: bpy.props.EnumProperty(
            name="Placement",
            description="Who decides where a part sits. Measured: the model is exact when it "
                        "states a location (median 0.0000 m), so Model is the default",
            items=[("MODEL", "Model places", "The model states the position; the harness checks and repairs it"),
                   ("HARNESS", "Harness places", "The authored coordinates always win; the model only picks shapes")],
            default="MODEL", update=lambda self, ctx: _write_policy(self))
        batch_parts: bpy.props.IntProperty(
            name="Batch parts per prompt", default=0, min=0, max=4,
            description="0 = one part per prompt (most accurate, 54% exact placement). Up to 4 = "
                        "far fewer turns (204 -> 76 on the street), but the harness then places "
                        "every part, because batching drops exact placement to 37%",
            update=lambda self, ctx: _write_policy(self))

        def draw(self, context):
            self.layout.prop(self, "plan_mode", expand=True)
            self.layout.prop(self, "backend")
            if self.backend == "LLAMA_SERVER":
                self.layout.prop(self, "server_url")
                self.layout.prop(self, "model")
            else:
                self.layout.prop(self, "ollama_url")
                self.layout.prop(self, "ollama_model")
            build = self.layout.box()
            build.label(text="Build")
            build.prop(self, "placement")
            build.prop(self, "batch_parts")
            box = self.layout.box()
            box.label(text="View (takes and the harness)")
            box.prop(self, "view_cam")
            box.prop(self, "view_showcase")
            if self.view_showcase:
                row = box.row(align=True)
                row.prop(self, "view_idle")
                row.prop(self, "view_beat")
            row = box.row(align=True)
            row.prop(self, "view_log")
            row.prop(self, "view_outliner")
            row.prop(self, "view_sidebar")
            row = self.layout.row()
            row.operator("copt.test", icon="FILE_REFRESH")
            if _STATE["ping"]:
                for line in _wrap(_STATE["ping"]):
                    self.layout.label(text=line, icon="INFO")

    _CLASSES = (COPT_OT_run, COPT_OT_undo, COPT_OT_test, COPT_OT_open_editor,
                COPT_PT_main, COPT_preferences)

    def register():
        if bpy.app.background:  # headless: preferences only (the installer writes URLs here),
            # no UI, no WindowManager props, no timers
            bpy.utils.register_class(COPT_preferences)
            return
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
        bpy.types.WindowManager.copt_prompt = bpy.props.StringProperty(
            name="Prompt", description="What should the Copilot build or edit?", subtype="NONE", maxlen=0)
        bpy.types.WindowManager.copt_mode = bpy.props.EnumProperty(
            name="Mode",
            description="Auto lets the copilot decide; Build/Edit force a mode for this request",
            items=[("AUTO", "Auto", "The copilot decides whether this request builds or edits"),
                   ("BUILD", "Build", "Force build: add objects to the scene"),
                   ("EDIT", "Edit", "Force edit: change what is already in the scene")],
            default="AUTO")
        _ensure_prompt_block()  # data-only; the sidebar reveal is timer-deferred (crash-safe)
        bpy.app.timers.register(executor.pump, persistent=True)  # THE one queue drain
        bpy.app.timers.register(_tick, persistent=True)          # live panel progress
        # 2.5s post-startup: the workspace is fully constructed by then (proven-safe delay)
        bpy.app.timers.register(_reveal_sidebar, first_interval=2.5)
        bpy.app.handlers.load_post.append(_on_file_load)  # re-opens after every file load

    def unregister():
        if bpy.app.background:
            try:
                bpy.utils.unregister_class(COPT_preferences)
            except Exception:
                pass
            return
        for timer in (executor.pump, _tick, _reveal_sidebar):
            try:
                bpy.app.timers.unregister(timer)
            except Exception:
                pass
        try:
            bpy.app.handlers.load_post.remove(_on_file_load)
        except Exception:
            pass
        del bpy.types.WindowManager.copt_prompt
        del bpy.types.WindowManager.copt_mode
        for cls in reversed(_CLASSES):
            bpy.utils.unregister_class(cls)
