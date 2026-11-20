"""refresh_wiring_docs: the steps on the signal workbooks, the as-built ABS v2 and the frozen RGB split v8.

None reads the public name map; the Princess dwarf rows, which do, stay in refresh_wiring_docs.py.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

from refresh_wiring_cells import apply_upper_deck_names, header_index
from refresh_wiring_rules import _SW_TOKEN_CTC, DISC_SORT, V8_MAST_HINT


def rebuild_asbuilt_inventory(ws: Worksheet, wiring: list[dict[str, str]], masts: list[dict[str, str]]) -> None:
    heads_by_mast: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in wiring:
        heads_by_mast[row["mast_user_name"]].append(row)
    # Keep header
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    plan_by_name = {r["proposed_mast_name"]: r for r in masts}
    for mast, pin_rows in heads_by_mast.items():
        pin_rows = sorted(
            pin_rows,
            key=lambda r: (
                DISC_SORT.get(r.get("disc_role") or r.get("head_role") or "S", 9),
                r.get("lamp_color") or "",
            ),
        )
        plan = plan_by_name.get(mast, {})
        packed_seen: list[str] = []
        topics_seen: list[str] = []
        for r in pin_rows:
            p = str(r["packed"])
            if p not in packed_seen:
                packed_seen.append(p)
                topics_seen.append(r["topic"])
        n = len(packed_seen)
        ports = " ".join(r["port_id"] for r in pin_rows)
        aspect = (
            "Basic two-searchlight (two 3-pin STOP/APPROACH/CLEAR discs)"
            if n == 2
            else "Basic one-low (3-pin STOP/APPROACH/CLEAR)"
        )
        ws.append(
            [
                plan.get("cp") or pin_rows[0].get("board_location"),
                mast,
                n,
                plan.get("direction") or "",
                f"({plan.get('panel_x')},{plan.get('panel_y')}) {plan.get('edge')}" if plan else "",
                plan.get("protects_switch") or "",
                pin_rows[0]["mqtt_node"],
                pin_rows[0]["parent_node_id"],
                " ".join(packed_seen),
                ports,
                " ".join(topics_seen),
                plan.get("mast_system_name") or "",
                "double" if n == 2 else "single",
                aspect,
                pin_rows[0].get("notes") or "",
            ]
        )


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


def add_split_readme(path: Path) -> None:
    wb = load_workbook(path)
    if "README" in wb.sheetnames:
        del wb["README"]
    ws = wb.create_sheet("README", 0)
    lines = [
        ("signals_split_v8 — frozen planned RGB matrix", True),
        ("", False),
        ("This workbook is the Nov 2025 RGB LED plan (S1-1 … S6-15).", False),
        ("Lower-deck switch columns use live CTC names (Switch 1, Switch 35, …).", False),
        ("Upper-deck plants are Switch 61, 63, 65…; heads are 62L, 64R, 66RA….", False),
        ("S4-* = CP4, S5-* = CP5, S6-* = CP6 (historical IDs kept in Notes as was S4-1).", False),
        ("Lower-deck Digicon searchlights (6LB, 8RA, 36RA, …) are NOT in this file.", False),
        ("", False),
        ("Live lower-deck signal matrix:", False),
        ("  docs/wiring/signals_asbuilt_abs_v2.xlsx", False),
        ("Port / MQTT / LCOS overlay:", False),
        ("  docs/wiring/signals/signal_wiring.csv", False),
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


def add_v8_mast_column(path: Path) -> int:
    """Fill Mast only when v8 routes make a grouping obvious."""
    wb = load_workbook(path)
    n = 0
    for name in wb.sheetnames:
        if not name.startswith("control_point_"):
            continue
        ws = wb[name]
        idx = header_index(ws)
        if "Mast" not in idx:
            sig_col = idx["Signal"]
            ws.insert_cols(sig_col + 1)
            ws.cell(1, sig_col + 1).value = "Mast"
            ws.cell(1, sig_col + 1).font = Font(bold=True)
            idx = header_index(ws)
        sig_col = idx["Signal"]
        mast_col = idx["Mast"]
        for row in range(2, ws.max_row + 1):
            sig = ws.cell(row, sig_col).value
            hint = V8_MAST_HINT.get(str(sig) if sig else "")
            if hint:
                ws.cell(row, mast_col).value = hint
                n += 1
    sw_n = 0
    for ws in wb.worksheets:
        if ws.title == "README":
            continue
        for row in ws.iter_rows():
            for cell in row:
                if not isinstance(cell.value, str) or not cell.value:
                    continue
                out = cell.value
                for pat, repl in _SW_TOKEN_CTC:
                    out = pat.sub(repl, out)
                if out != cell.value:
                    cell.value = out
                    sw_n += 1
    upper_n = apply_upper_deck_names(wb)
    wb.save(path)
    print(f"  v8 Mast cells: {n}; CTC switch tokens: {sw_n}; upper 61+ names: {upper_n}")
    return n
