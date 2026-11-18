"""Who places a part, and whether to batch -- the two settings that trade accuracy for speed.

The numbers are from the 24-part probe on the take's own rows (a placement probe).

    build single   location 83% | exact 54% | median 0.0000 m      <- the default
    build batch(4) location 83% | exact 37% | median 0.2800 m
    edit  single   location 83% | exact 41% | median 0.2750 m
    edit  batch(4) location 70% | exact 29% | median 0.5500 m
"""
from maris3d.copilot import policy


def clean_env(monkeypatch):
    for k in ("MARIS3D_PLACEMENT", "MARIS3D_BATCH"):
        monkeypatch.delenv(k, raising=False)


def test_the_default_is_the_mode_that_measured_exact():
    assert policy.placement_mode() == "model"
    assert policy.effective_placement() == "model"
    assert policy.batching() is False


def test_batching_always_places_from_the_harness():
    # batching doubles the median placement error, so a batched run cannot rely on the model
    policy.__dict__  # noqa: B018
    import os
    os.environ["MARIS3D_BATCH"] = "1"
    try:
        assert policy.effective_placement() == "harness"
    finally:
        del os.environ["MARIS3D_BATCH"]


def test_an_unknown_setting_falls_back_to_the_safe_mode(monkeypatch):
    monkeypatch.setenv("MARIS3D_PLACEMENT", "banana")
    assert policy.placement_mode() == "model"


def test_model_placement_is_left_alone():
    calls = [{"tool": "add_primitive", "shape": "cube", "name": "Seat", "location": [1, 2, 3]}]
    out, dropped = policy.strip_placement(calls)
    assert dropped == 0 and out[0]["location"] == [1, 2, 3]


def test_harness_placement_drops_the_models_own_position(monkeypatch):
    # the model's "offset" replies are the ones that came back with flipped and zeroed values,
    # so both spellings go
    monkeypatch.setenv("MARIS3D_PLACEMENT", "harness")
    calls = [{"tool": "add_primitive", "shape": "cube", "name": "Seat", "offset": [2, -0.4, 0.06]},
             {"tool": "set_transform", "object": "Seat", "location": [-2.0, -0.4, 0.45]}]
    out, dropped = policy.strip_placement(calls)
    assert dropped == 1
    assert "offset" not in out[0] and "location" not in out[0]
    # the authored transform row is the answer and is never touched
    assert out[1]["location"] == [-2.0, -0.4, 0.45]


def test_a_part_with_no_position_is_not_counted_as_dropped(monkeypatch):
    monkeypatch.setenv("MARIS3D_PLACEMENT", "harness")
    _out, dropped = policy.strip_placement([{"tool": "add_primitive", "shape": "torus"}])
    assert dropped == 0


def test_the_batch_limit_is_the_one_that_was_measured():
    # six mixed parts loop or duplicate; four coherent parts of one object hold
    assert policy.MAX_BATCH_PARTS == 4


def test_the_log_line_states_what_is_in_force(monkeypatch):
    assert "placement=model" in policy.describe() and "batch=off" in policy.describe()
    monkeypatch.setenv("MARIS3D_BATCH", "1")
    assert "placement=harness" in policy.describe() and "batch=on" in policy.describe()


from tests._plain import as_testcase  # noqa: E402

Plain = as_testcase(globals(), before=clean_env)
