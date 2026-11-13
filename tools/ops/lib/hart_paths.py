"""Shim: repo paths moved to ``hartlib.paths`` (tools/hartlib).

Kept for the audits that put tools/ops/lib on sys.path; new code imports
``from hartlib import paths`` (tools/hartlib/README.md). The STS, mirror and car-card
helpers that lived here had no callers and were dropped; the shell side reads the same
names from tools/env/load_env.sh.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[2] / "hartlib" / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from hartlib.paths import (  # noqa: E402,F401
    car_images_final,
    configured_repo_root as hart_repo_root,
    lcos_bridge as path_lcos_bridge,
    rel,
    runtime_root as hart_runtime_root,
)


def path_tables_xml() -> Path:
    """tables.xml under HART_RUNTIME_ROOT (this checkout when unset)."""
    return hart_runtime_root() / "jmri/layouts/hart/output/tables.xml"


def path_signal_wiring() -> Path:
    return hart_runtime_root() / "docs/wiring/signals/signal_wiring.csv"
