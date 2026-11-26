"""refresh_wiring_docs: the steps that turn the imported v84 LCOS inventory into v85.

Each takes the sheet (or workbook) it changes and returns a log or nothing; none reads a file or the public name map.
The steps that need the name map or the imported RGB workbook stay in refresh_wiring_docs.py.
"""
from __future__ import annotations

import re
from collections import defaultdict

from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from refresh_wiring_cells import _unique_keep_order, header_index, rewrite_legacy_node_ids
from refresh_wiring_rules import (
    BLOCK_IN_NOTES,
    HEAD_MAST_RE,
    LED_NAME_RE,
    NEW_5V_OU4,
    RETIRED_S2_TURNOUTS,
    RETIRED_S3_TURNOUTS,
    TURNOUT_SIGNAL_COLS,
    UPPER_TURNOUT_CP,
)


def summarize_node_labels(nodes: Worksheet, dnou: Worksheet, dnin: Worksheet) -> None:
    """Rebuild Turnout / button / FB / signal summary columns from live ports."""
    motors: dict[str, list[str]] = defaultdict(list)
    signals: dict[str, list[str]] = defaultdict(list)
    buttons: dict[str, list[str]] = defaultdict(list)
    fbs: dict[str, list[str]] = defaultdict(list)
    for row in range(2, dnou.max_row + 1):
        nid = dnou.cell(row, 2).value
        dev = dnou.cell(row, 5).value
        dtype = str(dnou.cell(row, 6).value or "")
        if not nid or not isinstance(dev, str):
            continue
        nid = str(nid)
        if dtype == "Turnout Motor":
            name = re.sub(r" [NR]$", "", dev).strip()
            motors[nid].append(name)
        elif dtype == "Searchlight Signal Head":
            m = HEAD_MAST_RE.match(dev)
            signals[nid].append(m.group(1) if m else dev)
        elif dtype in ("Signal LED", "Dwarf Upgrade"):
            m = HEAD_MAST_RE.match(dev)
            if m:
                signals[nid].append(m.group(1))
            elif LED_NAME_RE.match(dev.split()[0] if dev else ""):
                signals[nid].append(dev.split()[0])
    for row in range(2, dnin.max_row + 1):
        nid = dnin.cell(row, 2).value
        dev = dnin.cell(row, 5).value
        if not nid or not isinstance(dev, str):
            continue
        nid = str(nid)
        if dev.endswith(" BTN"):
            buttons[nid].append(dev)
        elif " FB" in dev:
            fbs[nid].append(dev)
    idx = header_index(nodes)
    id_col = idx["Node ID"]
    for row in range(2, nodes.max_row + 1):
        nid = nodes.cell(row, id_col).value
        if not nid:
            continue
        nid = str(nid)
        if "Turnout Names" in idx:
            names = _unique_keep_order(motors.get(nid, []))
            nodes.cell(row, idx["Turnout Names"]).value = ", ".join(names) or None
        if "Button Devices" in idx:
            names = _unique_keep_order(buttons.get(nid, []))
            nodes.cell(row, idx["Button Devices"]).value = ", ".join(names) or None
        if "Turnout Feedback Devices" in idx:
            names = _unique_keep_order(fbs.get(nid, []))
            nodes.cell(row, idx["Turnout Feedback Devices"]).value = ", ".join(names) or None
        if "Signal Names" in idx:
            names = _unique_keep_order(signals.get(nid, []))
            nodes.cell(row, idx["Signal Names"]).value = ", ".join(names) or None


def remap_workbook_node_ids(wb) -> dict[int, str]:
    """Rewrite every C#/D1 token. Returns Nodes-sheet row → legacy Node ID."""
    nodes = wb["Nodes"]
    idx = header_index(nodes)
    id_col = idx["Node ID"]
    legacy_by_row: dict[int, str] = {}
    for row in range(2, nodes.max_row + 1):
        nid = nodes.cell(row, id_col).value
        if nid:
            legacy_by_row[row] = str(nid)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                new = rewrite_legacy_node_ids(cell.value)
                if new != cell.value:
                    cell.value = new
    return legacy_by_row


def add_legacy_node_column(ws: Worksheet, legacy_by_row: dict[int, str]) -> None:
    if "Legacy Node ID" in header_index(ws):
        return
    ws.insert_cols(2)
    ws.cell(1, 2).value = "Legacy Node ID"
    ws.cell(1, 2).font = Font(bold=True)
    for row, old in legacy_by_row.items():
        ws.cell(row, 2).value = old


def sort_nodes_by_address(ws: Worksheet) -> None:
    idx = header_index(ws)
    addr_col = idx["Address"]
    rows: list[tuple[int, list]] = []
    max_col = ws.max_column
    for row in range(2, ws.max_row + 1):
        vals = [ws.cell(row, c).value for c in range(1, max_col + 1)]
        if not any(v is not None for v in vals):
            continue
        addr = ws.cell(row, addr_col).value
        try:
            key = int(addr)
        except (TypeError, ValueError):
            key = 999
        rows.append((key, vals))
    rows.sort(key=lambda item: item[0])
    for i, (_, vals) in enumerate(rows, start=2):
        for c, v in enumerate(vals, start=1):
            ws.cell(i, c).value = v
    extra = ws.max_row - (1 + len(rows))
    if extra > 0:
        ws.delete_rows(2 + len(rows), extra)


def refresh_block_sensors(ws: Worksheet, occ: dict[str, str]) -> list[str]:
    log: list[str] = []
    idx = header_index(ws)
    name_col = idx["Block Section Name"]
    notes_col = idx["Notes"]
    port_col = idx["Port ID"]
    for row in range(2, ws.max_row + 1):
        notes = ws.cell(row, notes_col).value
        if not isinstance(notes, str):
            continue
        m = BLOCK_IN_NOTES.search(notes)
        if not m:
            continue
        hw = f"Block {m.group(1)}"
        public = occ.get(hw)
        if not public:
            continue
        old = ws.cell(row, name_col).value
        if old != public:
            ws.cell(row, name_col).value = public
            log.append(f"{ws.cell(row, port_col).value}: {old!r} → {public!r} ({hw})")
    return log


def ensure_ou4_boards(ws: Worksheet) -> list[str]:
    """Append empty C*-OU4-1..8 5V rows so overlay / the schematic see the new boards."""
    log: list[str] = []
    have: set[str] = set()
    loc_by_node: dict[str, str] = {}
    for row in range(2, ws.max_row + 1):
        pid = ws.cell(row, 1).value
        parent = ws.cell(row, 2).value
        loc = ws.cell(row, 3).value
        if pid:
            have.add(str(pid))
        if parent and loc and str(parent) not in loc_by_node:
            loc_by_node[str(parent)] = str(loc)
    for nid in NEW_5V_OU4:
        loc = loc_by_node.get(nid, "")
        for ch in range(1, 9):
            port = f"{nid}-OU4-{ch}"
            if port in have:
                continue
            ws.append(
                (
                    port,
                    nid,
                    loc,
                    ch,
                    None,
                    None,
                    "5V",
                    "NEW 5V DNOU8 (OU4) for second searchlight disc",
                )
            )
            log.append(f"add {port}")
    return log


def overlay_dnou8(ws: Worksheet, wiring: list[dict[str, str]]) -> list[str]:
    log: list[str] = []
    by_port: dict[str, int] = {}
    for row in range(2, ws.max_row + 1):
        pid = ws.cell(row, 1).value
        if pid:
            by_port[str(pid)] = row
    for r in wiring:
        port = r["port_id"]
        channel = int(port.rsplit("-", 1)[-1])
        prev = None
        if port in by_port:
            prev = ws.cell(by_port[port], 5).value
        note = (
            f"HART Digicon {r.get('lcos_recipe', 'STOP/APPROACH/CLEAR')}; "
            f"lamp {r.get('lamp_color') or r.get('head_role')}; "
            f"MQTT {r['topic']}; packed {r['packed']} "
            f"(node {r['mqtt_node']} sig {r['signal_index']})"
        )
        if prev and str(prev) != r["user_name"]:
            note += f"; was {prev}"
        vals = (
            port,
            r["parent_node_id"],
            r["board_location"],
            channel,
            r["user_name"],
            "Searchlight Signal Head",
            "5V",
            note,
        )
        if port in by_port:
            rr = by_port[port]
            for col, v in enumerate(vals, start=1):
                ws.cell(rr, col, v)
            log.append(f"overlay {port}: {prev!r} → {r['user_name']!r}")
        else:
            ws.append(vals)
            log.append(f"append {port}: {r['user_name']}")
    return log


def first_5v_cal_ports(dnou_ws: Worksheet, bs_ws: Worksheet) -> dict[str, str]:
    """Pin 8 of the lowest-numbered 5V OU on each node that has block sensors."""
    nodes: set[str] = set()
    nidx = header_index(bs_ws)
    ncol = nidx.get("Node ID")
    if ncol:
        for row in range(2, bs_ws.max_row + 1):
            nid = bs_ws.cell(row, ncol).value
            if nid:
                nodes.add(str(nid))
    fives: dict[str, set[int]] = defaultdict(set)
    for row in range(2, dnou_ws.max_row + 1):
        port = dnou_ws.cell(row, 1).value
        parent = dnou_ws.cell(row, 2).value
        rail = dnou_ws.cell(row, 7).value
        if not port or str(parent) not in nodes or str(rail) != "5V":
            continue
        parts = str(port).split("-")
        if len(parts) < 2 or not parts[1].startswith("OU"):
            continue
        try:
            fives[str(parent)].add(int(parts[1][2:]))
        except ValueError:
            continue
    return {nid: f"{nid}-OU{min(ous)}-8" for nid, ous in fives.items() if ous}


def stamp_block_sensor_cal(
    ws: Worksheet, cal_ports: dict[str, str]
) -> list[str]:
    """Reserve first-5V-OU pin 8 for occupancy detector calibration current."""
    log: list[str] = []
    by_port: dict[str, int] = {}
    loc_by_node: dict[str, str] = {}
    for row in range(2, ws.max_row + 1):
        pid = ws.cell(row, 1).value
        parent = ws.cell(row, 2).value
        loc = ws.cell(row, 3).value
        if pid:
            by_port[str(pid)] = row
        if parent and loc and str(parent) not in loc_by_node:
            loc_by_node[str(parent)] = str(loc)
    for nid, port in sorted(cal_ports.items()):
        prev = None
        channel = 8
        loc = loc_by_node.get(nid, "")
        note = "Block sensor calibration current (first 5V OU pin 8); not a lamp"
        if port in by_port:
            prev = ws.cell(by_port[port], 5).value
            if prev:
                note += f"; was {prev}"
            loc = ws.cell(by_port[port], 3).value or loc
        vals = (
            port,
            nid,
            loc,
            channel,
            "Block sensor calibration",
            "Block Sensor Cal",
            "5V",
            note,
        )
        if port in by_port:
            rr = by_port[port]
            for col, v in enumerate(vals, start=1):
                ws.cell(rr, col, v)
            log.append(f"cal {port}: {prev!r} → Block sensor calibration")
        else:
            ws.append(vals)
            log.append(f"cal add {port}")
    return log


def clear_retired_s3_rgb(ws: Worksheet) -> list[str]:
    """Drop leftover CP3 RGB on C3, stray S3-14 on C13, leftover S2 on C2. Remove C3-OU3."""
    log: list[str] = []
    drop_rows: list[int] = []
    for row in range(2, ws.max_row + 1):
        pid = str(ws.cell(row, 1).value or "")
        if pid.startswith("C3-OU3-"):
            drop_rows.append(row)
            continue
        prev = ws.cell(row, 5).value
        if pid.startswith("C3-OU2-") and pid != "C3-OU2-8" and prev:
            ws.cell(row, 5).value = None
            ws.cell(row, 6).value = None
            ws.cell(row, 8).value = f"spare (CP3 leftover RGB removed; was {prev})"
            log.append(f"clear {pid}: {prev!r}")
        elif pid == "C13-OU1-7" and prev and str(prev).startswith("S3-"):
            ws.cell(row, 5).value = None
            ws.cell(row, 6).value = None
            ws.cell(row, 8).value = f"spare (CP3 leftover RGB removed; was {prev})"
            log.append(f"clear {pid}: {prev!r}")
        elif pid in ("C2-OU2-7",) or pid.startswith("C2-OU3-"):
            ch = int(pid.rsplit("-", 1)[-1])
            # 24RB lives on C2-OU3-6/7/8 — keep that dwarf; drop leftover S2 only.
            if pid.startswith("C2-OU3-") and ch >= 6:
                continue
            if prev and str(prev).startswith("S2-"):
                ws.cell(row, 5).value = None
                ws.cell(row, 6).value = None
                ws.cell(row, 8).value = "spare"
                log.append(f"clear {pid}: {prev!r}")
    for row in reversed(drop_rows):
        pid = ws.cell(row, 1).value
        ws.delete_rows(row)
        log.append(f"drop {pid}")
    return log


def clear_s3_turnout_signals(ws: Worksheet) -> list[str]:
    """Switch 15–21 / 25–29 no longer have leftover S3/S2 RGB faces."""
    log: list[str] = []
    idx = header_index(ws)
    tcol = idx["Turnout"]
    retired = set(RETIRED_S3_TURNOUTS + RETIRED_S2_TURNOUTS)
    for row in range(2, ws.max_row + 1):
        name = str(ws.cell(row, tcol).value or "")
        if name not in retired:
            continue
        changed = False
        for col_name in TURNOUT_SIGNAL_COLS:
            col = idx.get(col_name)
            if not col:
                continue
            if ws.cell(row, col).value:
                ws.cell(row, col).value = None
                changed = True
        if changed:
            log.append(f"{name}: cleared leftover S2/S3 faces")
    return log


def tag_upper_turnouts_cp(ws: Worksheet) -> list[str]:
    """S4/S5/S6 plant switches get CP4/CP5/CP6 location labels."""
    log: list[str] = []
    idx = header_index(ws)
    tcol = idx["Turnout"]
    loc_col = idx.get("Location/Area")
    if not loc_col:
        return log
    for row in range(2, ws.max_row + 1):
        name = str(ws.cell(row, tcol).value or "")
        loc = UPPER_TURNOUT_CP.get(name)
        if not loc:
            continue
        prev = ws.cell(row, loc_col).value
        if prev != loc:
            ws.cell(row, loc_col).value = loc
            log.append(f"{name}: {prev!r} → {loc!r}")
    return log


def refresh_nodes(ws: Worksheet) -> None:
    idx = header_index(ws)
    loc_col = idx.get("Location")
    boards_5v_col = idx.get("5V Boards")
    num_5v_col = idx.get("Num 5V")
    leds_col = idx.get("Num Signal LEDs")
    id_col = idx["Node ID"]
    boards_12 = idx.get("12V Boards")
    num_12 = idx.get("Num 12V")
    for row in range(2, ws.max_row + 1):
        nid = ws.cell(row, id_col).value
        # D5 is helix DCC (radio 5). Do not invent 5V signal boards there.
        if nid == "D5":
            if loc_col:
                ws.cell(row, loc_col).value = "Helix DCC (radio 5; no Digicon DNOU8)"
            if boards_5v_col:
                ws.cell(row, boards_5v_col).value = 0
            if num_5v_col:
                ws.cell(row, num_5v_col).value = 0
            if leds_col:
                ws.cell(row, leds_col).value = 0
        if nid == "C1":
            if loc_col:
                ws.cell(row, loc_col).value = "Helix - Lower (Princess)"
            if boards_5v_col:
                ws.cell(row, boards_5v_col).value = 3
            if num_5v_col:
                ws.cell(row, num_5v_col).value = 24
            dnou = idx.get("DNOU8")
            if dnou:
                ws.cell(row, dnou).value = "OU1, OU2, OU3, OU4"
        if nid == "C2":
            if loc_col:
                ws.cell(row, loc_col).value = "North - Lower (East End west 24)"
            if boards_12:
                ws.cell(row, boards_12).value = 0
            if num_12:
                ws.cell(row, num_12).value = 0
            if boards_5v_col:
                ws.cell(row, boards_5v_col).value = 3
            if num_5v_col:
                ws.cell(row, num_5v_col).value = 24
            dnou = idx.get("DNOU8")
            if dnou:
                ws.cell(row, dnou).value = "OU1, OU2, OU3"
        if nid == "C3":
            if loc_col:
                ws.cell(row, loc_col).value = "West - Lower (Switch 15–21 motors)"
            if boards_5v_col:
                ws.cell(row, boards_5v_col).value = 1
            if num_5v_col:
                ws.cell(row, num_5v_col).value = 8
            used_col = idx.get("5V Used")
            free_col = idx.get("5V Free")
            leds_col_n = idx.get("Num Signal LEDs")
            led_dev_col = idx.get("Signal LED Devices")
            if used_col:
                ws.cell(row, used_col).value = 1
            if free_col:
                ws.cell(row, free_col).value = 7
            if leds_col_n:
                ws.cell(row, leds_col_n).value = 0
            if led_dev_col:
                ws.cell(row, led_dev_col).value = 0
            dnou = idx.get("DNOU8")
            if dnou:
                ws.cell(row, dnou).value = "OU1, OU2"
        if nid == "C4":
            if loc_col:
                ws.cell(row, loc_col).value = "West - Lower (Brick / Plane)"
            if boards_5v_col:
                ws.cell(row, boards_5v_col).value = 3
            if num_5v_col:
                ws.cell(row, num_5v_col).value = 24
            dnou = idx.get("DNOU8")
            if dnou:
                ws.cell(row, dnou).value = "OU1, OU2, OU3, OU4"
        if nid == "C11" and loc_col:
            ws.cell(row, loc_col).value = "Helix (Princess east 40 + balloon)"
        if nid == "C12" and loc_col:
            ws.cell(row, loc_col).value = "North - Lower (East End 34 + Switch 25–33)"
        if nid == "C13":
            if loc_col:
                ws.cell(row, loc_col).value = "West - Lower (Barn)"
            if boards_5v_col:
                ws.cell(row, boards_5v_col).value = 3
            if num_5v_col:
                ws.cell(row, num_5v_col).value = 24
            dnou = idx.get("DNOU8")
            if dnou:
                ws.cell(row, dnou).value = "OU1, OU2, OU3, OU4"


def add_digicon_sheet(wb, wiring: list[dict[str, str]], heads: list[dict[str, str]]) -> None:
    if "DigiconSignals" in wb.sheetnames:
        del wb["DigiconSignals"]
    ws = wb.create_sheet("DigiconSignals", 0)
    ws["A1"] = "HART Digicon searchlight heads (from docs/wiring/signals/signal_wiring.csv)"
    ws["A1"].font = Font(bold=True, size=14)
    ws.merge_cells("A1:L1")
    headers = [
        "port_id",
        "parent_node_id",
        "mqtt_node",
        "board_location",
        "signal_index",
        "packed",
        "system_name",
        "user_name",
        "mast_user_name",
        "disc_role",
        "head_role",
        "lamp_color",
        "topic",
        "notes",
    ]
    for i, h in enumerate(headers, start=1):
        cell = ws.cell(2, i, h)
        cell.font = Font(bold=True)
    for r_i, row in enumerate(wiring, start=3):
        for c_i, key in enumerate(headers, start=1):
            ws.cell(r_i, c_i, row.get(key))
    start = 3 + len(wiring) + 2
    ws.cell(start, 1, "Masts (docs/wiring/signals/signal_head_plan.csv)")
    ws.cell(start, 1).font = Font(bold=True, size=12)
    m_headers = list(heads[0].keys()) if heads else []
    for i, h in enumerate(m_headers, start=1):
        cell = ws.cell(start + 1, i, h)
        cell.font = Font(bold=True)
    for r_i, row in enumerate(heads, start=start + 2):
        for c_i, key in enumerate(m_headers, start=1):
            ws.cell(r_i, c_i, row.get(key))
    for col in range(1, 13):
        ws.column_dimensions[get_column_letter(col)].width = 22
