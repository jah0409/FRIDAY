"""Language detection and Hinglish handling.

FRIDAY needs to know whether the boss spoke in English, Hindi (Devanagari),
romanised Hindi, or a Hinglish mix, so she can match the register.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# A small but practical list of common romanised Hindi tokens.
# Detection is intentionally simple — we only need to choose a reply style.
HINDI_TOKENS = {
    "hai", "hain", "ho", "hoon", "tha", "thi", "the", "kya", "kyun",
    "kaise", "kahan", "kab", "kaun", "kitna", "kitne", "kitni",
    "main", "mera", "meri", "mere", "tum", "aap", "aapka", "aapki",
    "tumhara", "tumhari", "humara", "humari", "uska", "uski",
    "nahi", "nahin", "haan", "achha", "acha", "theek", "thik",
    "bhai", "yaar", "boss", "sir", "ji", "matlab",
    "karo", "karunga", "karungi", "kar", "karna", "kiya", "kiye",
    "chahiye", "chahta", "chahti", "lagta", "lagti",
    "abhi", "thoda", "zara", "phir", "fir", "lekin", "magar",
    "agar", "warna", "kyunki", "isliye", "iska", "uska",
    "bana", "banao", "banaya", "banayi", "bata", "batao", "bataye",
    "dekho", "dekha", "sun", "suno", "suna", "bol", "bolo", "bola",
    "yaad", "dilana", "reminder",
}

DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


@dataclass
class LanguageProfile:
    """Result of detecting the boss's language for one utterance."""

    primary: str           # 'english' | 'hindi' | 'hinglish'
    devanagari: bool       # was native Hindi script present?
    confidence: float      # 0..1


def detect(text: str) -> LanguageProfile:
    """Best-effort detection. Cheap, deterministic, no model calls."""
    if not text or not text.strip():
        return LanguageProfile("english", False, 0.0)

    has_dev = bool(DEVANAGARI_RE.search(text))
    words = re.findall(r"[A-Za-zऀ-ॿ]+", text.lower())
    if not words:
        return LanguageProfile("english", has_dev, 0.0)

    hindi_hits = sum(1 for w in words if w in HINDI_TOKENS)
    ratio = hindi_hits / len(words)

    if has_dev and ratio < 0.2:
        return LanguageProfile("hindi", True, 0.9)
    if ratio >= 0.5:
        return LanguageProfile("hindi", has_dev, min(1.0, 0.6 + ratio / 2))
    if ratio >= 0.15:
        return LanguageProfile("hinglish", has_dev, 0.7)
    return LanguageProfile("english", has_dev, 0.8)


def style_directive(profile: LanguageProfile, preferred: str) -> str:
    """Turn a detected profile + user preference into an LLM instruction."""
    pref = (preferred or "hinglish").lower()
    detected = profile.primary

    if pref == "hindi" or detected == "hindi":
        return (
            "Reply in natural conversational Hindi. Use Devanagari only if "
            "the boss used it; otherwise romanise. Keep it short."
        )
    if pref == "english" and detected == "english":
        return "Reply in clear, friendly Indian English. Keep it concise."
    return (
        "Reply in Hinglish — natural Mumbai-style mix of Hindi and English, "
        "romanised. Address the boss respectfully. Keep replies short."
    )
