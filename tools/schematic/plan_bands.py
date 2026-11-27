"""The bands of a solved schematic and the levels and helix tracks they hold.

band_places() reads each band's level and height from a plan-overrides file, band_levels() and band_level() give a
band title's level, helix_tags() tags each level's helix track ("H1", "H2") and helix_blocks() names its block from
the plan overrides' helix map (read_helix_tracks). A band is found by its place, never by its title; the titles
stay the drawn text.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TypedDict

from hartlib import railroad
from map_error import MapError

# A solved band of the schematic-maps plugin (nodes, strands, rail, mp ...): the plugin's own JSON shape, read by key,
# so its values are Any at this boundary.
Band = dict[str, Any]
Bands = Sequence[tuple[str, Band, dict]]       # (title, band, overrides) of every band, in the plugin's order
Overrides = Mapping[str, Any]                  # one plan-overrides section (plan_overrides.json), the plugin's JSON
Levels = Mapping[str, int]                     # {band title: level} (band_levels)
HelixTags = Mapping[int, str]                  # {level: helix tag} (helix_tags): the helix track each level reaches

HELIX_SOURCE = railroad.Sources.under().plan_overrides     # plan_overrides.json: the helix ends and map


def band_places(overrides: Overrides) -> dict[str, tuple[int, float | None]]:
    """{band title: (level, height)} of one plan-overrides file: each `levels.bands` entry's name with its `level`
    (main and upper: 2 and 3) and its height, `below` (the cm its track lies under: 5 and 99), or, for a one-band
    input, `level_title` with the file's own `level` (staging: 1) and no height. MapError for a band with no level, a
    level that is not 1, 2 or 3, a height that is not a number above 0, a title two bands share, two bands at one
    level and height, or a file that names no band."""
    entries = [(b.get("name"), b.get("level"), b.get("below"), f"levels.bands entry {b.get('name')!r}")
               for b in overrides.get("levels", {}).get("bands", ())]
    if not entries and overrides.get("level_title"):
        entries = [(overrides["level_title"], overrides.get("level"), None, "level_title")]
    if not entries:
        raise MapError("the plan overrides name no band (levels.bands, or level_title)")
    out: dict[str, tuple[int, float | None]] = {}
    at: dict[tuple[int, float | None], str] = {}
    for name, level, height, what in entries:
        if not name:
            raise MapError(f"{what}: no name")
        if type(level) is not int or level not in (1, 2, 3):
            raise MapError(f"{what} has level {level!r}, which is not 1, 2 or 3")
        if height is not None and (type(height) not in (int, float) or not height > 0):
            raise MapError(f"{what}: band {name!r} has height (below) {height!r}, which is not a number above 0")
        if name in out:
            raise MapError(f"two bands are titled {name!r}")
        if (level, height) in at:
            raise MapError(f"bands {at[(level, height)]!r} and {name!r} are both at level {level}, "
                           f"{'height ' + format(height, 'g') if height is not None else 'no height'}")
        at[(level, height)] = name
        out[name] = (level, height)
    return out


def band_levels(overrides: Overrides) -> dict[str, int]:
    """{band title: level} of one plan-overrides file (band_places, every check of it, without the height)."""
    return {name: level for name, (level, _height) in band_places(overrides).items()}


def band_level(title: str, levels: Levels) -> int | None:
    """The level of a band by its title, in `levels` (band_levels); None for a band `levels` does not hold."""
    return levels.get(title) if title else None


def helix_tags(bands: Bands, overrides: Overrides) -> dict[int, str]:
    """{level: "H1"|"H2"}: the helix tracks in the overrides' order, each on the band holding its switch. MapError
    when the overrides have no relabel edit (its map gives each helix switch its drawn label)."""
    relabel = next((e["map"] for e in overrides["edits"] if e["op"] == "relabel"), None)
    if relabel is None:
        raise MapError("the plan overrides have no relabel edit, so the helix switches have no drawn label")
    levels: dict[str, int] = band_levels(overrides)
    out: dict[int, str] = {}
    for i, sw in enumerate(overrides.get("helix", {})):
        label = relabel.get(sw, sw)
        for title, band, _ in bands:
            if any(d.get("label", "").rstrip("*") == label for d in band["nodes"].values()):
                lv = band_level(title, levels)
                if lv is not None:         # a band with no level (none today) draws no helix track
                    out[lv] = f"H{i + 1}"
    return out


class HelixEntry(TypedDict):
    """One helix track as read_helix_tracks gives it: its JMRI block, the switches at its two ends and its shown name."""
    block: str
    staging_switch: str
    level_switch: str
    shown: str


def read_helix_tracks(path: Path | None = None) -> dict[str, HelixEntry]:
    """{plan helix track name: {block, staging_switch, level_switch, shown}} from the plan overrides (hartlib.railroad
    .read_helix_tracks, which checks them): each helix track is one JMRI block, "Track <plan name>" by the ordinary
    rule, from its staging switch to its main or upper switch; `shown` is the name a reader
    sees (preferences.json track_labels). Its FactsError as a MapError."""
    try:
        got = railroad.read_helix_tracks(path or HELIX_SOURCE)
    except railroad.FactsError as exc:
        raise MapError(str(exc)) from exc
    return {h.helix: HelixEntry(block=h.block, staging_switch=h.staging_switch, level_switch=h.level_switch,
                                shown=h.shown) for h in got.values()}


def helix_blocks(overrides: Overrides, helix: Mapping[str, HelixEntry] | None = None) -> dict[str, str]:
    """{helix tag ("H1", "H2", as helix_tags gives them): block} for the main and upper levels: the overrides' helix
    tracks in order, each "Track <plan name>" (read_helix_tracks). Stops on a helix track of `overrides` that
    `helix` does not hold, or one it holds that the overrides do not have."""
    helix = read_helix_tracks() if helix is None else helix
    plan = list(overrides.get("helix", {}).values())
    if sorted(plan) != sorted(helix):
        raise MapError(f"the helix tracks are {sorted(helix)}, the plan overrides' helix map {sorted(plan)}")
    return {f"H{i + 1}": helix[name]["block"] for i, name in enumerate(plan)}
