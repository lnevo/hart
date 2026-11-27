"""The main and upper device-map rows in the device master's form: the owner's values over the generated ones, each
block's bean names, the turnouts that start Thrown, and the checks that hold the rows to the drawing and to the
virtual name grammar. build_device_map.master_outputs joins these with staging's rows (device_map_staging) and
writes the master.
"""
from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import le_common  # noqa: E402  band_levels, STAGING_LEVELS
from device_map_records import DeviceMapRow, MasterCells, cells  # noqa: E402
from device_map_rows import follow_swaps, owner_over  # noqa: E402
from hartlib import block_numbering, devices, railroad  # noqa: E402
from hartlib.device_rows import DeviceRow  # noqa: E402
from mast_plan import Bands  # noqa: E402  the plugin's solved bands
from mast_rule import MapError  # noqa: E402

WRITER = "build_device_map.py"      # the master's written_by of every row the builder makes


def master_rows(rows: Iterable[DeviceMapRow]) -> list[MasterCells]:
    """`rows` (the device-map form) as master rows written by the builder (hartlib.devices.master_row)."""
    return [devices.master_row(cells(o), WRITER) for o in rows]


def owned_rows(rows: Iterable[DeviceMapRow], parts: Iterable[Mapping[str, str]], files: devices.Files
               ) -> tuple[list[MasterCells], list[MasterCells]]:
    """(the main and upper rows with the owner's values over them, the same rows as generated): build()'s `rows`
    (the device-map form) and `parts` (already master rows) in the master's form, each with the field row of its id
    in the field file of `files` over it (device_map_rows.owner_over, hartlib.devices.KEY), as staging's are: on
    every level the owner's name and values go over the generated ones the same way. A virtual JMRI name stays the
    generated one (hartlib.level_devices) unless the owner's row gives a jmri_name (its assignment then the name's
    unless the row gives one: a device swapped in by its row, ADR-028). A row with no field row is as build() gave
    it. master_outputs follows renames over both. Every block row but a helix block's gets its bean names
    (block_beans)."""
    field = devices.field_index(files)
    made = block_beans(master_rows(rows) + [dict(p) for p in parts])
    out: list[Mapping[str, str]] = []
    for r in made:
        f = field.get(devices.key_of(r))
        out.append(owner_over(r, f) if f is not None else r)
    return follow_swaps(out, field), made


def is_numbered(row: Mapping[str, str]) -> bool:
    """Whether master row `row` is a block block_numbering.csv numbers: a main or upper block but a helix block."""
    return row["layer"] == "block" and row["level"] in block_numbering.LEVELS and row["role"] != "helix"


def block_beans(rows: Iterable[MasterCells], numbering_path: Path | None = None) -> list[MasterCells]:
    """`rows` (main and upper master rows, as generated) with each block row's jmri_name and layout_block, a helix
    block's left out (its beans are staging's): the numbers block_numbering.csv gives (hartlib.block_numbering.read
    and bean_names: today's numbers until the levels are wired for good). They are numbered over the generated
    names, not the owner's, so an owner's rename in the field file keeps a block's numbers (sorting the owner's
    names would shift every block after a rename with no numbered_as row). Its assignment becomes virtual (an
    internal name) and its description is written again. `numbering_path`: block_numbering.csv (default the repo's).
    MapError on a numbering problem."""
    rows = list(rows)
    names = {(r["level"], r["id"]): r["user_name"] for r in rows if is_numbered(r)}
    try:
        numbering = block_numbering.read(numbering_path or block_numbering.PATH, names)
        beans = block_numbering.bean_names(names.values(), numbering)
    except block_numbering.NumberingError as exc:
        raise MapError(str(exc)) from exc
    out = []
    for r in rows:
        if is_numbered(r):
            r = dict(r)
            r["jmri_name"], r["layout_block"] = beans[r["user_name"]]
            r["assignment"] = devices.assignment_of(r["jmri_name"])
            r["description"] = devices.describe(r)
        out.append(r)
    return out


def startup_thrown(bands: Bands) -> frozenset[str]:
    """The switch numbers of the main and upper levels (not le_common.STAGING_LEVELS: staging's turnouts are the
    field's) whose virtual turnout starts Thrown: those whose main route runs through leg C and not leg B, so every
    virtual turnout lines the main line when the tables load (227 and 229 at the peninsula loop).
    A double crossover or a crossover half stays Closed (straight through). bean_cells writes it as the turnout
    row's start, which hartlib.tables_build's startup LogixNG sets."""
    out: set[str] = set()
    for (_title, band, _opts), level in zip(bands, le_common.band_levels(bands)):
        if level in le_common.STAGING_LEVELS:
            continue
        for d in band["nodes"].values():
            if d["kind"] != "switch":
                continue
            main = {p: bool(sid and band["strands"][sid]["main"])
                    for p in "BC" for sid in [d["ins"].get(p) or d["outs"].get(p)]}
            if main["C"] and not main["B"]:
                out.add(railroad.switch_number(d["label"]))
    return frozenset(out)


def check_switch_ids(rows: Iterable[Mapping[str, str]]) -> None:
    """Every switch number in a staging turnout, LCC alias or feedback ID is a switch the drawing has: it has an OS
    block ID (os:<n>, or a crossover half's os:<n>:...) among `rows`. staging_wired_rows makes those rows for the
    switches of the plan graph (staging_switches), the drawing's blocks come from the solved plan: this holds the two
    to each other. MapError naming each that is not."""
    rows = list(rows)
    drawn = {r["id"].split(":")[1] for r in rows if r["layer"] == "block" and r["id"].startswith("os:")}
    stray = sorted({r["id"] for r in rows if r["layer"] in ("turnout", "fb") and r["id"].split(":")[1] not in drawn},
                   key=railroad.natural)
    if stray:
        raise MapError(f"staging device IDs {', '.join(stray)} name a switch the plan does not draw")


def check_virtual(rows: Iterable[Mapping[str, object]]) -> None:
    """The rows' virtual names follow hartlib.level_devices (hartlib.railroad.check_virtual_names, which
    `python3 -m hartlib.railroad check` also holds the written file to); MapError naming each problem."""
    # the rows as generated, each with its id: a turnout's switch number and a block's detector are read by ID
    bad = railroad.check_virtual_names(DeviceRow.from_dict(dict(r)) for r in rows)
    if bad:
        raise MapError("; ".join(bad))
