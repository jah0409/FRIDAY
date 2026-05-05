"""Web skills — weather, news headlines, generic search-page open."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import webbrowser

from .base import Skill, SkillResult, SkillContext, register


def _http_get_json(url: str, timeout: float = 8.0) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FRIDAY/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


class WeatherSkill(Skill):
    name = "weather"
    description = "Get current weather for a city. Default: owner's city."
    schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string",
                     "description": "City name; defaults to owner's city."},
        },
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        city = (args.get("city")
                or ctx.config.get("owner", {}).get("city")
                or "Mumbai")
        # Use Open-Meteo's free geocoding + forecast — no API key needed.
        geo = _http_get_json(
            "https://geocoding-api.open-meteo.com/v1/search?"
            f"name={urllib.parse.quote(city)}&count=1"
        )
        if not geo or not geo.get("results"):
            return SkillResult(False, f"Couldn't locate {city}, Boss.")
        loc = geo["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        wx = _http_get_json(
            "https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        )
        if not wx or "current" not in wx:
            return SkillResult(False, f"Weather lookup failed for {city}.")
        c = wx["current"]
        msg = (
            f"{loc['name']}: {c['temperature_2m']}°C, "
            f"humidity {c['relative_humidity_2m']}%, "
            f"wind {c['wind_speed_10m']} km/h."
        )
        return SkillResult(True, msg, {"city": loc["name"], "current": c})


class NewsSkill(Skill):
    name = "news_headlines"
    description = "Fetch top headlines for the day."
    schema = {
        "type": "object",
        "properties": {
            "topic": {"type": "string",
                      "description": "Optional keyword filter."},
            "limit": {"type": "integer", "default": 5},
        },
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        topic = args.get("topic")
        limit = int(args.get("limit", 5))
        # Hacker News front page, no key required — good as a default source.
        ids = _http_get_json(
            "https://hacker-news.firebaseio.com/v0/topstories.json"
        ) or []
        headlines = []
        for sid in ids[: limit * 3]:
            item = _http_get_json(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
            )
            if not item or "title" not in item:
                continue
            if topic and topic.lower() not in item["title"].lower():
                continue
            headlines.append(item["title"])
            if len(headlines) >= limit:
                break
        if not headlines:
            return SkillResult(False, "No headlines found.")
        msg = "Top headlines, Boss:\n" + "\n".join(
            f"  • {h}" for h in headlines)
        return SkillResult(True, msg, {"headlines": headlines})


class WebSearchSkill(Skill):
    name = "web_search_open"
    description = ("Open a web search for a query in the default browser. "
                   "Use when the boss wants to look something up.")
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        q = (args.get("query") or "").strip()
        if not q:
            return SkillResult(False, "Empty query.")
        url = f"https://www.google.com/search?q={urllib.parse.quote(q)}"
        webbrowser.open(url)
        return SkillResult(True, f"Searching for '{q}'.", {"url": url})


register(WeatherSkill())
register(NewsSkill())
register(WebSearchSkill())
