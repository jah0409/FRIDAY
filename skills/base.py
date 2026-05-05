"""Skill base class and registry.

A Skill is a small, focused capability. It exposes:
  - name        : unique id
  - description : one-line summary FRIDAY uses to decide when to call it
  - schema      : JSON-schema for its arguments (Anthropic tool format)
  - run(args, ctx) -> SkillResult

The registry is module-level so `from skills import REGISTRY` always
returns every skill that has been loaded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SkillResult:
    ok: bool
    message: str
    data: dict[str, Any] | None = None


class Skill:
    name: str = "unnamed"
    description: str = ""
    schema: dict[str, Any] = {}

    def run(self, args: dict, ctx: "SkillContext") -> SkillResult:
        raise NotImplementedError


@dataclass
class SkillContext:
    """Everything a skill might need from the rest of FRIDAY."""

    memory: Any
    config: dict
    speak: Callable[[str], None]
    log: Any
    extras: dict = field(default_factory=dict)


REGISTRY: dict[str, Skill] = {}


def register(skill: Skill) -> Skill:
    """Decorator-friendly registration."""
    if not skill.name or skill.name == "unnamed":
        raise ValueError("Skill must define a name")
    REGISTRY[skill.name] = skill
    return skill


def as_tool_specs() -> list[dict]:
    """Render the registry into Anthropic tool-use format."""
    tools = []
    for s in REGISTRY.values():
        tools.append({
            "name": s.name,
            "description": s.description,
            "input_schema": s.schema or {
                "type": "object",
                "properties": {},
            },
        })
    return tools
