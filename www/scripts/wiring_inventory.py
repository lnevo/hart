"""The wiring viewer's data read from the LCOS inventory sheets (build_wiring_json.py builds and checks it).

Inventory makes one pass over the sheets write_inventory.workbook() builds: the Nodes sheet, the DNOU8 and DNIN8
board sheets, BlockSensors, DigiconSignals and TurnoutSummary. Each read_* step fills a part of the viewer data and
cross-checks it against the parts read before it; what does not agree is a warning in the build's BuildLog, not a
stop. A row the viewer cannot place at all (a turnout with no JMRI name, a DigiconSignals sheet with no header) is a
WiringDataError.
"""
from __future__ import annotations

import re
from collections import Counter, OrderedDict, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import NamedTuple, NotRequired, TypedDict

from wiring_sheet import (HEAD_RE, Row, board_sort, in_kind, node_sort, out_kind, parse_port, pick_location,
                          split_list, strip_history, table, version_of)


class WiringDataError(Exception):
    """The viewer data cannot be built from the wiring model, or fails a check; the message says why."""


@dataclass
class BuildLog:
    """What one build found along the way: data warnings, and the cells build_wiring_json.clean() dropped."""
    warnings: list[str] = dc_field(default_factory=list)
    scrubbed: list[str] = dc_field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


class Pin(TypedDict):
    """A DNOU8 or DNIN8 pin. color and head are set on a lamp; _note is a lamp's note while the build reads it (its
    route goes onto the head), dropped before the data is published."""
    pin: int
    port: str
    device: str
    kind: str
    color: NotRequired[str]
    head: NotRequired[str]
    place: NotRequired[str]
    note: NotRequired[str]
    _note: NotRequired[str]


class OutputBoard(TypedDict):
    """A node's DNOU8 board: its voltage rail, its place and its pins."""
    board: str
    rail: str
    place: str
    pins: list[Pin]


class InputBoard(TypedDict):
    board: str
    place: str
    pins: list[Pin]


class Channel(TypedDict):
    channel: str
    port: str
    block: str


class Detector(TypedDict):
    detector: str
    channels: list[Channel]


class Node(TypedDict):
    """A node of the Nodes sheet with the boards and detectors the other sheets put on it. declared (the boards the
    Nodes sheet lists) is dropped once check_declared_boards has compared it."""
    id: str
    address: str
    location: str
    type: str
    turnouts: list[str]
    signals: list[str]
    blockNames: list[str]
    summary: dict[str, dict[str, str]]
    outputs: list[OutputBoard]
    inputs: list[InputBoard]
    detectors: list[Detector]
    declared: NotRequired[dict[str, list[str]]]


class Head(TypedDict):
    """A signal head with its lamp pins by colour. cp and route are an RGB LED head's, from its DNOU8 note;
    appearance comes from its mast's row."""
    head: str
    mast: str
    disc: str
    node: str
    place: str
    packed: str
    type: str
    lamps: dict[str, str]
    cp: NotRequired[str]
    route: NotRequired[str]
    appearance: NotRequired[str]


class Mast(TypedDict):
    mast: str
    node: str
    heads: str
    appearance: str
    ports: list[str]


class BlockSensor(TypedDict):
    """A BlockSensors row: the detector channel and the block it reports."""
    port: str
    node: str
    detector: str
    channel: str
    block: str
    track: str
    area: str
    district: str
    note: str


class Source(TypedDict):
    """The workbook the sheets are saved as (a label only), and the build date build_wiring_json.build adds."""
    file: str
    version: str
    built: NotRequired[str]


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


class ViewerData(TypedDict):
    """wiring-inventory.json before its empty fields are pruned."""
    source: Source
    nodes: list[Node]
    signals: list[Head]
    masts: list[Mast]
    turnouts: list[Turnout]
    blocks: list[BlockSensor]


class Built(NamedTuple):
    """The viewer data of one build, with what that build reported."""
    data: ViewerData
    log: BuildLog


TURNOUT_SIGNALS = (("entry", "Entry Signal"), ("normal", "Normal Exit Signal"), ("reverse", "Reverse Exit Signal"))
TURNOUT_INPUTS = (("button", "BTN"), ("fbN", "N FB"), ("fbR", "R FB"))  # field, the DNIN8 device name's suffix
BoardKey = tuple[str, str]             # (node id, board), such as ("C13", "OU2")
NEEDED_SHEETS = ("Nodes", "DNOU8", "DNIN8", "TurnoutSummary", "BlockSensors", "DigiconSignals")
NOT_WIRED = ("spare", "reserved", "cal")  # output kinds that are not a device


class WorkBoard(TypedDict):
    """A board while its sheet is read: its pins, the places of its wired pins (_locs) and, on a DNOU8 board, the
    count of each voltage rail its pins give."""
    board: str
    rail: NotRequired[Counter[str]]
    pins: list[Pin]
    _locs: NotRequired[list[str]]


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


def board_order(item: tuple[BoardKey, WorkBoard]) -> tuple[tuple[int, int], tuple[str, int]]:
    """A board's sort key: its node's, then its own."""
    (nid, board), _ = item
    return node_sort(nid), board_sort(board)


class Inventory:
    """One pass over the inventory sheets. Each read_* step fills a part of the viewer data and warns through log;
    the cross-checks run after the parts they compare are read."""

    def __init__(self, sheets: dict[str, list[list[str]]], source: str, log: BuildLog) -> None:
        self.sheets, self.source, self.log = sheets, source, log
        self.nodes: OrderedDict[str, Node] = OrderedDict()
        self.out_boards: dict[BoardKey, WorkBoard] = {}
        self.out_pins: dict[str, Pin] = {}             # port id -> its DNOU8 pin record
        self.device_ports: dict[str, list[str]] = {}   # DNOU8 device -> its port ids
        self.heads: OrderedDict[str, Head] = OrderedDict()
        self.masts: list[Mast] = []
        self.blocks: list[BlockSensor] = []
        self.turnouts: list[Turnout] = []

    def node_for(self, nid: str, sheet: str, pid: str) -> Node:
        """The node nid, added bare (with a warning) when the Nodes sheet does not list it."""
        if nid not in self.nodes:
            self.log.warn(f"{sheet}: {pid} names node {nid}, which is not on the Nodes sheet")
            self.nodes[nid] = {"id": nid, "address": "", "location": "", "type": "",
                               "turnouts": [], "signals": [], "blockNames": [], "summary": {},
                               "outputs": [], "inputs": [], "detectors": [], "declared": {}}
        return self.nodes[nid]

    def read_nodes(self) -> None:
        """The Nodes sheet: one record per node id, its boards still empty."""
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

    def sorted_boards(self, sheet: str, boards: dict[BoardKey, WorkBoard], ports: dict[str, list[str]],
                      where: str) -> Iterator[tuple[str, str, WorkBoard, list[Pin]]]:
        """Warns of a device on more than one port, then gives (node, board, the board's record, its pins by number) in
        node and board order."""
        for dev, on in ports.items():
            if len(on) > 1:
                self.log.warn(f"{sheet}: {dev!r} is on more than one {where}: {', '.join(on)}")
        for (nid, board), b in sorted(boards.items(), key=board_order):
            pins = sorted(b["pins"], key=lambda x: x["pin"])
            yield nid, board, b, pins

    def missing_pins(self, sheet: str, nid: str, board: str, pins: list[Pin]) -> None:
        """Warns of a board with no row for one of its eight pins."""
        have = {x["pin"] for x in pins}
        missing = [i for i in range(1, 9) if i not in have]
        if missing:
            self.log.warn(f"{sheet}: {nid}-{board} has no row for pin(s) {missing}")

    def read_outputs(self) -> None:
        """The DNOU8 sheet: each node's output boards and their pins, and each device's output ports."""
        ports: dict[str, list[str]] = defaultdict(list)
        for nid, board, pin, pid, r in self.pin_rows("DNOU8", "Output Port ID", check_parent=True):
            device = r.get("Connected Device", "")
            kind, color, head = out_kind(device, r.get("Device Type", ""))
            b = self.out_boards.setdefault((nid, board), {"board": board, "rail": Counter(), "pins": [], "_locs": []})
            if r.get("Voltage Rail (12V/5V)"):
                b["rail"][r["Voltage Rail (12V/5V)"]] += 1
            rec: Pin = {"pin": pin, "port": pid, "device": device, "kind": kind}
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
        """The DNIN8 sheet: each node's input boards and their pins."""
        boards: dict[BoardKey, WorkBoard] = {}
        ports: dict[str, list[str]] = defaultdict(list)
        for nid, board, pin, pid, r in self.pin_rows("DNIN8", "Input Port ID", check_parent=False):
            device = r.get("Connected Device", "")
            kind = in_kind(device, r.get("Device Type (Sensor/Switch/etc.)", ""))
            rec: Pin = {"pin": pin, "port": pid, "device": device, "kind": kind}
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
        """The BlockSensors sheet: the block sensors, and each node's detectors with their channels."""
        det: dict[tuple[str, str], list[BlockSensor]] = defaultdict(list)
        seen: set[str] = set()
        for r in table(self.sheets["BlockSensors"], 0):
            pid = r.get("Port ID", "")
            nid = r.get("Node ID", "") or (pid.split("-")[0] if pid else "")
            if pid in seen:
                self.log.warn(f"BlockSensors: {pid} listed twice")
                continue
            seen.add(pid)
            rec: BlockSensor = {
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
        """The Digicon heads of the DigiconSignals port rows, each lamp checked against its DNOU8 pin."""
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
        """The RGB LED heads of the DNOU8 lamp pins (a Digicon head's pins are only checked), then every head's lamps
        checked: all three colours, on one node."""
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
        """The DigiconSignals mast rows, each mast's appearance copied onto its heads."""
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
        """The TurnoutSummary sheet: one record per labelled row (turnout)."""
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
            boards = {"DNOU8": [b["board"] for b in n["outputs"]], "DNIN8": [b["board"] for b in n["inputs"]]}
            for sheet, found in boards.items():
                if dec.get(sheet) is not None and sorted(dec.get(sheet, [])) != sorted(found):
                    self.log.warn(f"Nodes: {n['id']} declares {sheet} {dec.get(sheet)} but the {sheet} sheet has {found}")

    def data(self) -> ViewerData:
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
