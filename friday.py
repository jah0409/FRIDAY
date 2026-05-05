#!/usr/bin/env python3
"""FRIDAY — entry point.

Usage:
    python friday.py             # text mode REPL
    python friday.py --voice     # voice mode (mic + speaker)
    python friday.py --once "what's the weather?"   # one-shot
    python friday.py --journal   # write today's journal and exit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))

from core.assistant import Friday   # noqa: E402


BANNER = r"""
   ___ ___ ___ ___    _ __   __
  | __| _ \_ _|   \  /_\\ \ / /
  | _||   /| || |) |/ _ \\ V /
  |_| |_|_\___|___//_/ \_\|_|
        for Mohammad Javed
"""


def text_repl(friday: Friday) -> None:
    address = friday.config["owner"].get("address_as", "Boss")
    print(f"\nFRIDAY online. Hello {address}. (Ctrl+C to exit)\n")
    while True:
        try:
            user = input(f"{address}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nFRIDAY signing off. Take care, Boss.")
            return
        if not user:
            continue
        if user.lower() in ("exit", "quit", "bye", "goodbye"):
            print("FRIDAY signing off. Take care, Boss.")
            return
        try:
            reply = friday.respond(user)
        except Exception as e:
            reply = f"(error: {e})"
        print(f"Friday> {reply}\n")


def voice_loop(friday: Friday) -> None:
    address = friday.config["owner"].get("address_as", "Boss")
    wake = friday.config["assistant"].get("wake_word", "friday")
    friday.voice.speak(f"FRIDAY online. Hello {address}.")
    print(f"Voice mode. Say '{wake}' to wake me. Ctrl+C to exit.")

    if friday.voice._recognizer is None:
        print("[!] Speech recognition unavailable — falling back to text mode.")
        return text_repl(friday)

    while True:
        try:
            print("(listening for wake word...)")
            if not friday.voice.wait_for_wake_word():
                print("[!] Wake-word loop ended.")
                return
            friday.voice.speak("Yes Boss?")
            heard = friday.voice.listen(timeout=8.0, phrase_time_limit=15.0)
            if not heard:
                friday.voice.speak("Sorry Boss, kuch sunaayi nahi diya.")
                continue
            print(f"Heard: {heard}")
            reply = friday.respond(heard)
            print(f"Friday> {reply}")
            friday.voice.speak(reply)
        except KeyboardInterrupt:
            friday.voice.speak("Signing off, Boss.")
            return


def main() -> int:
    p = argparse.ArgumentParser(description="FRIDAY — Mohammad Javed's AI assistant")
    p.add_argument("--voice", action="store_true", help="Voice mode")
    p.add_argument("--once", type=str, help="Single prompt then exit")
    p.add_argument("--journal", action="store_true",
                   help="Write today's journal entry and exit")
    args = p.parse_args()

    print(BANNER)
    friday = Friday(ROOT)

    if args.journal:
        summary = friday.write_today_journal()
        print(f"\nJournal written:\n{summary}")
        return 0

    if args.once:
        print(friday.respond(args.once))
        return 0

    if args.voice:
        voice_loop(friday)
    else:
        text_repl(friday)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
