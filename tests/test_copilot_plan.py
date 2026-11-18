# SPDX-License-Identifier: Apache-2.0
"""Plan mode: one validated recipe plan, no tools, no execution — and edit requests stay put."""
import hashlib
import json
import unittest

from maris3d.copilot import plan
from maris3d.copilot.loop import Copilot
from maris3d.copilot.protocol import trim_tools
from maris3d.copilot.session import Executor, Session
from maris3d.runtimes.llama_server import LlamaServer

GOOD = '{"recipe": "chair", "count": 4, "material": "oak", "zone": "dining"}'

# Captured from the pre-change code (commit before the Plan switch) for one edit request.
PLANNER_SYSTEM_SHA256 = "29e5a1e094388e0f2c0bda38ca0c8eebcc4be001fab2aa6a9a0c279ecce32814"
EDIT_BODY_SHA256 = "a4f632c52a7fb05a690fbce0f57d7e9263a83788bdcad4b9990e4e8812c94133"


class FakeExec(Executor):
    def __init__(self):
        self.objs, self.calls = [], []

    def reset(self):
        self.objs = []

    def run_call(self, call):
        self.calls.append(call)
        self.objs.append({"name": call.get("name", "Cube"), "type": "MESH", "loc": [0, 0, 0]})
        return True, None

    def objects(self):
        return list(self.objs)


class FakeRuntime:
    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat(self, messages, tool_names, lora_scale=None, max_tokens=1024):
        self.seen.append({"messages": [dict(m) for m in messages], "tools": list(tool_names),
                          "scale": lora_scale, "max_tokens": max_tokens})
        return self.replies.pop(0)


class PlanModeRequest(unittest.TestCase):
    def test_good_plan_is_validated_and_nothing_runs(self):
        rt, ex = FakeRuntime([{"content": GOOD}]), FakeExec()
        res = Copilot(rt, Session(ex)).run("four oak chairs in the dining room", mode="plan")
        self.assertEqual(res.mode, "plan")
        self.assertEqual(res.plan, {"recipe": "chair", "count": 4, "material": "oak", "zone": "dining"})
        self.assertEqual(res.plan_error, "")
        self.assertEqual(res.calls, [])
        self.assertEqual(ex.calls, [])
        ask = rt.seen[0]
        self.assertEqual(ask["tools"], [])
        self.assertEqual(ask["scale"], 0.0)
        self.assertEqual(ask["max_tokens"], 2800)
        self.assertEqual(len(ask["messages"]), 1)
        self.assertTrue(ask["messages"][0]["content"].startswith(plan.PROMPT))
        self.assertIn("four oak chairs", ask["messages"][0]["content"])
        self.assertNotIn("[Scene objects:", ask["messages"][0]["content"])

    def test_bad_json_is_reported_and_not_retried_or_applied(self):
        rt, ex = FakeRuntime([{"content": "I would add four chairs."}]), FakeExec()
        res = Copilot(rt, Session(ex)).run("four chairs", mode="plan")
        self.assertIsNone(res.plan)
        self.assertIn("malformed JSON", res.plan_error)
        self.assertEqual(res.calls, [])
        self.assertEqual(ex.calls, [])
        self.assertEqual(len(rt.seen), 1)  # one ask: no retry, no silent edit fallback

    def test_unknown_recipe_is_rejected(self):
        rt, ex = FakeRuntime([{"content": '{"recipe": "spaceship", "count": 1}'}]), FakeExec()
        res = Copilot(rt, Session(ex)).run("a spaceship", mode="plan")
        self.assertIn("unknown recipe", res.plan_error)
        self.assertEqual(ex.calls, [])

    def test_negative_count_is_rejected(self):
        rt, ex = FakeRuntime([{"content": '{"recipe": "chair", "count": -2}'}]), FakeExec()
        res = Copilot(rt, Session(ex)).run("negative chairs", mode="plan")
        self.assertIn("count must be an integer", res.plan_error)
        self.assertEqual(ex.calls, [])

    def test_a_tool_call_reply_is_never_executed(self):
        reply = '<tool_call>{"name": "add_primitive", "arguments": {"shape": "cube"}}</tool_call>'
        rt, ex = FakeRuntime([{"content": reply}]), FakeExec()
        res = Copilot(rt, Session(ex)).run("add a cube", mode="plan")
        self.assertIn("unknown field", res.plan_error)
        self.assertEqual(ex.calls, [])

    def test_fenced_and_tagged_json_still_parse(self):
        for reply in ('```json\n%s\n```' % GOOD, "<tool_call>%s</tool_call>" % GOOD):
            obj, reason = plan.parse_reply(reply)
            self.assertIsNone(reason)
            self.assertEqual(obj["recipe"], "chair")


class PlanSchema(unittest.TestCase):
    def test_accepts_a_good_plan(self):
        self.assertEqual(plan.check(GOOD), (True, None))
        self.assertEqual(plan.check({"recipe": "pine", "count": 6, "zone": "street_west"}), (True, None))

    def test_rejects_bad_json(self):
        ok, reason = plan.check("not json at all")
        self.assertFalse(ok)
        self.assertIn("malformed JSON", reason)

    def test_rejects_an_unknown_recipe(self):
        ok, reason = plan.check({"recipe": "spaceship"})
        self.assertFalse(ok)
        self.assertIn("unknown recipe", reason)

    def test_rejects_a_negative_and_a_non_integer_count(self):
        for count in (-1, 0, 41, 1.5, True):
            ok, reason = plan.check({"recipe": "chair", "count": count})
            self.assertFalse(ok, count)
            self.assertIn("count must be an integer", reason)

    def test_rejects_coordinates_and_unknown_fields(self):
        ok, reason = plan.check({"recipe": "chair", "location": [0, 0, 0]})
        self.assertFalse(ok)
        self.assertIn("must not place objects", reason)
        ok, reason = plan.check({"recipe": "chair", "colour": "red"})
        self.assertFalse(ok)
        self.assertIn("unknown field", reason)


class EditRequestUnchanged(unittest.TestCase):
    def test_edit_request_is_byte_identical_to_before_the_switch(self):
        names = trim_tools("move the cube left", "edit")
        # `model` is the server's label (llama-server ignores it), not text the model reads: the hash leaves it
        # out and guards the trained bytes (system prompt, tools, LoRA) unchanged
        body = LlamaServer(base_url="http://127.0.0.1:9931", model="maris3d").body(
            [{"role": "user", "content": "move the cube left"}], names, 1.0, 2800)
        blob = json.dumps({k: v for k, v in body.items() if k != "model"}, sort_keys=True)
        self.assertEqual(hashlib.sha256(blob.encode()).hexdigest(), EDIT_BODY_SHA256)
        self.assertEqual(body["lora"], [{"id": 0, "scale": 1.0}])
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["max_tokens"], 2800)
        self.assertEqual(len(body["tools"]), len(names))

    def test_plan_request_has_no_tools_field(self):
        body = LlamaServer().body([{"role": "user", "content": plan.plan_text("a chair")}], [], 0.0, 2800)
        self.assertNotIn("tools", body)
        self.assertEqual(body["lora"], [{"id": 0, "scale": 0.0}])


class PlannerAdapter(unittest.TestCase):
    """Plan mode on a server that has the planner adapter loaded."""

    def test_the_trained_prompt_is_sent_byte_for_byte(self):
        # sha256 of the system prompt in the planner's 420-row held-out set; any edit to the
        # wording is a prompt the adapter never saw
        self.assertEqual(hashlib.sha256(plan.PLANNER_SYSTEM.encode()).hexdigest(), PLANNER_SYSTEM_SHA256)
        msgs = plan.planner_messages("One armchair in the lounge")
        self.assertEqual([m["role"] for m in msgs], ["system", "user"])
        self.assertEqual(msgs[1]["content"], "One armchair in the lounge")
        self.assertEqual(len(plan.PLANNER_RECIPES), 43)

    def test_a_plan_turn_runs_the_planner_alone(self):
        srv = LlamaServer(planner_id=1)
        body = srv.body(plan.planner_messages("a chair"), [], 0.0, 2800, planner=True)
        self.assertEqual(body["lora"], [{"id": 0, "scale": 0.0}, {"id": 1, "scale": 1.0}])
        self.assertNotIn("tools", body)

    def test_build_and_edit_turns_never_run_the_planner(self):
        srv = LlamaServer(planner_id=1)
        for scale in (0.0, 1.0):
            body = srv.body([{"role": "user", "content": "x"}], ["add_primitive"], scale, 100)
            self.assertEqual(body["lora"], [{"id": 0, "scale": scale}, {"id": 1, "scale": 0.0}])

    def test_the_planner_vocabulary_is_accepted_only_when_asked(self):
        ok, _ = plan.check({"recipe": "townhouse", "count": 2, "zone": "street_east"}, plan.PLANNER_RECIPES)
        self.assertTrue(ok)
        ok, reason = plan.check({"recipe": "townhouse"})
        self.assertFalse(ok)
        self.assertIn("unknown recipe", reason)

    def test_copilot_plan_mode_uses_the_planner_when_the_server_has_it(self):
        from maris3d.copilot.loop import Copilot

        class Fake:
            planner_id = 1

            def __init__(self):
                self.seen = None

            def chat(self, messages, tool_names, lora_scale=None, max_tokens=1024, planner=False):
                self.seen = (messages, tool_names, lora_scale, planner)
                return {"content": '{"recipe": "townhouse", "count": 2, "zone": "street_east"}'}

        fake = Fake()
        res = Copilot(fake, None).run("two townhouses on the east side", mode="plan")
        self.assertEqual(res.plan, {"recipe": "townhouse", "count": 2, "zone": "street_east"})
        self.assertTrue(res.planner)
        self.assertEqual(fake.seen[0][0]["content"], plan.PLANNER_SYSTEM)
        self.assertEqual(fake.seen[1:], ([], 0.0, True))

    def test_serve_loads_edit_then_planner_unapplied(self):
        from maris3d import cli
        cmd = cli.serve_command("llama-server", "base.gguf", "edit.gguf", 9931, "planner.gguf")
        i = cmd.index("--lora")
        self.assertEqual(cmd[i:i + 5], ["--lora", "edit.gguf", "--lora", "planner.gguf",
                                        "--lora-init-without-apply"])
        self.assertNotIn("planner.gguf", cli.serve_command("llama-server", "base.gguf", "edit.gguf", 9931))

    def test_the_addon_reads_adapter_ids_by_file_name(self):
        from maris3d.addon import client
        loaded = [{"id": 0, "path": "/m/maris3d-slm-blender-0.5b-planner-lora-f16.gguf", "scale": 0.0},
                  {"id": 1, "path": "/m/maris3d-slm-blender-0.5b-edit-lora-f16.gguf", "scale": 0.0}]
        self.assertEqual(client.adapter_ids(loaded), (1, 0))
        self.assertEqual(client.adapter_ids(loaded[1:]), (1, None))
        self.assertEqual(client.adapter_ids([]), (None, None))


if __name__ == "__main__":
    unittest.main()


# --- motion, named by the plan and performed by the harness --------------------------------
# Measured: asked for keyframes directly, neither adapter produces a usable animation (build: one
# keyframe; edit: many, wrong axis; both drop the object name). Naming the motion works.
def test_a_plan_can_name_a_motion():
    ok, why = plan.check({"recipe": "door", "animate": "door_close", "target": "HeroDoor",
                          "seconds": 1.5})
    assert ok, why


def test_a_motion_must_be_one_the_harness_can_perform():
    ok, why = plan.check({"recipe": "car", "animate": "explode", "target": "CarBody"})
    assert not ok and "animate must be one of" in why


def test_a_motion_needs_a_target():
    ok, why = plan.check({"recipe": "door", "animate": "door_close"})
    assert not ok and "target" in why


def test_a_target_without_a_motion_is_rejected():
    ok, why = plan.check({"recipe": "door", "target": "HeroDoor"})
    assert not ok and "only meaningful with animate" in why


def test_a_plan_still_may_not_send_coordinates():
    # the motion slot must not become a back door for placement
    for key in ("x", "location", "rotation_deg"):
        ok, why = plan.check({"recipe": "door", "animate": "door_close", "target": "D", key: 1})
        assert not ok and "must not place objects" in why


def test_the_motion_vocabulary_is_small_and_human():
    assert "door_close" in plan.ANIMATIONS and "drive_apart" in plan.ANIMATIONS
    assert all(a.islower() and " " not in a for a in plan.ANIMATIONS)


# --- finishes: the plan names it, the harness makes it --------------------------------------
def test_a_plan_can_ask_for_a_smooth_finish():
    ok, why = plan.check({"recipe": "car", "finish": "smooth", "target": "Car"})
    assert ok, why


def test_a_finish_is_a_word_the_harness_knows():
    ok, why = plan.check({"recipe": "car", "finish": "polish"})
    assert not ok and "finish must be one of" in why


def test_the_finish_vocabulary_stays_small():
    assert plan.FINISHES == ("smooth", "bevel", "join", "none")
