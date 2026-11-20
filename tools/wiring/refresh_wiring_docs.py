#!/usr/bin/env python3
"""Refresh LCOS inventory + Digicon as-built workbooks from hart CSVs.

Reads:
  cats/data/occupancy_bindings.csv
  docs/wiring/signals/signal_wiring.csv
  docs/wiring/signals/signal_head_plan.csv
  docs/wiring/signals/signal_mast_plan.csv
  docs/wiring/imported/LCOS_Layout_Inventory_v84.xlsx
  docs/wiring/imported/signals_asbuilt_abs_v1.xlsx
  docs/wiring/imported/signals_split_v8.xlsx

Writes:
  docs/wiring/LCOS_Layout_Inventory_v85.xlsx
  docs/wiring/signals_asbuilt_abs_v2.xlsx
  docs/wiring/signals_split_v8.xlsx  (historical RGB plan + README sheet)

This file holds the paths, the public-name layer (load_proposed / proposed), the steps that use it or read a file,
and main(). The rename tables are in refresh_wiring_rules.py, the cell rewrites in refresh_wiring_cells.py, and the
sheet steps in refresh_wiring_inventory.py (LCOS v85) and refresh_wiring_signals.py (as-built v2, split v8). Tests
patch paths and steps on this module, so the steps that read a path or the name map stay here.
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
from hartlib.railroad import FactsError, read_name_rows, read_rows  # noqa: E402

# The sibling modules below hold the tables and sheet steps. This file is also loaded by path (importlib) from tests
# that do not put tools/wiring on sys.path. Names not used here are re-exported for the tests.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_wiring_cells import (  # noqa: E402,F401
    _unique_keep_order,
    apply_ctc_switch_names,
    apply_legacy_sw_tokens,
    apply_upper_deck_names,
    drop_dead_heads,
    fix_mangled_switch_names,
    header_index,
    replace_in_cell,
    rewrite_legacy_node_ids,
    strip_dead_head_tokens,
    walk_replace,
)
from refresh_wiring_inventory import (  # noqa: E402,F401
    add_digicon_sheet,
    add_legacy_node_column,
    clear_retired_s3_rgb,
    clear_s3_turnout_signals,
    ensure_ou4_boards,
    first_5v_cal_ports,
    overlay_dnou8,
    refresh_block_sensors,
    refresh_nodes,
    remap_workbook_node_ids,
    sort_nodes_by_address,
    stamp_block_sensor_cal,
    summarize_node_labels,
    tag_upper_turnouts_cp,
)
# Re-exported for readers only. The moved functions read refresh_wiring_rules' own copies, so a
# test that wants to change one of these tables must patch it on refresh_wiring_rules, not here.
from refresh_wiring_rules import (  # noqa: E402,F401
    _DWARF_ASPECTS,
    BLOCK_IN_NOTES,
    LEGACY_NODE_IDS,
    PRINCESS_LOGIC_HEADERS,
    RGB_LED_RE,
    TURNOUT_DIGICON,
    UPPER_HEAD_NAME,
    V8_MAST_HINT,
)
from refresh_wiring_signals import (  # noqa: E402,F401
    _logic_signals,
    add_split_readme,
    add_v8_mast_column,
    rebuild_asbuilt_inventory,
)


ROOT = paths.REPO_ROOT
WIRING = ROOT / "docs/wiring"
IMPORTED = WIRING / "imported"
CATS = ROOT / "cats/data"
SIGNALS = ROOT / "docs/wiring/signals"
PUBLIC_MAP = paths.PUBLIC_NAME_MAP


def load_csv(path: Path) -> list[dict[str, str]]:
    """A signal CSV's rows with every column the file has. The callers need the file's own header: the head plan's
    goes into the DigiconSignals sheet as it stands, and a wiring row without an `lcos_recipe` column gets the
    default recipe. hartlib's read_rows keeps only the columns it is given, so it is used for the other CSVs."""
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_proposed(path: Path = PUBLIC_MAP) -> dict[str, str]:
    """Live public string → proposed (device-map grammar)."""
    out: dict[str, str] = {}
    for _line, row in read_name_rows(path):
        current = (row.get("current") or "").strip()
        proposed = (row.get("proposed") or "").strip()
        if current and proposed and current != proposed:
            out[current] = proposed
    return out


try:
    _PROPOSED = load_proposed()
except FactsError as exc:
    sys.exit(f"{Path(__file__).name}: {exc}")


def proposed(name: str | None) -> str | None:
    if not name:
        return name
    mapped = _PROPOSED.get(name)
    if mapped:
        return mapped
    if " / " in name:
        return " / ".join(proposed(part.strip()) or part.strip() for part in name.split("/"))
    return name


def apply_proposed_to_wiring(rows: list[dict[str, str]]) -> None:
    for row in rows:
        if row.get("user_name"):
            row["user_name"] = proposed(row["user_name"]) or row["user_name"]
        if row.get("mast_user_name"):
            row["mast_user_name"] = proposed(row["mast_user_name"]) or row["mast_user_name"]


def occupancy_by_hw(path: Path = CATS / "occupancy_bindings.csv") -> dict[str, str]:
    """MQTT occupancy userName (Block n-n) → public block name."""
    groups: dict[str, list[str]] = defaultdict(list)
    for _line, row in read_rows(path, ("block_user_name", "occupancy_sensor_user_name"),
                                optional=("cats_discipline",)):
        hw = (row.get("occupancy_sensor_user_name") or "").strip()
        name = (row.get("block_user_name") or "").strip()
        if hw and name and name not in groups[hw]:
            groups[hw].append(name)

    picked: dict[str, str] = {}
    for hw, names in groups.items():
        raw_os = [n for n in names if n.startswith("OS ")]
        raw_other = [n for n in names if n not in raw_os]
        os_names = [proposed(n) or n for n in raw_os]
        other = [proposed(n) or n for n in raw_other]
        if os_names and other:
            picked[hw] = f"{os_names[0]} / {other[0]}"
        else:
            picked[hw] = os_names[0] if os_names else other[0]
    return picked


# 2026-11-13: East Main Ext / West Main Ext became East Ext / West Ext. The imported
# workbooks are historical and keep the old names, so the outputs get the new ones here,
# by the same rule the speed-match logs use.
sys.path.insert(0, str(ROOT / "jmri/layouts/hart/scripts/speedmatch"))
from rename_extension_tracks import rename as _rename_ext  # noqa: E402


def rename_extension_tracks(wb) -> int:
    n = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str):
                    new, k = _rename_ext(v)
                    if k:
                        cell.value = new
                        n += 1
    return n


# The imported as-built v1 workbook uses the panel IH numbers from before the
# 2026-11-10 renumber; tables.xml now follows signal_wiring.csv. One pass,
# because the old and new sets overlap (IH1232 was 24RA, is now 34L).
PANEL_TO_WIRING_IH: dict[str, str] = {
    "IH1232": "IH232", "IH1233": "IH238",    # 24RA
    "IH1234": "IH233", "IH1235": "IH239",    # 24L
    "IH1236": "IH234",                       # 24RB
    "IH1237": "IH1232", "IH1238": "IH1233",  # 34L
    "IH1239": "IH1234",                      # 32R
    "IH1240": "IH1235", "IH1241": "IH1236",  # 34R
    "IH137": "IH132", "IH138": "IH133",      # 36RB
    "IH132": "IH1132", "IH133": "IH1135",    # 40LA
    "IH142": "IH1136",                       # 40LB
    "IH134": "IH1133",                       # 2036
    "IH141": "IH1134",                       # 2035
}
_IH_TOKEN = re.compile(r"\bIH\d+(?!\d)")


def remap_panel_ih(value: object) -> object:
    if not isinstance(value, str):
        return value
    return _IH_TOKEN.sub(lambda m: PANEL_TO_WIRING_IH.get(m.group(0), m.group(0)), value)


def walk_remap_panel_ih(ws: Worksheet) -> int:
    n = 0
    for row in ws.iter_rows():
        for cell in row:
            new = remap_panel_ih(cell.value)
            if new != cell.value:
                cell.value = new
                n += 1
    return n


NAME_REPLACEMENTS: list[tuple[str, str]] = [
    # Long JMRI mast userNames → Digicon (longest first)
    ("West Yard West East Main Ext", proposed("117RB") or "117RB"),
    ("West Yard East OS 117b", proposed("117LA") or "117LA"),
    ("West Yard East Yard T6", proposed("117LB") or "117LB"),
    ("West Yard West OS 117", proposed("117RA") or "117RA"),
    ("East End West Yard Track 1", proposed("111RB") or "111RB"),
    ("East End West Main West", proposed("111RA") or "111RA"),
    ("East End South OS 112", proposed("112R") or "112R"),
    ("East End South OS 110", proposed("110R") or "110R"),
    ("East End East OS 111a", proposed("111L") or "111L"),
    ("East End East Lead", proposed("112L") or "112L"),
    ("Princess North K-1", proposed("115LB") or "115LB"),
    ("Princess South K-2", proposed("114LB") or "114LB"),
    ("Princess West OS 113a", proposed("113RB") or "113RB"),
    ("Princess West OS 113b", proposed("113RA") or "113RA"),
    ("Princess East K-2", proposed("120R") or "120R"),
    ("Princess East K-1", proposed("120L") or "120L"),
    ("Princess East McKees Rocks", proposed("115LA") or "115LA"),
    ("Princess East McKeesport", proposed("114LA") or "114LA"),
    ("Plane East East Main Ext", proposed("102LB") or "102LB"),
    ("Plane East OS 102", proposed("102LA") or "102LA"),
    ("Brick East Main West", proposed("100L") or "100L"),
    ("Brick West Yard 1", proposed("101RA") or "101RA"),
    ("Brick West Yard 2", proposed("101RB") or "101RB"),
    ("Brick W-1 West Stub", proposed("101LA") or "101LA"),
    ("Brick W-2 West Stub", proposed("101LB") or "101LB"),
    # OS public names (ADR-005: CP lives in comment, not the name)
    ("OS 117b (West Yard)", proposed("OS 117b") or "OS 117b"),
    ("OS 119 (West Yard)", proposed("OS 119") or "OS 119"),
    ("OS 118 (West Yard)", proposed("OS 118") or "OS 118"),
    ("OS 117 (West Yard)", proposed("OS 117") or "OS 117"),
    ("OS 116 (West Yard)", proposed("OS 116") or "OS 116"),
    ("OS 115 (Princess)", proposed("OS 115") or "OS 115"),
    ("OS 114 (Princess)", proposed("OS 114") or "OS 114"),
    ("OS 113b (Princess)", proposed("OS 113b") or "OS 113b"),
    ("OS 113a (Princess)", proposed("OS 113a") or "OS 113a"),
    ("OS 112 (East End)", proposed("OS 112") or "OS 112"),
    ("OS 111b (East End)", proposed("OS 111b") or "OS 111b"),
    ("OS 111a (East End)", proposed("OS 111a") or "OS 111a"),
    ("OS 110 (East End)", proposed("OS 110") or "OS 110"),
    ("OS 109 (East End)", proposed("OS 109") or "OS 109"),
    ("OS 108 (East End)", proposed("OS 108") or "OS 108"),
    ("OS 107 (East End)", proposed("OS 107") or "OS 107"),
    ("OS 106 (South Yard)", proposed("OS 106") or "OS 106"),
    ("OS 105 (South Yard)", proposed("OS 105") or "OS 105"),
    ("OS 104 (South Yard)", proposed("OS 104") or "OS 104"),
    ("OS 103 (South Yard)", proposed("OS 103") or "OS 103"),
    ("OS 102 (Plane)", proposed("OS 102") or "OS 102"),
    ("OS 101 (Brick)", proposed("OS 101") or "OS 101"),
    ("OS 100 (Brick)", proposed("OS 100") or "OS 100"),
    ("Main West Brick–Plane", proposed("Brick-Plane") or "Brick-Plane"),
    ("Main West Brick-Plane", proposed("Brick-Plane") or "Brick-Plane"),
    # Yard plates (longest first so T11 before T1)
    ("Yard Track 5", proposed("S-5") or "S-5"),
    ("Yard Track 4", proposed("S-4") or "S-4"),
    ("Yard Track 3", proposed("S-3") or "S-3"),
    ("Yard Track 2", proposed("S-2") or "S-2"),
    ("Yard Track 1", proposed("S-1") or "S-1"),
    ("West Yard Track 2", proposed("W-2") or "W-2"),
    ("West Yard Track 1", proposed("W-1") or "W-1"),
    ("West Yard 2", proposed("W-2") or "W-2"),
    ("West Yard 1", proposed("W-1") or "W-1"),
    ("Yard T6", proposed("Barn") or "Barn"),
    ("Yard T1", proposed("Scale") or "Scale"),
    ("track/signalmast/464", "track/signalhead/IH438 / IH439"),
]


def load_v8_signal_info() -> dict[str, dict[str, str]]:
    """Route / block text from the frozen RGB workbook (imported snapshot)."""
    src = IMPORTED / "signals_split_v8.xlsx"
    wb = load_workbook(src, data_only=True)
    out: dict[str, dict[str, str]] = {}
    for name in wb.sheetnames:
        if not name.startswith("control_point_"):
            continue
        cp = "CP" + name.rsplit("_", 1)[-1]
        ws = wb[name]
        headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        for row in ws.iter_rows(min_row=2, values_only=True):
            d = dict(zip(headers, row))
            sig = d.get("Signal")
            if not sig or str(sig) in out:
                continue
            out[str(sig)] = {
                "cp": cp,
                "from": str(d.get("Route_From") or ""),
                "to": str(d.get("Route_To") or ""),
                "block": str(d.get("Signal_Block") or ""),
                "location": str(d.get("Location") or ""),
            }
    wb.close()
    return out


def annotate_upper_rgb_heads(ws: Worksheet) -> list[str]:
    """Label remaining S4/S5/S6 LEDs as defined heads on CP4/CP5/CP6."""
    info = load_v8_signal_info()
    log: list[str] = []
    for row in range(2, ws.max_row + 1):
        dev = ws.cell(row, 5).value
        if not isinstance(dev, str):
            continue
        m = RGB_LED_RE.match(dev.strip())
        if not m:
            continue
        sig, color = m.group(1), m.group(4)
        meta = info.get(sig, {})
        cp = meta.get("cp") or f"CP{m.group(2)}"
        mast_id = UPPER_HEAD_NAME.get(sig, sig)
        new_name = f"Head {mast_id} {color}"
        bits = [cp]
        if meta.get("from") or meta.get("to"):
            bits.append(f"{meta.get('from') or '?'} → {meta.get('to') or '?'}")
        if meta.get("block"):
            bits.append(meta["block"])
        mast = V8_MAST_HINT.get(sig)
        if mast:
            bits.append(f"mast {mast}")
        else:
            bits.append("defined head")
        bits.append(f"was {sig}")
        note = " | ".join(bits)
        ws.cell(row, 5).value = new_name
        prev_note = ws.cell(row, 8).value
        if prev_note and str(prev_note) not in note:
            note = f"{note}; was {prev_note}"
        ws.cell(row, 8).value = note
        log.append(f"{ws.cell(row, 1).value}: {dev!r} → {new_name!r}")
    return log


def refresh_turnout_summary(ws: Worksheet) -> list[str]:
    log: list[str] = []
    idx = header_index(ws)
    tcol = idx["Turnout"]
    for row in range(2, ws.max_row + 1):
        name = ws.cell(row, tcol).value
        spec = TURNOUT_DIGICON.get(str(name) if name else "")
        if not spec:
            continue
        ws.cell(row, tcol).value = proposed(str(name)) or name

        def set_group(prefix: str, signal_key: str, ports_key: str) -> None:
            sig = proposed(spec.get(signal_key)) or spec.get(signal_key)
            r_key, y_key, g_key = (
                f"{prefix} R Port",
                f"{prefix} Y Port",
                f"{prefix} G Port",
            )
            if not sig:
                ws.cell(row, idx[prefix]).value = None
                for key in (r_key, y_key, g_key):
                    if key in idx:
                        ws.cell(row, idx[key]).value = None
                return
            ws.cell(row, idx[prefix]).value = sig
            ports = spec.get(ports_key) or (None, None, None)
            # R/Y/G columns are lamp colors of one 3-pin head.
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


def refresh_inventory() -> Path:
    src = IMPORTED / "LCOS_Layout_Inventory_v84.xlsx"
    dest = WIRING / "LCOS_Layout_Inventory_v85.xlsx"
    shutil.copy2(src, dest)
    wb = load_workbook(dest)
    legacy_by_row = remap_workbook_node_ids(wb)
    mangled_n = fix_mangled_switch_names(wb)
    add_legacy_node_column(wb["Nodes"], legacy_by_row)
    sort_nodes_by_address(wb["Nodes"])
    occ = occupancy_by_hw()
    wiring = load_csv(SIGNALS / "signal_wiring.csv")
    apply_proposed_to_wiring(wiring)
    heads = load_csv(SIGNALS / "signal_head_plan.csv")
    apply_proposed_to_wiring(heads)

    bs_log = refresh_block_sensors(wb["BlockSensors"], occ)
    ou4_log = ensure_ou4_boards(wb["DNOU8"])
    dnou_log = overlay_dnou8(wb["DNOU8"], wiring)
    cal_ports = first_5v_cal_ports(wb["DNOU8"], wb["BlockSensors"])
    used = {r["port_id"] for r in wiring}
    clash = sorted(p for p in cal_ports.values() if p in used)
    if clash:
        raise SystemExit(
            "Digicon heads on block-sensor calibration pins: " + ", ".join(clash)
        )
    cal_log = stamp_block_sensor_cal(wb["DNOU8"], cal_ports)
    s3_log = clear_retired_s3_rgb(wb["DNOU8"])
    rgb_log = annotate_upper_rgb_heads(wb["DNOU8"])
    ts_log = refresh_turnout_summary(wb["TurnoutSummary"])
    ctc_n = apply_ctc_switch_names(wb)
    sw_n = apply_legacy_sw_tokens(wb)
    s3_ts_log = clear_s3_turnout_signals(wb["TurnoutSummary"])
    cp_ts_log = tag_upper_turnouts_cp(wb["TurnoutSummary"])
    upper_n = apply_upper_deck_names(wb)
    refresh_nodes(wb["Nodes"])
    summarize_node_labels(wb["Nodes"], wb["DNOU8"], wb["DNIN8"])
    add_digicon_sheet(wb, wiring, heads)
    mismatches = []
    nidx = header_index(wb["Nodes"])
    for row in range(2, wb["Nodes"].max_row + 1):
        nid = wb["Nodes"].cell(row, nidx["Node ID"]).value
        addr = wb["Nodes"].cell(row, nidx["Address"]).value
        if not nid or str(nid)[0] not in ("C", "D") or addr is None:
            continue
        expect = f"{str(nid)[0]}{int(addr)}"
        if str(nid) != expect:
            mismatches.append(f"{nid} address {addr} (expected {expect})")
    if mismatches:
        raise SystemExit("Node ID != C/D{Address}: " + "; ".join(mismatches))
    rename_extension_tracks(wb)
    wb.save(dest)

    print(f"wrote {dest}")
    print(f"  Mangled SW1xx restorations (cells): {mangled_n}")
    print(f"  DCC Switch 100–119 → CTC (cells): {ctc_n}")
    print(f"  Legacy SW/SCX tokens (cells): {sw_n}")
    print(f"  Upper-deck 61+ names (cells): {upper_n}")
    print(f"  BlockSensors renames: {len(bs_log)}")
    for line in bs_log:
        print(f"    {line}")
    print(f"  DNOU8 OU4 added: {len(ou4_log)}")
    for line in ou4_log:
        print(f"    {line}")
    print(f"  DNOU8 overlays: {len(dnou_log)}")
    for line in dnou_log:
        print(f"    {line}")
    print(f"  DNOU8 block-sensor cal: {len(cal_log)}")
    for line in cal_log:
        print(f"    {line}")
    print(f"  Retired C3 S3 RGB / drop OU3: {len(s3_log)}")
    for line in s3_log:
        print(f"    {line}")
    print(f"  Upper-deck RGB → CP heads: {len(rgb_log)}")
    print(f"  TurnoutSummary Digicon: {len(ts_log)}")
    for line in ts_log:
        print(f"    {line}")
    print(f"  TurnoutSummary cleared S3 faces: {len(s3_ts_log)}")
    for line in s3_ts_log:
        print(f"    {line}")
    print(f"  TurnoutSummary CP4/5/6 labels: {len(cp_ts_log)}")
    for line in cp_ts_log:
        print(f"    {line}")
    return dest


def _princess_dwarf_rows() -> list[dict[str, object]]:
    """ABS rows for 114LA / 115LA / 120R / 120L (SML PAIRS + SIGNAL_FACING)."""
    loc = "Princess / Helix DCC"
    routes = [
        # McKees Rocks dwarf, westbound. 115 Closed = McKees Rocks; dest 111L (113 N) or 112L (113 R).
        dict(
            Signal="115LA",
            Signal_Block="McKees Rocks",
            Route_From="McKees Rocks",
            Route_To="Track West Ext",
            Block1="OS 115",
            Block2="Track West Ext",
            Next_Signal="111L",
            SW113="N",
            SW115="N",
            ih="IH1136",
            Notes="McKees Rocks dwarf (one-low). SW115 Closed = McKees Rocks. Dest 111L when 113 Normal.",
        ),
        dict(
            Signal="115LA",
            Signal_Block="McKees Rocks",
            Route_From="McKees Rocks",
            Route_To="East Lead",
            Block1="OS 115",
            Block2="East Lead",
            Next_Signal="112L",
            SW113="R",
            SW115="N",
            ih="IH1136",
            Notes="McKees Rocks dwarf. Dest 112L when 113 Reverse (East Lead).",
        ),
        # McKeesport dwarf, westbound. 114 Closed = McKeesport.
        dict(
            Signal="114LA",
            Signal_Block="McKeesport",
            Route_From="McKeesport",
            Route_To="Track West Ext",
            Block1="OS 114",
            Block2="Track West Ext",
            Next_Signal="111L",
            SW113="N",
            SW114="N",
            ih="IH143",
            Notes="McKeesport dwarf (one-low). SW114 Closed = McKeesport. Dest 111L when 113 Normal.",
        ),
        dict(
            Signal="114LA",
            Signal_Block="McKeesport",
            Route_From="McKeesport",
            Route_To="East Lead",
            Block1="OS 114",
            Block2="East Lead",
            Next_Signal="112L",
            SW113="R",
            SW114="N",
            ih="IH143",
            Notes="McKeesport dwarf. Dest 112L when 113 Reverse (East Lead).",
        ),
        # Balloon A48: south-track 120R (IH1133) protects K-1 / OS 115; dest 120L.
        dict(
            Signal="120R",
            Signal_Block="K-1",
            Route_From="K-2",
            Route_To="K-1",
            Block1="K-1",
            Block2="OS 115",
            Next_Signal="120L",
            SW114="R",
            ih="IH1133",
            Notes=(
                "Balloon connector (one-low). A48 east ends join: 120R/IH1133 on K-2 "
                "track protects K-1 / OS 115. SW114 Thrown = K-2."
            ),
        ),
        # North-track 120L (IH1134) protects K-2 / OS 114; dest 120R.
        dict(
            Signal="120L",
            Signal_Block="K-2",
            Route_From="K-1",
            Route_To="K-2",
            Block1="K-2",
            Block2="OS 114",
            Next_Signal="120R",
            SW115="R",
            ih="IH1134",
            Notes=(
                "Balloon connector (one-low). 120L/IH1134 on K-1 track protects K-2 / "
                "OS 114. SML also Stop if K-1 occupied. SW115 Thrown = K-1."
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
    public_keys = (
        "Signal",
        "Signal_Block",
        "Route_From",
        "Route_To",
        "Block1",
        "Block2",
        "Next_Signal",
    )
    for row in out:
        for key in public_keys:
            value = row.get(key)
            if isinstance(value, str):
                row[key] = proposed(value) or value
    return out


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
        # 114LB / 115LB were authored as triples; IH1133/IH1134 (panel IH134/IH141,
        # remapped above) are now 120R/120L.
        mqtt_col = idx.get("MQTT_Out")
        notes_col = idx.get("Notes")
        sig_col = idx.get("Signal")
        if mqtt_col and sig_col:
            for row in range(2, ws.max_row + 1):
                sig = ws.cell(row, sig_col).value
                mqtt = ws.cell(row, mqtt_col).value
                if not isinstance(mqtt, str):
                    continue
                if sig == "115LB" and "IH1133" in mqtt:
                    ws.cell(row, mqtt_col).value = mqtt.replace(" IH1133=Red", "").replace(" IH1133=Green", "").replace(
                        " IH1133=Yellow", ""
                    )
                if sig == "114LB" and "IH1134" in mqtt:
                    ws.cell(row, mqtt_col).value = mqtt.replace(" IH1134=Red", "").replace(" IH1134=Green", "").replace(
                        " IH1134=Yellow", ""
                    )
                if notes_col and sig in ("114LB", "115LB"):
                    notes = ws.cell(row, notes_col).value
                    if isinstance(notes, str) and "Triple" in notes:
                        ws.cell(row, notes_col).value = notes.replace("Triple exit. ", "2-head exit. ")
    return added


TABLES_XML = paths.TABLES_XML


def live_heads(tables: Path = TABLES_XML) -> set[str]:
    """IH heads tables.xml defines. The imported v1 workbook also names heads removed
    since (IH435, the bottom head Mast 6LA lost in August 2026)."""
    return set(re.findall(r"<systemName>(IH\d+)</systemName>", tables.read_text(encoding="utf-8")))


def refresh_asbuilt() -> Path:
    src = IMPORTED / "signals_asbuilt_abs_v1.xlsx"
    dest = WIRING / "signals_asbuilt_abs_v2.xlsx"
    shutil.copy2(src, dest)
    wb = load_workbook(dest)
    wiring = load_csv(SIGNALS / "signal_wiring.csv")
    apply_proposed_to_wiring(wiring)
    masts = load_csv(SIGNALS / "signal_mast_plan.csv")
    for row in masts:
        if row.get("proposed_mast_name"):
            row["proposed_mast_name"] = (
                proposed(row["proposed_mast_name"]) or row["proposed_mast_name"]
            )
    rebuild_asbuilt_inventory(wb["inventory"], wiring, masts)
    n = 0
    live = live_heads()
    for name in wb.sheetnames:
        if name == "inventory":
            continue
        n += walk_replace(wb[name], NAME_REPLACEMENTS)
        n += walk_remap_panel_ih(wb[name])
        n += drop_dead_heads(wb[name], live)
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
    rename_extension_tracks(wb)
    wb.save(dest)
    print(f"wrote {dest} ({n} cell replacements on logic/mqtt sheets, +{dwarf_n} Princess dwarf rows)")
    return dest


def main() -> None:
    try:
        refresh_inventory()
        refresh_asbuilt()
    except FactsError as exc:
        sys.exit(f"{Path(__file__).name}: {exc}")
    split_dest = WIRING / "signals_split_v8.xlsx"
    shutil.copy2(IMPORTED / "signals_split_v8.xlsx", split_dest)
    add_v8_mast_column(split_dest)
    add_split_readme(split_dest)
    print(f"wrote {split_dest} (CTC switch names + Mast column + README)")


if __name__ == "__main__":
    main()
