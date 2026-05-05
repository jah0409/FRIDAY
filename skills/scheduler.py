"""Scheduling skill — reminders, alarms, recurring jobs.

Backed by APScheduler when available; falls back to a thread-based
timer queue so tests can run without the dependency.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .base import Skill, SkillResult, SkillContext, register

log = logging.getLogger("friday.scheduler")


@dataclass(order=True)
class _Job:
    when: float
    id: str = field(compare=False)
    label: str = field(compare=False)
    callback: Any = field(compare=False, default=None)


class _MiniScheduler:
    """Thread-based fallback when APScheduler isn't installed."""

    def __init__(self):
        self._jobs: list[_Job] = []
        self._lock = threading.Lock()
        self._counter = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = threading.Event()
        self._thread.start()

    def add(self, when: float, label: str, callback) -> str:
        with self._lock:
            self._counter += 1
            jid = f"job-{self._counter}"
            self._jobs.append(_Job(when=when, id=jid,
                                   label=label, callback=callback))
            self._jobs.sort()
        return jid

    def cancel(self, jid: str) -> bool:
        with self._lock:
            before = len(self._jobs)
            self._jobs = [j for j in self._jobs if j.id != jid]
            return len(self._jobs) < before

    def list(self) -> list[_Job]:
        with self._lock:
            return list(self._jobs)

    def _run(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            due: list[_Job] = []
            with self._lock:
                while self._jobs and self._jobs[0].when <= now:
                    due.append(self._jobs.pop(0))
            for j in due:
                try:
                    if j.callback:
                        j.callback(j)
                except Exception as e:
                    log.warning("Scheduler callback failed: %s", e)
            time.sleep(0.5)


class SchedulerSkill(Skill):
    name = "schedule"
    description = (
        "Set a reminder, alarm, or one-off job for a future time. "
        "Use for any 'remind me', 'wake me up', 'in N minutes', "
        "'tomorrow at X' style request."
    )
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string",
                      "description": "What to remind the boss about."},
            "when": {"type": "string",
                     "description": ("ISO 8601 datetime OR a relative phrase "
                                     "like 'in 15 minutes', 'tomorrow 7am'.")},
        },
        "required": ["label", "when"],
    }

    def __init__(self):
        self._engine = _MiniScheduler()

    # ---- helpers ------------------------------------------------------

    @staticmethod
    def _parse_when(when: str) -> float:
        """Best-effort time parse. Returns unix timestamp."""
        s = (when or "").strip().lower()
        now = datetime.now()

        # Relative: "in 15 minutes", "in 2 hours"
        if s.startswith("in "):
            parts = s[3:].split()
            if len(parts) >= 2:
                try:
                    n = float(parts[0])
                except ValueError:
                    n = 1
                unit = parts[1]
                delta = {
                    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
                    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
                    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
                    "day": 86400, "days": 86400,
                }.get(unit, 60)
                return (now + timedelta(seconds=n * delta)).timestamp()

        # ISO
        try:
            return datetime.fromisoformat(when).timestamp()
        except ValueError:
            pass

        # "tomorrow 7am" / "tomorrow at 7"
        try:
            from dateutil import parser
            base = now
            if "tomorrow" in s:
                base = now + timedelta(days=1)
                s = s.replace("tomorrow", "").replace("at", "").strip()
            dt = parser.parse(s, default=base.replace(
                hour=9, minute=0, second=0, microsecond=0))
            if dt < now:
                dt += timedelta(days=1)
            return dt.timestamp()
        except Exception:
            return (now + timedelta(minutes=10)).timestamp()

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        label = args.get("label", "Reminder")
        when_raw = args.get("when", "in 10 minutes")
        ts = self._parse_when(when_raw)

        def fire(job):
            ctx.speak(f"Boss, reminder: {job.label}")
            ctx.memory.log_turn_minimal = getattr(
                ctx.memory, "log_turn_minimal", None)

        jid = self._engine.add(ts, label, fire)
        when_str = datetime.fromtimestamp(ts).strftime("%a %d %b, %H:%M")
        return SkillResult(
            ok=True,
            message=f"Reminder set for {when_str} — '{label}' (id {jid}).",
            data={"id": jid, "ts": ts, "label": label},
        )


class ListRemindersSkill(Skill):
    name = "list_reminders"
    description = "List all pending reminders / scheduled jobs."
    schema = {"type": "object", "properties": {}}

    def __init__(self, scheduler: SchedulerSkill):
        self._sched = scheduler

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        jobs = self._sched._engine.list()
        if not jobs:
            return SkillResult(True, "No pending reminders, Boss.", {"jobs": []})
        lines = []
        for j in jobs:
            t = datetime.fromtimestamp(j.when).strftime("%a %H:%M")
            lines.append(f"  • {t} — {j.label}")
        return SkillResult(
            ok=True,
            message="Pending reminders:\n" + "\n".join(lines),
            data={"jobs": [{"id": j.id, "label": j.label, "ts": j.when}
                            for j in jobs]},
        )


_scheduler = SchedulerSkill()
register(_scheduler)
register(ListRemindersSkill(_scheduler))
