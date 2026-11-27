#!/usr/bin/env python3
"""Freeze a main or upper control point's wiring: copy what the rule gives it now into wiring.csv as wired rows.

    python3 tools/wiring/freeze_wiring.py --cp "CP 107"            # write the rows into wiring.csv
    python3 tools/wiring/freeze_wiring.py --cp "CP 107" --dry-run  # print them, write nothing
    make wiring-freeze CP="CP 107"

Run it when a control point is wired as the device map has it (owner, 2026-11-20: once main and upper are wired,
their values are static; the rule is for the design while it is open). The control point's devices in
the device master (levels 2 and 3, its `cp`) become rows of jmri/layouts/hart/data/wiring.csv,
status wired:
  - each turnout ("Switch <n>"; its LCC alias follows it) and feedback sensor ("FB Switch <n> N|R"): node, LCOS
    number, board and ports;
  - each head on a node ("Head <mast>[ Top| Bottom]"): node, LCOS signal, board and ports. A mast the board rule left
    without a node (HEAD_NOT_WIRED) stops the freeze: place it first;
  - each detector on a node: an OS block by its name ("OS Switch 107"), a helix block by its name, any other track
    by its end switches (switch_a, switch_b, parallel, half) as build_device_map.read_pins keys them. A detector the
    owner had placed (planned) turns wired.
tools/schematic/build_device_map.py then gives those devices the same values on every build (Nodes.freeze,
read_pins), and hands nothing else their node numbers or pins. Freezing changes no JMRI name: the devices stay
virtual in JMRI until the device map swaps the physical ones in. A device frozen already is left as it is.
Stops (exit 2, naming the cause) on an unknown control point, a staging one, or a head not placed.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, paths, wiring  # noqa: E402

ROOT = paths.REPO_ROOT
sys.path.insert(1, str(ROOT / "tools/schematic"))
from hartlib.railroad_facts import FactsError  # noqa: E402
from hartlib.levels import MAIN_UPPER  # noqa: E402
import build_device_map as bdm  # noqa: E402
import build_layout_le as bl  # noqa: E402

PORTS = re.compile(r"^Node: (\d+) (Turnout|Sensor|Signal): (\d+)((?: \| (?:OU|IN): \d+ Ports: [\d,]+)+)$")
GROUP = re.compile(r"(OU|IN): (\d+) Ports: ([\d,]+)")   # one board's pins in a wiring text
BLOCK = re.compile(r"^Node: (\d+) Block: (\d+)$")
KIND = {"Turnout": "turnout", "Sensor": "fb", "Signal": "head"}


class FreezeError(Exception):
    pass


def device_rows(path: Path | None = None) -> list[dict]:
    """Every main and upper row of the master in the device-map form plus its role and id, values stripped."""
    return [{c: v.strip() for c, v in {**devices.device_map_row(r), "role": r.role, "id": r.id}.items()}
            for r in devices.load(path) if r.level in MAIN_UPPER and r.role not in devices.OUT_OF_MAPS]


def track_keys(found: list[dict] | None = None) -> dict[str, dict]:
    """{block name: {switch_a, switch_b, parallel, half}} of every main and upper track block, as
    build_device_map.read_pins resolves them: the track's end switches (plan_tracks.track_key, lower first), `parallel`
    when two tracks share them (1, 2 in plan_tracks.plan_order, as resolve_track reads them back), `half` for a
    balloon loop's or a split track's halves."""
    import plan_tracks                  # on sys.path once build_device_map is loaded
    found = bdm.named_tracks() if found is None else found
    split = bdm.split_tracks(found=found)
    by_key: dict[tuple, list[dict]] = {}
    for t in found:
        key = plan_tracks.track_key(t)
        if key:
            by_key.setdefault((t["level"], key), []).append(t)
    out = {}
    for (_lv, (a, b)), same in by_key.items():
        same.sort(key=plan_tracks.plan_order)
        for i, t in enumerate(same, 1):
            halves = (1, 2) if (t["loop"] or t["name"] in split) else (None,)
            for half in halves:
                out[bdm.loop_placeholder(t["name"], half)] = dict(
                    switch_a=a, switch_b=b, parallel=str(i) if len(same) > 1 else "", half=str(half or ""))
    return out


def freeze_rows(cp: str, rows: list[dict], keys: dict[str, dict], helix: set[str], today: str) -> list[dict]:
    """The wiring.csv rows (wiring.COLUMNS, status wired) of control point `cp`'s devices on a node. FreezeError on
    no such control point or a head with no node."""
    # a line block's cp lists the places it joins (devices.LIST), its own level's first (build_device_map.line_cp):
    # its detector is frozen with that first one
    first = lambda r: devices.place(r).split(devices.LIST)[0]  # noqa: E731  a turnout's from the switch lists
    mine = [r for r in rows if first(r) == cp]
    if not mine:
        cps = sorted({first(r) for r in rows if first(r)}, key=lambda c: [int(t) if t.isdigit() else t
                                                                         for t in re.split(r"(\d+)", c)])
        raise FreezeError(f"no main or upper control point {cp!r}; they are {', '.join(cps)}")
    note = wiring.freeze_note(cp, today)
    where = devices.index().where              # a row's line in the device master, for a message
    out, bad = [], []
    for r in mine:
        base = {c: "" for c in wiring.COLUMNS} | dict(level=r["level"], status="wired", notes=note)
        if r["layer"] == "turnout" and devices.row_role(r, where(r)) == "lcc_alias":
            continue                                           # an LCC alias: its turnout's row carries it
        if r["layer"] in ("turnout", "fb", "head"):
            if r["layer"] == "head" and not r["node"]:
                bad.append(f"{r['user_name']} has no node (the board rule could not place it): place it first")
                continue
            m = PORTS.match(r["comment"])
            if not m:
                bad.append(f"{r['layer']} {r['user_name']}: its wiring {r['comment']!r} gives no port")
                continue
            groups = GROUP.findall(m.group(4))           # a head's pins may span two boards
            if len(groups) > 1 and r["layer"] != "head":
                bad.append(f"{r['layer']} {r['user_name']}: its wiring {r['comment']!r} spans two boards; only a "
                           "head's pins may")
                continue
            first = f"{groups[0][0]}{groups[0][1]}"
            ports = [p if f"{kind}{board}" == first else f"{kind}{board}-{p}"
                     for kind, board, pins in groups for p in pins.split(",")]
            out.append(base | dict(kind=KIND[m.group(2)], id=r["id"], node=m.group(1),
                                   index=m.group(3), board=first, ports=",".join(ports)))
        elif r["layer"] == "occupancy" and r["node"]:
            m = BLOCK.match(r["comment"])
            block = r["blocks"]
            if not m:
                bad.append(f"occupancy {r['user_name']}: its wiring {r['comment']!r} gives no input")
                continue
            row = base | dict(kind="detector", node=m.group(1), index=m.group(2))
            if devices.is_os(r, where(r)) or block in helix:        # its role is its block's
                row["id"] = r["id"]                                 # det:<block id>: the name store names it
            elif block in keys:
                row |= keys[block]
            else:
                bad.append(f"{r['user_name']}: no track key for {block}")
                continue
            out.append(row)
    if bad:
        raise FreezeError(f"{cp}: " + "; ".join(bad))
    return out


def key_of(r) -> tuple:
    """A wiring.csv row's identity: its level, kind and id (or a local device's label, or a track's switches and
    half)."""
    get = r.get if isinstance(r, dict) else lambda c: getattr(r, c)
    return (str(get("level")), get("kind"), get("id"), get("device"), get("switch_a"), get("switch_b"),
            get("parallel"), get("half"))


def merge(text: str, new: list[dict]) -> tuple[str, list[dict], list[dict]]:
    """(wiring.csv's text with `new` merged in, the rows added, the rows turned wired). A planned row of the same
    device turns wired; a wired one stays as it is. FreezeError on a planned row whose node or input the device map
    does not have (a stale map: rebuild it first)."""
    rows = [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]
    at = {key_of(r): i for i, r in enumerate(rows)}
    added, turned, moved = [], [], []
    for r in new:
        i = at.get(key_of(r))
        if i is None:
            rows.append(r)
            added.append(r)
        elif rows[i]["status"] == "planned":
            if (rows[i]["node"], rows[i]["index"]) != (r["node"], r["index"]):
                moved.append(f"{r['id'] or r['switch_a'] + '-' + r['switch_b']}: wiring.csv plans node "
                             f"{rows[i]['node']} input {rows[i]['index']}, the device map has node {r['node']} "
                             f"input {r['index']}")
                continue
            rows[i] = r | {"notes": "; ".join(x for x in (rows[i]["notes"], r["notes"]) if x)}
            turned.append(rows[i])
    if moved:
        raise FreezeError("planned rows the device map does not follow (rebuild it: "
                          "python3 tools/schematic/build_device_map.py): " + "; ".join(moved))
    return wiring.canonical(rows), added, turned               # staging, then main, then upper: the one format


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cp", required=True, help='the control point, as the device master names it ("CP 107")')
    ap.add_argument("--dry-run", action="store_true", help="print the rows; write nothing")
    args = ap.parse_args(argv)
    try:
        helix = {h["block"] for h in bdm.read_helix_tracks().values()}
        new = freeze_rows(args.cp, device_rows(), track_keys(), helix, date.today().isoformat())
        text, added, turned = merge(wiring.PATH.read_text(encoding="utf-8"), new)
        with tempfile.TemporaryDirectory() as tmp:            # the merged file holds wiring.csv's rules
            merged = Path(tmp) / wiring.PATH.name
            merged.write_text(text, encoding="utf-8")
            wiring.read(merged)
    except (FreezeError, FactsError, bdm.MapError, bl.BuildError) as exc:
        print(f"freeze_wiring.py: {exc}", file=sys.stderr)
        return 2
    print(f"{args.cp}: {len(added)} row(s) frozen, {len(turned)} planned row(s) now wired, "
          f"{len(new) - len(added) - len(turned)} frozen already")
    if args.dry_run:
        out = csv.DictWriter(sys.stdout, wiring.COLUMNS, lineterminator="\n")
        out.writerows(added + turned)
        return 0
    wiring.PATH.write_text(text, encoding="utf-8")
    print(f"wrote {wiring.PATH.relative_to(ROOT)}; check: python3 tools/schematic/build_device_map.py --check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
