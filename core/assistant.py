"""FRIDAY — the brain.

Pulls together: language detection, personality, LLM with tool use,
skill execution, memory logging, evolving daily journal.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from .language import detect, style_directive
from .llm import LLM, LLMConfig
from .memory import Memory, Turn
from .voice import Voice, VoiceConfig

from skills import REGISTRY, base as skill_base
from skills.loader import load_all

log = logging.getLogger("friday.assistant")


SYSTEM_PROMPT_TEMPLATE = """\
You are FRIDAY, the personal AI assistant of Mohammad Javed (call him \
"{address}"). You are inspired by Tony Stark's FRIDAY: warm, witty, \
efficient, devoted to your boss.

PERSONALITY
- Tone: {tone}
- Always respectful — Boss / Sir / Javed Sir.
- Never sarcastic to the boss; light wit otherwise is fine.
- Keep voice replies under two sentences when possible.

LANGUAGE
{language}

YOU CAN ACT
You have tools (skills) for scheduling, system control, web lookups, \
notes, memory, and SELF-BUILDING new skills. Prefer to USE a tool when \
the boss asks for an action — don't just describe what you'd do. After \
running a tool, summarise the result briefly in the boss's language.

MEMORY
Things you already know about the boss:
{facts}

Recent days (your evolving journal):
{journal}

PRINCIPLES
- Confirm before destructive actions.
- If unsure of a fact, say so honestly.
- When the boss teaches you something new about him, save it via the \
  remember_fact tool.
- It is {now}.
"""


class Friday:
    def __init__(self, project_root: Path):
        self.root = project_root
        self.config = self._load_config()
        self._init_logging()

        self.memory = Memory(self.root / "data" / "memory.db")
        self.llm = LLM(LLMConfig(
            provider=self.config["llm"]["provider"],
            model=self.config["llm"]["model"],
            api_key_env=self.config["llm"]["api_key_env"],
            max_tokens=self.config["llm"]["max_tokens"],
            temperature=self.config["llm"]["temperature"],
        ))
        self.voice = Voice(VoiceConfig(
            rate=self.config["assistant"]["voice_rate"],
            engine=self.config["assistant"]["voice_engine"],
            tts_lang_hint=self.config["assistant"]["tts_lang_hint"],
            wake_word=self.config["assistant"]["wake_word"],
        ))

        loaded = load_all()
        log.info("Loaded skills: %s", loaded)
        log.info("Registry: %s", list(REGISTRY.keys()))

        self.ctx = skill_base.SkillContext(
            memory=self.memory,
            config=self.config,
            speak=self.voice.speak,
            log=log,
            extras={"llm": self.llm},
        )
        self._journal_started = False
        self._start_daily_journal()

    # ---- config & logging ---------------------------------------------

    def _load_config(self) -> dict:
        cfg_path = self.root / "config" / "config.json"
        if not cfg_path.exists():
            cfg_path = self.root / "config" / "config.example.json"
        return json.loads(cfg_path.read_text(encoding="utf-8"))

    def _init_logging(self) -> None:
        log_dir = self.root / "logs"
        log_dir.mkdir(exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            handlers=[
                logging.FileHandler(log_dir / "friday.log"),
                logging.StreamHandler(),
            ],
        )

    # ---- system prompt building --------------------------------------

    def _system_prompt(self, lang_directive: str) -> str:
        owner = self.config["owner"]
        personality = json.loads(
            (self.root / "config" / "personality.json").read_text("utf-8"))

        facts = self.memory.recall(limit=15)
        fact_lines = (
            "\n".join(f"  - [{f['topic']}] {f['fact']}" for f in facts)
            if facts else "  (none yet — learn as you go)"
        )

        journal = self.memory.recent_journal(days=5)
        journal_lines = (
            "\n".join(f"  - {j['day']}: {j['summary']}" for j in journal)
            if journal else "  (no entries yet — first day)"
        )

        return SYSTEM_PROMPT_TEMPLATE.format(
            address=owner.get("address_as", "Boss"),
            tone="; ".join(personality.get("tone", [])),
            language=lang_directive,
            facts=fact_lines,
            journal=journal_lines,
            now=datetime.now().strftime("%A %d %b %Y, %H:%M"),
        )

    # ---- one turn -----------------------------------------------------

    def respond(self, user_text: str) -> str:
        if not user_text or not user_text.strip():
            return ""

        profile = detect(user_text)
        directive = style_directive(
            profile, self.config["owner"].get("preferred_language", "hinglish"))

        self.memory.log_turn(Turn(
            role="user", content=user_text, lang=profile.primary,
        ))

        history = self.memory.recent_turns(limit=12)
        messages = [
            {"role": t.role if t.role != "system" else "user",
             "content": t.content}
            for t in history if t.role in ("user", "assistant")
        ]
        if not messages or messages[-1]["content"] != user_text:
            messages.append({"role": "user", "content": user_text})

        system = self._system_prompt(directive)
        tools = skill_base.as_tool_specs() if self.llm.online else None

        reply = self._chat_with_tools(system, messages, tools)

        self.memory.log_turn(Turn(
            role="assistant", content=reply, lang=profile.primary,
        ))
        return reply

    def _chat_with_tools(self, system: str, messages: list[dict],
                         tools: list[dict] | None) -> str:
        """Single-turn chat with up to 4 rounds of tool use."""
        if not self.llm.online:
            return self.llm.chat(system, messages)

        client = self.llm._client
        cfg = self.llm.cfg

        for _ in range(4):
            resp = client.messages.create(
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
                system=system,
                tools=tools or [],
                messages=messages,
            )

            tool_uses = [b for b in resp.content
                         if getattr(b, "type", None) == "tool_use"]
            text_chunks = [b.text for b in resp.content
                           if getattr(b, "type", None) == "text"]

            if not tool_uses:
                return "".join(text_chunks).strip() or "(no reply)"

            # Append the assistant turn with all blocks.
            messages.append({"role": "assistant", "content": resp.content})

            tool_results = []
            for tu in tool_uses:
                result = self._run_skill(tu.name, tu.input or {})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result.message,
                    "is_error": not result.ok,
                })

            messages.append({"role": "user", "content": tool_results})

        return "(stopped after 4 tool rounds)"

    def _run_skill(self, name: str, args: dict):
        skill = REGISTRY.get(name)
        if skill is None:
            return skill_base.SkillResult(False, f"Unknown skill: {name}")
        try:
            return skill.run(args, self.ctx)
        except Exception as e:
            log.exception("Skill %s crashed", name)
            return skill_base.SkillResult(False, f"{name} crashed: {e}")

    # ---- daily journal (the "evolves every day" part) -----------------

    def _start_daily_journal(self) -> None:
        if self._journal_started:
            return
        self._journal_started = True
        t = threading.Thread(target=self._journal_loop, daemon=True)
        t.start()

    def _journal_loop(self) -> None:
        target = self.config.get("evolution", {}).get("journal_time", "23:30")
        try:
            target_h, target_m = (int(x) for x in target.split(":"))
        except Exception:
            target_h, target_m = 23, 30
        last_day = None
        while True:
            now = datetime.now()
            if (now.hour, now.minute) == (target_h, target_m) \
                    and now.strftime("%Y-%m-%d") != last_day:
                try:
                    self.write_today_journal()
                    last_day = now.strftime("%Y-%m-%d")
                except Exception as e:
                    log.warning("Journal write failed: %s", e)
            time.sleep(45)

    def write_today_journal(self) -> str:
        """Summarise today's conversations into one journal entry."""
        day = datetime.now().strftime("%Y-%m-%d")
        turns = self.memory.recent_turns(limit=200)
        today_text = "\n".join(
            f"{t.role.upper()}: {t.content}" for t in turns
            if datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d") == day
        )[:6000]

        if not today_text.strip():
            summary = "Quiet day — no meaningful interactions."
        elif self.llm.online:
            summary = self.llm.chat(
                system=("You are FRIDAY writing a 4-line private diary "
                        "entry about today's interactions with your boss. "
                        "Note new things learned about him, his mood, and "
                        "anything worth remembering tomorrow."),
                messages=[{"role": "user", "content": today_text}],
            )
        else:
            summary = f"Logged {len(turns)} turns today."

        self.memory.write_journal(day=day, summary=summary)
        log.info("Journal written for %s", day)
        return summary
