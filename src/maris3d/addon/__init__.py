# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) Maris3D contributors. Runs inside Blender, so it is GPL-3.0-or-later.
"""Maris3D Copilot — the model lives inside Blender.

N-panel ("Maris3D Copilot" tab): type the prompt, press **Run**. There is one way in: the
request goes to the copilot's own flow (plan first: the placer, the word edit, or planner
-> compile -> build). The page icon expands the prompt into a real multi-line text area in the
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
           "version": (0, 2, 0), "blender": (4, 2, 0), "location": "3D View > Maris3D Copilot",
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

    from . import executor, routing, show

    _STATE = {"running": False, "n": 0, "progress": "", "result": "", "error": "",
              "ping": "", "note": "", "dirty": False,
              "question": None, "asked": ""}   # Maris's open question (choice buttons) and its request

    _SESSION = {"session": None}    # the copilot session of the open file (reset on file load)

    PROMPT_NAME = "Copilot Prompt"
    LOG_NAME = "Copilot Log"        # who did what, every request, newest first (vendor/trace.py)
    _TRACE = {"trace": None, "written": -1}

    def _trace():
        if _TRACE["trace"] is None:
            from .vendor.trace import Trace
            _TRACE["trace"] = Trace()
        return _TRACE["trace"]

    def _write_log():
        """Main thread only: copy the trace into the Copilot Log text block when it changed."""
        tr = _TRACE["trace"]
        if tr is None or tr.version == _TRACE["written"]:
            return
        try:
            blk = bpy.data.texts.get(LOG_NAME) or bpy.data.texts.new(LOG_NAME)
            blk.clear()
            blk.write(tr.text())
            _TRACE["written"] = tr.version
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == "TEXT_EDITOR":
                        area.tag_redraw()
        except Exception:
            pass
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

    def _reveal_sidebar():
        """Open the N-panel sidebar so the Copilot tab is easy to find.

        Setting space.show_region_ui fires an RNA update
        (ED_region_visibility_change_update -> WM_window_get_active_workspace)
        that SEGFAULTS Blender when the window/workspace is not fully
        constructed — calling it from register() or a load handler crashes Blender
        on GUI launch. Therefore this
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
        _SESSION["session"] = None          # a new file: nothing in it was built by this session
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
        _write_log()
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
                "ollama_parts_model": prefs.ollama_parts_model,
                "view_cam": prefs.view_cam}

    def _worker(prompt, settings):
        try:
            from . import client, summary
            from .vendor.loop import Copilot
            from .vendor.session import Session
            tr = _trace()
            tr.start(prompt)
            rt = client.make_client(settings)
            if not getattr(rt, "final_format", False):
                _STATE["note"] = "the one adapter is not loaded on this server: the copilot has no model to ask"
            def on_call(call):
                _STATE.update(progress=f"step {_STATE['n'] + 1}: {call.get('tool')}", n=_STATE["n"] + 1)
                tr.tool(call)
            ex = executor.QueueExecutor(on_call=on_call)
            before = list(ex.objects())
            _STATE["progress"] = "asking the model…"
            # one session for the whole file: what was built stays known to the next request
            sess = _SESSION.get("session")
            if sess is None:
                sess = _SESSION["session"] = Session(ex)
            else:
                sess.rebind(ex)
            cop = Copilot(rt, sess, router=lambda req, objs, _turn: routing.resolve(req, bool(objs)))
            cop.say = tr.say
            def on_show(actions, _prompt=prompt):
                from .vendor import show as show_core
                q = show_core.question_of(actions)
                if q:                            # one button per choice; a click sends the answer
                    _STATE.update(question=q, asked=_prompt, dirty=True)
                show.post_actions(actions)
            cop.show = on_show                   # the model's show lines (say/maris/ask/clear)
            cop.listeners.append(show.post)      # Maris reacts (queued, applied on the main thread)
            # plan first, for everyone: the placer, the word edit, or planner -> compile -> build
            res = cop.run_auto(prompt)
            print(f"COPT-TURN mode={res.mode or 'auto'} prompt={prompt[:80]!r}", flush=True)
            after = ex.objects()
            if getattr(res, "plan_error", None):
                _STATE["note"] = f"no usable plan ({str(res.plan_error)[:60]}): nothing was built"
            if res.api_error:
                _STATE["error"] = f"server: {res.api_error}"
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
                tr.say("Result", _STATE["result"])
                _STATE["_said_result"] = True
                if settings.get("view_cam") == "FOLLOW" and not _STATE.get("external_camera"):
                    # follow the build: look at what this request made (new objects first, else
                    # whatever its calls touched), from an eye the scene says can see it
                    had = {o["name"] for o in before}
                    made = [o["name"] for o in after if o["name"] not in had]
                    made = made or [c.get("name") or c.get("object") for c in res.calls
                                    if c.get("name") or c.get("object")]
                    if made:
                        tr.say("Camera", "glides to " + ", ".join(str(m) for m in made[:4])
                               + (f" and {len(made) - 4} more" if len(made) > 4 else ""))
                        try:
                            executor.submit(("follow", made))
                        except Exception:
                            pass        # never lose the work over a camera move
            elif not _STATE["error"]:
                notes = "; ".join((getattr(res, "built", None) or {}).get("notes") or [])
                _STATE["result"] = (notes or res.text or "The model gave no usable answer.")[:160]
        except Exception as e:
            try:
                import traceback
                traceback.print_exc()  # full detail in the Blender console; the panel shows one line
            except Exception:
                pass
            _STATE["error"] = f"{type(e).__name__}: {e}"[:200]
        finally:
            try:
                tr = _trace()
                if _STATE["error"]:
                    tr.say("Error", _STATE["error"])
                elif _STATE["result"] and not _STATE.pop("_said_result", False):
                    tr.say("Result", _STATE["result"])
                if _STATE["note"]:
                    tr.say("Note", _STATE["note"])
            except Exception:
                pass
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
        bl_description = "Run the prompt: the copilot places, edits or builds, plan first"

        @classmethod
        def poll(cls, context):
            return not _STATE["running"] and bool(_current_prompt(context))

        def execute(self, context):
            prompt = _current_prompt(context)
            if not prompt:
                self.report({"WARNING"}, "Type a prompt first")
                return {"CANCELLED"}
            settings = _settings()
            if not settings["server_url"] and settings["backend"] == "LLAMA_SERVER":
                _STATE.update(result="", dirty=True, error="Set the llama-server URL in the add-on preferences.")
                self.report({"WARNING"}, "llama-server URL is empty")
                return {"CANCELLED"}
            _STATE.update(running=True, n=0, progress="starting…", result="", error="",
                          note="", question=None, dirty=True)
            import threading
            threading.Thread(target=_worker, args=(prompt, settings), daemon=True).start()
            return {"FINISHED"}

    class COPT_OT_maris_answer(bpy.types.Operator):
        bl_idname, bl_label = "copt.maris_answer", "Answer Maris"
        bl_description = "Answer Maris's question with this choice: the request runs again with it"

        index: bpy.props.IntProperty(default=0, options={"HIDDEN"})

        @classmethod
        def poll(cls, context):
            return not _STATE["running"] and bool(_STATE["question"])

        def execute(self, context):
            from .vendor import show as show_core
            q = _STATE["question"] or {}
            choices = q.get("choices") or []
            if not 0 <= self.index < len(choices):
                return {"CANCELLED"}
            context.window_manager.copt_prompt = show_core.answer_prompt(_STATE["asked"], choices[self.index])
            _STATE.update(question=None, dirty=True)
            return bpy.ops.copt.run()

    class COPT_OT_undo(bpy.types.Operator):
        bl_idname, bl_label = "copt.undo", "Undo"
        bl_description = "Revert the last Copilot request (one Blender undo step)"

        @classmethod
        def poll(cls, context):
            return not _STATE["running"]

        def execute(self, context):
            try:
                bpy.ops.ed.undo()  # each request was committed as one named step
                if _SESSION["session"] is not None:
                    _SESSION["session"].forget_last()
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
            row = col.row(align=True)
            row.prop(wm, "copt_prompt", text="", icon="SHADERFX")
            row.operator("copt.open_editor", text="", icon="FILE_TEXT")
            row = col.row(align=True)
            row.scale_y = 1.3
            row.operator("copt.run", text="Run", icon="PLAY")
            row.operator("copt.undo", text="Undo", icon="LOOP_BACK")
            if _STATE["running"]:
                col.label(text=_STATE["progress"] or "working…", icon="RENDER_RESULT")
            elif not wm.copt_prompt.strip():  # the expanded text area runs when the line is empty
                blk = bpy.data.texts.get(PROMPT_NAME)
                if blk is not None and blk.as_string().strip():
                    for ln in [l for l in blk.as_string().strip().split("\n") if l.strip()][:2]:
                        col.label(text=ln[:48], icon="SHADERFX")
                    col.label(text="↑ the text-area prompt runs (box is empty)", icon="INFO")
            if _STATE["result"]:
                col.separator()
                for line in _wrap(_STATE["result"]):
                    col.label(text=line)
            if _STATE["note"]:
                col.label(text=_STATE["note"], icon="INFO")
            q = _STATE["question"]
            if q and not _STATE["running"]:
                box = col.box()
                for line in _wrap(q["question"]):
                    box.label(text=line, icon="QUESTION")
                row = box.row(align=True)
                for i, choice in enumerate(q["choices"]):
                    row.operator("copt.maris_answer", text=choice[:24]).index = i
            if _STATE["ping"]:
                col.separator()
                for line in _wrap(_STATE["ping"]):
                    col.label(text=line, icon="INFO")

    class COPT_PT_log(bpy.types.Panel):
        """The last request, step by step: who did what, starting with what you typed.
        Every request is kept in the Copilot Log text block (Text Editor), newest first."""
        bl_label = "Log"
        bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", "Maris3D Copilot"
        bl_parent_id = "COPT_PT_main"

        def draw(self, context):
            col = self.layout.column(align=True)
            lines = _trace().last() if _TRACE["trace"] is not None else []
            if not lines:
                col.label(text="Run a prompt: each step shows here", icon="INFO")
                return
            for who, text in lines[-14:]:
                parts = _wrap(text, width=40, lines=2)
                row = col.split(factor=0.3, align=True)
                row.label(text=who)
                row.label(text=parts[0])
                for more in parts[1:]:
                    row = col.split(factor=0.3, align=True)
                    row.label(text="")
                    row.label(text=more)
            col.separator()
            col.operator("copt.open_log", text="Open full log", icon="TEXT")

    class COPT_OT_open_log(bpy.types.Operator):
        bl_idname, bl_label = "copt.open_log", "Open full log"
        bl_description = "Show the Copilot Log (every request, who did what) in a Text Editor"

        def execute(self, context):
            _write_log()
            blk = bpy.data.texts.get(LOG_NAME) or bpy.data.texts.new(LOG_NAME)
            areas = [a for w in context.window_manager.windows for a in w.screen.areas]
            target = next((a for a in areas if a.type == "TEXT_EDITOR"), None)
            if target is None:
                others = [a for a in areas if a.type != "VIEW_3D"]
                target = max(others, key=lambda a: a.width * a.height, default=None)
            if target is None:
                self.report({"WARNING"}, "Only a 3D view exists — split an area first, then retry")
                return {"CANCELLED"}
            target.type = "TEXT_EDITOR"
            for space in target.spaces:
                if space.type == "TEXT_EDITOR":
                    space.text = blk
                    space.show_word_wrap = True
                    space.show_line_numbers = False
            return {"FINISHED"}

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
        ollama_model: bpy.props.StringProperty(
            name="Ollama model (one)", default="maris3d-slm-blender-0.5b",
            description="The Ollama entry built from the base file plus the one adapter (Modelfile)")
        ollama_parts_model: bpy.props.StringProperty(
            name="Ollama model (parts)", default="",
            description="Optional: the Ollama entry built from the base file plus the parts adapter")
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

        def draw(self, context):
            self.layout.prop(self, "backend")
            if self.backend == "LLAMA_SERVER":
                self.layout.prop(self, "server_url")
                self.layout.prop(self, "model")
            else:
                self.layout.prop(self, "ollama_url")
                self.layout.prop(self, "ollama_model")
                self.layout.prop(self, "ollama_parts_model")
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
            box = self.layout.box()
            box.label(text="Maris (also in the panel's Maris section)")
            box.prop(self, "maris_on")
            row = box.row(align=True)
            row.prop(self, "fun_finish")
            row.prop(self, "effects")
            row.prop(self, "maris_in_renders")
            row = self.layout.row()
            row.operator("copt.test", icon="FILE_REFRESH")
            if _STATE["ping"]:
                for line in _wrap(_STATE["ping"]):
                    self.layout.label(text=line, icon="INFO")

    # Maris switches live in the preferences so they persist (addon/show.py)
    COPT_preferences.__annotations__.update(show.pref_props())

    _CLASSES = (COPT_OT_run, COPT_OT_maris_answer, COPT_OT_undo, COPT_OT_test, COPT_OT_open_editor, COPT_OT_open_log,
                COPT_PT_main, COPT_PT_log, COPT_preferences)

    def register():
        if bpy.app.background:  # headless: preferences only (the installer writes URLs here),
            # no UI, no WindowManager props, no timers
            bpy.utils.register_class(COPT_preferences)
            return
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
        bpy.types.WindowManager.copt_prompt = bpy.props.StringProperty(
            name="Prompt", description="What should the Copilot build or edit?", subtype="NONE", maxlen=0)
        _ensure_prompt_block()  # data-only; the sidebar reveal is timer-deferred (crash-safe)
        bpy.app.timers.register(executor.pump, persistent=True)  # THE one queue drain
        bpy.app.timers.register(_tick, persistent=True)          # live panel progress
        # 2.5s post-startup: the workspace is fully constructed by then (proven-safe delay)
        bpy.app.timers.register(_reveal_sidebar, first_interval=2.5)
        bpy.app.handlers.load_post.append(_on_file_load)  # re-opens after every file load
        show.register()                                   # Maris sub-panel, timer, save handlers

    def unregister():
        if bpy.app.background:
            try:
                bpy.utils.unregister_class(COPT_preferences)
            except Exception:
                pass
            return
        show.unregister()
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
        for cls in reversed(_CLASSES):
            bpy.utils.unregister_class(cls)
