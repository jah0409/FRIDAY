# FRIDAY — Personal AI Automation Assistant

FRIDAY is a personal, evolving AI assistant built for **Mohammad Javed**.
She is inspired by Tony Stark's FRIDAY: voice-first, multilingual
(Hinglish / English / Hindi), task automating, schedule keeping, and
capable of writing new skills for herself when asked.

## Features

- **Voice I/O** — Speak to her, she speaks back. Wake-word: "Friday".
- **Multilingual** — Replies in Hinglish by default, switches to pure
  Hindi / English on request. Detects which language you used and
  matches it.
- **Evolving memory** — Every conversation, fact, and preference is
  written to a SQLite memory store. She summarises each day into a
  long-term journal so her behaviour grows over time.
- **Skills system** — Each capability (scheduling, system control, web,
  notes, etc.) is a plug-in skill. Drop a Python file into `skills/` and
  she picks it up on next start.
- **Self-build** — Ask "Friday, ek skill bana jo X kare" and she will
  draft a new skill file, sandbox-test it, and load it.
- **Scheduling** — Reminders, recurring jobs, alarms, daily briefings.
- **Tony-Stark-style automation** — Open apps, control files, run shell
  commands, fetch the weather, read the news, brief the day.

## Quick start

```bash
pip install -r requirements.txt
cp config/config.example.json config/config.json   # add your API key
python friday.py                                   # text mode
python friday.py --voice                           # voice mode
```

See `docs/` (generated on first run) for the full skill API.

## Project layout

```
friday.py              entry point
core/                  brain, memory, voice, llm, language
skills/                pluggable capabilities
config/                user prefs + owner profile
data/                  SQLite memory + daily journal
logs/                  rotating logs
tests/                 unit tests
```

## Owner

Designed and tuned for **Mohammad Javed**. FRIDAY addresses him as
"Boss" or "Sir" by default — change it in `config/config.json`.
