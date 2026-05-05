"""System / OS automation skill.

Exposes a small, deliberately conservative set of operations:
  - open an app / URL
  - run a shell command (with confirmation)
  - get current time / battery / disk / cwd

Destructive shell commands are gated: the skill will refuse anything
matching a denylist unless `force=true` is passed (FRIDAY's brain only
sets that after explicit confirmation from the boss).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import webbrowser
from datetime import datetime

from .base import Skill, SkillResult, SkillContext, register


DENY_PATTERNS = (
    "rm -rf", "mkfs", "dd if=", ":(){:|:&};:", "shutdown", "reboot",
    "halt", "format ", "del /f", "deltree",
)


class OpenAppOrUrlSkill(Skill):
    name = "open_app_or_url"
    description = (
        "Open an application by name (chrome, vscode, spotify, ...) "
        "or open a URL in the default browser."
    )
    schema = {
        "type": "object",
        "properties": {
            "target": {"type": "string",
                       "description": "App name or full URL."},
        },
        "required": ["target"],
    }

    APP_MAP_LINUX = {
        "chrome": "google-chrome",
        "firefox": "firefox",
        "vscode": "code",
        "code": "code",
        "terminal": "x-terminal-emulator",
        "files": "xdg-open",
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        target = (args.get("target") or "").strip()
        if not target:
            return SkillResult(False, "Boss, kya open karna hai bataiye.")
        if target.startswith(("http://", "https://", "www.")):
            url = target if "://" in target else f"https://{target}"
            webbrowser.open(url)
            return SkillResult(True, f"Opened {url}", {"url": url})

        sysname = platform.system().lower()
        try:
            if sysname == "darwin":
                subprocess.Popen(["open", "-a", target])
            elif sysname == "windows":
                subprocess.Popen(["cmd", "/c", "start", "", target], shell=False)
            else:
                cmd = self.APP_MAP_LINUX.get(target.lower(), target)
                if shutil.which(cmd) is None:
                    return SkillResult(False, f"'{target}' not found on PATH.")
                subprocess.Popen([cmd])
            return SkillResult(True, f"Opening {target}, Boss.",
                               {"target": target})
        except Exception as e:
            return SkillResult(False, f"Couldn't open {target}: {e}")


class ShellSkill(Skill):
    name = "run_shell"
    description = (
        "Run a non-destructive shell command and return its output. "
        "Use only for safe, read-only style commands (ls, df, uptime, "
        "git status, etc). Destructive commands are blocked by default."
    )
    schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "force": {"type": "boolean",
                      "description": "Set true ONLY after explicit confirmation."},
        },
        "required": ["command"],
    }

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        cmd = (args.get("command") or "").strip()
        force = bool(args.get("force"))
        if not cmd:
            return SkillResult(False, "No command given.")
        low = cmd.lower()
        if not force and any(p in low for p in DENY_PATTERNS):
            return SkillResult(
                False,
                f"Boss, ye command destructive lag rahi hai: '{cmd}'. "
                "Confirm karo to dobara bhejo with force=true.",
            )
        try:
            res = subprocess.run(cmd, shell=True, capture_output=True,
                                 text=True, timeout=20)
            out = (res.stdout or "") + (res.stderr or "")
            return SkillResult(
                ok=res.returncode == 0,
                message=out.strip()[:2000] or "(no output)",
                data={"returncode": res.returncode},
            )
        except subprocess.TimeoutExpired:
            return SkillResult(False, "Command timed out after 20s.")
        except Exception as e:
            return SkillResult(False, f"Shell error: {e}")


class StatusSkill(Skill):
    name = "system_status"
    description = "Get current time, OS, cwd, and disk usage summary."
    schema = {"type": "object", "properties": {}}

    def run(self, args: dict, ctx: SkillContext) -> SkillResult:
        now = datetime.now().strftime("%A %d %b %Y, %H:%M")
        usage = shutil.disk_usage(os.getcwd())
        gb = lambda b: round(b / 1024**3, 1)
        msg = (
            f"Time: {now}\n"
            f"OS: {platform.system()} {platform.release()}\n"
            f"CWD: {os.getcwd()}\n"
            f"Disk: {gb(usage.used)}GB used / {gb(usage.total)}GB total"
        )
        return SkillResult(True, msg, {
            "time": now,
            "os": platform.system(),
            "cwd": os.getcwd(),
            "disk_total_gb": gb(usage.total),
            "disk_used_gb": gb(usage.used),
        })


register(OpenAppOrUrlSkill())
register(ShellSkill())
register(StatusSkill())
