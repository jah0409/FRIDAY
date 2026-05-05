"""Smoke tests for the skill registry and a few built-in skills."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory import Memory
from skills import REGISTRY
from skills.base import SkillContext
from skills.loader import load_all


def _ctx() -> SkillContext:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return SkillContext(
        memory=Memory(tmp.name),
        config={"owner": {"city": "Mumbai", "address_as": "Boss"}},
        speak=lambda s: None,
        log=None,
    )


def test_skills_load():
    load_all()
    # core skills should have registered themselves
    for name in ("schedule", "system_status", "remember_fact", "recall_facts",
                 "self_build_skill", "open_app_or_url"):
        assert name in REGISTRY, f"missing skill: {name}"


def test_status_skill():
    load_all()
    res = REGISTRY["system_status"].run({}, _ctx())
    assert res.ok
    assert "Time" in res.message


def test_remember_then_recall():
    load_all()
    ctx = _ctx()
    REGISTRY["remember_fact"].run(
        {"topic": "food", "fact": "Boss prefers chai"}, ctx)
    res = REGISTRY["recall_facts"].run({"topic": "food"}, ctx)
    assert res.ok
    assert "chai" in res.message


def test_scheduler_parses_relative():
    load_all()
    res = REGISTRY["schedule"].run(
        {"label": "Test reminder", "when": "in 5 minutes"}, _ctx())
    assert res.ok
    assert "Test reminder" in res.message


def test_shell_blocks_destructive():
    load_all()
    res = REGISTRY["run_shell"].run(
        {"command": "rm -rf /tmp/something"}, _ctx())
    assert not res.ok
    assert "destructive" in res.message.lower()
