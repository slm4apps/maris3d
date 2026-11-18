"""Who places a part: the model, or the harness. And whether to batch.

Measured on the take's own rows (24 authored parts): when the model emits a location it
is exact -- median 0.0000 m in build+single. Everything that went wrong was the model NOT emitting
one, or emitting it as ``offset``: build+single placed 54% exactly, build+batch(4) 37% with a
0.28 m median error, edit+single 41% (0.275 m), edit+batch(4) 29% (0.55 m).

So the two settings are related:

  placement=model    the model states the position, the harness verifies it and repairs it.
                     This is the default and the only mode that measured exact.
  placement=harness  the harness ignores what the model stated and places the part from the
                     authored coordinates. Required for batching (batching doubles the error),
                     and the only safe choice when a row's transform is authored anyway.

Batching is a speed setting, not an accuracy one: the street scene took 204 model turns in single
mode and 76 batched, at 1.55 s per batch, with 66 of 74 batches exactly right. It is worth it for
a long scene the user is willing to watch the harness place; it is the wrong default.

Set them with the environment (or the copilot UI once it exposes them):

    MARIS3D_PLACEMENT=harness MARIS3D_BATCH=1
"""
import os

PLACEMENT_MODES = ("model", "harness")

# the largest number of parts one reply may be asked for; six mixed parts loop or duplicate
# (measured), four coherent parts of ONE object hold
MAX_BATCH_PARTS = 4


def placement_mode():
    """'model' (default) or 'harness'."""
    v = (os.environ.get("MARIS3D_PLACEMENT") or "model").strip().lower()
    return v if v in PLACEMENT_MODES else "model"


def batching():
    """True when the caller asked for batched builds (faster, harness places)."""
    return (os.environ.get("MARIS3D_BATCH") or "0").strip().lower() in ("1", "true", "yes", "on")


def effective_placement():
    """The mode actually in force: batching always implies harness placement."""
    return "harness" if batching() else placement_mode()


def strip_placement(calls):
    """Drop the model's own position so the authored transform decides it, in harness mode.

    Returns (calls, dropped). Only add_primitive carries a position to argue with; a
    set_transform row is the authored answer and is never touched.
    """
    if effective_placement() != "harness":
        return calls, 0
    dropped = 0
    out = []
    for c in calls:
        if c.get("tool") == "add_primitive" and ("location" in c or "offset" in c):
            c = {k: v for k, v in c.items() if k not in ("location", "offset")}
            dropped += 1
        out.append(c)
    return out, dropped


def describe():
    """One line for a log header: what placement and batching are in force."""
    return (f"placement={effective_placement()} batch={'on' if batching() else 'off'} "
            f"(max {MAX_BATCH_PARTS} parts per reply)")
