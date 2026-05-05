"""FRIDAY skills.

Drop a Python file in this folder that subclasses `Skill`. On startup
the loader picks it up automatically. Skills declare which intents they
handle and how to run them.
"""

from .base import Skill, SkillResult, register, REGISTRY  # noqa: F401
