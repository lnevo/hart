"""Paths the CPython tools use, resolved from the checkout hartlib sits in.

There is one railroad and one layout directory, ``jmri/layouts/hart``. ``JMRI_LAYOUT`` is
still read (the shell sets ``JMRI_LAYOUT=hart``), but it is a single-layout setting: any
other value points every layout path at a directory this repo does not have. When the
railroad is split later, the unit will be the level or district, not the layout name.

Every path names a file in *this* checkout, the one hartlib sits in, so a script in a
worktree reads that worktree's tables.xml. ``HART_REPO_ROOT`` and ``HART_RUNTIME_ROOT``
(exported by tools/env/load_env.sh) do not move them.
"""
from __future__ import annotations

import os
from pathlib import Path


def _find_repo_root() -> Path:
    # src/hartlib/paths.py -> src -> tools/hartlib -> tools -> repo
    root = Path(__file__).resolve().parents[4]
    if not (root / "jmri" / "layouts").is_dir() or not (root / "tools" / "hartlib").is_dir():
        raise ImportError(
            f"hartlib at {Path(__file__).resolve()} is not inside a repo checkout; put "
            "<repo>/tools/hartlib/src on sys.path instead of installing a copy (README.md)"
        )
    return root


REPO_ROOT = _find_repo_root()
JMRI_DIR = REPO_ROOT / "jmri"

LAYOUT = os.environ.get("JMRI_LAYOUT", "").strip() or "hart"
LAYOUT_DIR = JMRI_DIR / "layouts" / LAYOUT
LAYOUT_DATA = LAYOUT_DIR / "data"
LAYOUT_OUTPUT = LAYOUT_DIR / "output"
LAYOUT_SCRIPTS = LAYOUT_DIR / "scripts"

TABLES_XML = LAYOUT_OUTPUT / "tables.xml"
PUBLIC_NAME_MAP = LAYOUT_DATA / "public_name_map.csv"
SIGNAL_WIRING = REPO_ROOT / "docs" / "wiring" / "signals" / "signal_wiring.csv"
CATS_DIR = REPO_ROOT / "cats"

# Where PanelPro loads preference:tables.xml on every host (ADR-014).
JMRI_USER_FILES = Path.home() / "JMRI_UserFiles"


def lcos_bridge() -> Path:
    """The LCOS bridge source: the external/lcos-bridge submodule, else a sibling clone."""
    sub = REPO_ROOT / "external" / "lcos-bridge"
    if (sub / "serial_to_mqtt.py").is_file():
        return sub
    sibling = REPO_ROOT.parent / "LCOS_ESP32_MQTT_Client"
    return sibling if sibling.is_dir() else sub


def car_images_final() -> Path:
    """HART_CAR_IMAGES_FINAL, else the repo copy (~/Desktop/HART was retired 2026-11-09, ADR-007)."""
    value = os.environ.get("HART_CAR_IMAGES_FINAL", "").strip()
    if value:
        return Path(value).expanduser().resolve()
    return REPO_ROOT / "ops" / "car-cards" / "car-images" / "CarImagesFinal"


def rel(path: Path | str, root: Path | None = None) -> str:
    """``path`` relative to the checkout (or ``root``) for messages; absolute when outside it."""
    p = Path(path)
    try:
        return str(p.resolve().relative_to((root or REPO_ROOT).resolve()))
    except ValueError:
        return str(p)


def layout_paths(layout: str | None = None) -> dict[str, str]:
    """The old jmri/layout_paths.py dict, kept for the AnyRail-era scripts in jmri/scripts.

    ``authoritative`` is tables.xml. ``anyrail``, ``style_defaults`` and ``layout_dir``
    exist; ``output``, ``excel``, ``merge``, ``nx_pairs`` and ``working`` are defaults for
    files those scripts create. The Dispatcher keys (NextTrain workbook and the rest) are
    gone: nothing reads them.
    """
    base = JMRI_DIR / "layouts" / (layout or LAYOUT)
    return {
        "layout_dir": str(base),
        "anyrail": str(base / "anyrail" / "hart.xml"),
        "authoritative": str(base / "output" / "tables.xml"),
        "output": str(base / "output" / "hart_blocked.xml"),
        "excel": str(base / "data" / "layout_blocks.xlsx"),
        "merge": str(base / "data" / "block_merges.txt"),
        "nx_pairs": str(base / "output" / "nx_pairs.txt"),
        "working": str(base / "working"),
        "style_defaults": str(JMRI_DIR / "templates" / "panel_style.xml"),
    }
