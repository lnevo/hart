"""The physical wiring source: jmri/layouts/hart/data/wiring.csv, one row per device on an LCOS node (owner,
2026-11-20: the repo keeps the wiring the inventory workbook holds, edited here).

Staging's rows are what JMRI holds, as wired (status `wired`), and the ports assigned to devices not connected yet
(status `planned`: a button or relay on its port with nothing connected, a reserved calibration relay port). Main
and upper are still being designed: their devices are given nodes and ports by build_device_map.py's rule, except
the rows here, which the rule then leaves alone (status `planned` for a device the owner placed, `wired` once a
control point is wired and frozen).

Columns (COLUMNS):
- level 1, 2 or 3; kind: turnout, fb (turnout feedback), head (signal head), detector (block occupancy), button (a
  fascia button on an input), relay (on an output) or calibration (the relay on an output that resets the DCC power
  so the node's block detectors calibrate; every node with detectors has one reserved, owner 2026-11-21). Buttons
  and relays are wired on the nodes but have no JMRI device (owner, 2026-11-20: live today, more to come); their
  index is blank. A calibration row's status is wired where the relay is in, planned where the port is reserved.
- device: the device's user name (Switch 1, FB Switch 1 N, Head 6LB), or a detector's block name. A main or upper
  detector on a track is named by switch_a, switch_b, parallel and half instead (mast_rule.track_key: lower number
  first), since those block names are placeholders. A staging detector with no block is a spare input.
- node: the LCOS radio address. index: the LCOS number in the device's wiring text, "Turnout: <i>", "Sensor: <i>",
  "Signal: <i>" from 0, "Block: <i>" from 1 (1 to 8). board (OU<n> or IN<n>) and ports: where a turnout, feedback or
  head lands; a detector has neither (its input is the index).
- status: wired or planned. notes: text for people. (Power districts are not mapped yet; the owner,
  2026-11-21: the inventory's were old names, not real.)

The JMRI address follows from node and index (address), and the wiring text from all four (wiring_text): devices.csv
holds both only as written from here.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import NamedTuple

from . import paths
from .railroad_facts import FactsError

PATH = paths.LAYOUT_DATA / "wiring.csv"
COLUMNS = ["level", "kind", "device", "switch_a", "switch_b", "parallel", "half", "node", "index", "board", "ports",
           "status", "notes"]
KINDS = ("turnout", "fb", "head", "detector", "button", "relay", "calibration")
LOCAL = ("button", "relay", "calibration")      # on a node, no JMRI device: no index, no address
STATUSES = ("wired", "planned")
# kind -> (system name prefix, LCOS UID offset, the word in the wiring text, the board it lands on, ports per device)
LCOS = {"turnout": ("M2T", 8, "Turnout", "OU", 2), "fb": ("M2S", 67, "Sensor", "IN", 1),
        "head": ("IH", 32, "Signal", "OU", 3), "detector": ("M2S", 0, "Block", "", 0),
        "button": ("", 0, "", "IN", 1), "relay": ("", 0, "", "OU", 1), "calibration": ("", 0, "", "OU", 1)}
CAP = {"turnout": 8, "fb": 16, "head": 16, "detector": 8}     # LCOS numbers per node (a detector's from 1)
BOARD = re.compile(r"^(OU|IN)([1-4])$")


class Wire(NamedTuple):
    line: int
    level: int
    kind: str
    device: str
    switch_a: str
    switch_b: str
    parallel: str
    half: str
    node: int
    index: int | None
    board: str
    ports: tuple[int, ...]
    status: str
    notes: str

    @property
    def address(self) -> str:
        """The JMRI system name: M2T, M2S or IH and node x 100 + the UID offset + the index (a detector's from 0).
        A button or relay has none (ValueError)."""
        if self.kind in LOCAL:
            raise ValueError(f"a {self.kind} has no JMRI address")
        prefix, uid, _word, _board, _n = LCOS[self.kind]
        return f"{prefix}{self.node * 100 + uid + self.index - (self.kind == 'detector')}"

    @property
    def wiring_text(self) -> str:
        """The device's wiring as devices.csv and the JMRI comment tell it: "Node: 4 Turnout: 0 | OU: 1 Ports: 1,2",
        a detector's "Node: 13 Block: 1"."""
        word = LCOS[self.kind][2]
        if self.kind in LOCAL:
            return f"Node: {self.node} | {self.board[:2]}: {self.board[2:]} Ports: {','.join(map(str, self.ports))}"
        text = f"Node: {self.node} {word}: {self.index}"
        if self.kind == "detector":
            return text
        return f"{text} | {self.board[:2]}: {self.board[2:]} Ports: {','.join(map(str, self.ports))}"

    @property
    def input(self) -> str:
        """A detector's node input as the name map and the block comment give it: "Block 13-1"."""
        return f"Block {self.node}-{self.index}"


def read(path: Path | None = None) -> list[Wire]:
    """The rows of wiring.csv, each checked. Stops (FactsError, naming the file and line) on a file not in COLUMNS, an
    unknown level, kind or status, a number that is not one, an index past its kind's range, a board or ports that do
    not fit the kind, a device given twice on its level, two devices on one LCOS number or on one port of a board."""
    path = path or PATH
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows, header = list(reader), reader.fieldnames or []
    except OSError as exc:
        raise FactsError(f"cannot read {path.name}: {exc}") from None
    if list(header) != COLUMNS:
        raise FactsError(f"{path.name}: columns {list(header)}, not {COLUMNS}")
    out, bad = [], []
    names, numbers, pins = {}, {}, {}
    for i, raw in enumerate(rows, 2):
        if None in raw:
            bad.append(f"line {i}: more fields than columns")
            continue
        r = {k: (v or "").strip() for k, v in raw.items()}
        at = f"line {i}"
        if r["level"] not in ("1", "2", "3"):
            bad.append(f"{at}: level is 1, 2 or 3, not {r['level']!r}")
            continue
        if r["kind"] not in KINDS:
            bad.append(f"{at}: kind is one of {', '.join(KINDS)}, not {r['kind']!r}")
            continue
        if r["status"] not in STATUSES:
            bad.append(f"{at}: status is wired or planned, not {r['status']!r}")
            continue
        kind = r["kind"]
        try:
            node = int(r["node"])
            index = None if kind in LOCAL and not r["index"] else int(r["index"])
            ports = tuple(int(p) for p in r["ports"].split(",")) if r["ports"] else ()
        except ValueError:
            bad.append(f"{at}: node, index and ports are numbers")
            continue
        low = 1 if kind == "detector" else 0
        if kind in LOCAL:
            if index is not None:
                bad.append(f"{at}: a {kind} has no JMRI device, so no index")
                continue
        elif not low <= index < low + CAP[kind]:
            bad.append(f"{at}: a {kind}'s index is {low} to {low + CAP[kind] - 1}, not {index}")
            continue
        keyed = any(r[c] for c in ("switch_a", "switch_b", "parallel", "half"))
        if kind == "detector":
            if r["board"] or ports:
                bad.append(f"{at}: a detector has no board or ports (its input is its index)")
                continue
            if keyed and r["level"] == "1":
                bad.append(f"{at}: a staging detector is named by its block alone (device), not by switches")
                continue
            if keyed and r["device"]:
                bad.append(f"{at}: a detector is named by its block or, on main and upper, by its switches, not both")
                continue
        else:
            m = BOARD.match(r["board"])
            want = LCOS[kind]
            if keyed:
                bad.append(f"{at}: a {kind} is named by device alone")
                continue
            if not r["device"]:
                bad.append(f"{at}: a {kind} needs its device name")
                continue
            if not m or m.group(1) != want[3]:
                bad.append(f"{at}: a {kind} lands on an {want[3]} board ({want[3]}1 to {want[3]}4), not {r['board']!r}")
                continue
            if len(ports) != want[4] or not all(1 <= p <= 8 for p in ports):
                bad.append(f"{at}: a {kind} takes {want[4]} port(s) of 1 to 8, not {r['ports']!r}")
                continue
        level = int(r["level"])
        name = r["device"] or (",".join(r[c] for c in ("switch_a", "switch_b", "parallel", "half")) if keyed else "")
        if name and (level, kind, name) in names:
            bad.append(f"{at}: {kind} {name} is line {names[level, kind, name]}'s as well")
            continue
        number = (node, LCOS[kind][2], index)
        if kind not in LOCAL and number in numbers:
            bad.append(f"{at}: node {node} {LCOS[kind][2]} {index} is line {numbers[number]}'s as well")
            continue
        taken = [p for p in ports if (node, r["board"], p) in pins]
        if taken:
            bad.append(f"{at}: node {node} {r['board']} port(s) {taken} are line {pins[node, r['board'], taken[0]]}'s")
            continue
        if name:
            names[level, kind, name] = i
        if kind not in LOCAL:
            numbers[number] = i
        for p in ports:
            pins[node, r["board"], p] = i
        out.append(Wire(i, level, kind, r["device"], r["switch_a"], r["switch_b"], r["parallel"], r["half"], node,
                        index, r["board"], ports, r["status"], r["notes"]))
    if bad:
        raise FactsError(f"{path.name}: " + "; ".join(bad))
    return out
