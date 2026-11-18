"""The add-on's log: one request reads as who did what, starting with what the user typed."""
import unittest

from maris3d.copilot import trace


class TraceTest(unittest.TestCase):
    def test_request_reads_in_order(self):
        tr = trace.Trace()
        tr.start("put a bench beside the station")
        tr.say("Router", "new things: plan first")
        tr.say("Planner", "1 thing: bench beside station")
        for k in range(trace.TOOL_LINES + 5):
            tr.tool({"tool": "add_primitive", "name": f"Bench_{k}", "shape": "cube"})
        tr.say("Result", "added 17 objects")
        who = [w for w, _ in tr.last()]
        self.assertEqual(who[:3], ["You", "Router", "Planner"])
        self.assertEqual(who[-1], "Result")
        self.assertEqual(who.count("Blender"), trace.TOOL_LINES + 1)
        self.assertIn("5 more calls (17 in all)", tr.text())

    def test_newest_request_first(self):
        tr = trace.Trace()
        tr.start("first")
        tr.start("second")
        text = tr.text()
        self.assertLess(text.index("second"), text.index("first"))

    def test_copilot_says_who(self):
        from maris3d.copilot.loop import Copilot
        lines = []
        cop = Copilot(runtime=None, session=None)
        cop.say = lambda who, text: lines.append((who, text))
        cop._say("Router", "x")
        cop.say = lambda who, text: 1 / 0          # a broken log never breaks a request
        cop._say("Router", "y")
        self.assertEqual(lines, [("Router", "x")])


if __name__ == "__main__":
    unittest.main()
