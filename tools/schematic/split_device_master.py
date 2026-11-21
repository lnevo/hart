#!/usr/bin/env python3
"""Split a one-file device master into devices_generated.csv and devices_field.csv (ADR-029 amendment, 2026-11-21).

    python3 tools/schematic/split_device_master.py ONE_FILE [--data DIR]    # write the pair under DIR
    python3 tools/schematic/split_device_master.py --check                  # the committed pair splits back to itself

Run once, on 2026-11-21, on the last devices.csv; kept for its test, which holds the rule below to the committed
pair (split(load()) gives the two files byte for byte).

The field file gets exactly the cells the builders used to carry over from the master's previous rows (the owner's
cells; build_device_map.staging_rows and staging_wired_rows, build_masts.CARRIED), and the identity cells (role,
assignment) of each staging device they took from the owner's row. Per row kind (staging, level 1):

- turnout, LCC alias, feedback sensor: role, assignment, cp, dcc, trial_name, jmri_comment, detector, stop,
  layout_block; notes but on an LCC alias (its note is the builder's, alias_note); system_name and jmri_name on an LCC
  alias, jmri_name on another row only where it is not its system name (the address wiring.csv gives).
- block (not a part): role, assignment, system_name, jmri_name, dcc, notes, detector, stop, layout_block, and
  jmri_comment; cp on a block that is no line block (a line block's is line_cp's); node on a block no wiring.csv pin
  wires. A wired block's comment keeps the owner's words, with {occupancy} where the builder puts its detector's
  wiring.csv text (devices.OCCUPANCY_MARK).
- occupancy sensor (not a spare): role, assignment, dcc, jmri_comment, trial_name, notes, detector, stop,
  layout_block (its cp, node, names and wiring are the builder's).
- wired mast: node. wired head (assignment field): notes.

A spare detector gets no field row: wiring.csv's spare inputs make it, and it holds no owner cell (its role and
assignment are spare by definition, its other carried cells empty), so a spare that goes when a pin takes its input
loses nothing and stops nothing.

Every other cell, and every row of another kind, is the builders' and goes to the generated file, which keeps a
field cell empty. A cell the old builders carried but that is empty on every row (wiring on a block, blocks, switch,
facing, protects, dir, part_of) is not a field column: no builder takes it from the owner any more.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_device_map as bdm  # noqa: E402  the pins that wire staging's blocks
from hartlib import devices  # noqa: E402

FIELD_LEVEL = devices.FIELD_LEVEL
WIRED = ("turnout", "fb")
_ALL = ("role", "assignment", "cp", "dcc", "jmri_comment", "trial_name", "notes", "detector", "stop", "layout_block")
OCCUPANCY = re.compile(devices.OCCUPANCY_TEXT)


def wired_blocks() -> set[str]:
    """Staging's blocks a wiring.csv pin wires (a staging detector, or a helix block's main or upper one)."""
    return {p.block for p in bdm.read_staging_pins() if p.block} | set(bdm.helix_pins())


def field_cells(r, wired: set[str]) -> dict[str, str]:
    """{column: value} of row `r`'s field cells (the module docstring), the template comment of a wired block
    included; {} for a row with none. SystemExit on a wired block comment with no detector text to mark."""
    if r["level"] != FIELD_LEVEL:
        return {}
    layer, role = r["layer"], r["role"]
    if layer in WIRED:
        cols = [c for c in _ALL if c != "notes" or role != "lcc_alias"]
        if role == "lcc_alias":
            cols += ["system_name", "jmri_name"]
        elif r["jmri_name"] != r["system_name"]:
            cols.append("jmri_name")
    elif layer == "block" and role != "part":
        cols = ["role", "assignment", "system_name", "jmri_name", "dcc", "jmri_comment", "notes", "detector", "stop",
                "layout_block"]
        if role not in devices.LINE_ROLES:
            cols.append("cp")
        if r["user_name"] not in wired:
            cols.append("node")
    elif layer == "occupancy" and role != "spare":
        cols = [c for c in _ALL if c != "cp"]
    elif layer == "mast" and r["node"]:
        cols = ["node"]
    elif layer == "head" and r["assignment"] == "field" and r["written_by"] == "build_masts.py":
        cols = ["notes"]
    else:
        return {}
    out = {c: r[c] for c in devices.FIELD_COLUMNS if c in cols and r[c]}
    if layer == "block" and r["user_name"] in wired:
        found = OCCUPANCY.findall(out.get("jmri_comment", ""))
        if len(found) != 1:
            raise SystemExit(f"{r['user_name']}: its comment has {len(found)} detector texts to mark, not one")
        out["jmri_comment"] = out["jmri_comment"].replace(found[0], devices.OCCUPANCY_MARK)
    return out


def split(rows, wired: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """(generated rows, field rows) of merged rows `rows`, in their order. A row with field cells (a staging
    device's identity among them) gets a field row; a level-less row (a Store's device) goes to the field file whole."""
    wired = wired_blocks() if wired is None else wired
    gen, field = [], []
    for r in rows:
        if not r["level"]:
            field.append(dict(r))
            continue
        cells = field_cells(r, wired)
        g = dict(r)
        if cells:
            f = dict.fromkeys(devices.COLUMNS, "")
            f.update({c: r[c] for c in devices.KEY}, **cells)
            field.append(f)
            for c in cells:
                if c != "jmri_comment" or devices.OCCUPANCY_MARK not in cells[c]:
                    g[c] = ""
        gen.append(g)
    return gen, field


def texts(rows, files: devices.Files) -> dict[Path, str]:
    gen, field = split(rows)
    return {files.master: devices.master_text(gen), files.field: devices.master_text(field)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source", nargs="?", type=Path, help="the one-file master to split")
    ap.add_argument("--data", type=Path, default=devices.paths.LAYOUT_DATA, help="where to write the pair")
    ap.add_argument("--check", action="store_true", help="the committed pair splits back to itself")
    args = ap.parse_args(argv)
    if args.check:
        files = devices.Files.here()
        stale = [p.name for p, t in texts(devices.load(files), files).items() if p.read_text(encoding="utf-8") != t]
        print("the pair splits back to itself" if not stale else f"stale: {', '.join(stale)}")
        return 1 if stale else 0
    if args.source is None:
        ap.error("name the one-file master to split, or --check")
    old = args.source.read_bytes()
    rows = devices.load(devices.Files(args.source, args.data / "devices.columns.csv", None))
    files = devices.Files(devices.master_path(args.data), args.data / "devices.columns.csv",
                          devices.field_path(args.data))
    for p, t in texts(rows, files).items():
        p.write_text(t, encoding="utf-8")
        print(f"wrote {p.name}")
    if devices.master_text(devices.load(files)).encode("utf-8") != old:
        print("the merged pair is not the one-file master byte for byte", file=sys.stderr)
        return 1
    print(f"the merged pair is {args.source.name} byte for byte ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
