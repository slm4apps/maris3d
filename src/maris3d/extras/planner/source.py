# SPDX-License-Identifier: Apache-2.0
"""Planner setting and fallback order.

Order for every request: recipe match, then the configured planner, then builder self-plan.
The setting picks the middle stage only:
    recipes -> recipe match, then self-plan (no network, the default)
    lora    -> recipe match, then the LoRA planner (S5b; caller supplies the callable), then self-plan
    api     -> recipe match, then the API planner, then self-plan
    self    -> recipe match, then self-plan
Every candidate must pass validate.check before it is used. The API planner is built and
called only when the setting is "api" (make_api_planner returns None otherwise).
"""
import json
from dataclasses import dataclass, field

from . import plan as P
from . import validate
from .api import ApiPlanner, PlannerError

SOURCES = ("recipes", "lora", "api", "self")
DEFAULT_SOURCE = "recipes"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PlannerConfig:
    source: str = DEFAULT_SOURCE
    base_url: str = ""
    model: str = ""
    key_env: str = ""
    key_file: str = ""
    timeout: float = 30.0


@dataclass
class Resolution:
    plan: dict
    source: str                      # "recipe", "lora", "api" or "self"; None when nothing passed
    reasons: list = field(default_factory=list)


def config_from(mapping=None):
    """Build the planner config from the `planner` block of the MCP config. Empty means the default."""
    mapping = dict(mapping or {})
    unknown = sorted(set(mapping) - {"source", "base_url", "model", "key_env", "key_file", "timeout"})
    if unknown:
        raise ConfigError("unknown planner config key(s): " + ", ".join(unknown))
    source = mapping.get("source", DEFAULT_SOURCE)
    if source not in SOURCES:
        raise ConfigError("planner source must be one of: " + ", ".join(SOURCES))
    if source == "api" and (not mapping.get("base_url") or not mapping.get("model")):
        raise ConfigError("planner source api needs base_url and model")
    if mapping.get("key_env") and mapping.get("key_file"):
        raise ConfigError("set key_env or key_file, not both")
    return PlannerConfig(source=source, base_url=mapping.get("base_url", ""), model=mapping.get("model", ""),
                         key_env=mapping.get("key_env", ""), key_file=mapping.get("key_file", ""),
                         timeout=float(mapping.get("timeout", 30.0)))


def make_api_planner(config):
    """The API planner when the setting selects it, else None. No object, no network, otherwise."""
    if config.source != "api":
        return None
    return ApiPlanner(config.base_url, config.model, key_env=config.key_env or None,
                      key_file=config.key_file or None, timeout=config.timeout)


def resolve(prompt, config, *, recipe_lookup=None, planner=None, self_plan=None, max_parts=P.MAX_PARTS):
    """Run the fallback chain. Each stage is a callable(prompt) -> plan or None, or None when switched off.

    Returns a Resolution. plan is None only when every stage was off, empty or invalid.
    A failing stage adds a plain reason and the chain moves on; an invalid plan never leaves here.
    """
    stages = [("recipe", recipe_lookup)]
    if config.source in ("lora", "api"):
        stages.append((config.source, planner))
    stages.append(("self", self_plan))

    reasons = []
    for label, stage in stages:
        if stage is None:
            reasons.append(f"{label}: off")
            continue
        try:
            candidate = stage(prompt)
        except PlannerError as exc:
            reasons.append(f"{label}: failed ({exc})")
            continue
        except Exception as exc:  # the reason is the exception type only, never its message
            reasons.append(f"{label}: failed ({type(exc).__name__})")
            continue
        if candidate is None:
            reasons.append(f"{label}: no plan")
            continue
        ok, reason = validate.check(candidate, max_parts)
        if not ok:
            reasons.append(f"{label}: rejected, {reason}")
            continue
        if isinstance(candidate, (str, bytes)):
            candidate = json.loads(candidate)
        return Resolution(plan=candidate, source=label, reasons=reasons)
    return Resolution(plan=None, source=None, reasons=reasons)
