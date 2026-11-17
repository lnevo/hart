"""What every part of the Layout Editor build shares: its error, the plugin and the solved schematic, the band key and the
files it reads (split out of build_layout_le.py, the entry point)."""
from __future__ import annotations

import csv
import functools
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import le_inputs  # noqa: E402  the frozen staging facts (jmri/layouts/hart/data/schematic/staging_le/)
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
from hartlib import paths  # noqa: E402


SWITCHES = paths.LAYOUT_DATA / "switches.csv"
SWITCH_LEGS = paths.LAYOUT_DATA / "switch_legs.csv"
DEVICE_MAP = pd.DATA / "device_map_main_upper.csv"   # main and upper names (trial_name: the drawing's placeholder)
STAGING = "Staging"                  # band key (first word of the band title) bound to the live objects

TURNOUT_SYS = "IT:HART:C3:"          # internal turnouts: nothing reaches the field
BLOCK_SYS = "IB:C3:"
LAYOUT_BLOCK_FIRST = 1001            # ILB1001 up; the live file stops well below


class BuildError(le_inputs.InputsError):
    """A build that cannot go on; main() also stops on le_inputs.InputsError (a frozen file of the wrong shape)."""


@functools.lru_cache(maxsize=None)
def plugin():
    """The plugin's modules: sheet, le, core (found and checked once)."""
    try:
        folder = pd.plugin()
    except SystemExit as exc:
        raise BuildError(str(exc.code)) from None
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    return (importlib.import_module("schematic.sheet"), importlib.import_module("schematic.le"),
            importlib.import_module("schematic.core"))


@functools.lru_cache(maxsize=None)
def schematic():
    """(bands, page options) of the solved schematic (the inputs of publish_draft.py), solved once per run."""
    sheet = plugin()[0]
    built = pd.solved_sheet(sheet)
    return built.bands, built.opts


def overlay_mod():
    """tools/schematic/le_overlay.py: the live panel's icons and labels carried onto the new one."""
    import le_overlay
    return le_overlay


def slots_module():
    plugin()
    return importlib.import_module("schematic.slots")


def band_key(title: str) -> str:
    return (title or "").split()[0] if title else ""


def bare(label: str) -> str:
    return (label or "").rstrip("*")


# ---------------------------------------------------------------- staging, from the frozen inputs (le_inputs.py)

def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
