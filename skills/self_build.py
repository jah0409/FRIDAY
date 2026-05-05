"""Self-build skill — FRIDAY writes new skills on demand.

When the boss says "Friday, ek skill bana jo X kare", the brain calls
this skill with a natural-language description. The skill asks the LLM
to generate a Skill subclass file, syntax-checks it, writes it into
skills/, and registers it so it's usable in the same session.

Safety:
  - Generated code is compiled (compile()) before being written, so a
    syntax error never lands on disk.
  - When `sandbox=True` (default in config), the file is written to
    skills/_generated/ — these auto-load but are easy to wipe.
  - The generator is told NOT to perform destructive operations.
"""

from __future__ import annotations

import importlib
import logging
import re
import textwrap
from pathlib import Path

from .base import Skill, SkillResult, SkillContext, register

log = logging.getLogger("friday.selfbuild")


SKILL_TEMPLATE = '''\
"""Auto-generated skill: {name}

Description: {description}
Generated for Mohammad Javed by FRIDAY.
"""

from __future__ import annotations

from skills.base import Skill, SkillResult, SkillContext, register


class {class_name}(Skill):
    name = "{name}"
    description = {description!r}
    schema = {schema!r}

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
{body}


register({class_name}())
'''


GENERATOR_PROMPT = """\
You are FRIDAY's self-build engineer. Generate ONLY the body of a
Skill.run method (Python). Constraints:
  - The body must be syntactically valid, indented 8 spaces.
  - It must end by returning a SkillResult(ok=..., message=..., data=...).
  - Use only the standard library plus `requests` if needed.
  - Never run destructive operations (rm -rf, format, shutdown).
  - Read args via `args.get(...)`. Speak via `ctx.speak(...)` if useful.
  - Keep it under 40 lines.

Spec from the boss:
---
{spec}
---

Return JSON only:
{{"name": "<snake_case>", "class_name": "<PascalCase>",
  "description": "<one line>",
  "schema": {{"type": "object", "properties": {{...}}}},
  "body": "<python body, 8-space indented>"}}
"""


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return s or "custom_skill"


class SelfBuildSkill(Skill):
    name = "self_build_skill"
    description = (
        "Create a brand-new skill from a natural-language description. "
        "Use when the boss says things like 'banao ek tool jo X kare', "
        "'build a skill that ...', 'add a feature to ...'. "
        "Only call after the boss has clearly described what the new "
        "skill should do."
    )
    schema = {
        "type": "object",
        "properties": {
            "spec": {
                "type": "string",
                "description": "Plain-English description of the new skill.",
            },
            "name_hint": {
                "type": "string",
                "description": "Optional preferred name for the new skill.",
            },
        },
        "required": ["spec"],
    }

    def __init__(self, sandbox: bool = True):
        self.sandbox = sandbox
        self.gen_dir = Path(__file__).parent / "_generated"
        self.gen_dir.mkdir(exist_ok=True)
        (self.gen_dir / "__init__.py").touch(exist_ok=True)

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        spec = (args.get("spec") or "").strip()
        if not spec:
            return SkillResult(False, "Boss, skill ka description toh do.")

        llm = ctx.extras.get("llm")
        if llm is None or not getattr(llm, "online", False):
            return SkillResult(
                False,
                "Self-build needs the LLM online. Set ANTHROPIC_API_KEY first.",
            )

        prompt = GENERATOR_PROMPT.format(spec=spec)
        try:
            raw = llm.chat(
                system="You output strict JSON. No prose.",
                messages=[{"role": "user", "content": prompt}],
            )
            spec_json = _extract_json(raw)
        except Exception as e:
            return SkillResult(False, f"Generator failed: {e}")

        name = _slugify(args.get("name_hint") or spec_json.get("name", spec[:20]))
        class_name = spec_json.get("class_name") or "".join(
            p.capitalize() for p in name.split("_")) + "Skill"
        description = spec_json.get("description", spec)
        schema = spec_json.get("schema") or {"type": "object", "properties": {}}
        body = spec_json.get("body", "")
        if not body.strip():
            return SkillResult(False, "Generator returned empty body.")
        # Re-indent body to 8 spaces just in case.
        body = textwrap.indent(textwrap.dedent(body), " " * 8)

        source = SKILL_TEMPLATE.format(
            name=name,
            class_name=class_name,
            description=description,
            schema=schema,
            body=body,
        )

        # Compile before writing — never let bad code on disk.
        try:
            compile(source, f"<gen:{name}>", "exec")
        except SyntaxError as e:
            return SkillResult(False, f"Generated code didn't compile: {e}")

        target_dir = self.gen_dir if self.sandbox else Path(__file__).parent
        target = target_dir / f"{name}.py"
        target.write_text(source, encoding="utf-8")

        # Hot-load.
        try:
            mod_path = ("skills._generated." if self.sandbox else "skills.") + name
            importlib.invalidate_caches()
            importlib.import_module(mod_path)
        except Exception as e:
            return SkillResult(
                False,
                f"Wrote {target} but import failed: {e}",
            )

        return SkillResult(
            ok=True,
            message=(f"Boss, naya skill '{name}' ban gaya aur load ho gaya. "
                     f"File: {target.relative_to(Path.cwd()) if target.is_relative_to(Path.cwd()) else target}"),
            data={"name": name, "path": str(target)},
        )


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a string, tolerating code fences."""
    import json
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in generator output")
    return json.loads(s[start: end + 1])


register(SelfBuildSkill(sandbox=True))


# Auto-load any previously generated skills on import.
def _load_generated() -> None:
    gen_dir = Path(__file__).parent / "_generated"
    if not gen_dir.exists():
        return
    for p in gen_dir.glob("*.py"):
        if p.stem.startswith("_"):
            continue
        try:
            importlib.import_module(f"skills._generated.{p.stem}")
        except Exception as e:
            log.warning("Failed to load generated skill %s: %s", p.stem, e)


_load_generated()
