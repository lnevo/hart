"""What every part of the Layout Editor build shares: its error, the plugin and the solved schematic, the band key and the
files it reads (split out of build_layout_le.py, the entry point)."""
from __future__ import annotations

import csv
import functools
import importlib
import re
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


HALF = re.compile(r"(\d+)[AB]")


def crossover_half_legs(band) -> dict[str, str]:
    """{switch node: "B" or "C"} for every crossover half of a main or upper band (label <n>A or <n>B): the leg that
    leads to its other half, so its other leg is its closed (normal) route. That is leg C for halves joined C to C
    and for a half whose other half is on another band (its leg C leads to the connector); leg B for a half the plan
    joins by its leg B (AnyRail's leg B of T1 and T14 is the diagonal of crossovers 121 and 125, owner 2026-11-19).
    BuildError when a half has no leg, or both legs, leading to its other half."""
    nodes, strands = band["nodes"], band["strands"]
    out, bad = {}, []
    for n, d in sorted(nodes.items()):
        m = HALF.fullmatch(bare(d.get("label")))
        if d["kind"] != "switch" or not m:
            continue
        toward = []
        for leg in "BC":
            s = strands.get((d["ins"] | d["outs"]).get(leg))
            if s is None:       # no track on that leg: it leads to no other half
                continue
            far = s["dst"][0] if s["src"][0] == n else s["src"][0]
            other = HALF.fullmatch(bare(nodes.get(far, {}).get("label")))
            if (leg == "C" and far.startswith("LINK:")) or (far != n and other and other.group(1) == m.group(1)):
                toward.append(leg)
        if len(toward) != 1:
            bad.append(f"switch {d['label']}: {len(toward)} of its legs B and C lead to its other half, not one")
        else:
            out[n] = toward[0]
    if bad:
        raise BuildError("crossover halves: " + "; ".join(bad))
    return out


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
