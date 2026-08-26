#!/usr/bin/env python3
"""Refresh LCOS inventory + Digicon as-built workbooks from hart CSVs.

Reads:
  cats/data/occupancy_bindings.csv
  cats/data/signal_wiring.csv
  cats/data/signal_head_plan.csv
  cats/data/signal_mast_plan.csv
  docs/wiring/imported/LCOS_Layout_Inventory_v84.xlsx
  docs/wiring/imported/signals_asbuilt_abs_v1.xlsx
  docs/wiring/imported/signals_split_v8.xlsx

Writes:
  docs/wiring/LCOS_Layout_Inventory_v85.xlsx
  docs/wiring/signals_asbuilt_abs_v2.xlsx
  docs/wiring/signals_split_v8.xlsx  (historical RGB plan + README sheet)
"""
from __future__ import annotations

import csv
import re
import shutil
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

ROOT = Path(__file__).resolve().parents[3]
WIRING = ROOT / "docs/wiring"
IMPORTED = WIRING / "imported"
CATS = ROOT / "cats/data"

BLOCK_IN_NOTES = re.compile(r"Block\s+(\d+-\d+)")


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def occupancy_by_hw() -> dict[str, str]:
    """MQTT occupancy userName (Block n-n) → public block name."""
    groups: dict[str, list[str]] = defaultdict(list)
    for row in load_csv(CATS / "occupancy_bindings.csv"):
        hw = (row.get("occupancy_sensor_user_name") or "").strip()
        name = (row.get("block_user_name") or "").strip()
        if hw and name and name not in groups[hw]:
            groups[hw].append(name)

    picked: dict[str, str] = {}
    for hw, names in groups.items():
        os_names = [n for n in names if n.startswith("OS ")]
        other = [n for n in names if n not in os_names]
        if os_names and other:
            picked[hw] = f"{os_names[0]} / {other[0]}"
        else:
            picked[hw] = os_names[0] if os_names else other[0]
    return picked


def replace_in_cell(value, replacements: list[tuple[str, str]]):
    if not isinstance(value, str) or not value:
        return value
    out = value
    for old, new in replacements:
        if old in out:
            out = out.replace(old, new)
    return out


def walk_replace(ws: Worksheet, replacements: list[tuple[str, str]]) -> int:
    n = 0
    for row in ws.iter_rows():
        for cell in row:
            new = replace_in_cell(cell.value, replacements)
            if new != cell.value:
                cell.value = new
                n += 1
    return n


NAME_REPLACEMENTS: list[tuple[str, str]] = [
    # Long JMRI mast userNames → Digicon (longest first)
    ("West Yard West East Main Ext", "117RB"),
    ("West Yard East OS 117b", "117LA"),
    ("West Yard East Yard T6", "117LB"),
    ("West Yard West OS 117", "117RA"),
    ("East End West Yard Track 1", "111RB"),
    ("East End West Main West", "111RA"),
    ("East End South OS 112", "112R"),
    ("East End South OS 110", "110R"),
    ("East End East OS 111a", "111L"),
    ("East End East Lead", "112L"),
    ("Princess North McKees Rocks", "115LB"),
    ("Princess South McKeesport", "114LB"),
    ("Princess West OS 113a", "113RB"),
    ("Princess West OS 113b", "113RA"),
    ("Princess East McKeesport", "120R"),
    ("Princess East McKees Rocks", "120L"),
    ("Princess East K-1", "115LA"),
    ("Princess East K-2", "114LA"),
    ("Plane East East Main Ext", "102LB"),
    ("Plane East OS 102", "102LA"),
    ("Brick East Main West", "100L"),
    ("Brick West Yard 1", "101RA"),
    ("Brick West Yard 2", "101RB"),
    ("Brick W-1 West Stub", "101LA"),
    ("Brick W-2 West Stub", "101LB"),
    # OS public names (ADR-005: CP lives in comment, not the name)
    ("OS 117b (West Yard)", "OS 117b"),
    ("OS 119 (West Yard)", "OS 119"),
    ("OS 118 (West Yard)", "OS 118"),
    ("OS 117 (West Yard)", "OS 117"),
    ("OS 116 (West Yard)", "OS 116"),
    ("OS 115 (Princess)", "OS 115"),
    ("OS 114 (Princess)", "OS 114"),
    ("OS 113b (Princess)", "OS 113b"),
    ("OS 113a (Princess)", "OS 113a"),
    ("OS 112 (East End)", "OS 112"),
    ("OS 111b (East End)", "OS 111b"),
    ("OS 111a (East End)", "OS 111a"),
    ("OS 110 (East End)", "OS 110"),
    ("OS 109 (East End)", "OS 109"),
    ("OS 108 (East End)", "OS 108"),
    ("OS 107 (East End)", "OS 107"),
    ("OS 106 (South Yard)", "OS 106"),
    ("OS 105 (South Yard)", "OS 105"),
    ("OS 104 (South Yard)", "OS 104"),
    ("OS 103 (South Yard)", "OS 103"),
    ("OS 102 (Plane)", "OS 102"),
    ("OS 101 (Brick)", "OS 101"),
    ("OS 100 (Brick)", "OS 100"),
    ("Main West Brick–Plane", "Brick-Plane"),
    ("Main West Brick-Plane", "Brick-Plane"),
    # Yard plates (longest first so T11 before T1)
    ("Yard Track 5", "S-5"),
    ("Yard Track 4", "S-4"),
    ("Yard Track 3", "S-3"),
    ("Yard Track 2", "S-2"),
    ("Yard Track 1", "S-1"),
    ("West Yard Track 2", "W-2"),
    ("West Yard Track 1", "W-1"),
    ("West Yard 2", "W-2"),
    ("West Yard 1", "W-1"),
    ("Yard T6", "Barn"),
    ("Yard T1", "Scale"),
    ("track/signalmast/464", "track/signalhead/IH438 / IH439"),
]


# TurnoutSummary Digicon faces (searchlight heads, not RGB R/Y/G).
# Entry / Normal Exit / Reverse Exit columns keep the old 3-slot shape.
TURNOUT_DIGICON: dict[str, dict[str, object]] = {
    "Switch 100": {
        "entry": "100L",
        "entry_ports": ("C4-OU3-1", "C4-OU3-2", None),
        "normal": None,
        "reverse": None,
    },
    "Switch 101": {
        "entry": None,
        "normal": "101RA",
        "normal_ports": ("C4-OU2-5", None, None),
        "reverse": "101RB",
        "reverse_ports": ("C4-OU2-6", None, None),
    },
    "Switch 102": {
        "entry": "102LA",
        "entry_ports": ("C4-OU2-3", None, None),
        "normal": None,
        "reverse": "102LB",
        "reverse_ports": ("C4-OU2-1", "C4-OU2-2", None),
    },
    "Switch 111": {
        "entry": "111L",
        "entry_ports": ("C7-OU2-3", "C7-OU2-4", None),
        "normal": "111RA",
        "normal_ports": ("C7-OU2-1", "C7-OU2-2", None),
        "reverse": "111RB",
        "reverse_ports": ("C7-OU2-5", None, None),
    },
    "Switch 110": {
        "entry": "110R",
        "entry_ports": ("C7-OU3-2", None, None),
        "normal": None,
        "reverse": None,
    },
    "Switch 112": {
        "entry": "112L",
        "entry_ports": ("C7-OU2-6", "C7-OU3-1", None),
        "normal": None,
        "reverse": "112R",
        "reverse_ports": ("C7-OU3-3", "C7-OU3-4", None),
    },
    "Switch 113": {
        "entry": "113RA",
        "entry_ports": ("D1-OU2-4", "D1-OU2-5", None),
        "normal": None,
        "reverse": "113RB",
        "reverse_ports": ("D1-OU2-6", "D1-OU2-7", None),
    },
    "Switch 114": {
        "entry": "120R",
        "entry_ports": ("D1-OU2-3", None, None),
        "normal": "114LB",
        "normal_ports": ("D1-OU2-8", "D1-OU3-1", None),
        "reverse": "114LA",
        "reverse_ports": ("D1-OU3-4", None, None),
    },
    "Switch 115": {
        "entry": "120L",
        "entry_ports": ("D1-OU3-2", None, None),
        "normal": "115LB",
        "normal_ports": ("D1-OU2-1", "D1-OU2-2", None),
        "reverse": "115LA",
        "reverse_ports": ("D1-OU3-3", None, None),
    },
    "Switch 117": {
        "entry": "117RA",
        "entry_ports": ("C1-OU2-1", "C1-OU2-2", None),
        "normal": "117LA",
        "normal_ports": ("C1-OU2-6", "C1-OU3-1", None),
        "reverse": "117LB / 117RB",
        "reverse_ports": ("C1-OU2-3", "C1-OU2-4", "C1-OU2-5"),
    },
}


def header_index(ws: Worksheet) -> dict[str, int]:
    return {str(c.value): i for i, c in enumerate(next(ws.iter_rows(min_row=1, max_row=1)), start=1) if c.value}


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
            f"HART Digicon searchlight; MQTT {r['topic']}; "
            f"packed {r['packed']} (node {r['mqtt_node']} sig {r['signal_index']})"
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


def refresh_nodes(ws: Worksheet) -> None:
    idx = header_index(ws)
    loc_col = idx.get("Location")
    boards_5v_col = idx.get("5V Boards")
    num_5v_col = idx.get("Num 5V")
    leds_col = idx.get("Num Signal LEDs")
    id_col = idx["Node ID"]
    for row in range(2, ws.max_row + 1):
        nid = ws.cell(row, id_col).value
        if nid == "D1":
            if loc_col:
                ws.cell(row, loc_col).value = "Princess / Helix DCC node"
            if boards_5v_col:
                ws.cell(row, boards_5v_col).value = 2
            if num_5v_col:
                ws.cell(row, num_5v_col).value = 2
            if leds_col:
                ws.cell(row, leds_col).value = 12
        if nid == "C1" and loc_col:
            ws.cell(row, loc_col).value = "Helix - Lower (Barn / West Yard)"
        if nid == "C7" and loc_col:
            current = ws.cell(row, loc_col).value or ""
            if "East End" not in str(current):
                ws.cell(row, loc_col).value = f"{current} (Digicon East End heads on OU2/OU3)"


def refresh_turnout_summary(ws: Worksheet) -> list[str]:
    log: list[str] = []
    idx = header_index(ws)
    tcol = idx["Turnout"]
    for row in range(2, ws.max_row + 1):
        name = ws.cell(row, tcol).value
        spec = TURNOUT_DIGICON.get(str(name) if name else "")
        if not spec:
            continue

        def set_group(prefix: str, signal_key: str, ports_key: str) -> None:
            sig = spec.get(signal_key)
            if not sig:
                return
            ws.cell(row, idx[prefix]).value = sig
            ports = spec.get(ports_key) or (None, None, None)
            r_key, y_key, g_key = (
                f"{prefix} R Port",
                f"{prefix} Y Port",
                f"{prefix} G Port",
            )
            # Reuse RGB port columns as head 1/2/3 (searchlights, not lamp colors).
            if r_key in idx:
                ws.cell(row, idx[r_key]).value = ports[0]
            if y_key in idx:
                ws.cell(row, idx[y_key]).value = ports[1]
            if g_key in idx:
                ws.cell(row, idx[g_key]).value = ports[2]

        set_group("Entry Signal", "entry", "entry_ports")
        set_group("Normal Exit Signal", "normal", "normal_ports")
        set_group("Reverse Exit Signal", "reverse", "reverse_ports")
        log.append(f"{name}: Digicon faces {spec.get('entry')} / {spec.get('normal')} / {spec.get('reverse')}")
    return log


def add_digicon_sheet(wb, wiring: list[dict[str, str]], heads: list[dict[str, str]]) -> None:
    if "DigiconSignals" in wb.sheetnames:
        del wb["DigiconSignals"]
    ws = wb.create_sheet("DigiconSignals", 0)
    ws["A1"] = "HART Digicon searchlight heads (from cats/data/signal_wiring.csv)"
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
        "head_role",
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
    ws.cell(start, 1, "Masts (cats/data/signal_head_plan.csv)")
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


def rebuild_asbuilt_inventory(ws: Worksheet, wiring: list[dict[str, str]], masts: list[dict[str, str]]) -> None:
    heads_by_mast: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in wiring:
        heads_by_mast[row["mast_user_name"]].append(row)
    # Keep header
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    plan_by_name = {r["proposed_mast_name"]: r for r in masts}
    for mast, head_rows in heads_by_mast.items():
        head_rows = sorted(head_rows, key=lambda r: int(r["signal_index"]))
        plan = plan_by_name.get(mast, {})
        packed = " ".join(r["packed"] for r in head_rows)
        ports = " ".join(r["port_id"] for r in head_rows)
        topics = " ".join(r["topic"] for r in head_rows)
        ws.append(
            [
                plan.get("cp") or head_rows[0].get("board_location"),
                mast,
                len(head_rows),
                plan.get("direction") or "",
                f"({plan.get('panel_x')},{plan.get('panel_y')}) {plan.get('edge')}" if plan else "",
                plan.get("protects_switch") or "",
                head_rows[0]["mqtt_node"],
                head_rows[0]["parent_node_id"],
                packed,
                ports,
                topics,
                plan.get("mast_system_name") or "",
                "double" if len(head_rows) == 2 else "single",
                "hart-aar SL-2-digicon" if len(head_rows) == 2 else "AAR-1946 SL-1-low",
                head_rows[0].get("notes") or "",
            ]
        )


def add_split_readme(path: Path) -> None:
    wb = load_workbook(path)
    if "README" in wb.sheetnames:
        del wb["README"]
    ws = wb.create_sheet("README", 0)
    lines = [
        ("signals_split_v8 — frozen planned RGB matrix", True),
        ("", False),
        ("This workbook is the Nov 2025 RGB LED plan (S1-1 … S6-15, SW1–SW18, SCXA).", False),
        ("Lower-deck Digicon searchlights (100L, 102LA, 117LA, 114LA, …) are NOT in this file.", False),
        ("", False),
        ("Live lower-deck signal matrix:", False),
        ("  docs/wiring/signals_asbuilt_abs_v2.xlsx", False),
        ("Port / MQTT / LCOS overlay:", False),
        ("  cats/data/signal_wiring.csv", False),
        ("  docs/wiring/LCOS_Layout_Inventory_v85.xlsx  (DigiconSignals + DNOU8)", False),
        ("", False),
        ("Upper-deck CP4–CP6 (Helix/North/Peninsula Upper) still use this RGB plan.", False),
        ("Do not rename S1-* here to Digicon 11x names — those are a different plant.", False),
    ]
    for i, (text, bold) in enumerate(lines, start=1):
        ws.cell(i, 1, text).font = Font(bold=bold, size=14 if bold else 11)
        ws.row_dimensions[i].height = 18
    ws.column_dimensions["A"].width = 100
    ws["A1"].alignment = Alignment(wrap_text=True)
    wb.save(path)


def refresh_inventory() -> Path:
    src = IMPORTED / "LCOS_Layout_Inventory_v84.xlsx"
    dest = WIRING / "LCOS_Layout_Inventory_v85.xlsx"
    shutil.copy2(src, dest)
    wb = load_workbook(dest)
    occ = occupancy_by_hw()
    wiring = load_csv(CATS / "signal_wiring.csv")
    heads = load_csv(CATS / "signal_head_plan.csv")

    bs_log = refresh_block_sensors(wb["BlockSensors"], occ)
    dnou_log = overlay_dnou8(wb["DNOU8"], wiring)
    ts_log = refresh_turnout_summary(wb["TurnoutSummary"])
    refresh_nodes(wb["Nodes"])
    add_digicon_sheet(wb, wiring, heads)
    wb.save(dest)

    print(f"wrote {dest}")
    print(f"  BlockSensors renames: {len(bs_log)}")
    for line in bs_log:
        print(f"    {line}")
    print(f"  DNOU8 overlays: {len(dnou_log)}")
    for line in dnou_log:
        print(f"    {line}")
    print(f"  TurnoutSummary Digicon: {len(ts_log)}")
    for line in ts_log:
        print(f"    {line}")
    return dest


# Princess sheet / all_logic column order (asbuilt v1).
PRINCESS_LOGIC_HEADERS = [
    "Control_Point",
    "Location",
    "Signal",
    "Signal_Block",
    "Route_From",
    "Route_To",
    "Block1",
    "Block2",
    "Next_Signal",
    "SW100",
    "SW101",
    "SW102",
    "SW117",
    "SW111",
    "SW110",
    "SW112",
    "SW113",
    "SW114",
    "SW115",
    "B1",
    "B2",
    "BO_Rule",
    "BO_Aspect",
    "MQTT_Out",
    "Notes",
]

# Clear / Approach / Stop occupancy flags (B1 = stop, B2 = approach).
_DWARF_ASPECTS = (
    (None, None, "R281", "Clear", "Green"),
    (None, "X", "R285", "Approach", "Yellow"),
    ("X", None, "R292", "Stop", "Red"),
)


def _princess_dwarf_rows() -> list[dict[str, object]]:
    """ABS rows for 114LA / 115LA / 120R / 120L (SML PAIRS + SIGNAL_FACING)."""
    loc = "Princess / Helix DCC"
    routes = [
        # K-1 dwarf, westbound. 115 Closed = K-1; dest 111L (113 N) or 112L (113 R).
        dict(
            Signal="115LA",
            Signal_Block="K-1",
            Route_From="K-1",
            Route_To="West Main Ext",
            Block1="OS 115",
            Block2="West Main Ext",
            Next_Signal="111L",
            SW113="N",
            SW115="N",
            ih="IH142",
            Notes="K-1 dwarf (SL-1-low). SW115 Closed = K-1. Dest 111L when 113 Normal.",
        ),
        dict(
            Signal="115LA",
            Signal_Block="K-1",
            Route_From="K-1",
            Route_To="East Lead",
            Block1="OS 115",
            Block2="East Lead",
            Next_Signal="112L",
            SW113="R",
            SW115="N",
            ih="IH142",
            Notes="K-1 dwarf. Dest 112L when 113 Reverse (East Lead).",
        ),
        # K-2 dwarf, westbound. 114 Closed = K-2.
        dict(
            Signal="114LA",
            Signal_Block="K-2",
            Route_From="K-2",
            Route_To="West Main Ext",
            Block1="OS 114",
            Block2="West Main Ext",
            Next_Signal="111L",
            SW113="N",
            SW114="N",
            ih="IH143",
            Notes="K-2 dwarf (SL-1-low). SW114 Closed = K-2. Dest 111L when 113 Normal.",
        ),
        dict(
            Signal="114LA",
            Signal_Block="K-2",
            Route_From="K-2",
            Route_To="East Lead",
            Block1="OS 114",
            Block2="East Lead",
            Next_Signal="112L",
            SW113="R",
            SW114="N",
            ih="IH143",
            Notes="K-2 dwarf. Dest 112L when 113 Reverse (East Lead).",
        ),
        # Balloon A48: south-track 120R (IH134) protects Rocks / OS 115; dest 120L.
        dict(
            Signal="120R",
            Signal_Block="McKees Rocks",
            Route_From="McKeesport",
            Route_To="McKees Rocks",
            Block1="McKees Rocks",
            Block2="OS 115",
            Next_Signal="120L",
            SW114="R",
            ih="IH134",
            Notes=(
                "Balloon connector (SL-1-low). A48 east ends join: 120R/IH134 on McKeesport "
                "track protects Rocks / OS 115. SW114 Thrown = McKeesport."
            ),
        ),
        # North-track 120L (IH141) protects McKeesport / OS 114; dest 120R.
        dict(
            Signal="120L",
            Signal_Block="McKeesport",
            Route_From="McKees Rocks",
            Route_To="McKeesport",
            Block1="McKeesport",
            Block2="OS 114",
            Next_Signal="120R",
            SW115="R",
            ih="IH141",
            Notes=(
                "Balloon connector (SL-1-low). 120L/IH141 on Rocks track protects McKeesport / "
                "OS 114. SML also Stop if McKees Rocks occupied. SW115 Thrown = Rocks."
            ),
        ),
    ]
    out: list[dict[str, object]] = []
    for route in routes:
        ih = route.pop("ih")
        for b1x, b2x, rule, aspect, color in _DWARF_ASPECTS:
            row = {h: None for h in PRINCESS_LOGIC_HEADERS}
            row.update(
                Control_Point="Princess",
                Location=loc,
                B1=b1x,
                B2=b2x,
                BO_Rule=rule,
                BO_Aspect=aspect,
                MQTT_Out=f"{ih}={color}",
                **route,
            )
            out.append(row)
    return out


def _logic_signals(ws: Worksheet) -> set[str]:
    idx = header_index(ws)
    col = idx.get("Signal")
    if not col:
        return set()
    found: set[str] = set()
    for row in range(2, ws.max_row + 1):
        v = ws.cell(row, col).value
        if v:
            found.add(str(v))
    return found


def append_princess_dwarf_logic(wb) -> int:
    """Add 114LA/115LA/120R/120L ABS rows; strip leftover 3-head MQTT on 114LB/115LB."""
    added = 0
    new_rows = _princess_dwarf_rows()
    for sheet_name in ("Princess", "all_logic"):
        ws = wb[sheet_name]
        have = _logic_signals(ws)
        idx = header_index(ws)
        for spec in new_rows:
            if spec["Signal"] in have:
                continue
            ws.append([spec.get(h) for h in PRINCESS_LOGIC_HEADERS])
            added += 1
        # 114LB / 115LB were authored as triples; IH134/IH141 are now 120R/120L.
        mqtt_col = idx.get("MQTT_Out")
        notes_col = idx.get("Notes")
        sig_col = idx.get("Signal")
        if mqtt_col and sig_col:
            for row in range(2, ws.max_row + 1):
                sig = ws.cell(row, sig_col).value
                mqtt = ws.cell(row, mqtt_col).value
                if not isinstance(mqtt, str):
                    continue
                if sig == "115LB" and "IH134" in mqtt:
                    ws.cell(row, mqtt_col).value = mqtt.replace(" IH134=Red", "").replace(" IH134=Green", "").replace(
                        " IH134=Yellow", ""
                    )
                if sig == "114LB" and "IH141" in mqtt:
                    ws.cell(row, mqtt_col).value = mqtt.replace(" IH141=Red", "").replace(" IH141=Green", "").replace(
                        " IH141=Yellow", ""
                    )
                if notes_col and sig in ("114LB", "115LB"):
                    notes = ws.cell(row, notes_col).value
                    if isinstance(notes, str) and "Triple" in notes:
                        ws.cell(row, notes_col).value = notes.replace("Triple exit. ", "2-head exit. ")
    return added


def refresh_asbuilt() -> Path:
    src = IMPORTED / "signals_asbuilt_abs_v1.xlsx"
    dest = WIRING / "signals_asbuilt_abs_v2.xlsx"
    shutil.copy2(src, dest)
    wb = load_workbook(dest)
    wiring = load_csv(CATS / "signal_wiring.csv")
    masts = load_csv(CATS / "signal_mast_plan.csv")
    rebuild_asbuilt_inventory(wb["inventory"], wiring, masts)
    n = 0
    for name in wb.sheetnames:
        if name == "inventory":
            continue
        n += walk_replace(wb[name], NAME_REPLACEMENTS)
    occ = occupancy_by_hw()
    mqtt = wb["mqtt_topics"]
    idx = header_index(mqtt)
    name_col = idx.get("Name")
    jmri_col = idx.get("JMRI")
    if name_col and jmri_col:
        for row in range(2, mqtt.max_row + 1):
            jmri = mqtt.cell(row, jmri_col).value
            if not isinstance(jmri, str):
                continue
            m = BLOCK_IN_NOTES.search(jmri)
            if not m:
                continue
            public = occ.get(f"Block {m.group(1)}")
            if public:
                mqtt.cell(row, name_col).value = public.split(" / ", 1)[0]
                if "Digicon_Block_or_Role" in idx:
                    mqtt.cell(row, idx["Digicon_Block_or_Role"]).value = public
    dwarf_n = append_princess_dwarf_logic(wb)
    # README header
    readme = wb["README_ABS"]
    readme["A1"] = "HART Digicon as-built signals — ABS field logic (v2)"
    readme["A2"] = (
        "Refreshed 2026-08-22 from signal_head_plan / signal_wiring / public names "
        "(Scale, Barn, S-1…S-5, W-1/W-2, EH-*, Digicon 100L/117LA/114LA). "
        "Companion to frozen signals_split_v8.xlsx (planned RGB). "
        "100L is IH438/IH439 searchlights (not MQTT mast 464). "
        "Princess dwarfs 114LA / 115LA / 120R / 120L have ABS rows on Princess + all_logic."
    )
    wb.save(dest)
    print(f"wrote {dest} ({n} cell replacements on logic/mqtt sheets, +{dwarf_n} Princess dwarf rows)")
    cats_copy = CATS / "signals_asbuilt_abs_v2.xlsx"
    shutil.copy2(dest, cats_copy)
    old = CATS / "signals_asbuilt_abs_v1.xlsx"
    if old.exists():
        old.unlink()
        print(f"replaced {old} → {cats_copy}")
    return dest


def main() -> None:
    refresh_inventory()
    refresh_asbuilt()
    split_dest = WIRING / "signals_split_v8.xlsx"
    shutil.copy2(IMPORTED / "signals_split_v8.xlsx", split_dest)
    add_split_readme(split_dest)
    print(f"wrote {split_dest} (historical + README)")
    # Ports extract for cats/data
    inv = load_workbook(WIRING / "LCOS_Layout_Inventory_v85.xlsx")
    extract = CATS / "LCOS_Layout_Inventory_v85_signal_ports.xlsx"
    # Keep a thin copy of the full v85 next to the old v48 extract name.
    shutil.copy2(WIRING / "LCOS_Layout_Inventory_v85.xlsx", extract)
    old_extract = CATS / "LCOS_Layout_Inventory_v48_signal_ports.xlsx"
    if old_extract.exists():
        old_extract.unlink()
    print(f"wrote {extract}")
    inv.close()


if __name__ == "__main__":
    main()
