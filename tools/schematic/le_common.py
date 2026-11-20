"""What every part of the Layout Editor build shares: its error, the plugin and the solved schematic, the band key and the
files it reads (split out of build_layout_le.py, the entry point)."""
from __future__ import annotations

import csv
import functools
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
from hartlib import railroad  # noqa: E402  the railroad's facts, each file read and checked in one place
from hartlib import level_devices  # noqa: E402  the main and upper naming rule


DEVICE_MAP = railroad.Sources.under().device_map    # main and upper names (trial_name: the drawing's placeholder)
STAGING = "Staging"                  # band key (first word of the band title) bound to the live objects

TURNOUT_SYS = level_devices.TURNOUT_PREFIX     # internal turnouts: nothing reaches the field
BLOCK_SYS = level_devices.BLOCK_PREFIX
LAYOUT_BLOCK_FIRST = 1001            # ILB1001 up; the live file stops well below


class BuildError(RuntimeError):
    """A build that cannot go on (main() prints it and exits 1)."""


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


def slots_module():
    plugin()
    return importlib.import_module("schematic.slots")


def band_key(title: str) -> str:
    return (title or "").split()[0] if title else ""


def bare(label: str) -> str:
    return (label or "").rstrip("*")


@functools.lru_cache(maxsize=None)
def staging_switches() -> dict[int, railroad.Switch]:
    """The staging switches, read once per run (hartlib.railroad: switches.csv with switch_legs.csv and each switch's
    live turnout row of public_name_map.csv). BuildError names the file and row that cannot be read."""
    try:
        return railroad.Railroad(upto="inputs").switches
    except railroad.FactsError as exc:
        raise BuildError(f"staging switches: {exc}") from None


def switch_idents() -> dict[str, str]:
    """{switch number as text: its live Layout Editor ident} of every staging switch (staging_switches)."""
    return {str(n): sw.le_ident for n, sw in staging_switches().items()}


def main_upper_device_map(path: Path = DEVICE_MAP) -> railroad.DeviceMap:
    """The main and upper device map (hartlib.railroad.read_device_map, every row checked); BuildError names the
    file and row that cannot be read."""
    try:
        return railroad.read_device_map(path)
    except railroad.FactsError as exc:
        raise BuildError(f"the device map: {exc}") from None


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
