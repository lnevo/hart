"""The main and upper drawing as the device map reads it (build_device_map.py): its tracks with their names
(named_tracks), the owner's block splits (split_tracks, split_edges), its balloon loop halves, its block layer and home
masts (main_upper_layer, home_and_posts), its double crossovers' corners (dx_corners, xover_corners, corner_blocks_of),
its helix blocks (helix_tracks, check_helix_ends), a line block's role (line_role) and the control points'
plan_overrides.json keys (labels_by_level, overrides_keys).

The builder's paths and the levels they give (OVERRIDES, SHEET, LEVELS, band_level) and its solve() are read from
build_device_map when a function runs (builder()), as they are then (a test may patch them): that module imports this
one, so this one does not import it at load.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import block_layer  # noqa: E402  the one block process for every level
import device_map_inputs as inputs  # noqa: E402  read_pins, which this gives its tracks
import le_common  # noqa: E402  band_key: the plugin's key for a band, which rotate_bands lists
import mast_plan  # noqa: E402  the one mast process for every level
import block_override_rows  # noqa: E402  read_block_splits
import mast_rule  # noqa: E402  running_tracks
from map_error import MapError  # noqa: E402
from plan_bands import band_levels, read_helix_tracks  # noqa: E402
from plan_tracks import end_label  # noqa: E402
from hartlib import layer_files, railroad  # noqa: E402

base = railroad.switch_number
natural = railroad.natural


def builder():
    """build_device_map, imported on first use (it imports this module): its paths, levels and solve() as they are
    when called (a test may patch them)."""
    import build_device_map
    return build_device_map


def labels_by_level(bands) -> dict[int, set[str]]:
    bdm = builder()
    out = defaultdict(set)
    for title, band, _ in bands:
        lv = bdm.band_level(title)
        if lv:
            out[lv] |= {d["label"] for d in band["nodes"].values() if d["kind"] in ("switch", "dx")}
    return out


def overrides_keys(cps, by_level) -> dict:
    """control_points for plan_overrides.json's main_upper section: each control point lists the labels of its
    switches on its own level's band (both halves of a crossover there, one half when the other is on the
    other band), as the band prints them: a moved switch keeps its star ("223*"), which station bars match on."""
    cp_out = {}
    for cp in cps:
        have = by_level[cp.level]
        refs = []
        for s in cp.switches:
            mine = sorted(lb for lb in have if base(lb) == s)
            if not mine:
                raise MapError(f"{cp.name}: switch {s} is not on the level {cp.level} band")
            refs += mine
        cp_out[cp.name] = {"switches": refs}
    return cp_out


def xover_corners(number: str, corners: dict) -> dict:
    """{schematic leg: OS block} of a double crossover's four corner blocks, named by the Layout Editor corner each
    leg reaches (`corners`, {leg: corner}: dx_corners); see the module text."""
    if sorted(corners) != list("ABCD") or sorted(corners.values()) != list("ABCD"):
        raise MapError(f"double crossover {number}: legs to corners {corners} is not one corner per leg")
    return {leg: f"OS Switch {number}{corner.lower()}" for leg, corner in sorted(corners.items())}


def dx_corners(bands, le_mod, page) -> dict:
    """{switch number: {schematic leg: Layout Editor corner}} of each double crossover on the main and upper bands,
    as the plugin draws it (le.double_corners; a band in the page's rotate_bands is turned)."""
    bdm = builder()
    out = {}
    for title, band, _ in bands:
        if not bdm.band_level(title):
            continue
        for n, d in band["nodes"].items():
            if d["kind"] == "dx":
                # rotate_bands lists the plugin's band keys (le_common.band_key), not levels
                turned = le_common.band_key(title) in page.get("rotate_bands", ())
                out[base(d["label"])] = le_mod.double_corners(band, n, turned)
    return out


def block_overrides() -> Path:
    """block_overrides.csv beside plan_overrides.json, as OVERRIDES is when called (a test may patch it): the one path
    every reader here takes for every kind of its rows (splits, track pieces, crossover halves)."""
    bdm = builder()
    return block_layer.overrides_path(bdm.OVERRIDES.parent)


def helix_tracks() -> dict:
    """read_helix_tracks of OVERRIDES as it is when called (a test may patch it)."""
    bdm = builder()
    return read_helix_tracks(bdm.OVERRIDES)


def split_tracks(path: Path | None = None, found: list | None = None) -> set[str]:
    """The main and upper track names block_overrides.csv splits into two blocks at their turnback (the owner's choice,
    not a rule: block_override_rows.read_block_splits): each row's end switches resolved to the generated name in `found` (tracks
    with names; default: the solved schematic's) at build time, so a renumbered switch moves its row with it."""
    bdm = builder()
    return block_override_rows.read_block_splits(path or block_overrides(), named_tracks() if found is None else found, bdm.LEVELS)


def named_tracks(bands=None, joined=None, runs=None, overrides=None, helix=None, owner=None) -> list[dict]:
    """The track entries of the bands `overrides` names (default: the main and upper bands) with their names
    (block_layer.tracks and name_tracks: the name store's by the strands' IDs, a helix track's helix block, else the
    end-switch rule); the solved schematic's bands when none are given. `helix`: read_helix_tracks (default);
    `owner`: the owner's track names (hartlib.track_names.owner_names, default the rows beside OVERRIDES' folder)."""
    bdm = builder()
    if bands is None:
        bands, joined, runs, _corners = bdm.solve()
    if overrides is None:
        overrides = layer_files.read("plan_overrides", bdm.SHEET, bdm.OVERRIDES.parent)
    found = block_layer.tracks(bands, runs, joined, band_levels(overrides), bdm.OVERRIDES.parent, owner)
    block_layer.name_tracks(found, helix_tracks() if helix is None else helix)
    return found


def split_edges(path: Path | None = None, found: list | None = None) -> dict:
    """{plan edge: track name} of the main and upper split tracks (block_layer.split_edges over block_overrides.csv):
    each name resolved to the one plan edge its track is drawn on, in `found` (tracks with names; default: the solved
    schematic's), at build time. Stops on a name no track has, or a track drawn on more than one plan edge (a split
    needs one track folded at one turnback)."""
    bdm = builder()
    found = named_tracks() if found is None else found
    # a block_overrides.csv with no main or upper split gives no drawing key: no splits
    return block_layer.split_edges(found, bdm.LEVELS, path or block_overrides(), bdm.OVERRIDES.parent).get(bdm.SHEET, {})


def read_pins(path: Path | None = None, found: list | None = None, split: set | None = None,
              ids: dict | None = None) -> dict:
    """device_map_inputs.read_pins over `found` (tracks with names; default named_tracks, the solved schematic's),
    `split` (default split_tracks of `found`) and `ids` ({block id: name} of this build's tracks, for a pin given by
    id): the tracks its pins resolve against, which the readers do not solve."""
    found = named_tracks() if found is None else found
    return inputs.read_pins(path, found, split_tracks(found=found) if split is None else split, ids)



def loop_halves(band, runs, split: dict | None = None) -> dict:
    """{strand id: 1 or 2} of each balloon loop and split track of a main or upper `band` (block_layer.loop_halves);
    `split`: split_edges (default: block_overrides.csv's)."""
    return block_layer.loop_halves(band, runs, split_edges() if split is None else split, block_overrides().name)


def main_upper_layer(bands, runs, found, split_map: dict, corner_blocks: dict, posts: dict,
                     overrides: Path | None = None) -> block_layer.Layer:
    """block_layer.layer of the main and upper levels, as mast_plan.plan reads it (`bands`, `cm`) and build() writes
    its rows: `split_map` (split_edges), block_overrides.csv, `corner_blocks` (a double crossover's corner blocks,
    {switch: {leg: block}}) and `posts` (where the home masts stand, home_and_posts). One block per track, a balloon
    loop or split track in two halves (half 1 at the lower-numbered switch; each half's length is half the track's), a
    crossover's inside its switch's OS block, a link (under block_layer.LINK_CM between two switches) a part of an OS
    block; an OS block counts 0 cm (the boundary is at the switch's leg). `overrides`: block_overrides.csv's path
    (default block_overrides()), the file `split_map` was read from too."""
    bdm = builder()
    return block_layer.layer(bands, runs, found, bdm.LEVELS, {bdm.SHEET: split_map},
                             block_layer.read_exceptions(found, bands, bdm.LEVELS, overrides or block_overrides()),
                             corners=corner_blocks, posts=posts,
                             data=bdm.OVERRIDES.parent)


def home_and_posts(bands, joined, found, levels: dict, cp_of: dict, corner_blocks: dict | None, split: set
                   ) -> tuple[list[dict], dict]:
    """(mast_plan.home_masts of `levels`, mast_plan.home_posts of them): the home masts stand where the track rule puts
    them, before any block is known, and the block layer reads where they stand (a link a mast faces from its own
    switch joins the OS block at its other end). One step for every level."""
    home = mast_plan.home_masts(bands, joined, found, cp_of, mast_rule.running_tracks(bands, found, cp_of), levels=levels,
                                corner_blocks=corner_blocks, split=split)
    return home, mast_plan.home_posts(home)


def corner_blocks_of(bands, corners: dict | None) -> dict:
    """{switch: {schematic leg: corner block}} of each double crossover on the main and upper bands (xover_corners
    over `corners`, dx_corners). MapError on a double crossover with no corners given."""
    bdm = builder()
    corners = corners or {}
    dxs = {base(d["label"]) for title, band, _ in bands if bdm.band_level(title)
           for d in band["nodes"].values() if d["kind"] == "dx"}
    if dxs - set(corners):
        raise MapError(f"double crossover {', '.join(sorted(dxs - set(corners), key=natural))}: no corners given")
    return {s: xover_corners(s, corners[s]) for s in dxs}


def check_helix_ends(bands, joined, found, helix) -> None:
    """Stop unless each track up the helix ends at the switch plan_overrides.json gives it (level_switch, the label the
    drawing prints: 131A, 131B), so the file cannot give a helix track the other one's block."""
    if not helix:
        return
    want = {v["block"]: v["level_switch"] for v in helix.values()}
    bad = []
    for t in found:
        if not any(k == "helix" for k, _v in t["ends"]):
            continue
        labels = [end_label(bands, joined, t["band"], n) for (n, _p), (k, _v) in zip(t["legs"], t["ends"]) if k == "sw"]
        if t["name"] not in want or labels != [want[t["name"]]]:
            bad.append(f"{t['name']} runs from switch {', '.join(labels) or 'none'}, plan_overrides.json says "
                       f"{want.get(t['name'], 'nothing')}")
    drawn = {t["name"] for t in found}
    bad += [f"{b} is drawn on neither the main nor the upper band" for b in want if b not in drawn]
    if bad:
        raise MapError("helix tracks: " + "; ".join(bad))


def line_role(t: dict, half: int | None) -> str:
    """The role (hartlib.devices.ROLES) of a line block of track entry `t`, from its ends (plan_tracks.end_ref: sw,
    helix, bumper), never its name: helix for a track up the helix, loop_half for a half of a balloon loop, spur for a
    switch at one end and a buffer stop at the other, track for a switch at each end (a split track's halves are track
    blocks, as the whole track would be). MapError, naming the track, on any other pair of ends."""
    kinds = sorted(k for k, _v in t["ends"])
    if "helix" in kinds:
        return "helix"
    if t["loop"]:
        if half is None:
            raise MapError(f"{t['name']}: a balloon loop is two blocks, one per half; this one has none")
        return "loop_half"
    if kinds == ["bumper", "sw"]:
        return "spur"
    if kinds == ["sw", "sw"]:
        return "track"
    raise MapError(f"{t['name']}: a line block ends at {' and '.join(kinds) or 'nothing'}; a track runs from a switch "
                   "to a switch, a buffer stop or the helix")
