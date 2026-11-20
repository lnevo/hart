#!/usr/bin/env python3
"""Write LCOS_Layout_Inventory_v86.xlsx: v85 with the main and upper levels from the device map.

    python3 tools/wiring/add_main_upper_levels.py           # write v86
    python3 tools/wiring/add_main_upper_levels.py --check   # exit 1 if v86 differs from what v85 + the map give

Runs after refresh_wiring_docs.py (which writes v85, staging only). Reads:
  docs/wiring/LCOS_Layout_Inventory_v85.xlsx
  jmri/layouts/hart/data/schematic/device_map_main_upper.csv   (tools/schematic/build_device_map.py)
  jmri/layouts/hart/data/schematic/lcos_nodes_main_upper.csv  (each node's level and area)

v85 still carries the August 2026 upper-deck plan, drawn for an older track plan: nodes C14, C21, C22, C23, C24
and C32 with Switches 61 to 91, and three motor outputs on C11 (Switches 63, 65, 67). Those rows go; C11 keeps
its helix blocks, since the helix is still there. Every node of the device map is written in their place, one row per port: turnouts on 12V boards,
heads and the detector calibration pin on 5V boards, feedback on DNIN8 boards, detectors on B devices (two
blocks each), with the ports the device map gives, each row shaded light blue. Staging rows and the
DigiconSignals sheet are unchanged.
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import PatternFill

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.railroad import DEVICE_COLUMNS, FactsError, read_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WIRING = ROOT / "docs/wiring"
SRC = WIRING / "LCOS_Layout_Inventory_v85.xlsx"
OUT = WIRING / "LCOS_Layout_Inventory_v86.xlsx"
DATA = ROOT / "jmri/layouts/hart/data/schematic"
DEVICE_MAP = DATA / "device_map_main_upper.csv"
NODES = DATA / "lcos_nodes_main_upper.csv"

OLD_UPPER = {"C14", "C21", "C22", "C23", "C24", "C32"}       # the August 2026 upper-deck nodes
OLD_SWITCH = re.compile(r"^Switch (6[1-9]|[78]\d|9[01])\b")    # its Switches 61 to 91
LEVEL_NAME = {"2": "Main", "3": "Upper"}
SHADE = PatternFill("solid", fgColor="DDEBF7")    # light blue: every main and upper level row (owner, 2026-11-15)
PORT = re.compile(r"(OU|IN): (\d+) Ports: ([\d,]+)$")
NODE_K = re.compile(r"^Node: (\d+) (Turnout|Signal|Sensor|Block): (\d+)")


def read_device_rows(path: Path = DEVICE_MAP) -> list[dict]:
    """The device map's rows. comment and trial_name are required here, beyond what hartlib's own reader needs: the
    ports and the Switch Elements names are read from them on every row."""
    return [r for _line, r in read_rows(path, DEVICE_COLUMNS[:10] + ("switch",), optional=DEVICE_COLUMNS[10:])]


def read_node_rows(path: Path = NODES) -> list[dict]:
    return [r for _line, r in read_rows(path, ("level", "area", "node"), optional=("source",))]


def natural(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


class Node:
    def __init__(self, num: int, location: str):
        self.num, self.id, self.location = num, f"C{num}", location
        self.ou = defaultdict(dict)       # board -> {pin: (device, type, rail, notes)}
        self.inp = defaultdict(dict)      # board -> {pin: (device, type, notes)}
        self.turnouts, self.feedback, self.heads, self.masts, self.blocks = [], [], [], [], []


def gather(rows, node_rows) -> dict[int, Node]:
    """{node number: Node} with every port the device map gives."""
    where = {int(r["node"]): f"{r['area']} - {LEVEL_NAME[r['level']]}" for r in node_rows}
    nodes: dict[int, Node] = {}

    def get(num: int) -> Node:
        if num not in where:
            raise SystemExit(f"node {num} is in the device map but not in {NODES.name}")
        return nodes.setdefault(num, Node(num, where[num]))

    for r in rows:
        if not r["node"] or r["system_name"].startswith("MTT"):
            continue
        n = get(int(r["node"]))
        m = PORT.search(r["comment"])
        if r["layer"] == "turnout":
            board, pins = int(m.group(2)), [int(p) for p in m.group(3).split(",")]
            for pin, nr in zip(pins, "NR"):
                n.ou[board][pin] = (f"{r['user_name']} {nr}", "Turnout Motor", "12V",
                                    f"{r['system_name']} / DCC{r['dcc']}")
            n.turnouts.append((r["user_name"], [f"{n.id}-OU{board}-{p}" for p in pins], r))
        elif r["layer"] == "fb":
            board, pin = int(m.group(2)), int(m.group(3))
            n.inp[board][pin] = (r["user_name"].removeprefix("FB ") + " FB", "Turnout Feedback", r["system_name"])
            n.feedback.append((r["user_name"], f"{n.id}-IN{board}-{pin}"))
        elif r["layer"] == "head":
            board, pins = int(m.group(2)), [int(p) for p in m.group(3).split(",")]
            for pin, lamp in zip(pins, "RYG"):
                n.ou[board][pin] = (f"{r['user_name']} {lamp}", "Signal LED", "5V",
                                    f"{r['system_name']}; STOP/APPROACH/CLEAR; lamp {lamp}")
            n.heads.append((r["user_name"], board, pins))
        elif r["layer"] == "mast":
            n.masts.append(r["user_name"].removeprefix("Mast "))
        elif r["layer"] == "occupancy":
            k = int(NODE_K.match(r["comment"]).group(3)) - 1      # "Block: 1" is UID 0
            n.blocks.append((k, r))
    for n in nodes.values():
        n12 = -(-len(n.turnouts) // 4)
        if n.blocks:                                  # pin 8 of the first 5V board: detector calibration
            n.ou[n12 + 1][8] = ("Block sensor calibration", "Block Sensor Cal", "5V",
                                "Block sensor calibration current (first 5V OU pin 8); not a lamp")
    return nodes


def rail(n: Node, board: int) -> str:
    return "12V" if board <= -(-len(n.turnouts) // 4) else "5V"


def header(ws) -> list[str]:
    return [c.value for c in ws[1]]


def append(ws, values) -> None:
    """Add a main or upper level row, shaded so it stands apart from the staging rows."""
    ws.append(values)
    for cell in ws[ws.max_row][:len(values)]:      # every cell the row writes, one per header column
        cell.fill = SHADE


def drop_rows(ws, keep) -> None:
    """Delete the data rows for which keep(row values) is false (bottom up, so indexes hold)."""
    for i in range(ws.max_row, 1, -1):
        vals = [c.value for c in ws[i]]
        if any(v is not None for v in vals) and not keep(vals):
            ws.delete_rows(i)


def apply(wb, nodes: dict[int, Node], rows) -> None:
    by_name = {r["user_name"]: r for r in rows}

    # Nodes
    ws = wb["Nodes"]
    cols = header(ws)
    col = {name: i for i, name in enumerate(cols) if name}
    drop_rows(ws, lambda v: v[0] not in OLD_UPPER)
    for row in ws.iter_rows(min_row=2):
        if row[0].value == "C11":                     # its motor outputs were the old upper deck's 63/65/67
            for name, value in (("Num Turnouts", 0), ("Turnout Output Ports", None), ("Turnout Names", None),
                                ("12V Used", 0), ("12V Free", 8)):
                row[col[name]].value = value
    for num in sorted(nodes):
        n = nodes[num]
        boards12 = -(-len(n.turnouts) // 4)
        boards = sorted(n.ou)
        five = [b for b in boards if b > boards12]
        used5 = sum(len(n.ou[b]) for b in five)
        heads_pins = sum(len(p) for _, _, p in n.heads)
        bdev = sorted({f"{n.id}-B{k // 2 + 1}" for k, _ in n.blocks}, key=natural)
        vals = {
            "Node ID": n.id, "Legacy Node ID": None, "Address": num, "Location": n.location, "Type": "Client",
            "DNOU8": ", ".join(f"OU{b}" for b in boards) or None,
            "DNIN8": ", ".join(f"IN{b}" for b in sorted(n.inp)) or None,
            "12V Boards": boards12, "5V Boards": len(five), "Num 12V": 8 * boards12,
            "12V Used": 2 * len(n.turnouts), "12V Free": 8 * boards12 - 2 * len(n.turnouts),
            "Num Turnouts": len(n.turnouts),
            "Turnout Output Ports": ", ".join(p for _, ps, _ in n.turnouts for p in ps) or None,
            "Turnout Names": ", ".join(t for t, _, _ in n.turnouts) or None,
            "Num IN": 8 * len(n.inp), "Input Used": len(n.feedback), "Input Free": 8 * len(n.inp) - len(n.feedback),
            "Num Buttons": 0, "Num Sensors": len(n.feedback), "Button Devices": None,
            "Turnout Feedback Devices": ", ".join(f.removeprefix("FB ") + " FB" for f, _ in n.feedback) or None,
            "Num 5V": 8 * len(five), "5V Used": used5, "5V Free": 8 * len(five) - used5,
            "Num Signal LEDs": heads_pins, "Signal LED Devices": len(n.heads),
            "Signal Names": ", ".join(sorted(n.masts, key=natural)) or None, "DNCTA": None,
            "BS Devices": ", ".join(bdev) or None, "Num Blocks": len(n.blocks),
            "Block Section Names": ", ".join(block_name(r, by_name) for _, r in sorted(n.blocks, key=lambda b: b[0]))
            or None,
        }
        append(ws, [vals.get(name) if name else None for name in cols])

    # DNOU8
    ws = wb["DNOU8"]
    drop_rows(ws, lambda v: v[1] not in OLD_UPPER)
    for row in ws.iter_rows(min_row=2):
        if row[1].value == "C11" and row[0].value in {f"C11-OU1-{p}" for p in range(1, 7)}:
            row[4].value, row[5].value = None, None
            row[7].value = "free: was a motor of the old upper-deck plan (Switch 63, 65 or 67) in v85"
    for num in sorted(nodes):
        n = nodes[num]
        for board in sorted(n.ou):
            for pin in range(1, 9):
                dev, kind, volts, notes = n.ou[board].get(pin, (None, None, rail(n, board), None))
                append(ws, [f"{n.id}-OU{board}-{pin}", n.id, n.location, pin, dev, kind, volts, notes])

    # DNIN8
    ws = wb["DNIN8"]
    drop_rows(ws, lambda v: v[1] not in OLD_UPPER)
    for num in sorted(nodes):
        n = nodes[num]
        for board in sorted(n.inp):
            for pin in range(1, 9):
                dev, kind, notes = n.inp[board].get(pin, (None, None, None))
                append(ws, [f"{n.id}-IN{board}-{pin}", n.id, n.location, pin, dev, kind, notes])

    # TurnoutSummary
    ws = wb["TurnoutSummary"]
    cols = header(ws)
    drop_rows(ws, lambda v: not OLD_SWITCH.match(str(v[0] or "")))
    fb = {name: port for n in nodes.values() for name, port in n.feedback}
    entry = {}                                        # switch -> its two-head mast and that mast's top head pins
    for n in nodes.values():
        for head, board, pins in n.heads:
            if head.endswith(" Top"):
                mast = head.removeprefix("Head ").removesuffix(" Top")
                sw = by_name[f"Mast {mast}"]["switch"]          # its switch column (hartlib.railroad.DEVICE_FACTS)
                entry.setdefault(sw, (mast, [f"{n.id}-OU{board}-{p}" for p in pins]))
    for n in sorted(nodes.values(), key=lambda n: n.num):
        for name, _, r in n.turnouts:
            sw = name.removeprefix("Switch ")
            mast, pins = entry.get(sw, (None, [None, None, None]))
            vals = {"Turnout": name, "Parent Node": n.id,
                    "Location/Area": f"{r['cp']} ({n.location})" if r["cp"] else n.location,
                    "Switch Elements": r["trial_name"] or name, "Button": None,
                    "Feedback N": fb.get(f"FB {name} N"), "Feedback R": fb.get(f"FB {name} R"),
                    "Entry Signal": mast, "Entry Signal R Port": pins[0], "Entry Signal Y Port": pins[1],
                    "Entry Signal G Port": pins[2]}
            append(ws, [vals.get(c) for c in cols])

    # BlockSensors
    ws = wb["BlockSensors"]
    drop_rows(ws, lambda v: v[1] not in OLD_UPPER)       # C11 keeps the helix blocks: the helix is still there
    for num in sorted(nodes):
        n = nodes[num]
        for k, r in sorted(n.blocks, key=lambda b: b[0]):
            dev = f"{n.id}-B{k // 2 + 1}"
            blk = block_name(r, by_name)
            append(ws, [f"{dev}-{k % 2 + 1}", n.id, dev, k % 2 + 1, blk, by_name[blk]["trial_name"] or None,
                       n.location, None, f"Block {num}-{k + 1} / {r['system_name']}"])


def block_name(occ: dict, by_name: dict) -> str:
    """The JMRI block an occupancy row detects: a switch's sensor ("BS Switch <n>") detects its OS block
    ("OS Switch <n>"), any other ("BS <a>-<b>") the track of the same name ("Track <a>-<b>")."""
    rest = occ["user_name"].removeprefix("BS ")
    name = f"OS {rest}" if rest.startswith("Switch ") else f"Track {rest}"
    if name not in by_name:
        raise SystemExit(f"{occ['user_name']}: no block {name} in {DEVICE_MAP.name}")
    return name


def build(dest: Path) -> None:
    rows = read_device_rows()
    nodes = gather(rows, read_node_rows())
    wb = load_workbook(SRC)
    apply(wb, nodes, rows)
    wb.save(dest)


def values(path: Path) -> dict:
    """Every cell's value and fill colour, per sheet: the shading is part of what --check compares."""
    wb = load_workbook(path, data_only=True)
    return {ws.title: [[(c.value, (c.fill.fill_type, c.fill.fgColor.rgb) if c.fill and c.fill.fill_type else None)
                        for c in row]
                       for row in ws.iter_rows()] for ws in wb.worksheets}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if v86 differs from what v85 and the map give")
    args = ap.parse_args(argv)
    try:
        if not args.check:
            build(OUT)
            print(f"wrote {OUT.relative_to(ROOT)}")
            return 0
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / OUT.name
            build(fresh)
            same = OUT.exists() and values(OUT) == values(fresh)
    except FactsError as exc:
        print(f"{Path(__file__).name}: {exc}", file=sys.stderr)
        return 2
    print(f"{OUT.name} is current" if same else f"{OUT.name} is stale: run {Path(__file__).name}")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
