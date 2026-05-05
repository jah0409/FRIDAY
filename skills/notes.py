"""Notes & remember-this skill — quick capture, quick recall.

Two intents:
  - remember_fact: durable fact about the boss / world
  - take_note   : a freeform note with optional tag
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .base import Skill, SkillResult, SkillContext, register

NOTES_FILE = Path("data") / "notes.jsonl"


class RememberFactSkill(Skill):
    name = "remember_fact"
    description = (
        "Save a durable fact about the boss or his world (e.g. "
        "'wife's birthday is 12 March', 'I prefer tea over coffee'). "
        "FRIDAY will recall these in future conversations."
    )
    schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "fact": {"type": "string"},
        },
        "required": ["topic", "fact"],
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        topic = (args.get("topic") or "general").strip()
        fact = (args.get("fact") or "").strip()
        if not fact:
            return SkillResult(False, "Empty fact.")
        ctx.memory.remember(topic=topic, fact=fact, source="explicit", weight=2.0)
        return SkillResult(True, f"Yaad rakh liya, Boss — {topic}: {fact}",
                           {"topic": topic, "fact": fact})


class TakeNoteSkill(Skill):
    name = "take_note"
    description = "Append a freeform note to the boss's notes file."
    schema = {
        "type": "object",
        "properties": {
            "note": {"type": "string"},
            "tag": {"type": "string"},
        },
        "required": ["note"],
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        note = (args.get("note") or "").strip()
        if not note:
            return SkillResult(False, "Empty note.")
        tag = args.get("tag") or "general"
        NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with NOTES_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.time(), "tag": tag, "note": note,
            }) + "\n")
        return SkillResult(True, f"Note saved under '{tag}', Boss.")


class RecallSkill(Skill):
    name = "recall_facts"
    description = "Recall stored facts, optionally filtered by topic."
    schema = {
        "type": "object",
        "properties": {"topic": {"type": "string"}},
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        rows = ctx.memory.recall(topic=args.get("topic"), limit=20)
        if not rows:
            return SkillResult(True, "Kuch yaad nahi, Boss — abhi tak khali hai.")
        msg = "Yaad hai:\n" + "\n".join(
            f"  • [{r['topic']}] {r['fact']}" for r in rows)
        return SkillResult(True, msg, {"facts": rows})


register(RememberFactSkill())
register(TakeNoteSkill())
register(RecallSkill())
