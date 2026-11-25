#!/usr/bin/env python3
"""Build the public wiring viewer data (behind/wiring.html) from the wiring model.

Reads the LCOS inventory's sheets as tools/wiring/write_inventory.py builds them in memory from the wiring model
(the device master, hartlib.wiring's wiring.csv, lcos_nodes.csv and signal_head_plan.csv), the same sheets it saves
as LCOS_Layout_Inventory_v86.xlsx. The workbook file is an output only: this script never opens it (ADR-039). It
writes:

  data/wiring-inventory.json  nodes with DNOU8 / DNIN8 / block-detector port maps,
                              signal heads with their R/Y/G pins, turnouts, block sensors

The signal-split view and its workbook were retired on 2026-11-25 (owner): the signals and their rules are
generated for the whole layout. The split workbook, its v85 inventory and the last signal-splits.json are in
archive/docs/wiring/.

Re-run after a wiring change:

  python3 www/scripts/build_wiring_json.py

Data problems found along the way are printed as warnings; they do not stop the build. Network details (IP addresses, hostnames, serial ports, machine paths,
credentials) are scrubbed from every cell before it reaches the JSON.

--check builds without writing and exits 1 when the JSON file holds other data than the
wiring model gives. The build date is ignored. tools/check.sh runs it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
ROOT = PORTAL.parent
OUT_INV = PORTAL / "data" / "wiring-inventory.json"
sys.path.insert(0, str(ROOT / "tools" / "wiring"))
import write_inventory  # noqa: E402  (the wiring model's inventory sheets; it puts hartlib on the path)

WARNINGS: list[str] = []
SCRUBBED: list[str] = []


def warn(msg: str) -> None:
    WARNINGS.append(msg)


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


def clean(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (dt.datetime, dt.date)):
        v = v.isoformat()[:10]
    s = re.sub(r"\s+", " ", str(v)).strip()
    for pat in UNSAFE:
        if pat.search(s):
            SCRUBBED.append(s)
            return ""
    return s


def sheet_rows(ws) -> list[list[str]]:
    """Every row as cleaned strings, empty rows dropped."""
    out = []
    for row in ws.iter_rows(values_only=True):
        cells = [clean(c) for c in row]
        if any(cells):
            out.append(cells)
    return out


def table(rows: list[list[str]], header_idx: int, stop=None) -> list[dict]:
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


def parse_port(pid: str):
    m = PORT_RE.match(pid)
    if not m:
        return None
    return m.group("node"), m.group("board"), int(m.group("pin"))


def board_sort(b: str):
    m = re.match(r"([A-Z]+)(\d+)", b)
    return (m.group(1), int(m.group(2))) if m else (b, 0)


def node_sort(n: str):
    m = re.match(r"([A-Z]+)(\d+)", n)
    return ({"M": 0, "C": 1, "D": 2}.get(m.group(1), 3), int(m.group(2))) if m else (9, 0)


# —— Inventory ——————————————————————————————————————————————————

def out_kind(device: str, dtype: str) -> tuple[str, str]:
    """(kind, lamp color) for a DNOU8 pin."""
    m = HEAD_RE.match(device)
    if m:
        return "lamp", m.group("color")
    t = dtype.lower()
    if "turnout" in t:
        return "motor", ""
    if "cal" in t:
        return "cal", ""
    if "relay" in t:
        return "relay", ""
    if "reserved" in t or device.lower() == "reserved":
        return "reserved", ""
    if not device:
        return "spare", ""
    return "other", ""


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


def build_inventory(wb=None, source: str = write_inventory.OUT.name) -> dict:
    """The viewer's data from the inventory sheets of wb: by default the workbook write_inventory.py builds in memory
    from the wiring model (source is the file it saves it as, for the JSON's source)."""
    wb = wb if wb is not None else write_inventory.workbook()
    sheets = {ws.title: sheet_rows(ws) for ws in wb.worksheets}
    for need in ("Nodes", "DNOU8", "DNIN8", "TurnoutSummary", "BlockSensors", "DigiconSignals"):
        if need not in sheets:
            raise SystemExit(f"{source}: missing sheet {need}")

    # Nodes
    node_rows = table(sheets["Nodes"], 0)
    nodes: "OrderedDict[str, dict]" = OrderedDict()
    for r in node_rows:
        nid = r.get("Node ID", "")
        if not nid:
            continue
        nodes[nid] = {
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

    def node_for(nid: str, sheet: str, pid: str):
        if nid not in nodes:
            warn(f"{sheet}: {pid} names node {nid}, which is not on the Nodes sheet")
            nodes[nid] = {"id": nid, "address": "", "location": "", "type": "",
                          "turnouts": [], "signals": [], "blockNames": [], "summary": {},
                          "outputs": [], "inputs": [], "detectors": [], "declared": {}}
        return nodes[nid]

    # DNOU8
    boards: dict[tuple[str, str], dict] = {}
    seen_ports: set[str] = set()
    device_ports: dict[str, list[str]] = defaultdict(list)
    out_pins: dict[str, dict] = {}
    for r in table(sheets["DNOU8"], 0):
        pid = r.get("Output Port ID", "")
        p = parse_port(pid)
        if not p:
            warn(f"DNOU8: unreadable port id {pid!r}")
            continue
        nid, board, pin = p
        if r.get("Parent Node ID") and r["Parent Node ID"] != nid:
            warn(f"DNOU8: {pid} has Parent Node {r['Parent Node ID']}")
        if pid in seen_ports:
            warn(f"DNOU8: port {pid} listed twice")
            continue
        seen_ports.add(pid)
        device = r.get("Connected Device", "")
        kind, color = out_kind(device, r.get("Device Type", ""))
        b = boards.setdefault((nid, board), {"board": board, "rail": Counter(), "pins": [], "_locs": []})
        if r.get("Voltage Rail (12V/5V)"):
            b["rail"][r["Voltage Rail (12V/5V)"]] += 1
        rec = {"pin": pin, "port": pid, "device": device, "kind": kind}
        if color:
            rec["color"] = color
            rec["head"] = HEAD_RE.match(device).group("head")
        if r.get("Board Location"):
            rec["place"] = r["Board Location"]
            if kind not in ("spare", "reserved", "cal"):
                b["_locs"].append(r["Board Location"])
        if r.get("Notes"):
            if kind == "lamp":
                rec["_note"] = r["Notes"]  # route info is lifted onto the head; not published per pin
            elif strip_history(r["Notes"]):
                rec["note"] = strip_history(r["Notes"])
        b["pins"].append(rec)
        out_pins[pid] = rec
        if device and kind not in ("spare", "reserved", "cal"):
            device_ports[device].append(pid)
    for dev, ports in device_ports.items():
        if len(ports) > 1:
            warn(f"DNOU8: {dev!r} is on more than one pin: {', '.join(ports)}")
    for (nid, board), b in sorted(boards.items(), key=lambda kv: (node_sort(kv[0][0]), board_sort(kv[0][1]))):
        rails = list(b["rail"])
        if len(rails) > 1:
            warn(f"DNOU8: {nid}-{board} mixes rails {rails}")
        pins = sorted(b["pins"], key=lambda x: x["pin"])
        have = {x["pin"] for x in pins}
        missing = [i for i in range(1, 9) if i not in have]
        if missing:
            warn(f"DNOU8: {nid}-{board} has no row for pin(s) {missing}")
        node_for(nid, "DNOU8", f"{nid}-{board}")["outputs"].append({
            "board": board,
            "rail": b["rail"].most_common(1)[0][0] if b["rail"] else "",
            "place": pick_location(b["_locs"]),
            "pins": pins,
        })

    # DNIN8
    in_boards: dict[tuple[str, str], dict] = {}
    seen_in: set[str] = set()
    in_device_ports: dict[str, list[str]] = defaultdict(list)
    for r in table(sheets["DNIN8"], 0):
        pid = r.get("Input Port ID", "")
        p = parse_port(pid)
        if not p:
            warn(f"DNIN8: unreadable port id {pid!r}")
            continue
        nid, board, pin = p
        if pid in seen_in:
            warn(f"DNIN8: port {pid} listed twice")
            continue
        seen_in.add(pid)
        device = r.get("Connected Device", "")
        kind = in_kind(device, r.get("Device Type (Sensor/Switch/etc.)", ""))
        rec = {"pin": pin, "port": pid, "device": device, "kind": kind}
        if r.get("Board Location"):
            rec["place"] = r["Board Location"]
        if strip_history(r.get("Notes", "")):
            rec["note"] = strip_history(r["Notes"])
        in_boards.setdefault((nid, board), {"board": board, "pins": [], "_locs": []})
        in_boards[(nid, board)]["pins"].append(rec)
        if device:
            in_boards[(nid, board)]["_locs"].append(r.get("Board Location", ""))
            in_device_ports[device].append(pid)
    for dev, ports in in_device_ports.items():
        if len(ports) > 1:
            warn(f"DNIN8: {dev!r} is on more than one input: {', '.join(ports)}")
    for (nid, board), b in sorted(in_boards.items(), key=lambda kv: (node_sort(kv[0][0]), board_sort(kv[0][1]))):
        pins = sorted(b["pins"], key=lambda x: x["pin"])
        missing = [i for i in range(1, 9) if i not in {x["pin"] for x in pins}]
        if missing:
            warn(f"DNIN8: {nid}-{board} has no row for pin(s) {missing}")
        node_for(nid, "DNIN8", f"{nid}-{board}")["inputs"].append(
            {"board": board, "place": pick_location(b["_locs"]), "pins": pins})

    # Block sensors
    blocks = []
    det: dict[tuple[str, str], list] = defaultdict(list)
    seen_bs: set[str] = set()
    for r in table(sheets["BlockSensors"], 0):
        pid = r.get("Port ID", "")
        nid = r.get("Node ID", "") or (pid.split("-")[0] if pid else "")
        if pid in seen_bs:
            warn(f"BlockSensors: {pid} listed twice")
            continue
        seen_bs.add(pid)
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
            warn(f"BlockSensors: {pid} has no block name")
        blocks.append(rec)
        det[(nid, rec["detector"])].append(rec)
    for (nid, d), chans in sorted(det.items(), key=lambda kv: (node_sort(kv[0][0]), kv[0][1])):
        node_for(nid, "BlockSensors", d)["detectors"].append({
            "detector": d,
            "channels": [{"channel": c["channel"], "port": c["port"], "block": c["block"]} for c in
                         sorted(chans, key=lambda c: str(c["channel"]))],
        })

    # Signal heads: Digicon searchlights (DigiconSignals, lower deck) + RGB LED heads (DNOU8, upper deck)
    dig_rows = sheets["DigiconSignals"]
    hdr = next(i for i, r in enumerate(dig_rows) if r and r[0] == "port_id")
    mast_hdr = next((i for i, r in enumerate(dig_rows) if r and r[0] == "mast_user_name"), None)
    port_rows = table(dig_rows[: (mast_hdr - 1) if mast_hdr else None], hdr)
    mast_rows = table(dig_rows, mast_hdr) if mast_hdr else []

    heads: "OrderedDict[str, dict]" = OrderedDict()
    for r in port_rows:
        name = r.get("user_name", "")
        m = HEAD_RE.match(name)
        if not m:
            continue
        head = m.group("head")
        color = r.get("lamp_color") or m.group("color")
        mast = r.get("mast_user_name", "").replace("Mast ", "")
        h = heads.setdefault(head, {
            "head": head, "mast": mast, "disc": r.get("disc_role", ""),
            "node": r.get("parent_node_id", ""), "place": r.get("board_location", ""),
            "packed": r.get("system_name", ""), "type": "Digicon searchlight", "lamps": {},
        })
        if color in h["lamps"]:
            warn(f"DigiconSignals: {head} lamp {color} on both {h['lamps'][color]} and {r['port_id']}")
        h["lamps"][color] = r.get("port_id", "")
        dn = out_pins.get(r.get("port_id", ""))
        if not dn:
            warn(f"DigiconSignals: {head} {color} on {r.get('port_id')} which is not on the DNOU8 sheet")
        elif dn.get("head") != head or dn.get("color") != color:
            warn(f"DigiconSignals: {head} {color} on {r['port_id']}, but DNOU8 has {dn.get('device') or 'nothing'} there")

    for pid, rec in sorted(out_pins.items(), key=lambda kv: (node_sort(kv[0].split("-")[0]), kv[0])):
        if rec["kind"] != "lamp":
            continue
        head = rec["head"]
        if head in heads and heads[head]["type"] == "Digicon searchlight":
            if heads[head]["lamps"].get(rec["color"]) != pid:
                warn(f"DNOU8: {rec['device']} on {pid} is not in DigiconSignals")
            continue
        note = rec.get("_note", "")
        parts = [p.strip() for p in note.split("|")]
        mast = ""
        mm = re.search(r"mast (Switch \d+[^|]*)", note)
        if mm:
            mast = mm.group(1).strip()
        h = heads.setdefault(head, {
            "head": head, "mast": mast, "disc": "", "node": pid.split("-")[0],
            "place": rec.get("place", ""), "packed": "", "type": "RGB LED", "lamps": {},
            "cp": parts[0] if parts and re.match(r"CP\d", parts[0]) else "",
            "route": parts[1] if len(parts) > 1 and "→" in parts[1] else "",
        })
        if rec["color"] in h["lamps"]:
            warn(f"DNOU8: {head} lamp {rec['color']} on both {h['lamps'][rec['color']]} and {pid}")
        h["lamps"][rec["color"]] = pid
    for h in heads.values():
        miss = [c for c in "RYG" if c not in h["lamps"]]
        if miss:
            warn(f"Signals: head {h['head']} has no {'/'.join(miss)} pin")
        nodes_used = sorted({p.split("-")[0] for p in h["lamps"].values()})
        if len(nodes_used) > 1:
            warn(f"Signals: head {h['head']} spans nodes {nodes_used}")

    masts = []
    for r in mast_rows:
        masts.append({
            "mast": r.get("mast_user_name", "").replace("Mast ", ""),
            "node": r.get("parent_node_id", ""),
            "heads": r.get("heads", ""),
            "appearance": r.get("appearance", ""),
            "ports": r.get("port_ids", "").split(),
        })
    mast_by = {m["mast"]: m for m in masts}
    for h in heads.values():
        m = mast_by.get(h["mast"])
        if m:
            h["appearance"] = m["appearance"]

    # Node signal names vs the heads actually wired there
    for n in nodes.values():
        wired = {h["head"].split(" ")[0] for h in heads.values() if h["node"] == n["id"]}
        listed = set(n["signals"])
        extra = sorted(listed - wired)
        if extra and n["outputs"]:
            warn(f"Nodes: {n['id']} lists signal(s) {extra} with no lamp pins on that node")

    # Turnouts
    turnouts = []
    for r in table(sheets["TurnoutSummary"], 0):
        name = r.get("Turnout", "")
        if not name:
            continue
        # The turnout's own name; a crossover's half rows (labelled by OS block) share it. The older workbook (v85) has
        # no such column and one row per turnout, so its label is the name.
        jmri = r["JMRI Turnout"] if "JMRI Turnout" in r else name
        if not jmri:
            raise SystemExit(f"TurnoutSummary: row {name!r} has no JMRI Turnout; rebuild v86 with write_inventory.py")
        motor = {pos: device_ports.get(f"{jmri} {pos}", []) for pos in ("N", "R")}
        if not motor["N"] and not motor["R"]:
            warn(f"TurnoutSummary: {name} has no motor pins on the DNOU8 sheet")
        half = ""
        if name != jmri:                    # a crossover half: "<turnout> (<OS block>)"
            if not (name.startswith(jmri + " (") and name.endswith(")")):
                raise SystemExit(f"TurnoutSummary: row {name!r} is not {jmri!r} or {jmri!r} (<OS block>)")
            half = name[len(jmri) + 2:-1]
        t = {
            "turnout": name,
            "name": jmri,
            "half": half,
            "node": r.get("Parent Node", ""),
            "area": r.get("Location/Area", ""),
            "elements": r.get("Switch Elements", ""),
            "motorN": ", ".join(motor["N"]),
            "motorR": ", ".join(motor["R"]),
            "button": r.get("Button", ""),
            "fbN": r.get("Feedback N", ""),
            "fbR": r.get("Feedback R", ""),
            "signals": {},
        }
        motor_nodes = {p.split("-")[0] for p in motor["N"] + motor["R"]}
        if motor_nodes and t["node"] and t["node"] not in motor_nodes:
            warn(f"TurnoutSummary: {name} parent node {t['node']}, but its motor is on {sorted(motor_nodes)}")
        for key, label in (("entry", "Entry Signal"), ("normal", "Normal Exit Signal"), ("reverse", "Reverse Exit Signal")):
            sig = r.get(label, "")
            base = label.replace(" Signal", "")
            ports = {c: r.get(f"{base} Signal {c} Port", "") or r.get(f"{base} {c} Port", "") for c in "RYG"}
            if sig:
                t["signals"][key] = sig
            # Cross-check the sheet's lamp pins against the DNOU8 pin assignments
            for c, pid in ports.items():
                if not pid:
                    continue
                dn = out_pins.get(pid)
                who = dn.get("device") if dn else None
                if not sig:
                    warn(f"TurnoutSummary: {name} {base.lower()} has {c} pin {pid} but no signal name")
                elif not dn:
                    warn(f"TurnoutSummary: {name} {base.lower()} {sig} {c} → {pid}, not on the DNOU8 sheet")
                elif dn.get("head", "").split(" ")[0] != sig.split(" ")[0] or dn.get("color") != c:
                    warn(f"TurnoutSummary: {name} {base.lower()} {sig} {c} → {pid}, but DNOU8 has {who or 'nothing (spare)'} there")
        for f, want in (("button", "BTN"), ("fbN", "N FB"), ("fbR", "R FB")):
            pid = t[f]
            if not pid:
                continue
            dev = next((x["device"] for b in nodes.get(pid.split("-")[0], {}).get("inputs", []) for x in b["pins"] if x["port"] == pid), None)
            if dev != f"{jmri} {want}":
                warn(f"TurnoutSummary: {name} {f} → {pid}, but DNIN8 has {dev or 'nothing'} there")
        turnouts.append(t)

    # Declared boards vs boards found
    for n in nodes.values():
        dec = n.pop("declared", {})
        found_ou = [b["board"] for b in n["outputs"]]
        found_in = [b["board"] for b in n["inputs"]]
        if dec.get("DNOU8") is not None and sorted(dec.get("DNOU8", [])) != sorted(found_ou):
            warn(f"Nodes: {n['id']} declares DNOU8 {dec.get('DNOU8')} but the DNOU8 sheet has {found_ou}")
        if dec.get("DNIN8") is not None and sorted(dec.get("DNIN8", [])) != sorted(found_in):
            warn(f"Nodes: {n['id']} declares DNIN8 {dec.get('DNIN8')} but the DNIN8 sheet has {found_in}")

    for b in boards.values():
        b.pop("_locs", None)
    for rec in out_pins.values():
        rec.pop("_note", None)
    inv = {
        "source": {"file": source, "version": version_of(Path(source))},
        "nodes": sorted(nodes.values(), key=lambda n: node_sort(n["id"])),
        "signals": sorted(heads.values(), key=lambda h: (node_sort(h["node"]), h["head"])),
        "masts": masts,
        "turnouts": turnouts,
        "blocks": blocks,
    }
    return inv


def prune(x):
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


DATES = ("built", "modified")  # when the JSON was built; "modified", a workbook's save date in a JSON built from the file


def stale(path: Path, data: dict) -> bool:
    """True when the file at path is missing or holds other data than `data`, apart from the dates in source."""
    if not path.is_file():
        return True
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True
    new = json.loads(render(data))
    if not isinstance(old, dict) or not isinstance(old.get("source"), dict) or not isinstance(new.get("source"), dict):
        return old != new
    for key in DATES:
        old["source"].pop(key, None)
        new["source"].pop(key, None)
    return old != new


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", type=Path, default=PORTAL / "data", help="where the JSON goes")
    ap.add_argument("-q", "--quiet", action="store_true", help="don't list data warnings")
    ap.add_argument("--check", action="store_true",
                    help="write nothing; exit 1 if the JSON file is out of date with the wiring model")
    args = ap.parse_args()
    try:
        inv = build_inventory()
    except write_inventory.FactsError as exc:
        print(f"{Path(__file__).name}: {exc}", file=sys.stderr)
        return 2
    inv["source"]["built"] = dt.date.today().isoformat()

    outputs = (("wiring-inventory.json", inv),)
    if args.check:
        old = [name for name, data in outputs if stale(args.out_dir / name, data)]
        for name in old:
            print(f"STALE: {shown(args.out_dir / name)} differs from the wiring model; "
                  "rebuild with the same arguments, without --check")
        if not old:
            print("wiring viewer data is current with the wiring model")
        return 1 if old else 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in outputs:
        p = args.out_dir / name
        p.write_text(render(data), encoding="utf-8")
        print(f"wrote {p} ({p.stat().st_size // 1024} KB)")

    n_pins = sum(len(b["pins"]) for n in inv["nodes"] for b in n["outputs"] + n["inputs"])
    print(f"{inv['source']['file']}: {len(inv['nodes'])} nodes, {n_pins} pins, {len(inv['signals'])} heads, "
          f"{len(inv['turnouts'])} turnouts, {len(inv['blocks'])} block sensors")
    if SCRUBBED:
        print(f"scrubbed {len(SCRUBBED)} cell(s) that looked like network details or secrets")
    if WARNINGS:
        print(f"{len(WARNINGS)} data warning(s)" + ("" if args.quiet else ":"))
        if not args.quiet:
            for w in WARNINGS:
                print("  - " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
