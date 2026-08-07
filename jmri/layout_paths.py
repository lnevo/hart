"""
Shared paths for JMRI panel workflows.

Set environment variable JMRI_LAYOUT to work on a layout other than ``mac``
(e.g. after copying ``layouts/new/`` to ``layouts/myline/``).
"""
from __future__ import annotations

import os

JMRI_ROOT = os.path.dirname(os.path.abspath(__file__))
ACTIVE_LAYOUT = os.environ.get("JMRI_LAYOUT", "mac")

# Per-layout filenames under anyrail/, authoritative/, output/
_LAYOUT_FILES: dict[str, dict[str, str]] = {
    "mac": {
        "anyrail": "upper_both4.xml",
        "authoritative": "mac_jmri2.xml",
        "output": "mac_jmri_blocked.xml",
    },
    "linear3": {
        "anyrail": "linear3.xml",
        "authoritative": "linear3.xml",
        "output": "linear3_blocked.xml",
        "style_defaults": os.path.join(
            JMRI_ROOT, "layouts", "mac", "authoritative", "mac_jmri2.xml"
        ),
    },
    "linear4": {
        "anyrail": "linear4.xml",
        "authoritative": "linear4.xml",
        "output": "linear4_blocked.xml",
        "style_defaults": os.path.join(
            JMRI_ROOT, "layouts", "mac", "authoritative", "mac_jmri2.xml"
        ),
    },
    "linear5": {
        "anyrail": "linear5.xml",
        "authoritative": "linear5.xml",
        "output": "linear5_blocked.xml",
        "style_defaults": os.path.join(
            JMRI_ROOT, "layouts", "mac", "authoritative", "mac_jmri2.xml"
        ),
    },
    "hart": {
        "anyrail": "hart.xml",
        "authoritative": "hart.xml",
        "output": "hart_blocked.xml",
        "style_defaults": os.path.join(
            JMRI_ROOT, "layouts", "mac", "authoritative", "mac_jmri2.xml"
        ),
    },
}

_DEFAULT_FILES = {
    "anyrail": "anyrail_export.xml",
    "authoritative": "authoritative.xml",
    "output": "panel_blocked.xml",
}


def layout_root(layout: str | None = None) -> str:
    return os.path.join(JMRI_ROOT, "layouts", layout or ACTIVE_LAYOUT)


def layout_paths(layout: str | None = None) -> dict[str, str]:
    name = layout or ACTIVE_LAYOUT
    base = layout_root(name)
    files = {**_DEFAULT_FILES, **_LAYOUT_FILES.get(name, {})}
    style = files.get("style_defaults")
    if style and not os.path.isabs(style):
        style = os.path.join(base, style) if os.path.isfile(os.path.join(base, style)) else style
    dispatcher_dir = os.path.join(base, "dispatcher")
    repo_dispatcher = os.path.join(os.path.dirname(JMRI_ROOT), "dispatcher")
    return {
        "layout_dir": base,
        "anyrail": os.path.join(base, "anyrail", files["anyrail"]),
        "authoritative": os.path.join(base, "authoritative", files["authoritative"]),
        "output": os.path.join(base, "output", files["output"]),
        "excel": os.path.join(base, "data", "layout_blocks.xlsx"),
        "merge": os.path.join(base, "data", "block_merges.txt"),
        "nx_pairs": os.path.join(base, "output", "nx_pairs.txt"),
        "working": os.path.join(base, "working"),
        "style_defaults": style or os.path.join(base, "authoritative", files["authoritative"]),
        "dispatcher_dir": dispatcher_dir,
        "dispatcher_tables": os.path.join(dispatcher_dir, "tables.xml"),
        "dispatcher_workbook": os.path.join(
            dispatcher_dir, "NextTrainDispatcherApp.xlsx"
        ),
        "dispatcher_template_workbook": os.path.join(
            repo_dispatcher, "exports", "NextTrainDispatcherApp.xlsx"
        ),
    }
