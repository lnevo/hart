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
import mast_rule  # noqa: E402  band_levels: a band's level from its plan-overrides section (after pd: hartlib's path)
from hartlib import layer_files, railroad  # noqa: E402  the layer files; the railroad's facts, each read and checked once
from hartlib import level_devices  # noqa: E402  the main and upper naming rule
from hartlib import tables_build  # noqa: E402  GENERATED_LEVELS: the levels whose beans the base holds


DEVICE_MAP = railroad.Sources.under().devices    # devices.csv: main and upper names (trial_name: the drawing's placeholder)
STAGING = "Staging"                  # band key (first word of the band title) bound to the live objects
# The levels whose turnouts, blocks, sensors and masts the generator's base holds (hartlib.tables_build's
# GENERATED_LEVELS: devices.csv's level 1 rows): a band of one of them binds the base's beans and adds none, and its
# candidate is the one the owner approves alone (the staging candidate). Every other level's beans the build adds,
# virtual (le_tables.add_level_objects, add_level_signals).
BASE_LEVELS = frozenset(int(v) for v in tables_build.GENERATED_LEVELS)

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


def plan_levels(data: Path | None = None) -> dict[str, int]:
    """{band title: level} of every band of the schematic, from each section of plan_overrides.json in `data`
    (default publish_draft.DATA, read when called; mast_rule.band_levels: the owner's level numbers, not the titles).
    Read once per folder and file state (its modification time and size), so a patched folder or an edited file is
    read again. BuildError names the file and section."""
    folder = Path(pd.DATA if data is None else data)
    try:
        st = layer_files.path("plan_overrides", folder).stat()
    except OSError as exc:
        raise BuildError(f"plan_overrides.json in {folder}: cannot be read ({exc.strerror or exc})") from None
    return dict(_plan_levels(folder.resolve(), st.st_mtime_ns, st.st_size))


@functools.lru_cache(maxsize=8)
def _plan_levels(folder: Path, _mtime_ns: int, _size: int) -> dict[str, int]:
    """plan_levels for one folder and file state (the last two arguments only key the cache)."""
    try:
        whole = layer_files.read_file("plan_overrides", folder)
    except layer_files.LayerFileError as exc:
        raise BuildError(str(exc)) from None
    out = {}
    for sheet in (k for k in whole if not k.startswith("_")):
        try:
            levels = mast_rule.band_levels(whole[sheet])
        except mast_rule.MapError as exc:
            raise BuildError(f"plan_overrides.json section {sheet}: {exc}") from None
        clash = sorted(set(levels) & set(out))
        if clash:
            raise BuildError(f"plan_overrides.json: band {', '.join(clash)} is titled in two sections")
        out.update(levels)
    return out


def band_levels(bands) -> list[int]:
    """The level of each of `bands` (the solved sheet's (title, band, options)), in order (plan_levels). BuildError
    names a band the plan overrides give no level."""
    levels = plan_levels()
    missing = [t for t, _b, _o in bands if t not in levels]
    if missing:
        raise BuildError(f"plan_overrides.json gives no level to band {', '.join(map(repr, missing))} (it has "
                         f"{', '.join(map(repr, levels))})")
    return [levels[t] for t, _b, _o in bands]


def base_bands(bands) -> list[int]:
    """The indexes of the bands of a level the base holds (BASE_LEVELS): the staging candidate's bands."""
    return [i for i, lv in enumerate(band_levels(bands)) if lv in BASE_LEVELS]


def bare(label: str) -> str:
    return (label or "").rstrip("*")


@functools.lru_cache(maxsize=None)
def staging_switches() -> dict[int, railroad.Switch]:
    """The staging switches, read once per run (hartlib.railroad: switches.csv with switch_legs.csv and each switch's
    live turnout row of the name map of devices.csv). BuildError names the file and row that cannot be read."""
    try:
        return railroad.Railroad(upto="inputs").switches
    except railroad.FactsError as exc:
        raise BuildError(f"staging switches: {exc}") from None


def switch_idents() -> dict[str, str]:
    """{switch number as text: its live Layout Editor ident} of every staging switch (staging_switches)."""
    return {str(n): sw.le_ident for n, sw in staging_switches().items()}


def main_upper_device_map(path: Path = DEVICE_MAP) -> railroad.DeviceMap:
    """The main and upper rows of devices.csv (hartlib.railroad.read_device_map, every row checked); BuildError names the
    file and row that cannot be read."""
    try:
        return railroad.read_device_map(path)
    except railroad.FactsError as exc:
        raise BuildError(f"the device map: {exc}") from None


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
