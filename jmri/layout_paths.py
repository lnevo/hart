"""Shim: these paths moved to ``hartlib.paths`` (tools/hartlib). Kept only for
jmri/scripts/check_hart_phase02.py and the scripts under archive/; new code imports hartlib
(tools/hartlib/README.md).

``JMRI_LAYOUT`` is a single-layout setting; this repo has only ``hart``.
"""
from __future__ import annotations

import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "hartlib", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from hartlib.paths import JMRI_DIR, LAYOUT as ACTIVE_LAYOUT, layout_paths  # noqa: E402,F401

JMRI_ROOT = str(JMRI_DIR)


def layout_root(layout: str | None = None) -> str:
    return os.path.join(JMRI_ROOT, "layouts", layout or ACTIVE_LAYOUT)
