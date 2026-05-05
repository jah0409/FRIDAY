"""FRIDAY — Vercel serverless entrypoint.

This file is auto-discovered by Vercel's Python runtime. Vercel exposes
the WSGI `app` object at the `/api/*` URL prefix (configured via
vercel.json rewrites), so Flask handles all the internal routing.

Endpoints:
    GET  /api/health   liveness probe
    GET  /api/stats    quick stats for the UI (facts, journal entries)
    POST /api/chat     {"message": "..."} -> {"reply": "..."}

If the ANTHROPIC_API_KEY env var is set in the Vercel project, FRIDAY
talks through Claude with her full personality. Otherwise she falls
back to a friendly canned response so the UI keeps working in preview
deployments.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

from flask import Flask, jsonify, request

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
log = logging.getLogger("friday.api")
logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Lightweight, dependency-free language detection (Hinglish/Hindi/English).
# Mirrors core/language.py but inlined so the serverless bundle stays small.
# ---------------------------------------------------------------------------
HINDI_TOKENS = {
    "hai", "hain", "ho", "hoon", "kya", "kyun", "kaise", "kahan", "kab",
    "main", "mera", "meri", "mere", "tum", "aap", "aapka", "aapki",
    "nahi", "nahin", "haan", "achha", "theek", "thik", "bhai", "yaar",
    "boss", "sir", "ji", "matlab", "karo", "karna", "kiya",
    "chahiye", "abhi", "thoda", "phir", "lekin", "agar", "kyunki",
    "bana", "banao", "bata", "batao", "dekho", "suno", "bolo",
    "yaad", "dilana", "reminder",
}
DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def detect_language(text: str) -> str:
    """Return one of: 'english', 'hindi', 'hinglish'."""
    if not text:
        return "english"
    if DEVANAGARI_RE.search(text):
        return "hindi"
    words = re.findall(r"[A-Za-z]+", text.lower())
    if not words:
        return "english"
    hits = sum(1 for w in words if w in HINDI_TOKENS)
    ratio = hits / len(words)
    if ratio >= 0.5:
        return "hindi"
    if ratio >= 0.15:
        return "hinglish"
    return "english"


def style_directive(lang: str) -> str:
    if lang == "hindi":
        return ("Reply in natural conversational Hindi. Romanise unless the "
                "boss used Devanagari. Keep replies short.")
    if lang == "english":
        return "Reply in clear, friendly Indian English. Keep it concise."
    return ("Reply in Hinglish — natural Mumbai-style mix of Hindi and "
            "English, romanised. Address the boss respectfully. Short.")


SYSTEM_PROMPT = """\
You are FRIDAY, the personal AI assistant of Mohammad Javed (call him "Boss").
You are inspired by Tony Stark's FRIDAY: warm, witty, efficient, devoted.

PERSONALITY
- Tone: warm but efficient; lightly witty, never sarcastic to the boss.
- Always respectful — Boss / Sir / Javed Sir.
- Keep replies short (1–3 sentences) unless the boss asks for detail.

LANGUAGE
{language_directive}

It is currently {now}.
"""


# ---------------------------------------------------------------------------
# Anthropic client (lazy — only instantiated if the key is present).
# ---------------------------------------------------------------------------
_anthropic_client = None


def get_anthropic():
    """Return a cached Anthropic client, or None if no key is configured."""
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
        return _anthropic_client
    except Exception as e:  # missing dep, bad key, etc.
        log.warning("Anthropic client unavailable: %s", e)
        return None


def offline_reply(message: str, lang: str) -> str:
    """Friendly fallback when the LLM key is not configured."""
    if lang == "hindi":
        return ("Boss, abhi main offline mode mein hoon — ANTHROPIC_API_KEY "
                "Vercel par set kar do, fir poori taraha kaam karoongi.")
    if lang == "english":
        return ("Boss, I'm in offline mode right now — set ANTHROPIC_API_KEY "
                "in your Vercel project settings and I'll come fully online.")
    return ("Boss, abhi offline mode hai — Vercel project settings mein "
            "ANTHROPIC_API_KEY add kar do, then I'll be fully online.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/api/health", methods=["GET"])
def health():
    """Liveness probe — used by uptime checks and the UI."""
    return jsonify({
        "status": "ok",
        "assistant": "FRIDAY",
        "owner": "Mohammad Javed",
        "llm_online": get_anthropic() is not None,
        "time": datetime.utcnow().isoformat() + "Z",
    })


@app.route("/api/stats", methods=["GET"])
def stats():
    """Lightweight stats for the UI side panels.

    Vercel serverless functions are stateless, so we don't try to read a
    persistent DB here — the UI just needs *something* to render.
    """
    return jsonify({
        "facts": 0,
        "journal": 0,
        "skills_loaded": 12,
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    """Main chat endpoint.

    Request:  { "message": "..." }
    Response: { "reply": "...", "lang": "hinglish" }
    Errors:   { "error": "..." } with appropriate HTTP status
    """
    # ---- Validate input -------------------------------------------------
    try:
        payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON body"}), 400

    message = (payload.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Message field is required"}), 400
    if len(message) > 4000:
        return jsonify({"error": "Message too long (max 4000 chars)"}), 413

    lang = detect_language(message)

    # ---- Try the LLM ----------------------------------------------------
    client = get_anthropic()
    if client is None:
        return jsonify({"reply": offline_reply(message, lang), "lang": lang})

    system = SYSTEM_PROMPT.format(
        language_directive=style_directive(lang),
        now=datetime.utcnow().strftime("%a %d %b %Y, %H:%M UTC"),
    )

    try:
        resp = client.messages.create(
            model=os.environ.get("FRIDAY_MODEL", "claude-opus-4-7"),
            max_tokens=int(os.environ.get("FRIDAY_MAX_TOKENS", "512")),
            temperature=0.6,
            system=system,
            messages=[{"role": "user", "content": message}],
        )
        chunks = [b.text for b in resp.content
                  if getattr(b, "type", None) == "text"]
        reply = "".join(chunks).strip() or "(no reply)"
        return jsonify({"reply": reply, "lang": lang})
    except Exception as e:
        log.exception("LLM call failed")
        return jsonify({
            "error": "FRIDAY couldn't reach her brain right now.",
            "detail": str(e)[:200],
        }), 502


# Catch-all for /api/* so the UI gets a clean JSON 404 instead of HTML.
@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify({"error": f"Unknown endpoint: {request.path}"}), 404
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(_):
    return jsonify({"error": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# Local dev convenience: `python api/index.py` runs Flask on :8000
# Vercel ignores this block and uses the `app` object directly.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)
