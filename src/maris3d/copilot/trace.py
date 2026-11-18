"""trace.py -- who did what for one request, as a readable log.

The copilot answers one sentence with several workers: the router decides what kind of request
it is, the placer moves a thing by words, the planner lists the things to build, the parts
planner designs a thing the library lacks, code lays out and builds the parts, a model writes
tool calls, Blender runs them, and the camera looks at the result. Each says one line here, in
order, so the add-on can show the whole process starting from what the user typed:

    -- 3  10:21:05 ------------------------------
    You            put a bench beside the station
    Router         a new thing: plan first
    Planner        1 thing: bench beside station
    Code           lays out 1 thing, 4 parts
    Blender        add_primitive Bench_Seat
    ...
    Result         added 4 objects (4 calls)
    Camera         glides to Bench

Pure Python, no Blender: the add-on writes the lines into a text block.
"""
import threading
import time

WHO_WIDTH = 14
TOOL_LINES = 12        # a long build shows its first tool calls, then one line for the rest


class Trace:
    """Lines of the current and earlier requests, newest request last. Thread safe: the copilot
    runs in a worker thread, the add-on reads from Blender's main thread."""

    def __init__(self, keep=30):
        self.keep = keep
        self.requests = []          # [{"n", "time", "lines": [(who, text)], "tools": int}]
        self._lock = threading.Lock()
        self._count = 0
        self.version = 0            # bumps on every change, so a reader knows when to redraw

    def start(self, prompt):
        with self._lock:
            self._count += 1
            self.requests.append({"n": self._count, "time": time.strftime("%H:%M:%S"),
                                  "lines": [], "tools": 0})
            self.requests = self.requests[-self.keep:]
            self.version += 1
        self.say("You", prompt)

    def say(self, who, text):
        text = " ".join(str(text or "").split())
        if not text:
            return
        with self._lock:
            if not self.requests:
                self.requests.append({"n": 0, "time": time.strftime("%H:%M:%S"), "lines": [], "tools": 0})
            self.requests[-1]["lines"].append((who, text))
            self.version += 1

    def tool(self, call):
        """One tool call Blender ran. After TOOL_LINES of them a request only counts the rest."""
        with self._lock:
            req = self.requests[-1] if self.requests else None
        if req is None:
            return
        req["tools"] += 1
        if req["tools"] <= TOOL_LINES:
            self.say("Blender", call_line(call))
        elif req["tools"] == TOOL_LINES + 1:
            self.say("Blender", "...")
        else:
            with self._lock:
                self.version += 1

    def last(self):
        """(who, text) lines of the newest request, with the tool count folded in."""
        with self._lock:
            if not self.requests:
                return []
            return _folded(self.requests[-1])

    def text(self):
        """The whole log, newest request first, for a text block."""
        with self._lock:
            reqs = list(self.requests)
        out = []
        for req in reversed(reqs):
            out.append(f"-- {req['n']}  {req['time']} " + "-" * 30)
            for who, text in _folded(req):
                out.append(f"{who:<{WHO_WIDTH}} {text}")
            out.append("")
        return "\n".join(out)


def _folded(req):
    lines = []
    for who, text in req["lines"]:
        if who == "Blender" and text == "...":
            text = f"... {req['tools'] - TOOL_LINES} more calls ({req['tools']} in all)"
        lines.append((who, text))
    return lines


def call_line(call):
    """add_primitive Bench_Seat, set_transform Bench, set_material Bench red ..."""
    tool = str(call.get("tool") or "?")
    name = call.get("name") or call.get("object") or ""
    bits = [tool, str(name)]
    for key in ("shape", "color", "material"):
        if isinstance(call.get(key), str):
            bits.append(call[key])
    return " ".join(b for b in bits if b)


def plan_line(plan, describe=None):
    """'2 things: station; bench beside station' from a planner answer."""
    if not plan:
        return ""
    try:
        if describe is not None:
            return describe(plan)
    except Exception:
        pass
    items = plan.get("items") or plan.get("objects") or []
    return f"{len(items)} things"
