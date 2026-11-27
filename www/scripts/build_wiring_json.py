#!/usr/bin/env python3
"""Build the public wiring viewer data (behind/wiring.html) from the wiring model.

Reads the LCOS inventory's sheets as tools/wiring/write_inventory.py builds them in memory from the wiring model
(the device master, hartlib.wiring's wiring.csv, lcos_nodes.csv and signal_head_plan.csv), the same sheets it saves
as LCOS_Layout_Inventory_v86.xlsx. The workbook file is an output only: this script never opens it (ADR-039). It
writes:

  data/wiring-inventory.json  nodes with DNOU8 / DNIN8 / block-detector port maps,
                              signal heads with their R/Y/G pins, turnouts, block sensors

The JSON is not committed (ADR-036): the site build and the local preview build it with view() (site_views.py,
make site-data), and --check builds it in memory and runs its checks (problems()). To write it by hand:

  python3 www/scripts/build_wiring_json.py           # www/data/wiring-inventory.json (--out-dir for another folder)
  python3 www/scripts/build_wiring_json.py --check   # build in memory, exit 1 when it cannot be built or fails a check

Data problems found along the way are printed as warnings; they do not stop the build. Network details (IP
addresses, hostnames, serial ports, machine paths, credentials) are scrubbed from every cell before it reaches the
JSON, and problems() fails a built JSON that still holds one.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, OrderedDict, defaultdict
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple, TypedDict

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

PORTAL = Path(__file__).resolve().parents[1]
ROOT = PORTAL.parent
OUT_INV = PORTAL / "data" / "wiring-inventory.json"
OUT_REL = OUT_INV.relative_to(PORTAL).as_posix()  # its path in the site (site_views.VIEWS)
sys.path.insert(0, str(ROOT / "tools" / "wiring"))
import write_inventory  # noqa: E402  (the wiring model's inventory sheets; it puts hartlib on the path)

class WiringDataError(Exception):
    """The viewer data cannot be built from the wiring model, or fails a check; the message says why."""


# —— Cell cleanup ————————————————————————————————————————————————

# Anything that looks like a network detail, a machine path or a secret. A matching cell
# is dropped whole rather than half-redacted.
UNSAFE = [
    re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),  # IPv4
    re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I),  # MAC
    re.compile(r"\b[\w-]+\.(?:local|lan|home|internal)\b", re.I),  # mDNS / LAN hosts
    re.compile(r"\b(?:mqtt|tcp|ws|wss|http|https)://", re.I),
    re.compile(r"\bCOM\d+\b"),
    re.compile(r"/dev/(?:tty|cu)\S*"),
    re.compile(r"(?:/Users/|/home/|[A-Z]:\\)"),
    re.compile(r"\b(?:password|passwd|pwd|secret|token|api[_ -]?key|ssid|wi-?fi|psk|credential)s?\b", re.I),
    re.compile(r"\bbroker\b", re.I),
]


def clean(v: object, scrubbed: list[str]) -> str:
    """A cell as one line of text; a cell that looks like a network detail or a secret is dropped whole and noted in
    scrubbed."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (dt.datetime, dt.date)):
        v = v.isoformat()[:10]
    s = re.sub(r"\s+", " ", str(v)).strip()
    for pat in UNSAFE:
        if pat.search(s):
            scrubbed.append(s)
            return ""
    return s


def sheet_rows(ws: Worksheet, scrubbed: list[str]) -> list[list[str]]:
    """Every row as cleaned strings, empty rows dropped."""
    out = []
    for row in ws.iter_rows(values_only=True):
        cells = [clean(c, scrubbed) for c in row]
        if any(cells):
            out.append(cells)
    return out


def table(rows: list[list[str]], header_idx: int, stop: Callable[[list[str]], bool] | None = None) -> list[dict[str, str]]:
    """Rows under header_idx as dicts keyed by header, trailing empty columns dropped."""
    header = rows[header_idx]
    width = max((i + 1 for i, h in enumerate(header) if h), default=0)
    header = header[:width]
    out = []
    for r in rows[header_idx + 1 :]:
        if stop and stop(r):
            break
        d = {header[i]: (r[i] if i < len(r) else "") for i in range(width) if header[i]}
        if any(d.values()):
            out.append(d)
    return out


def strip_history(note: str) -> str:
    """Drop rename history ("was S3-6 G", "renamed for linear6") that only confuses a reader.

    The inventory's "was" notes disagree with each other (DNOU8 and DigiconSignals give
    different old IDs for the same pin), so none of them are published.
    """
    note = re.sub(r"\s*\([^)]*\bwas\b[^)]*\)", "", note)
    parts = re.split(r"\s*[;|]\s*", note)
    keep = [p for p in parts if p and not re.match(r"(?i)was\b", p) and "renamed for" not in p.lower()]
    return "; ".join(keep).strip()


def version_of(path: Path) -> str:
    m = re.search(r"_v(\d+)", path.stem)
    return f"v{m.group(1)}" if m else path.stem


def split_list(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


PORT_RE = re.compile(r"^(?P<node>[A-Z]+\d+)-(?P<board>(?:OU|IN|B)\d+)-(?P<pin>\d+)$")
HEAD_RE = re.compile(r"^Head (?P<head>.+?) (?P<color>[RYG])$")


def parse_port(pid: str) -> tuple[str, str, int] | None:
    m = PORT_RE.match(pid)
    if not m:
        return None
    return m.group("node"), m.group("board"), int(m.group("pin"))


def board_sort(b: str) -> tuple[str, int]:
    m = re.match(r"([A-Z]+)(\d+)", b)
    return (m.group(1), int(m.group(2))) if m else (b, 0)


def node_sort(n: str) -> tuple[int, int]:
    m = re.match(r"([A-Z]+)(\d+)", n)
    return ({"M": 0, "C": 1, "D": 2}.get(m.group(1), 3), int(m.group(2))) if m else (9, 0)


# —— Inventory ——————————————————————————————————————————————————

class OutKind(NamedTuple):
    """What a DNOU8 pin drives; color and head are set for a lamp only ("Head 12 R": head "12", color "R")."""
    kind: str
    color: str = ""
    head: str = ""


def out_kind(device: str, dtype: str) -> OutKind:
    """What a DNOU8 pin drives, from its device name and device type."""
    m = HEAD_RE.match(device)
    if m:
        return OutKind("lamp", m.group("color"), m.group("head"))
    t = dtype.lower()
    if "turnout" in t:
        return OutKind("motor")
    if "cal" in t:
        return OutKind("cal")
    if "relay" in t:
        return OutKind("relay")
    if "reserved" in t or device.lower() == "reserved":
        return OutKind("reserved")
    if not device:
        return OutKind("spare")
    return OutKind("other")


def in_kind(device: str, dtype: str) -> str:
    t = dtype.lower()
    if "feedback" in t:
        return "feedback"
    if "button" in t:
        return "button"
    if not device:
        return "spare"
    return "other"


def pick_location(locs: list[str]) -> str:
    """The board's place: the most common specific location among its used pins."""
    locs = [l for l in locs if l]
    if not locs:
        return ""
    specific = [l for l in locs if "(" in l]
    return Counter(specific or locs).most_common(1)[0][0]


class BuildLog:
    """What one build found along the way: data warnings, and the cells clean() dropped. A plain class, not a
    dataclass: other scripts load this module by path without registering it in sys.modules."""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.scrubbed: list[str] = []

    def __eq__(self, other: object) -> bool:
        return isinstance(other, BuildLog) and (self.warnings, self.scrubbed) == (other.warnings, other.scrubbed)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


class Built(NamedTuple):
    """The viewer data of one build, with what that build reported."""
    data: dict
    log: BuildLog


Row = dict[str, str]                   # one sheet row, keyed by its header


class Turnout(TypedDict):
    """One TurnoutSummary row as the viewer shows it. turnout is the row's label, name the JMRI turnout; a crossover
    half's label is "<name> (<OS block>)" and half is that OS block. motorN and motorR are DNOU8 port ids, button,
    fbN and fbR DNIN8 port ids, signals the entry, normal and reverse signal names the row gives."""
    turnout: str
    name: str
    half: str
    node: str
    area: str
    elements: str
    motorN: str
    motorR: str
    button: str
    fbN: str
    fbR: str
    signals: dict[str, str]


TURNOUT_SIGNALS = (("entry", "Entry Signal"), ("normal", "Normal Exit Signal"), ("reverse", "Reverse Exit Signal"))
TURNOUT_INPUTS = (("button", "BTN"), ("fbN", "N FB"), ("fbR", "R FB"))  # field, the DNIN8 device name's suffix
BoardKey = tuple[str, str]             # (node id, board), such as ("C13", "OU2")
NEEDED_SHEETS = ("Nodes", "DNOU8", "DNIN8", "TurnoutSummary", "BlockSensors", "DigiconSignals")
NOT_WIRED = ("spare", "reserved", "cal")  # output kinds that are not a device


def turnout_name(r: Row, label: str) -> str:
    """The JMRI turnout of a TurnoutSummary row: its own column, which a crossover's half rows (labelled by OS block)
    share. The older workbook (v85) has no such column and one row per turnout, so its label is the name."""
    jmri = r["JMRI Turnout"] if "JMRI Turnout" in r else label
    if not jmri:
        raise WiringDataError(f"TurnoutSummary: row {label!r} has no JMRI Turnout; rebuild v86 with write_inventory.py")
    return jmri


def crossover_half(label: str, jmri: str) -> str:
    """The OS block of a crossover half's row label "<jmri> (<OS block>)"; "" when the label is the turnout itself."""
    if label == jmri:
        return ""
    if not (label.startswith(jmri + " (") and label.endswith(")")):
        raise WiringDataError(f"TurnoutSummary: row {label!r} is not {jmri!r} or {jmri!r} (<OS block>)")
    return label[len(jmri) + 2:-1]


def board_order(item: tuple[BoardKey, dict]) -> tuple:
    (nid, board), _ = item
    return node_sort(nid), board_sort(board)


class Inventory:
    """One pass over the inventory sheets. Each read_* step fills a part of the viewer data and warns through log;
    the cross-checks run after the parts they compare are read."""

    def __init__(self, sheets: dict[str, list[list[str]]], source: str, log: BuildLog) -> None:
        self.sheets, self.source, self.log = sheets, source, log
        self.nodes: OrderedDict[str, dict] = OrderedDict()
        self.out_boards: dict[BoardKey, dict] = {}
        self.out_pins: dict[str, dict] = {}            # port id -> its DNOU8 pin record
        self.device_ports: dict[str, list[str]] = {}   # DNOU8 device -> its port ids
        self.heads: OrderedDict[str, dict] = OrderedDict()
        self.masts: list[dict] = []
        self.blocks: list[dict] = []
        self.turnouts: list[Turnout] = []

    def node_for(self, nid: str, sheet: str, pid: str) -> dict:
        """The node nid, added bare (with a warning) when the Nodes sheet does not list it."""
        if nid not in self.nodes:
            self.log.warn(f"{sheet}: {pid} names node {nid}, which is not on the Nodes sheet")
            self.nodes[nid] = {"id": nid, "address": "", "location": "", "type": "",
                               "turnouts": [], "signals": [], "blockNames": [], "summary": {},
                               "outputs": [], "inputs": [], "detectors": [], "declared": {}}
        return self.nodes[nid]

    def read_nodes(self) -> None:
        for r in table(self.sheets["Nodes"], 0):
            nid = r.get("Node ID", "")
            if not nid:
                continue
            self.nodes[nid] = {
                "id": nid,
                "address": r.get("Address", ""),
                "location": r.get("Location", ""),
                "type": r.get("Type", ""),
                "turnouts": split_list(r.get("Turnout Names", "")),
                "signals": split_list(r.get("Signal Names", "")),
                "blockNames": split_list(r.get("Block Section Names", "")),
                "summary": {
                    "outputs12v": {"used": r.get("12V Used", ""), "free": r.get("12V Free", "")},
                    "outputs5v": {"used": r.get("5V Used", ""), "free": r.get("5V Free", "")},
                    "inputs": {"used": r.get("Input Used", ""), "free": r.get("Input Free", "")},
                },
                "outputs": [],
                "inputs": [],
                "detectors": [],
                "declared": {
                    "DNOU8": split_list(r.get("DNOU8", "")),
                    "DNIN8": split_list(r.get("DNIN8", "")),
                    "BS": split_list(r.get("BS Devices", "")),
                },
            }

    # —— DNOU8 and DNIN8: one board sheet each ——

    def pin_rows(self, sheet: str, port_col: str, check_parent: bool) -> Iterator[tuple[str, str, int, str, Row]]:
        """(node, board, pin, port id, row) for each readable, first-listed row of a board sheet."""
        seen: set[str] = set()
        for r in table(self.sheets[sheet], 0):
            pid = r.get(port_col, "")
            p = parse_port(pid)
            if not p:
                self.log.warn(f"{sheet}: unreadable port id {pid!r}")
                continue
            nid, board, pin = p
            if check_parent and r.get("Parent Node ID") and r["Parent Node ID"] != nid:
                self.log.warn(f"{sheet}: {pid} has Parent Node {r['Parent Node ID']}")
            if pid in seen:
                self.log.warn(f"{sheet}: port {pid} listed twice")
                continue
            seen.add(pid)
            yield nid, board, pin, pid, r

    def sorted_boards(self, sheet: str, boards: dict[BoardKey, dict], ports: dict[str, list[str]],
                      where: str) -> Iterator[tuple[str, str, dict, list[dict]]]:
        """Warns of a device on more than one port, then gives (node, board, the board's record, its pins by number) in
        node and board order."""
        for dev, on in ports.items():
            if len(on) > 1:
                self.log.warn(f"{sheet}: {dev!r} is on more than one {where}: {', '.join(on)}")
        for (nid, board), b in sorted(boards.items(), key=board_order):
            pins = sorted(b["pins"], key=lambda x: x["pin"])
            yield nid, board, b, pins

    def missing_pins(self, sheet: str, nid: str, board: str, pins: list[dict]) -> None:
        have = {x["pin"] for x in pins}
        missing = [i for i in range(1, 9) if i not in have]
        if missing:
            self.log.warn(f"{sheet}: {nid}-{board} has no row for pin(s) {missing}")

    def read_outputs(self) -> None:
        ports: dict[str, list[str]] = defaultdict(list)
        for nid, board, pin, pid, r in self.pin_rows("DNOU8", "Output Port ID", check_parent=True):
            device = r.get("Connected Device", "")
            kind, color, head = out_kind(device, r.get("Device Type", ""))
            b = self.out_boards.setdefault((nid, board), {"board": board, "rail": Counter(), "pins": [], "_locs": []})
            if r.get("Voltage Rail (12V/5V)"):
                b["rail"][r["Voltage Rail (12V/5V)"]] += 1
            rec = {"pin": pin, "port": pid, "device": device, "kind": kind}
            if color:
                rec["color"] = color
                rec["head"] = head
            if r.get("Board Location"):
                rec["place"] = r["Board Location"]
                if kind not in NOT_WIRED:
                    b["_locs"].append(r["Board Location"])
            if r.get("Notes"):
                if kind == "lamp":
                    rec["_note"] = r["Notes"]  # route info is lifted onto the head; not published per pin
                elif strip_history(r["Notes"]):
                    rec["note"] = strip_history(r["Notes"])
            b["pins"].append(rec)
            self.out_pins[pid] = rec
            if device and kind not in NOT_WIRED:
                ports[device].append(pid)
        self.device_ports = ports
        for nid, board, b, pins in self.sorted_boards("DNOU8", self.out_boards, ports, "pin"):
            rails = list(b["rail"])
            if len(rails) > 1:
                self.log.warn(f"DNOU8: {nid}-{board} mixes rails {rails}")
            self.missing_pins("DNOU8", nid, board, pins)
            self.node_for(nid, "DNOU8", f"{nid}-{board}")["outputs"].append({
                "board": board,
                "rail": b["rail"].most_common(1)[0][0] if b["rail"] else "",
                "place": pick_location(b["_locs"]),
                "pins": pins,
            })

    def read_inputs(self) -> None:
        boards: dict[BoardKey, dict] = {}
        ports: dict[str, list[str]] = defaultdict(list)
        for nid, board, pin, pid, r in self.pin_rows("DNIN8", "Input Port ID", check_parent=False):
            device = r.get("Connected Device", "")
            kind = in_kind(device, r.get("Device Type (Sensor/Switch/etc.)", ""))
            rec = {"pin": pin, "port": pid, "device": device, "kind": kind}
            if r.get("Board Location"):
                rec["place"] = r["Board Location"]
            if strip_history(r.get("Notes", "")):
                rec["note"] = strip_history(r["Notes"])
            b = boards.setdefault((nid, board), {"board": board, "pins": [], "_locs": []})
            b["pins"].append(rec)
            if device:
                b["_locs"].append(r.get("Board Location", ""))
                ports[device].append(pid)
        for nid, board, b, pins in self.sorted_boards("DNIN8", boards, ports, "input"):
            self.missing_pins("DNIN8", nid, board, pins)
            self.node_for(nid, "DNIN8", f"{nid}-{board}")["inputs"].append(
                {"board": board, "place": pick_location(b["_locs"]), "pins": pins})

    def read_blocks(self) -> None:
        det: dict[tuple[str, str], list] = defaultdict(list)
        seen: set[str] = set()
        for r in table(self.sheets["BlockSensors"], 0):
            pid = r.get("Port ID", "")
            nid = r.get("Node ID", "") or (pid.split("-")[0] if pid else "")
            if pid in seen:
                self.log.warn(f"BlockSensors: {pid} listed twice")
                continue
            seen.add(pid)
            rec = {
                "port": pid,
                "node": nid,
                "detector": r.get("B Device ID", ""),
                "channel": r.get("B Number (1-2)", ""),
                "block": r.get("Block Section Name", ""),
                "track": r.get("Connected Track Segment", ""),
                "area": r.get("Block Location", ""),
                "district": r.get("Power District", ""),
                "note": strip_history(r.get("Notes", "")),
            }
            if not rec["block"]:
                self.log.warn(f"BlockSensors: {pid} has no block name")
            self.blocks.append(rec)
            det[(nid, rec["detector"])].append(rec)
        for (nid, d), chans in sorted(det.items(), key=lambda kv: (node_sort(kv[0][0]), kv[0][1])):
            self.node_for(nid, "BlockSensors", d)["detectors"].append({
                "detector": d,
                "channels": [{"channel": c["channel"], "port": c["port"], "block": c["block"]} for c in
                             sorted(chans, key=lambda c: str(c["channel"]))],
            })

    # —— Signal heads: Digicon searchlights (DigiconSignals, lower deck) + RGB LED heads (DNOU8, upper deck) ——

    def digicon_tables(self) -> tuple[list[Row], list[Row]]:
        """The DigiconSignals sheet's port rows and mast rows (two tables, one under the other)."""
        rows = self.sheets["DigiconSignals"]
        hdr = next((i for i, r in enumerate(rows) if r and r[0] == "port_id"), None)
        if hdr is None:
            raise WiringDataError(f"{self.source}: the DigiconSignals sheet has no port_id header row")
        mast_hdr = next((i for i, r in enumerate(rows) if r and r[0] == "mast_user_name"), None)
        port_rows = table(rows[: (mast_hdr - 1) if mast_hdr else None], hdr)
        return port_rows, (table(rows, mast_hdr) if mast_hdr else [])

    def read_digicon_heads(self, port_rows: list[Row]) -> None:
        for r in port_rows:
            m = HEAD_RE.match(r.get("user_name", ""))
            if not m:
                continue
            head = m.group("head")
            color = r.get("lamp_color") or m.group("color")
            mast = r.get("mast_user_name", "").replace("Mast ", "")
            h = self.heads.setdefault(head, {
                "head": head, "mast": mast, "disc": r.get("disc_role", ""),
                "node": r.get("parent_node_id", ""), "place": r.get("board_location", ""),
                "packed": r.get("system_name", ""), "type": "Digicon searchlight", "lamps": {},
            })
            if color in h["lamps"]:
                self.log.warn(f"DigiconSignals: {head} lamp {color} on both {h['lamps'][color]} and {r['port_id']}")
            h["lamps"][color] = r.get("port_id", "")
            dn = self.out_pins.get(r.get("port_id", ""))
            if not dn:
                self.log.warn(f"DigiconSignals: {head} {color} on {r.get('port_id')} which is not on the DNOU8 sheet")
            elif dn.get("head") != head or dn.get("color") != color:
                self.log.warn(f"DigiconSignals: {head} {color} on {r['port_id']}, "
                              f"but DNOU8 has {dn.get('device') or 'nothing'} there")

    def read_led_heads(self) -> None:
        for pid, rec in sorted(self.out_pins.items(), key=lambda kv: (node_sort(kv[0].split("-")[0]), kv[0])):
            if rec["kind"] != "lamp":
                continue
            head = rec["head"]
            if head in self.heads and self.heads[head]["type"] == "Digicon searchlight":
                if self.heads[head]["lamps"].get(rec["color"]) != pid:
                    self.log.warn(f"DNOU8: {rec['device']} on {pid} is not in DigiconSignals")
                continue
            note = rec.get("_note", "")
            parts = [p.strip() for p in note.split("|")]
            mm = re.search(r"mast (Switch \d+[^|]*)", note)
            h = self.heads.setdefault(head, {
                "head": head, "mast": mm.group(1).strip() if mm else "", "disc": "", "node": pid.split("-")[0],
                "place": rec.get("place", ""), "packed": "", "type": "RGB LED", "lamps": {},
                "cp": parts[0] if parts and re.match(r"CP\d", parts[0]) else "",
                "route": parts[1] if len(parts) > 1 and "→" in parts[1] else "",
            })
            if rec["color"] in h["lamps"]:
                self.log.warn(f"DNOU8: {head} lamp {rec['color']} on both {h['lamps'][rec['color']]} and {pid}")
            h["lamps"][rec["color"]] = pid
        for h in self.heads.values():
            miss = [c for c in "RYG" if c not in h["lamps"]]
            if miss:
                self.log.warn(f"Signals: head {h['head']} has no {'/'.join(miss)} pin")
            nodes_used = sorted({p.split("-")[0] for p in h["lamps"].values()})
            if len(nodes_used) > 1:
                self.log.warn(f"Signals: head {h['head']} spans nodes {nodes_used}")

    def read_masts(self, mast_rows: list[Row]) -> None:
        for r in mast_rows:
            self.masts.append({
                "mast": r.get("mast_user_name", "").replace("Mast ", ""),
                "node": r.get("parent_node_id", ""),
                "heads": r.get("heads", ""),
                "appearance": r.get("appearance", ""),
                "ports": r.get("port_ids", "").split(),
            })
        mast_by = {m["mast"]: m for m in self.masts}
        for h in self.heads.values():
            m = mast_by.get(h["mast"])
            if m:
                h["appearance"] = m["appearance"]

    def check_node_signals(self) -> None:
        """Node signal names vs the heads actually wired there."""
        for n in self.nodes.values():
            wired = {h["head"].split(" ")[0] for h in self.heads.values() if h["node"] == n["id"]}
            extra = sorted(set(n["signals"]) - wired)
            if extra and n["outputs"]:
                self.log.warn(f"Nodes: {n['id']} lists signal(s) {extra} with no lamp pins on that node")

    # —— Turnouts ——

    def read_turnouts(self) -> None:
        for r in table(self.sheets["TurnoutSummary"], 0):
            name = r.get("Turnout", "")
            if name:
                self.turnouts.append(self.turnout(r, name))

    def device_input(self, pid: str) -> str | None:
        """The device on DNIN8 port pid, or None when no input pin read so far has that port."""
        node = self.nodes.get(pid.split("-")[0])
        return next((x["device"] for b in (node["inputs"] if node else []) for x in b["pins"] if x["port"] == pid), None)

    def turnout(self, r: Row, name: str) -> Turnout:
        """The viewer's record of the TurnoutSummary row labelled name, after its pins are checked against the board
        sheets (read_outputs and read_inputs run first)."""
        jmri = turnout_name(r, name)
        motor = {pos: self.device_ports.get(f"{jmri} {pos}", []) for pos in ("N", "R")}
        t = Turnout(
            turnout=name,
            name=jmri,
            half=crossover_half(name, jmri),
            node=r.get("Parent Node", ""),
            area=r.get("Location/Area", ""),
            elements=r.get("Switch Elements", ""),
            motorN=", ".join(motor["N"]),
            motorR=", ".join(motor["R"]),
            button=r.get("Button", ""),
            fbN=r.get("Feedback N", ""),
            fbR=r.get("Feedback R", ""),
            signals={key: r[label] for key, label in TURNOUT_SIGNALS if r.get(label)},
        )
        self.check_turnout_motor(t, motor["N"] + motor["R"])
        for _, label in TURNOUT_SIGNALS:
            self.check_turnout_lamps(r, name, label.replace(" Signal", ""), r.get(label, ""))
        self.check_turnout_inputs(t)
        return t

    def check_turnout_motor(self, t: Turnout, ports: list[str]) -> None:
        """A turnout's motor pins: there are some, and they are on its parent node."""
        if not ports:
            self.log.warn(f"TurnoutSummary: {t['turnout']} has no motor pins on the DNOU8 sheet")
        motor_nodes = {p.split("-")[0] for p in ports}
        if motor_nodes and t["node"] and t["node"] not in motor_nodes:
            self.log.warn(f"TurnoutSummary: {t['turnout']} parent node {t['node']}, but its motor is on {sorted(motor_nodes)}")

    def check_turnout_inputs(self, t: Turnout) -> None:
        """A turnout's button and feedback ports against the devices the DNIN8 sheet puts there."""
        ports = {"button": t["button"], "fbN": t["fbN"], "fbR": t["fbR"]}
        for field, want in TURNOUT_INPUTS:
            pid = ports[field]
            if not pid:
                continue
            dev = self.device_input(pid)
            if dev != f"{t['name']} {want}":
                self.log.warn(f"TurnoutSummary: {t['turnout']} {field} → {pid}, but DNIN8 has {dev or 'nothing'} there")

    def check_turnout_lamps(self, r: Row, name: str, base: str, sig: str) -> None:
        """The sheet's lamp pins for one of a turnout's signals against the DNOU8 pin assignments."""
        ports = {c: r.get(f"{base} Signal {c} Port", "") or r.get(f"{base} {c} Port", "") for c in "RYG"}
        for c, pid in ports.items():
            if not pid:
                continue
            dn = self.out_pins.get(pid)
            who = dn.get("device") if dn else None
            if not sig:
                self.log.warn(f"TurnoutSummary: {name} {base.lower()} has {c} pin {pid} but no signal name")
            elif not dn:
                self.log.warn(f"TurnoutSummary: {name} {base.lower()} {sig} {c} → {pid}, not on the DNOU8 sheet")
            elif dn.get("head", "").split(" ")[0] != sig.split(" ")[0] or dn.get("color") != c:
                self.log.warn(f"TurnoutSummary: {name} {base.lower()} {sig} {c} → {pid}, "
                              f"but DNOU8 has {who or 'nothing (spare)'} there")

    def check_declared_boards(self) -> None:
        """The boards each node declares vs the boards found on the DNOU8 and DNIN8 sheets."""
        for n in self.nodes.values():
            dec = n.pop("declared", {})
            for sheet, side in (("DNOU8", "outputs"), ("DNIN8", "inputs")):
                found = [b["board"] for b in n[side]]
                if dec.get(sheet) is not None and sorted(dec.get(sheet, [])) != sorted(found):
                    self.log.warn(f"Nodes: {n['id']} declares {sheet} {dec.get(sheet)} but the {sheet} sheet has {found}")

    def data(self) -> dict:
        """The viewer data, with the working fields (_locs, _note) dropped."""
        for b in self.out_boards.values():
            b.pop("_locs", None)
        for rec in self.out_pins.values():
            rec.pop("_note", None)
        return {
            # a label: the workbook these sheets are saved as (write_inventory.OUT), which this build never reads
            "source": {"file": self.source, "version": version_of(Path(self.source))},
            "nodes": sorted(self.nodes.values(), key=lambda n: node_sort(n["id"])),
            "signals": sorted(self.heads.values(), key=lambda h: (node_sort(h["node"]), h["head"])),
            "masts": self.masts,
            "turnouts": self.turnouts,
            "blocks": self.blocks,
        }


def read_sheets(wb: Workbook | None, source: str, log: BuildLog) -> dict[str, list[list[str]]]:
    """Every sheet's cleaned rows: by default the workbook write_inventory.py builds in memory from the wiring model."""
    try:
        wb = wb if wb is not None else write_inventory.workbook()
    except write_inventory.FactsError as err:
        raise WiringDataError(f"the wiring model cannot be read: {err}") from err
    sheets = {ws.title: sheet_rows(ws, log.scrubbed) for ws in wb.worksheets}
    missing = [need for need in NEEDED_SHEETS if need not in sheets]
    if missing:
        raise WiringDataError(f"{source}: missing sheet(s) {', '.join(missing)}")
    return sheets


def build_inventory(wb: Workbook | None = None, source: str = write_inventory.OUT.name) -> Built:
    """The viewer's data from the inventory sheets of wb, with the warnings and scrubbed cells of this build. source is
    the file write_inventory.py saves the workbook as, for the JSON's source."""
    log = BuildLog()
    inv = Inventory(read_sheets(wb, source, log), source, log)
    inv.read_nodes()
    inv.read_outputs()
    inv.read_inputs()
    inv.read_blocks()
    port_rows, mast_rows = inv.digicon_tables()
    inv.read_digicon_heads(port_rows)
    inv.read_led_heads()
    inv.read_masts(mast_rows)
    inv.check_node_signals()
    inv.read_turnouts()
    inv.check_declared_boards()
    return Built(inv.data(), log)


def prune(x: object) -> object:
    """Drop empty-string fields so the JSON only carries what a cell actually says."""
    if isinstance(x, dict):
        return {k: prune(v) for k, v in x.items() if v != ""}
    if isinstance(x, list):
        return [prune(v) for v in x]
    return x


# —— Main ——————————————————————————————————————————————————————————

def shown(path: Path) -> str:
    """path relative to the repo when it lies inside it, for messages."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def render(data: dict) -> str:
    return json.dumps(prune(data), indent=1, ensure_ascii=False) + "\n"


# Lists every wiring model fills; an empty one means the model or the reader is broken.
REQUIRED = ("nodes", "signals", "masts", "turnouts", "blocks")


def _strings(x: object) -> Iterator[str]:
    if isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def problems(inv: dict) -> list[str]:
    """What is wrong with built viewer data: no source, a required list that is empty, a node id empty or twice, or a
    string that still looks like a network detail or a secret (clean() should have dropped it)."""
    out = []
    if not (inv.get("source") or {}).get("file"):
        out.append("source.file is empty")
    for key in REQUIRED:
        if not isinstance(inv.get(key), list) or not inv[key]:
            out.append(f"{key!r} has no entries")
    ids = [n.get("id") for n in inv.get("nodes") or []]
    twice = sorted({i for i in ids if ids.count(i) > 1})
    if twice or not all(ids):
        out.append(f"node ids are not one each: {twice or 'an empty id'}")
    leaks = sorted({s for s in _strings(inv) if any(p.search(s) for p in UNSAFE)})
    if leaks:
        out.append(f"{len(leaks)} string(s) look like network details or secrets: {leaks[:3]}")
    return out


def data_text(inv: dict) -> str:
    """The checked wiring-inventory.json text of built viewer data. WiringDataError when it fails a check."""
    bad = problems(inv)
    if bad:
        raise WiringDataError("www/%s fails its checks:\n  %s" % (OUT_REL, "\n  ".join(bad)))
    return render(inv)


def build(wb: Workbook | None = None) -> Built:
    """The viewer data from the wiring model, dated today (its build date)."""
    built = build_inventory(wb)
    built.data["source"]["built"] = dt.date.today().isoformat()
    return built


def view() -> str:
    """The viewer data for the site build and the local preview (site_views.VIEWS)."""
    return data_text(build().data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", type=Path, default=PORTAL / "data", help="where the JSON goes")
    ap.add_argument("-q", "--quiet", action="store_true", help="don't list data warnings")
    ap.add_argument("--check", action="store_true",
                    help="write nothing; build the JSON in memory and exit 1 when it cannot be built or fails a check")
    args = ap.parse_args()
    try:
        inv, log = build()
    except WiringDataError as exc:  # the model cannot be read: 2
        print(f"{Path(__file__).name}: {exc}", file=sys.stderr)
        return 2
    try:
        text = data_text(inv)
    except WiringDataError as exc:  # built, but fails a check
        print(f"{Path(__file__).name}: {exc}", file=sys.stderr)
        return 1
    if args.check:
        print(f"www/{OUT_REL} builds from the wiring model and passes its checks (not committed, ADR-036)")
    else:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        p = args.out_dir / OUT_INV.name
        p.write_text(text, encoding="utf-8")
        print(f"wrote {shown(p)} ({p.stat().st_size // 1024} KB)")

    n_pins = sum(len(b["pins"]) for n in inv["nodes"] for b in n["outputs"] + n["inputs"])
    print(f"{inv['source']['file']}: {len(inv['nodes'])} nodes, {n_pins} pins, {len(inv['signals'])} heads, "
          f"{len(inv['turnouts'])} turnouts, {len(inv['blocks'])} block sensors")
    if log.scrubbed:
        print(f"scrubbed {len(log.scrubbed)} cell(s) that looked like network details or secrets")
    if log.warnings:
        print(f"{len(log.warnings)} data warning(s)" + ("" if args.quiet else ":"))
        if not args.quiet:
            for w in log.warnings:
                print("  - " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
