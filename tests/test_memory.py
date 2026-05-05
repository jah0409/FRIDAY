"""Tests for the evolving memory store."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory import Memory, Turn


def _fresh() -> Memory:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return Memory(tmp.name)


def test_log_and_read_turns():
    m = _fresh()
    m.log_turn(Turn("user", "kaise ho friday", lang="hindi"))
    m.log_turn(Turn("assistant", "Theek hoon Boss", lang="hindi"))
    turns = m.recent_turns(limit=10)
    assert [t.role for t in turns] == ["user", "assistant"]
    assert turns[0].content == "kaise ho friday"


def test_facts_remember_recall():
    m = _fresh()
    m.remember("food", "Boss likes filter coffee")
    m.remember("family", "Wife's birthday is 12 March", weight=2.0)
    rows = m.recall(topic="food")
    assert len(rows) == 1
    all_rows = m.recall()
    assert len(all_rows) == 2
    # higher weight first
    assert all_rows[0]["topic"] == "family"


def test_journal_upsert():
    m = _fresh()
    m.write_journal("2026-05-05", "First day. Learned the basics.")
    m.write_journal("2026-05-05", "Updated summary.")
    j = m.recent_journal(days=5)
    assert len(j) == 1
    assert "Updated" in j[0]["summary"]


def test_counts():
    m = _fresh()
    assert m.fact_count() == 0
    assert m.turn_count() == 0
    m.log_turn(Turn("user", "hi"))
    m.remember("x", "y")
    assert m.fact_count() == 1
    assert m.turn_count() == 1
