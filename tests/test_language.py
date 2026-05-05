"""Tests for the language detector."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.language import detect, style_directive


def test_pure_english():
    p = detect("What is the weather like today in Mumbai?")
    assert p.primary == "english"


def test_pure_hindi_devanagari():
    p = detect("आज मौसम कैसा है?")
    assert p.primary == "hindi"
    assert p.devanagari is True


def test_hinglish_typical():
    p = detect("Boss, kal subah 7 baje ka reminder set kar do please")
    assert p.primary in ("hinglish", "hindi")


def test_romanised_hindi():
    p = detect("aap kaise ho aaj, sab theek hai na")
    assert p.primary == "hindi"


def test_empty():
    p = detect("")
    assert p.primary == "english"


def test_directive_respects_preference():
    p = detect("hello there friday")
    d = style_directive(p, "hinglish")
    assert "Hinglish" in d
