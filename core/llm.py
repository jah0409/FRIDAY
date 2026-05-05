"""LLM client wrapper.

FRIDAY's brain. Wraps Anthropic's Claude API. Falls back to a local
"echo" responder if no API key is configured, so the rest of the system
stays testable offline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMConfig:
    provider: str = "anthropic"
    model: str = "claude-opus-4-7"
    api_key_env: str = "ANTHROPIC_API_KEY"
    max_tokens: int = 1024
    temperature: float = 0.6


class LLM:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self._client: Any | None = None
        self._init_client()

    def _init_client(self) -> None:
        if self.cfg.provider != "anthropic":
            return
        api_key = os.environ.get(self.cfg.api_key_env)
        if not api_key:
            return
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            self._client = None

    @property
    def online(self) -> bool:
        return self._client is not None

    def chat(self, system: str, messages: list[dict],
             tools: list[dict] | None = None) -> str:
        """Send a turn. `messages` is a list of {role, content} dicts."""
        if self._client is None:
            return self._offline_reply(messages)

        kwargs: dict[str, Any] = dict(
            model=self.cfg.model,
            max_tokens=self.cfg.max_tokens,
            temperature=self.cfg.temperature,
            system=system,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools

        resp = self._client.messages.create(**kwargs)
        # Concatenate text blocks; ignore tool-use blocks for now (the
        # skill router handles tools at a higher layer).
        chunks = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                chunks.append(block.text)
        return "".join(chunks).strip() or "(no reply)"

    @staticmethod
    def _offline_reply(messages: list[dict]) -> str:
        last = messages[-1]["content"] if messages else ""
        if isinstance(last, list):
            last = " ".join(p.get("text", "") for p in last if isinstance(p, dict))
        return (
            "Boss, abhi main offline mode mein hoon — "
            f"ANTHROPIC_API_KEY set kar do. (You said: {last[:120]!r})"
        )
