"""Evolving memory store.

Three layers:
  1. Conversation log — every turn, raw.
  2. Facts — durable things FRIDAY has learned about the boss
     ("Boss likes filter coffee", "Wife's birthday is 12 March").
  3. Daily journal — at end of day, an LLM-written summary of what
     mattered. This is what makes FRIDAY "evolve" — tomorrow's system
     prompt includes yesterday's journal.

All stored in a single SQLite file so it travels with the project.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    role      TEXT NOT NULL,           -- 'user' | 'assistant' | 'system'
    content   TEXT NOT NULL,
    lang      TEXT,                    -- detected language profile
    meta      TEXT                     -- JSON
);

CREATE TABLE IF NOT EXISTS facts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    topic     TEXT NOT NULL,
    fact      TEXT NOT NULL,
    source    TEXT,
    weight    REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS journal (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    day       TEXT UNIQUE NOT NULL,    -- YYYY-MM-DD
    summary   TEXT NOT NULL,
    learned   TEXT,                    -- JSON list of new facts
    mood      TEXT,
    created   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_ts ON conversations(ts);
CREATE INDEX IF NOT EXISTS idx_facts_topic ON facts(topic);
"""


@dataclass
class Turn:
    role: str
    content: str
    lang: str | None = None
    meta: dict | None = None


class Memory:
    """Tiny SQLite-backed memory layer. Thread-safe enough for FRIDAY's needs."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- conversations -------------------------------------------------

    def log_turn(self, turn: Turn) -> None:
        with self._connect() as c:
            c.execute(
                "INSERT INTO conversations(ts, role, content, lang, meta) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    time.time(),
                    turn.role,
                    turn.content,
                    turn.lang,
                    json.dumps(turn.meta) if turn.meta else None,
                ),
            )

    def recent_turns(self, limit: int = 20) -> list[Turn]:
        with self._connect() as c:
            rows = c.execute(
                "SELECT role, content, lang, meta FROM conversations "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        rows = list(reversed(rows))
        return [
            Turn(
                role=r["role"],
                content=r["content"],
                lang=r["lang"],
                meta=json.loads(r["meta"]) if r["meta"] else None,
            )
            for r in rows
        ]

    # ---- facts ---------------------------------------------------------

    def remember(self, topic: str, fact: str, source: str = "chat",
                 weight: float = 1.0) -> None:
        with self._connect() as c:
            c.execute(
                "INSERT INTO facts(ts, topic, fact, source, weight) "
                "VALUES (?, ?, ?, ?, ?)",
                (time.time(), topic.lower().strip(), fact.strip(),
                 source, weight),
            )

    def recall(self, topic: str | None = None, limit: int = 30) -> list[dict]:
        with self._connect() as c:
            if topic:
                rows = c.execute(
                    "SELECT topic, fact, weight FROM facts "
                    "WHERE topic = ? ORDER BY weight DESC, ts DESC LIMIT ?",
                    (topic.lower().strip(), limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT topic, fact, weight FROM facts "
                    "ORDER BY weight DESC, ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    # ---- journal -------------------------------------------------------

    def write_journal(self, day: str, summary: str,
                      learned: Iterable[str] | None = None,
                      mood: str | None = None) -> None:
        with self._connect() as c:
            c.execute(
                "INSERT INTO journal(day, summary, learned, mood, created) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(day) DO UPDATE SET "
                "  summary=excluded.summary, "
                "  learned=excluded.learned, "
                "  mood=excluded.mood",
                (
                    day,
                    summary,
                    json.dumps(list(learned)) if learned else None,
                    mood,
                    time.time(),
                ),
            )

    def recent_journal(self, days: int = 7) -> list[dict]:
        with self._connect() as c:
            rows = c.execute(
                "SELECT day, summary, learned, mood FROM journal "
                "ORDER BY day DESC LIMIT ?",
                (days,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- summary helpers ----------------------------------------------

    def fact_count(self) -> int:
        with self._connect() as c:
            return c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]

    def turn_count(self) -> int:
        with self._connect() as c:
            return c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
