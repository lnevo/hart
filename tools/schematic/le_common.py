"""What every part of the Layout Editor build shares: its error, the plugin and the solved schematic, the band key and the
files it reads (split out of build_layout_le.py, the entry point)."""
from __future__ import annotations

import csv
import enum
import functools
import importlib
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple, TypeAlias

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
from map_error import MapError  # noqa: E402
import plan_bands  # noqa: E402
from hartlib import layer_files, railroad  # noqa: E402  the layer files; the railroad's facts, each read and checked once
from hartlib import level_devices  # noqa: E402  the main and upper naming rule


DEVICE_MAP = railroad.Sources.under().devices    # the device master: main and upper names (trial_name: the drawing's placeholder)
# The staging level: its band's names are the staging device map's (staging_device_map.load) and every other band is
# drawn under it; its candidate is the one the owner approves alone (the staging candidate). Every level's beans are
# the generator's base's (hartlib.tables_build.base), so the level says only where a band's
# names come from.
STAGING_LEVELS = frozenset({int(railroad.STAGING_LEVEL)})

BLOCK_SYS = level_devices.BLOCK_PREFIX
LAYOUT_BLOCK_FIRST = level_devices.LAYOUT_BLOCK_FIRST


class BuildError(RuntimeError):
    """A build that cannot go on (main() prints it and exits 1)."""


Band: TypeAlias = tuple[str, Any, dict[str, Any]]   # the solved sheet's (title, band, options)
Height: TypeAlias = "float | None"                  # a band's plan-overrides `below`; None for a band with none


class BandPlace(NamedTuple):
    """Where plan_overrides.json puts a band: its section, level and height."""
    section: str
    level: int
    height: Height


class _AnyHeight(enum.Enum):
    ANY = "any"


ANY = _AnyHeight.ANY    # find_band's height when none is asked for: any height (None is a band with no height)
HeightAsked: TypeAlias = "float | None | _AnyHeight"


@functools.lru_cache(maxsize=None)
def plugin() -> tuple[ModuleType, ModuleType, ModuleType]:
    """The plugin's modules: sheet, le, core (found and checked once)."""
    try:
        folder = pd.plugin()
    except pd.PluginMissing as exc:
        raise BuildError(str(exc)) from exc
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    return (importlib.import_module("schematic.sheet"), importlib.import_module("schematic.le"),
            importlib.import_module("schematic.core"))


@functools.lru_cache(maxsize=None)
def schematic() -> tuple[list[Band], dict[str, Any]]:
    """(bands, page options) of the solved schematic (the inputs of publish_draft.py), solved once per run."""
    sheet = plugin()[0]
    try:
        built = pd.solved_sheet(sheet)
    except pd.host_screen.HostScreenError as exc:       # the panel's window: the page's host_screen
        raise BuildError(str(exc)) from exc
    return built.bands, built.opts


def slots_module() -> ModuleType:
    plugin()
    return importlib.import_module("schematic.slots")


def plugin_module(name: str) -> ModuleType:
    """The plugin's module schematic.<name> (the plugin found and checked once: plugin()); BuildError when the plugin
    has no such module (a SCHEMATIC_PLUGIN older than the module)."""
    folder = plugin()[0].__file__
    if folder is None:
        raise BuildError("the schematic-maps plugin's schematic.sheet has no file: it is not a plugin folder")
    try:
        return importlib.import_module(f"schematic.{name}")
    except ModuleNotFoundError as exc:
        if exc.name != f"schematic.{name}":
            raise                       # the module is there but imports something missing: its own fault, shown
        raise BuildError(f"the schematic-maps plugin at {Path(folder).parents[1]} has no schematic.{name}: "
                         "update it (git submodule update, or a newer SCHEMATIC_PLUGIN)") from exc


def band_key(title: str) -> str:
    """The plugin's key for a band (its draw.band_key), which its options and the names given to it are keyed by.
    A key names a band to the plugin; HART finds a band by its place (find_band), never by its title or key."""
    return plugin_module("draw").band_key(title)


def _height(height: Height) -> str:
    return "no height" if height is None else f"height {height:g}"


def _where(level: int, height: HeightAsked = ANY) -> str:
    """"level 2" for any height (ANY) or a band with none, "level 2, height 5" for one with a height."""
    return f"level {level}" + ("" if isinstance(height, _AnyHeight) or height is None else f", height {height:g}")


def plan_places(data: Path | None = None) -> dict[str, BandPlace]:
    """{band title: (section, level, height)} of every band of the schematic, from each section of plan_overrides.json
    in `data` (default publish_draft.DATA, read when called; plan_bands.band_places: the owner's level numbers and
    heights, not the titles). Read once per folder and file state (its modification time and size), so a patched
    folder or an edited file is read again. BuildError names the file and section, for a band two sections title or
    two bands at one level and height."""
    folder = Path(pd.DATA if data is None else data)
    try:
        st = layer_files.path("plan_overrides", folder).stat()
    except OSError as exc:
        raise BuildError(f"plan_overrides.json in {folder}: cannot be read ({exc.strerror or exc})") from exc
    return dict(_plan_places(folder.resolve(), st.st_mtime_ns, st.st_size))


@functools.lru_cache(maxsize=8)
def _plan_places(folder: Path, _mtime_ns: int, _size: int) -> dict[str, BandPlace]:
    """plan_places for one folder and file state (the last two arguments only key the cache)."""
    try:
        whole = layer_files.read_file("plan_overrides", folder)
    except layer_files.LayerFileError as exc:
        raise BuildError(str(exc)) from exc
    out: dict[str, BandPlace] = {}
    at: dict[tuple[int, Height], str] = {}             # (level, height) -> the band title there
    for sheet in (k for k in whole if not k.startswith("_")):
        try:
            places = plan_bands.band_places(whole[sheet])
        except MapError as exc:
            raise BuildError(f"plan_overrides.json section {sheet}: {exc}") from exc
        clash = sorted(set(places) & set(out))
        if clash:
            raise BuildError(f"plan_overrides.json: band {', '.join(clash)} is titled in two sections")
        for title, place in places.items():
            if place in at:
                other = at[place]
                raise BuildError(f"plan_overrides.json: bands {other!r} (section {out[other][0]}) and {title!r} "
                                 f"(section {sheet}) are both at level {place[0]}, "
                                 + (f"height {place[1]:g}" if place[1] is not None else "no height"))
            at[place] = title
            out[title] = BandPlace(sheet, *place)
    return out


def plan_levels(data: Path | None = None) -> dict[str, int]:
    """{band title: level} of every band of the schematic (plan_places without the section and height)."""
    return {t: lv for t, (_s, lv, _h) in plan_places(data).items()}


def band_places(bands: Sequence[Band], data: Path | None = None) -> list[tuple[int, Height]]:
    """The (level, height) of each of `bands` (the solved sheet's (title, band, options), titles unchanged), in order
    (plan_places of `data`, default publish_draft.DATA). BuildError names a band the plan overrides give no level,
    and a band drawn twice."""
    places = plan_places(data)
    missing = [t for t, _b, _o in bands if t not in places]
    if missing:
        raise BuildError(f"plan_overrides.json gives no level to band {', '.join(map(repr, missing))} (it has "
                         f"{', '.join(map(repr, places))})")
    seen: dict[str, int] = {}
    for i, (t, _b, _o) in enumerate(bands):
        if t in seen:
            raise BuildError(f"bands {seen[t]} and {i} are both {t!r}: a band is drawn once")
        seen[t] = i
    return [(places[t].level, places[t].height) for t, _b, _o in bands]


def band_levels(bands: Sequence[Band], data: Path | None = None) -> list[int]:
    """The level of each of `bands`, in order (band_places)."""
    return [lv for lv, _h in band_places(bands, data)]


def _at(places: Sequence[tuple[int, Height]], level: int, height: HeightAsked = ANY) -> list[int]:
    """The indexes of `places` (band_places) at `level` and `height` (ANY: whatever height, None: no height)."""
    return [i for i, (lv, h) in enumerate(places) if lv == level and (isinstance(height, _AnyHeight) or h == height)]


def find_band(bands: Sequence[Band], level: int, height: HeightAsked = ANY, data: Path | None = None) -> int:
    """The index of the one band of `bands` at `level` and `height` (its plan-overrides `below`; None for a band with
    none; not given: any height), by plan_places of `data` (default publish_draft.DATA): the one way the Layout
    Editor build finds a band (by its level and height, never by its title). BuildError when no
    band is there (naming every band's place), or several are and no height tells them apart."""
    places = band_places(bands, data)
    found = _at(places, level, height)
    if not found:
        want = _where(level, height) + (", no height" if height is None else "")
        raise BuildError(f"no band is at {want} (bands: "
                         + ", ".join(f"{t!r} at {_where(*p)}" for (t, _b, _o), p in zip(bands, places)) + ")")
    if len(found) > 1:
        raise BuildError(f"{len(found)} bands are at level {level} ("
                         + ", ".join(f"{bands[i][0]!r} at {_height(places[i][1])}" for i in found)
                         + "): give the height")
    return found[0]


def base_bands(bands: Sequence[Band]) -> list[int]:
    """The indexes of the staging level's bands (STAGING_LEVELS): the staging candidate's bands."""
    return [i for i, lv in enumerate(band_levels(bands)) if lv in STAGING_LEVELS]


def base_band(bands: Sequence[Band]) -> int:
    """The index of the one band of the staging level (find_band at each of STAGING_LEVELS): the staging
    candidate's band. BuildError when there is none, or more than one."""
    places = band_places(bands)
    found = sorted(i for lv in STAGING_LEVELS for i in _at(places, lv))
    if len(found) != 1:
        if not found:
            find_band(bands, min(STAGING_LEVELS))       # stops, naming every band's place
        raise BuildError(f"the staging levels {sorted(STAGING_LEVELS)} have {len(found)} bands ("
                         + ", ".join(repr(bands[i][0]) for i in found) + "); the build draws one")
    return found[0]


def base_keys(bands: Sequence[Band]) -> set[str]:
    """The plugin's keys (band_key) of the staging level's bands (base_bands): the names le_names leaves
    to the staging device map."""
    return {band_key(bands[i][0]) for i in base_bands(bands)}


def le_station_labels(bands: Sequence[Band], data: Path | None = None) -> list[Band]:
    """`bands` with the stations the plugin's Layout Editor labeller names (each band's `stations` option) as each
    sheet's section of preferences.json asks: its `le_nested_station_labels` false leaves out, on the bands of that
    section (plan_places of `data`), each station of the band's level in stations.csv that is a desk area nested in a
    station of another (hartlib.railroad.nested_own_areas: Engine House in Barn; West Yard, in Brick's own area,
    stays); true, or not set, names every station. The drawings read the layer files, not these bands, so they keep
    every station. The bands given are not changed. BuildError naming the section for a value that is not true or
    false, or naming stations.csv's row for one that breaks its rules."""
    folder = Path(pd.DATA if data is None else data)
    try:
        prefs = layer_files.read_file("preferences", folder)
    except layer_files.LayerFileError as exc:
        raise BuildError(str(exc)) from exc
    leave_out: dict[str, int] = {}          # band title -> its level, for the bands whose nested areas go unnamed
    for sheet in (k for k in prefs if not k.startswith("_")):
        if "le_nested_station_labels" not in prefs[sheet]:
            continue
        given = prefs[sheet]["le_nested_station_labels"]
        if not isinstance(given, bool):
            raise BuildError(f"preferences.json section {sheet}: le_nested_station_labels is true or false, not "
                             f"{given!r}")
        if not given:
            leave_out.update({t: lv for t, (s, lv, _h) in plan_places(folder).items() if s == sheet})
    if not leave_out:
        return list(bands)
    try:
        rows = railroad.read_stations(folder / "stations.csv")
    except railroad.FactsError as exc:
        raise BuildError(str(exc)) from exc
    out: list[Band] = []
    for title, band, opts in bands:
        stations = opts.get("stations") or {}
        if title not in leave_out or not stations:
            out.append((title, band, opts))
            continue
        own = railroad.nested_own_areas([r for r in rows if r.level == leave_out[title]])
        out.append((title, band, dict(opts, stations={n: e for n, e in stations.items() if n not in own})))
    return out


ALIGN_SIDES = ("left", "centre", "right")


def _align_band(where: str, key: object, side: object, own: dict[str, BandPlace]) -> tuple[int, str, Height]:
    """(level, title, height) of the one band of a section (`own`: its bands' places) that its le_band_align entry
    `key`: `side` names. BuildError, opening with `where`, for a key that is not a level number, a side not in
    ALIGN_SIDES, a level no band of the section is at, or one two of its bands are at."""
    if not (isinstance(key, str) and key.isdigit()):
        raise BuildError(f"{where} names level {key!r}, which is not a level number")
    level = int(key)
    if side not in ALIGN_SIDES:
        raise BuildError(f"{where} level {level}: {side!r} is not {', '.join(ALIGN_SIDES[:-1])} or {ALIGN_SIDES[-1]}")
    mine = [(t, p.height) for t, p in own.items() if p.level == level]
    if not mine:
        raise BuildError(f"{where} names level {level}, which no band of the section is at (its bands: "
                         + ", ".join(f"{t!r} at {_where(p.level, p.height)}" for t, p in own.items()) + ")")
    if len(mine) > 1:
        raise BuildError(f"{where} level {level}: the section has {len(mine)} bands at that level ("
                         + ", ".join(f"{t!r} at {_height(h)}" for t, h in mine) + "); one rule cannot name one of them")
    title, height = mine[0]
    return level, title, height


def le_band_align(bands: Sequence[Band], data: Path | None = None) -> dict[str, str]:
    """The plugin's page band_align ({band key: side}) for `bands` on the Layout Editor panel, from each sheet's
    section of preferences.json: its `le_band_align`, {level: "left", "centre" or "right"} for the bands of that
    section (plan_places of `data`), each found by the level and height of that section's own band (find_band), so a
    band of another section at the same level cannot be taken for it. A level whose band is not drawn now has no
    entry. BuildError naming the section, for an entry that is not that shape, a level no band of the section is at,
    or one two of its bands are at."""
    folder = Path(pd.DATA if data is None else data)
    try:
        prefs = layer_files.read_file("preferences", folder)
    except layer_files.LayerFileError as exc:
        raise BuildError(str(exc)) from exc
    places = plan_places(folder)
    drawn = {t for t, _b, _o in bands}
    out: dict[str, str] = {}
    for sheet in (k for k in prefs if not k.startswith("_")):
        given = prefs[sheet].get("le_band_align")
        if given is None:
            continue
        where = f"preferences.json section {sheet}: le_band_align"
        if not isinstance(given, dict):
            raise BuildError(f"{where} must be an object of level: side ({', '.join(ALIGN_SIDES)}), not {given!r}")
        own = {t: p for t, p in places.items() if p.section == sheet}
        for key, side in given.items():
            level, title, height = _align_band(where, key, side, own)
            if title not in drawn:
                continue                    # that band is not drawn in this build
            try:
                bi = find_band(bands, level, height, folder)    # its own band: level and height
            except BuildError as exc:
                raise BuildError(f"{where} level {level}: {exc}") from exc
            out[band_key(bands[bi][0])] = side
    return out


def bare(label: str) -> str:
    return (label or "").rstrip("*")


@functools.lru_cache(maxsize=None)
def staging_switches() -> dict[int, railroad.Switch]:
    """The staging switches, read once per run (hartlib.railroad: the level 1 rows of switches.csv and each switch's
    turnout row of the device master). BuildError names the file and row that cannot be read."""
    try:
        return railroad.Railroad(upto="inputs").switches
    except railroad.FactsError as exc:
        raise BuildError(f"staging switches: {exc}") from exc


def switch_idents() -> dict[str, str]:
    """{switch number as text: its live Layout Editor ident} of every staging switch (staging_switches)."""
    return {str(n): sw.le_ident for n, sw in staging_switches().items()}


def main_upper_device_map(path: Path = DEVICE_MAP) -> railroad.DeviceMap:
    """The main and upper rows of the device master (hartlib.railroad.read_device_map, every row checked); BuildError names the
    file and row that cannot be read."""
    try:
        return railroad.read_device_map(path)
    except railroad.FactsError as exc:
        raise BuildError(f"the device map: {exc}") from exc


def read_csv(path: Path) -> list[dict[str, str]]:
    """The rows of the CSV file at `path`, each {column: text} (OSError when it cannot be read)."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
