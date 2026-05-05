"""Auto-discover and import every skill module under skills/."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

log = logging.getLogger("friday.skills")

SKIP = {"base", "loader", "__init__"}


def load_all() -> list[str]:
    """Import every module in this package; built-ins self-register on import."""
    pkg_dir = Path(__file__).parent
    loaded: list[str] = []
    for mod in pkgutil.iter_modules([str(pkg_dir)]):
        if mod.name in SKIP or mod.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"skills.{mod.name}")
            loaded.append(mod.name)
        except Exception as e:
            log.warning("Failed to load skill %s: %s", mod.name, e)
    return loaded
