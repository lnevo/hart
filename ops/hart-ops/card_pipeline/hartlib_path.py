"""Puts this checkout's tools/hartlib/src on sys.path, for the card pipeline modules that import hartlib.

A module that needs hartlib imports this one and calls ensure_on_path() before ``from hartlib import ...``. When no
folder above the card pipeline holds tools/hartlib/src (the folder was copied out of the repo), the call raises
HartlibNotFoundError at import time, before any main() runs, so it ends the command with a traceback.
"""
from __future__ import annotations

import sys
from pathlib import Path

from card_errors import CardPipelineError

HARTLIB_SRC = Path("tools/hartlib/src")


class HartlibNotFoundError(CardPipelineError, ImportError):
    """No folder above the card pipeline holds tools/hartlib/src: the scripts run only inside a hart checkout."""


def find_hartlib_src(start: Path) -> Path:
    """The nearest ``<folder>/tools/hartlib/src`` above ``start``."""
    for parent in start.resolve().parents:
        candidate = parent / HARTLIB_SRC
        if candidate.is_dir():
            return candidate
    raise HartlibNotFoundError(f"no {HARTLIB_SRC} above {start}: run the card pipeline from a hart checkout")


def ensure_on_path(start: Path = Path(__file__)) -> Path:
    """Put the hartlib source folder above ``start`` first on sys.path, once, and return it."""
    src = find_hartlib_src(start)
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return src
