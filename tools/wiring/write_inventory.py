#!/usr/bin/env python3
"""Write LCOS_Layout_Inventory_v86.xlsx, the wiring inventory of every level, from the repo's own sources.

    python3 tools/wiring/write_inventory.py           # write v86
    python3 tools/wiring/write_inventory.py --check   # exit 1 if v86 differs from what the sources give

The workbook is a view: nobody edits it (owner, 2026-11-20). It is written from scratch from
  The device master           every level's turnouts, feedback, heads, masts and detectors, with the
                                               ports in their wiring text. Staging's are written from wiring.csv (the
                                               physical wiring source, as JMRI has it wired), main and upper's by
                                               tools/schematic/build_device_map.py's rule (a draft) but for the rows
                                               wiring.csv lists.
  jmri/layouts/hart/data/wiring.csv            the fascia buttons and relays (no JMRI device).
  jmri/layouts/hart/data/schematic/lcos_nodes.csv   every node, its level and area.
  jmri/layouts/hart/output/signal_head_plan.csv     the DigiconSignals sheet's masts (its pins are wiring.csv's heads).

One row per port, as the inventory always had: turnouts on the OU boards their wiring names, feedback on DNIN8 boards,
heads on OU boards, detectors on B devices (two blocks each), and wiring.csv's fascia buttons, relays and
calibration relays (the relay that resets the DCC power so a node's detectors calibrate; every node with detectors
has one, owner 2026-11-21). Staging's rows are only what is wired, or reserved; main and upper's follow the rule's
boards (12V boards for turnouts first, 5V boards after them, pin 8 of the first 5V board for the calibration relay)
and are shaded light blue (owner, 2026-11-15). The workbooks before it, the imported
v84 and the v85 written from it, are history in archive/ (owner, 2026-11-20).

v86 is an output only (ADR-039): www/scripts/build_wiring_json.py and create_wiring_schematic_ppt.py take the same
sheets from workbook(), built in memory, and never open the file.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, paths, wiring  # noqa: E402
from hartlib import railroad  # noqa: E402
from hartlib.railroad import FactsError  # noqa: E402

class InventoryError(FactsError):
    """The device master and the node file disagree about a port or a block; the message names the row."""


ROOT = paths.REPO_ROOT
WIRING_DOCS = ROOT / "docs/wiring"
OUT = WIRING_DOCS / "LCOS_Layout_Inventory_v86.xlsx"
SOURCES = railroad.Sources.under()               # the data files, read through hartlib.railroad
DEVICE_MAP = devices.MASTER
NODES = SOURCES.lcos_nodes

LEVEL_NAME = {"1": "Staging", "2": "Main", "3": "Upper"}
DESIGN = ("2", "3")                               # main and upper: the rule's draft, shaded
SHADE = PatternFill("solid", fgColor="DDEBF7")    # light blue: every main and upper level row (owner, 2026-11-15)
PORT = re.compile(r"(OU|IN): (\d+) Ports: ([\d,]+)$")
GROUPS = re.compile(r"(OU|IN): (\d+) Ports: ([\d,]+)")      # every board's pins of a wiring text (a head may span two)
NODE_K = re.compile(r"^Node: (\d+) (Turnout|Signal|Sensor|Block): (\d+)")
LEGACY = re.compile(r"\bwas ([CDM]\d+)\b")        # a staging node's old ID, as lcos_nodes.csv's source notes it
NODE_ID = re.compile(r"^inventory v86: ([CDM]\d+)\b")    # a staging node's ID in the inventory (M1 main, D5 DCC)
NODE_TYPE = {"C": "Client", "M": "Main", "D": "DCC"}
SWITCHES = SOURCES.switches                          # staging's legs: a wired mast's place at its switch

NODE_COLUMNS = ["Node ID", "Legacy Node ID", "Address", "Location", "Type", "DNOU8", "DNIN8", "12V Boards",
                "5V Boards", "Num 12V", "12V Used", "12V Free", "Num Turnouts", "Turnout Output Ports",
                "Turnout Names", "Num IN", "Input Used", "Input Free", "Num Buttons", "Num Sensors", "Button Devices",
                "Turnout Feedback Devices", "Num 5V", "5V Used", "5V Free", "Num Signal LEDs", "Signal LED Devices",
                "Signal Names", "DNCTA", "BS Devices", "Num Blocks", "Block Section Names"]
OU_COLUMNS = ["Output Port ID", "Parent Node ID", "Board Location", "Output Channel (1-8)", "Connected Device",
              "Device Type", "Voltage Rail (12V/5V)", "Notes"]
IN_COLUMNS = ["Input Port ID", "Parent Node ID", "Board Location", "Input Channel (1-8)", "Connected Device",
              "Device Type (Sensor/Switch/etc.)", "Notes"]
TURNOUT_COLUMNS = ["Turnout", "Parent Node", "Location/Area", "Switch Elements", "Button", "Feedback N", "Feedback R",
                   "Entry Signal", "Entry Signal R Port", "Entry Signal Y Port", "Entry Signal G Port",
                   "Normal Exit Signal", "Normal Exit R Port", "Normal Exit Y Port", "Normal Exit G Port",
                   "Reverse Exit Signal", "Reverse Exit R Port", "Reverse Exit Y Port", "Reverse Exit G Port",
                   "JMRI Turnout"]        # the turnout's own name: a crossover's two half rows carry the same one
BLOCK_COLUMNS = ["Port ID", "Node ID", "B Device ID", "B Number (1-2)", "Block Section Name",
                 "Connected Track Segment", "Block Location", "Power District", "Notes"]
DIGICON_COLUMNS = ["port_id", "parent_node_id", "mqtt_node", "board_location", "signal_index", "packed",
                   "system_name", "user_name", "mast_user_name", "disc_role", "head_role", "lamp_color", "topic",
                   "notes"]


def read_device_rows(path: Path = DEVICE_MAP) -> list[dict]:
    """Every level's rows of the master in the device-map form (hartlib.devices.device_map_lines), values stripped:
    the ports are read from each row's wiring text (its comment)."""
    return [{c: v.strip() for c, v in r.items()} for _line, r in devices.device_map_lines(("1", "2", "3"), path)]


def read_node_rows(path: Path = NODES) -> list[dict]:
    """Every row of the node file as text cells (level, area, node, source), read by hartlib.railroad.read_lcos_nodes,
    which stops (FactsError) on a level that is not 1, 2 or 3, a node given twice or a row with no area."""
    return [{"level": str(n.level), "area": n.area, "node": str(n.node), "source": n.source}
            for n in railroad.read_lcos_nodes(path)]


def natural(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


class Node:
    def __init__(self, num: int, level: str, location: str, legacy: str = "", ident: str = ""):
        self.num, self.id, self.level, self.location = num, ident or f"C{num}", level, location
        self.type = NODE_TYPE[self.id[0]]
        self.legacy = legacy or (self.id if level == "1" else "")
        self.ou = defaultdict(dict)       # board -> {pin: (device, type, rail, notes)}
        self.inp = defaultdict(dict)      # board -> {pin: (device, type, notes)}
        self.turnouts, self.feedback, self.heads, self.masts, self.blocks = [], [], [], [], []
        self.buttons = []                 # (name, port id): fascia buttons, from wiring.csv

    @property
    def design(self) -> bool:
        return self.level in DESIGN

    @property
    def twelve(self) -> set[int]:
        """The OU boards that carry turnouts (12V), on every level from where the turnouts are."""
        return {int(p.split("-OU")[1].split("-")[0]) for _t, ps, _r in self.turnouts for p in ps}


def spare_rows(path: Path | None = None) -> list[dict]:
    """Staging's spare detector inputs (wiring.csv detectors with no block) as occupancy rows: they have a sensor in
    JMRI but no block, and the device-map form leaves them out (hartlib.devices.OUT_OF_MAPS)."""
    return [dict(layer="occupancy", role="spare", user_name=f"unused {w.input}", node=str(w.node),
                 system_name=w.address, comment=w.wiring_text, dcc="", trial_name="", cp="")
            for w in wiring.read(path) if w.kind == "detector" and w.level == 1 and not w.device]


def lamp_names(wired: list[dict]) -> dict[str, str]:
    """{port id: lamp name} of the Digicon heads as wired (hartlib.wiring.digicon_rows: "Head 6LB R", "Head 24RA T R"), so DNOU8 and the
    DigiconSignals sheet name a staging lamp the same."""
    return {r["port_id"]: r["user_name"] for r in wired if r.get("port_id") and r.get("user_name")}


def gather(rows, node_rows, lamps: dict | None = None) -> dict[int, Node]:
    """{node number: Node} of every node in lcos_nodes.csv, with every port the master gives (`rows`, with
    spare_rows). InventoryError on a row on a node the node file does not list."""
    nodes = {}
    for r in node_rows:
        source = r.get("source") or ""
        legacy, ident = LEGACY.search(source), NODE_ID.match(source)
        nodes[int(r["node"])] = Node(int(r["node"]), r["level"], f"{r['area']} - {LEVEL_NAME[r['level']]}",
                                     legacy.group(1) if legacy else "", ident.group(1) if ident else "")

    def get(num: int) -> Node:
        if num not in nodes:
            raise InventoryError(f"node {num} is in {DEVICE_MAP.name} but not in {NODES.name}")
        return nodes[num]

    for r in rows:
        if not r["node"] or r["system_name"].startswith("MTT"):
            continue
        n = get(int(r["node"]))
        m = PORT.search(r["comment"])
        if r["layer"] in ("turnout", "fb") and not m or r["layer"] == "occupancy" and not NODE_K.match(r["comment"]):
            raise FactsError(f"{DEVICE_MAP.name}: {r['layer']} {r['user_name']} is on node {r['node']} but its wiring "
                             f"{r['comment']!r} gives no port")
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
            if not m:
                continue                              # a mast's node with no head wiring of its own
            spread = [(int(b), int(p)) for _k, b, ps in GROUPS.findall(r["comment"]) for p in ps.split(",")]
            kind = "Signal LED" if n.design else "Searchlight Signal Head"     # staging's are Digicon searchlights
            for (board, pin), lamp in zip(spread, "RYG"):   # a head's pins may span two boards
                name = (lamps or {}).get(f"{n.id}-OU{board}-{pin}") if not n.design else None
                n.ou[board][pin] = (name or f"{r['user_name']} {lamp}", kind, "5V",
                                    f"{r['system_name']}; STOP/APPROACH/CLEAR; lamp {lamp}")
            n.heads.append((r["user_name"], spread))
        elif r["layer"] == "mast":
            n.masts.append(r["user_name"].removeprefix("Mast "))
        elif r["layer"] == "occupancy":
            k = int(NODE_K.match(r["comment"]).group(3)) - 1      # "Block: 1" is UID 0
            n.blocks.append((k, r))
    return nodes


CAL = "Calibration Relay"
CAL_NOTE = "resets the DCC power so the node's block detectors calibrate"


def calibration(nodes: dict[int, Node]) -> None:
    """Every node with block detectors has a calibration relay port (owner, 2026-11-21). Staging's are wiring.csv's
    rows (add_local); a main or upper node without one gets the rule's, pin 8 of its first 5V board. FactsError on a
    staging node with detectors and no calibration row, or a rule pin something else holds."""
    for n in nodes.values():
        if not n.blocks or any(v[1] == CAL for b in n.ou.values() for v in b.values()):
            continue
        if not n.design:
            raise FactsError(f"node {n.num} has block detectors but no calibration relay port in "
                             f"{wiring.PATH.name}: add a calibration row")
        first5 = next(b for b in range(1, 6) if b not in n.twelve)
        if 8 in n.ou[first5]:
            raise FactsError(f"node {n.num}: OU{first5}-8 is the calibration relay's port by the rule, but "
                             f"{n.ou[first5][8][0]} is on it")
        n.ou[first5][8] = (f"{n.id} calibration relay", CAL, "5V", f"{CAL_NOTE} (the rule: first 5V OU pin 8)")


def add_local(nodes: dict[int, Node], path: Path | None = None) -> None:
    """The fascia buttons, relays and calibration relays of wiring.csv (no JMRI device) on their nodes' boards."""
    for w in wiring.read(path):
        if w.kind not in wiring.LOCAL:
            continue
        if w.node not in nodes:
            raise FactsError(f"{wiring.PATH.name} line {w.line}: node {w.node} is not in {NODES.name}")
        n, board, pin = nodes[w.node], int(w.board[2:]), w.ports[0]
        taken = (n.inp if w.kind == "button" else n.ou)[board].get(pin)
        if taken:
            raise FactsError(f"{wiring.PATH.name} line {w.line}: {w.device} is on {n.id}-{w.board}-{pin}, which "
                             f"{taken[0]} has")
        planned = "planned, not connected" if w.status == "planned" and w.kind != "calibration" else ""
        if w.kind == "button":
            n.inp[board][pin] = (w.device, "Button", "; ".join(x for x in (planned, w.notes) if x) or None)
            n.buttons.append((w.device + (" (planned)" if planned else ""),
                              f"{n.id}-IN{board}-{pin}" + (" (planned)" if planned else "")))
        elif w.kind == "calibration":
            n.ou[board][pin] = (w.device, CAL, "5V", "; ".join(x for x in (CAL_NOTE, w.notes,
                                                                          "reserved" if w.status == "planned" else "")
                                                               if x))
        else:
            n.ou[board][pin] = (w.device, "Relay", "5V", "; ".join(x for x in (planned, w.notes) if x) or None)


def rail(n: Node, board: int) -> str:
    """The rail of an empty pin: 12V on a board with turnouts; else on main and upper 5V (the rule), on staging the
    rail of what the board carries."""
    if board in n.twelve:
        return "12V"
    if n.design:
        return "5V"
    used = {v[2] for v in n.ou[board].values()}
    return used.pop() if len(used) == 1 else ""


def block_name(occ: dict, by_name: dict) -> str | None:
    """The JMRI block an occupancy row detects: the first of its `blocks` column, never read from its name (hand-off
    row 8); None for a spare input. InventoryError when the row names no block, or one with no block row."""
    if devices.row_role(occ, devices.index(DEVICE_MAP).where(occ)) == "spare":
        return None
    name = next((b.strip() for b in occ.get("blocks", "").split(devices.LIST) if b.strip()), "")
    if not name:
        raise InventoryError(f"{DEVICE_MAP.name}: occupancy {occ['user_name']} names no block in its blocks column")
    if name not in by_name:
        raise InventoryError(f"{DEVICE_MAP.name}: occupancy {occ['user_name']} detects {name}, which has no block row")
    return name


def sheet(wb, title: str, columns: list[str], at: int | None = None):
    ws = wb.create_sheet(title, at) if at is not None else wb.create_sheet(title)
    ws.append(columns)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    return ws


def append(ws, values, shade: bool) -> None:
    """Add a row; a main or upper level row is shaded so it stands apart from the staging rows."""
    ws.append(values)
    if shade:
        for cell in ws[ws.max_row][:len(values)]:  # every cell the row writes, one per header column
            cell.fill = SHADE


def nodes_sheet(wb, nodes: dict[int, Node], by_name: dict) -> None:
    ws = sheet(wb, "Nodes", NODE_COLUMNS)
    for num in sorted(nodes, key=lambda k: (nodes[k].level, k)):
        n = nodes[num]
        boards = sorted(n.ou)
        twelve = [b for b in boards if b in n.twelve]
        five = [b for b in boards if b not in twelve]
        used5 = sum(len(n.ou[b]) for b in five)
        bdev = sorted({f"{n.id}-B{k // 2 + 1}" for k, _ in n.blocks}, key=natural)
        vals = {
            "Node ID": n.id, "Legacy Node ID": n.legacy or None, "Address": num, "Location": n.location,
            "Type": n.type,
            "DNOU8": ", ".join(f"OU{b}" for b in boards) or None,
            "DNIN8": ", ".join(f"IN{b}" for b in sorted(n.inp)) or None,
            "12V Boards": len(twelve), "5V Boards": len(five), "Num 12V": 8 * len(twelve),
            "12V Used": 2 * len(n.turnouts), "12V Free": 8 * len(twelve) - 2 * len(n.turnouts),
            "Num Turnouts": len(n.turnouts),
            "Turnout Output Ports": ", ".join(p for _, ps, _ in n.turnouts for p in ps) or None,
            "Turnout Names": ", ".join(t for t, _, _ in n.turnouts) or None,
            "Num IN": 8 * len(n.inp), "Input Used": len(n.feedback) + len(n.buttons),
            "Input Free": 8 * len(n.inp) - len(n.feedback) - len(n.buttons),
            "Num Buttons": len(n.buttons), "Num Sensors": len(n.feedback),
            "Button Devices": ", ".join(b for b, _ in n.buttons) or None,
            "Turnout Feedback Devices": ", ".join(f.removeprefix("FB ") + " FB" for f, _ in n.feedback) or None,
            "Num 5V": 8 * len(five), "5V Used": used5, "5V Free": 8 * len(five) - used5,
            "Num Signal LEDs": sum(len(p) for _, p in n.heads), "Signal LED Devices": len(n.heads),
            "Signal Names": ", ".join(sorted(n.masts, key=natural)) or None, "DNCTA": None,
            "BS Devices": ", ".join(bdev) or None, "Num Blocks": len(n.blocks),
            "Block Section Names": ", ".join(b for _, r in sorted(n.blocks, key=lambda b: b[0])
                                             if (b := block_name(r, by_name))) or None,
        }
        append(ws, [vals.get(name) for name in NODE_COLUMNS], n.design)


def port_sheets(wb, nodes: dict[int, Node]) -> None:
    ou = sheet(wb, "DNOU8", OU_COLUMNS)
    inp = sheet(wb, "DNIN8", IN_COLUMNS)
    for num in sorted(nodes, key=lambda k: (nodes[k].level, k)):
        n = nodes[num]
        for board in sorted(n.ou):
            for pin in range(1, 9):
                dev, kind, volts, notes = n.ou[board].get(pin, (None, None, rail(n, board) or None, None))
                append(ou, [f"{n.id}-OU{board}-{pin}", n.id, n.location, pin, dev, kind, volts, notes], n.design)
        for board in sorted(n.inp):
            for pin in range(1, 9):
                dev, kind, notes = n.inp[board].get(pin, (None, None, None))
                append(inp, [f"{n.id}-IN{board}-{pin}", n.id, n.location, pin, dev, kind, notes], n.design)


def staging_legs() -> dict[str, list]:
    """Staging's switches.csv rows by switch number: a crossover (7, 23, 35) has one row per OS block."""
    legs: dict[str, list] = {}
    for r in railroad.read_switch_rows(SWITCHES):
        if r.level == 1:
            legs.setdefault(str(r.switch), []).append(r)
    return legs


def mast_role(rows: list, facing: str) -> str:
    """The leg a mast faces, against every row of its switch (each OS block's closed and thrown legs)."""
    if not rows:
        raise FactsError(f"no switches.csv rows to place a mast facing {facing!r} against")
    if any(facing == r.closed_leg for r in rows):
        return "Normal Exit"
    return "Reverse Exit" if any(facing == r.thrown_leg for r in rows) else "Entry"


def mast_half(rows: list, sw: str, mast: str, protects: str, where: str = devices.MASTER_FILE) -> str | None:
    """The OS block (half) of switch sw that a staging mast belongs to: the one it faces into (its protects column).
    A switch with one OS block has no halves (None). A crossover mast that protects none of its halves stops."""
    if len(rows) < 2:
        return None
    for r in rows:
        if r.os_block == protects:
            return r.os_block
    raise FactsError(f"{where}: Mast {mast} on crossover Switch {sw} protects {protects!r}, which is none of its OS blocks "
                     f"({', '.join(r.os_block for r in rows)}) in switches.csv")


def take_role(place: dict, sw: str, role: str, mast: str, ports: list, half: str | None = None,
              design: bool = False) -> None:
    """Put a wired mast in its role slot of its switch (of its half, on a crossover); two in one slot stop. Slots are
    per level kind (staging, or main and upper), so a main or upper mast never lands on a staging switch's row."""
    slots = place.setdefault((design, sw, half), {})
    held = slots.get(role)
    if held:
        where = f"Switch {sw}" + (f" ({half})" if half else "")
        raise FactsError(f"{where}: masts {held[0]} and {mast} are both wired as its {role} signal; "
                         f"TurnoutSummary has one {role} slot per {'crossover half' if half else 'switch'}")
    slots[role] = (mast, ports)


def turnout_sheet(wb, nodes: dict[int, Node], by_name: dict) -> None:
    """One row per turnout, but a staging crossover (Switch 7, 23, 35: one turnout, two OS blocks) has one row per
    half, each with its own entry and exit slots (owner, 2026-11-21); the turnout, DCC and button facts repeat."""
    ws = sheet(wb, "TurnoutSummary", TURNOUT_COLUMNS)
    fb = {name: port for n in nodes.values() for name, port in n.feedback}
    button = {name.removesuffix(" (planned)").removesuffix(" BTN"): port for n in nodes.values()
              for name, port in n.buttons}
    legs = staging_legs()
    devices_index = devices.index(DEVICE_MAP)
    place: dict = {}        # (main or upper, switch, half or None) -> {"Entry" | "Normal Exit" | "Reverse Exit": (mast, its head's pins)}
    for n in nodes.values():
        for head, spread in n.heads:
            ports = [f"{n.id}-OU{board}-{p}" for board, p in spread]
            key = re.sub(r" (Top|Bottom)$", "", head.removeprefix("Head "))
            mast = by_name.get(f"Mast {key}", {})
            sw = mast.get("switch", "")
            if not n.design and sw in legs:                # staging: the leg it stands on (switches.csv)
                half = mast_half(legs[sw], sw, key, mast["protects"], devices_index.where(mast))
                mine = [r for r in legs[sw] if half in (None, r.os_block)]
                role = mast_role(mine, mast["facing"])
                if not head.endswith(" Bottom"):
                    take_role(place, sw, role, key, ports, half, n.design)
            elif head.endswith(" Top"):                  # main and upper: a two-head mast's top head is the entry
                place.setdefault((n.design, sw, None), {}).setdefault("Entry", (key, ports))
    for n in sorted(nodes.values(), key=lambda n: (n.level, n.num)):
        for name, _, r in n.turnouts:
            sw = name.removeprefix("Switch ")
            halves = [x.os_block for x in legs[sw]] if not n.design and len(legs.get(sw, ())) > 1 else [None]
            for half in halves:
                vals = {"Turnout": f"{name} ({half})" if half else name, "Parent Node": n.id,
                        "Location/Area": f"{r['cp']} ({n.location})" if r["cp"] else n.location,
                        "JMRI Turnout": name, "Switch Elements": r["trial_name"] or name, "Button": button.get(name),
                        "Feedback N": fb.get(f"FB {name} N"), "Feedback R": fb.get(f"FB {name} R")}
                for role, (mast, pins) in place.get((n.design, sw, half), {}).items():
                    cols = "Entry Signal" if role == "Entry" else role          # the sheet's column names
                    vals.update({f"{role} Signal": mast, f"{cols} R Port": pins[0], f"{cols} Y Port": pins[1],
                                 f"{cols} G Port": pins[2]})
                append(ws, [vals.get(c) for c in TURNOUT_COLUMNS], n.design)


def block_sheet(wb, nodes: dict[int, Node], by_name: dict) -> None:
    ws = sheet(wb, "BlockSensors", BLOCK_COLUMNS)
    for num in sorted(nodes, key=lambda k: (nodes[k].level, k)):
        n = nodes[num]
        for k, r in sorted(n.blocks, key=lambda b: b[0]):
            dev = f"{n.id}-B{k // 2 + 1}"
            blk = block_name(r, by_name)
            append(ws, [f"{dev}-{k % 2 + 1}", n.id, dev, k % 2 + 1, blk or "Unused",
                        (by_name[blk]["trial_name"] or None) if blk else None, n.location,
                        None, f"Block {num}-{k + 1} / {r['system_name']}"], n.design)   # districts: not mapped


def load_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def digicon_sheet(wb, wired: list[dict], heads: list[dict]) -> None:
    """The Digicon searchlight heads as wired (wiring.csv's heads, three pins per disc) and the mast plan
    (signal_head_plan.csv), first in the workbook as it always was."""
    ws = wb.create_sheet("DigiconSignals", 0)
    ws["A1"] = "HART Digicon searchlight heads (from jmri/layouts/hart/data/wiring.csv)"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:L1")
    for i, h in enumerate(DIGICON_COLUMNS, start=1):
        ws.cell(2, i, h).font = Font(bold=True)
    for r_i, row in enumerate(wired, start=3):
        for c_i, key in enumerate(DIGICON_COLUMNS, start=1):
            ws.cell(r_i, c_i, row.get(key))
    start = 3 + len(wired) + 2
    ws.cell(start, 1, "Masts (jmri/layouts/hart/output/signal_head_plan.csv)").font = Font(bold=True, size=12)
    m_headers = list(heads[0].keys()) if heads else []
    for i, h in enumerate(m_headers, start=1):
        ws.cell(start + 1, i, h).font = Font(bold=True)
    for r_i, row in enumerate(heads, start=start + 2):
        for c_i, key in enumerate(m_headers, start=1):
            ws.cell(r_i, c_i, row.get(key))
    for col in range(1, 13):
        ws.column_dimensions[get_column_letter(col)].width = 22


def workbook() -> Workbook:
    """The inventory workbook in memory, built from the wiring model (the device master, hartlib.wiring's wiring.csv,
    the node file and the head plan): v86 is this saved, and build_wiring_json.py and create_wiring_schematic_ppt.py
    read their sheets from it, not from the file."""
    rows = read_device_rows()
    by_name = {r["user_name"]: r for r in rows}
    wired = wiring.digicon_rows()
    nodes = gather(rows + spare_rows(), read_node_rows(), lamp_names(wired))
    add_local(nodes)
    calibration(nodes)
    wb = Workbook()
    wb.remove(wb.active)
    nodes_sheet(wb, nodes, by_name)
    port_sheets(wb, nodes)
    turnout_sheet(wb, nodes, by_name)
    block_sheet(wb, nodes, by_name)
    digicon_sheet(wb, wired, load_csv(paths.SIGNAL_HEAD_PLAN))
    return wb


def build(dest: Path) -> None:
    workbook().save(dest)


def values(path: Path) -> dict:
    """Every cell's value and fill colour, per sheet: the shading is part of what --check compares."""
    wb = load_workbook(path, data_only=True)
    return {ws.title: [[(c.value, (c.fill.fill_type, c.fill.fgColor.rgb) if c.fill and c.fill.fill_type else None)
                        for c in row]
                       for row in ws.iter_rows()] for ws in wb.worksheets}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if v86 differs from what the sources give")
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
    except InventoryError as exc:   # a row the master and the node file disagree on: exit 1 with the bare message
        raise SystemExit(str(exc)) from exc
    except FactsError as exc:
        print(f"{Path(__file__).name}: {exc}", file=sys.stderr)
        return 2
    print(f"{OUT.name} is current" if same else f"{OUT.name} is stale: run {Path(__file__).name}")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
