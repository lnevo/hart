#!/usr/bin/env python3
"""Class 1 Digicon CTC for HART — Armstrong / Chubb fragment assembler.

Never invent SecEdge topology (ClassCast). Clone example cells only.

Primary board is the **Armstrong Magnet chassis** with HART names placed by
role: track blocks on HORIZONTAL cells, OS plants on SWITCHPOINTS cells.
Chubb 3-row remains an alt (`--only chubb`) — it is CTC-look only, not HART geometry.

Outputs:
  cats/panels/HART_magnet.xml / HART.xml — Gate 1 Brick→100-102→Plane (+ occ)
  cats/panels/HART_armstrong_magnet.xml  — full Armstrong rename demo
  cats/panels/HART_chubb_magnet.xml      — Chubb 3-row alt (schematic CTC)
  cats/panels/HART_triple_magnet.xml     — Armstrong-shaped 3-row alt
  cats/panels/HART_stacked_magnet.xml    — 2-row Armstrong
  cats/panels/HART_ladder_frag.xml       — ladder throat bisect

Designer is authoritative for Neville topology (ADR-004). Generator builds an
interim Gate 1 from abutted Armstrong fragments; use --wire-only on Designer XML.


Usage:
  python3 cats/scripts/jmri_to_cats_digicon.py
  python3 cats/scripts/jmri_to_cats_digicon.py --only gate1|magnet|chubb|splice|ladder
  python3 cats/scripts/jmri_to_cats_digicon.py --wire-only cats/panels/HART.xml
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HART_PANEL = ROOT / "jmri/layouts/hart/output/hart_prod.xml"
PLAN_PATH = ROOT / "cats/data/digicon_plant_plan.json"
OUT_DIR = ROOT / "cats/panels"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cats_paths import armstrong_magnet, chubb_route  # noqa: E402

TEMPLATE = armstrong_magnet()
CHUBB = chubb_route()


def load_plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def load_occupancy() -> dict[str, tuple[str, str]]:
    root = ET.parse(HART_PANEL).getroot()
    sensor_addr: dict[str, str] = {}
    for s in root.iter("sensor"):
        sn = s.get("systemName") or s.findtext("systemName") or ""
        un = (s.findtext("userName") or "").strip()
        if sn.startswith("M2S") and un:
            sensor_addr[un] = sn[3:]
    out: dict[str, tuple[str, str]] = {}
    for lb in root.iter("layoutblock"):
        un = (lb.findtext("userName") or "").strip()
        occ = (lb.get("occupancysensor") or "").strip()
        if un and occ and occ in sensor_addr:
            out[un] = (sensor_addr[occ], occ)
    return out


def header_shell(template: Path = TEMPLATE) -> tuple[ET.Element, ET.Element]:
    root = ET.parse(template).getroot()
    for ops in root.iter("OPERATIONS"):
        ops.set("CONNECT", "false")
    tp = root.find("TRACKPLAN")
    assert tp is not None
    for ch in list(tp):
        tp.remove(ch)
    return root, tp


def strip_turnout_feedback_io(root: ET.Element) -> None:
    kill = {"SELECTEDREPORT", "ROUTECOMMAND"}
    changed = True
    while changed:
        changed = False
        parent = {c: p for p in root.iter() for c in p}
        for tag in kill:
            for el in list(root.iter(tag)):
                p = parent.get(el)
                if p is not None:
                    p.remove(el)
                    changed = True


def ensure_mqtt(root: ET.Element) -> None:
    last = list(root.findall("JMRINAME"))[-1]
    idx = list(root).index(last)
    for prefix, xtype, cls in (
        ("M2S", "Sensor", "jmri.jmrix.mqtt.MqttSensorManager"),
        ("M2T", "Turnout", "jmri.jmrix.mqtt.MqttTurnoutManager"),
        # M2R omitted — see wire_occupancy TRAINREPORTER note
    ):
        if any(j.get("JMRIPREFIX") == prefix for j in root.findall("JMRINAME")):
            continue
        el = ET.Element("JMRINAME", {"JMRIPREFIX": prefix, "XMLTYPE": xtype})
        el.text = cls
        idx += 1
        root.insert(idx, el)


def wire_occupancy(root: ET.Element, occ: dict[str, tuple[str, str]]) -> None:
    for b in root.iter("BLOCK"):
        name = b.get("NAME")
        if not name or name not in occ:
            continue
        for child in list(b):
            if child.tag in ("OCCUPIEDSPEC", "UNOCCUPIEDSPEC", "TRAINREPORTER"):
                b.remove(child)
        addr, uname = occ[name]
        # CATS SensorAdapter polarity is inverted vs JMRI names:
        #   IOSPEC "close" → trigger KnownState ACTIVE (2)
        #   IOSPEC "throw" → trigger KnownState INACTIVE (4)
        # MQTT occupancy ACTIVE must therefore use "close" for OCCUPIEDSPEC.
        oc = ET.SubElement(b, "OCCUPIEDSPEC")
        ios = ET.SubElement(
            oc, "IOSPEC", {"DECADDR": addr, "JMRIPREFIX": "M2S", "USER_NAME": uname}
        )
        ios.text = "close"
        uoc = ET.SubElement(b, "UNOCCUPIEDSPEC")
        ios2 = ET.SubElement(uoc, "IOSPEC", {"DECADDR": addr, "JMRIPREFIX": "M2S"})
        ios2.text = "throw"
        # TRAINREPORTER (M2R) disabled in generator: creating MQTT reporters at
        # panel load races the broker and has blanked Dispatcher Panel.
        # Tracking path: Appearance → Train Tracker ON, right-click block →
        # Position Train → HART Local (HL1). Occupancy then moves the label.
        # Optional MQTT content: sim still publishes track/reporter/{addr}.


# Demo train shown by Train Tracker (TRANSPONDING must match MQTT reporter loco id).
HART_TRAIN_SYMBOL = "HL1"
HART_TRAIN_ENGINE = "4501"
HART_TRAIN_NAME = "HART Local"
HART_TRAINS_CSV = Path(__file__).resolve().parents[1] / "data" / "hart_trains.csv"

# Blocks that get TRAINREPORTER (Neville tour path — keep this list short).
TRAIN_REPORTER_BLOCKS = frozenset(
    {
        "Main West",
        "OS Switch 23a",
        "West Main Ext",
        "OS Switch 35b",
        "OS Switch 35a",
        "OS Switch 37",
        "McKeesport",
        "East Lead",
        "OS Switch 33",
        "Main East",
        "OS Switch 7b (Barn)",
        "East Main Ext",
        "OS Switch 5",
        "Main West Brick–Plane",
        "OS Switch 1",
    }
)


def load_hart_trains(
    csv_path: Path | None = None,
) -> list[dict[str, str]]:
    """Dispatcher train lineup from Car Cards DS-01 (cats/data/hart_trains.csv)."""
    path = csv_path or HART_TRAINS_CSV
    if not path.is_file():
        return [
            {
                "train_name": HART_TRAIN_NAME,
                "train_symbol": HART_TRAIN_SYMBOL,
                "engine": HART_TRAIN_ENGINE,
                "font": "FONT_TRAIN",
                "runs_job": "true",
            }
        ]
    import csv

    with path.open(newline="", encoding="utf-8") as f:
        return [
            {k: (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(f)
            if (row.get("train_symbol") or "").strip()
        ]


def ensure_hart_trains(root: ET.Element, csv_path: Path | None = None) -> int:
    """Replace TRAINSTORE/JOBSTORE with HART jobs from hart_trains.csv (DS-01)."""
    trains = load_hart_trains(csv_path)
    ts = root.find("TRAINSTORE")
    if ts is None:
        return 0
    td = ts.find("TRAINDATA")
    if td is None:
        td = ET.SubElement(ts, "TRAINDATA")
    for rec in list(td.findall("DATARECORD")):
        td.remove(rec)
    for t in trains:
        eng = t.get("engine") or ""
        ET.SubElement(
            td,
            "DATARECORD",
            {
                "TRAIN_NAME": t["train_name"],
                "TRAIN_SYMBOL": t["train_symbol"],
                "ENGINE": eng,
                "TRANSPONDING": "false",
                "CABOOSE": "",
                "CREW": "",
                "ONDUTY": "",
                "DEPARTURE": "",
                "FONT": t.get("font") or "FONT_TRAIN",
                "LENGTH": "0",
                "WEIGHT": "0",
                "CARS": "0",
                "AUTOTERMINATE": "false",
                "LABELBACKGROUND": "false",
            },
        )

    # Jobs: desk roles + DS-01 / CI crew jobs (Car Cards).
    js = root.find("JOBSTORE")
    if js is not None:
        jd = js.find("JOBDATA")
        if jd is None:
            jd = ET.SubElement(js, "JOBDATA")
        for rec in list(jd.findall("DATARECORD")):
            jd.remove(rec)
        jobs = [
            ("Dispatcher", "false"),
            ("Yardmaster", "false"),
            ("Route 23", "true"),
            ("D749", "true"),
            ("OCS-1", "true"),
            ("NVL", "true"),
            ("CK1", "true"),
        ]
        for name, runs in jobs:
            ET.SubElement(
                jd,
                "DATARECORD",
                {
                    "FONT": "",
                    "JOB_NAME": name,
                    "RUNS_TRAIN": runs,
                    "CREW_NAME": "",
                    "ASSISTANT": "",
                },
            )

    return len(trains)


def rename_blocks(root: ET.Element, mapping: dict[str, str]) -> None:
    for b in root.iter("BLOCK"):
        n = b.get("NAME")
        if n in mapping:
            b.set("NAME", mapping[n])
        st = b.get("STATION")
        if st in mapping:
            b.set("STATION", mapping[st])


def rename_labels(root: ET.Element, mapping: dict[str, str]) -> None:
    for sn in root.iter("SEC_NAME"):
        n = sn.get("NAME")
        if n in mapping:
            sn.set("NAME", mapping[n])


def occupied(tp: ET.Element) -> set[tuple[int, int]]:
    return {(int(s.get("X")), int(s.get("Y"))) for s in tp.findall("SECTION")}


def add_label(tp: ET.Element, x: int, y: int, text: str) -> None:
    if (x, y) in occupied(tp):
        return
    s = ET.Element("SECTION", {"X": str(x), "Y": str(y)})
    ET.SubElement(
        s, "SEC_NAME", {"LOC_NAME": "CENT", "NAME": text, "FONT_NAME": "FONT_LABEL"}
    )
    tp.append(s)


def strip_label_row(sections: list[ET.Element], y: int = 1) -> list[ET.Element]:
    return [
        s
        for s in sections
        if not (
            int(s.get("Y")) == y
            and s.find("TRACKGROUP") is None
            and s.find("SEC_NAME") is not None
        )
    ]


def clear_sec_names_on_track(sections: list[ET.Element]) -> None:
    for s in sections:
        for sn in list(s.findall("SEC_NAME")):
            s.remove(sn)


def assert_no_collisions(tp: ET.Element) -> None:
    coords = [(s.get("X"), s.get("Y")) for s in tp.findall("SECTION")]
    dups = [c for c, n in Counter(coords).items() if n > 1]
    if dups:
        raise SystemExit(f"cell collision {dups}")


def _horizontal_donor(tp: ET.Element) -> ET.Element | None:
    """Pick a simple HORIZONTAL cell to clone (has real SEC_EDGEs — load-safe)."""
    fallback = None
    for s in tp.findall("SECTION"):
        tg = s.find("TRACKGROUP")
        if tg is None:
            continue
        texts = [(t.text or "").strip() for t in tg.findall("TRACK")]
        if texts != ["HORIZONTAL"]:
            continue
        if fallback is None:
            fallback = s
        # Prefer a cell without a named BLOCK (spacer must not steal occupancy).
        if not any(b.get("NAME") for b in s.iter("BLOCK")):
            return s
    return fallback


def add_left_track_margin(tp: ET.Element, n: int = 4) -> None:
    """Shift board right and fill new left columns with cloned HORIZONTAL track.

    Label-only cells do not create a left margin in CATS (content bbox / pack).
    Cloned track columns do — and keep SecEdge topology legal.
    """
    if n <= 0:
        return
    donor = _horizontal_donor(tp)
    if donor is None:
        raise SystemExit("no HORIZONTAL donor cell for left margin")
    track_ys = sorted(
        {
            int(s.get("Y"))
            for s in tp.findall("SECTION")
            if s.find("TRACKGROUP") is not None
        }
    )
    for s in tp.findall("SECTION"):
        s.set("X", str(int(s.get("X")) + n))
    for x in range(1, n + 1):
        for y in track_ys:
            if (x, y) in occupied(tp):
                continue
            cell = copy.deepcopy(donor)
            cell.set("X", str(x))
            cell.set("Y", str(y))
            # Spacers: geometry only — drop names / occupancy / signals.
            for sn in list(cell.findall("SEC_NAME")):
                cell.remove(sn)
            for edge in cell.findall("SEC_EDGE"):
                for sig in list(edge.findall("SECSIGNAL")):
                    edge.remove(sig)
                for blk in list(edge.findall("BLOCK")):
                    if blk.get("NAME") or blk.find("OCCUPIEDSPEC") is not None:
                        edge.remove(blk)
                    else:
                        # keep anonymous <BLOCK /> placeholders if present
                        pass
            for sp in list(cell.iter("SWITCHPOINTS")):
                parent = {c: p for p in cell.iter() for c in p}
                p = parent.get(sp)
                if p is not None:
                    p.remove(sp)
            tp.append(cell)


def center_trackplan(
    tp: ET.Element,
    *,
    pad_x: int = 1,
    pad_y: int = 1,
) -> None:
    """Normalize SECTION origin and set COLUMNS/ROWS to the content bbox."""
    sections = list(tp.findall("SECTION"))
    if not sections:
        return
    xs = [int(s.get("X")) for s in sections]
    ys = [int(s.get("Y")) for s in sections]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    dx = pad_x - min_x
    dy = pad_y - min_y
    if dx or dy:
        for s in sections:
            s.set("X", str(int(s.get("X")) + dx))
            s.set("Y", str(int(s.get("Y")) + dy))
        max_x += dx
        max_y += dy
    cols = max_x + pad_x
    rows = max_y + pad_y
    tp.set("COLUMNS", str(cols))
    tp.set("ROWS", str(rows))


def clone_rect(
    src_tp: ET.Element, x0: int, x1: int, y0: int, y1: int, dx: int, dy: int = 0
) -> list[ET.Element]:
    out: list[ET.Element] = []
    for s in src_tp.findall("SECTION"):
        x, y = int(s.get("X")), int(s.get("Y"))
        if x0 <= x <= x1 and y0 <= y <= y1:
            c = copy.deepcopy(s)
            c.set("X", str(x + dx))
            c.set("Y", str(y + dy))
            for sh in c.iter("SHARED"):
                sh.set("X", str(int(sh.get("X")) + dx))
                if sh.get("Y") is not None:
                    sh.set("Y", str(int(sh.get("Y")) + dy))
            out.append(c)
    return out


def prune_dangling_shared(root: ET.Element, tp: ET.Element) -> None:
    have = occupied(tp)
    parent = {c: p for p in root.iter() for c in p}
    for sh in list(root.iter("SHARED")):
        tx, ty = int(sh.get("X")), int(sh.get("Y"))
        if (tx, ty) not in have:
            p = parent.get(sh)
            if p is not None:
                p.remove(sh)


def _rename_blocks_in_x_range(
    tp: ET.Element,
    x0: int,
    x1: int,
    mapping: dict[str, str],
    *,
    y0: int | None = None,
    y1: int | None = None,
) -> None:
    for s in tp.findall("SECTION"):
        x = int(s.get("X"))
        y = int(s.get("Y"))
        if not (x0 <= x <= x1):
            continue
        if y0 is not None and y < y0:
            continue
        if y1 is not None and y > y1:
            continue
        for b in s.iter("BLOCK"):
            n = b.get("NAME")
            if n in mapping:
                b.set("NAME", mapping[n])
            st = b.get("STATION")
            if st in mapping:
                b.set("STATION", mapping[st])


def finalize(
    root: ET.Element,
    *,
    mqtt: bool,
    width: int = 1800,
    height: int = 520,
    strip_turnout_io: bool = True,
) -> None:
    if strip_turnout_io:
        strip_turnout_feedback_io(root)
    tp = root.find("TRACKPLAN")
    assert tp is not None
    if mqtt:
        ensure_mqtt(root)
        wire_occupancy(root, load_occupancy())
        ensure_hart_trains(root)
        # Live JMRI/MQTT I/O (occupancy sensors). Chubb template has no OPERATIONS.
        ops_list = list(root.iter("OPERATIONS"))
        if ops_list:
            for ops in ops_list:
                ops.set("CONNECT", "true")
        else:
            # Insert before TRACKPLAN (CATS convention from Armstrong examples)
            tp_el = root.find("TRACKPLAN")
            ops = ET.Element("OPERATIONS", {"CONNECT": "true"})
            if tp_el is not None:
                idx = list(root).index(tp_el)
                root.insert(idx, ops)
            else:
                root.append(ops)
    root.set("WIDTH", str(width))
    root.set("HEIGHT", str(height))
    assert_no_collisions(tp)


def wire_existing_panel(path: Path, *, inplace: bool = True) -> Path:
    """MQTT + occupancy + trains on an existing TRACKPLAN (Designer or magnet).

    Does not replace or reshape track geometry.
    """
    if not path.is_file():
        raise SystemExit(f"Missing panel: {path}")
    root = ET.parse(path).getroot()
    if root.find("TRACKPLAN") is None:
        raise SystemExit(f"No TRACKPLAN in {path}")
    # Preserve geometry; only I/O + train store.
    finalize(root, mqtt=True, width=int(root.get("WIDTH") or 1600), height=int(root.get("HEIGHT") or 520))
    out = path if inplace else path.with_name(path.stem + "_wired.xml")
    write(out, root)
    print(f"Wired MQTT/occupancy (TRACKPLAN unchanged): {out}")
    return out


def build_gate1(mqtt: bool) -> ET.Element:
    """Gate 1 Digicon: contiguous Armstrong Brick→Plane window + HART names.

    One clone_rect only (abutting foreign bands ClassCasts VitalLogic).
    Main West Brick–Plane → Intermediate1 (HORIZONTAL between Brick ladder and Plane).
    True LH100 continuing geography requires Designer — GATE1_BRICK_PLANE.md.
    """
    src = ET.parse(TEMPLATE).getroot()
    src_tp = src.find("TRACKPLAN")
    assert src_tp is not None
    root, tp = header_shell()

    # Contiguous donor: Brick plant through Plane / Intermediate2 (SecEdge-safe).
    cells = clone_rect(src_tp, 3, 20, 2, 6, dx=0, dy=0)
    cells = [
        s
        for s in cells
        if not (
            s.find("TRACKGROUP") is None and s.find("SEC_NAME") is not None
        )
    ]
    clear_sec_names_on_track(cells)
    for s in cells:
        tp.append(s)
    prune_dangling_shared(root, tp)

    rename_blocks(
        root,
        {
            "YardLeft": "Main West",
            "Yardsiding": "OS Switch 1",
            "LeftLoop": "OS Switch 3",
            "YardInterchange": "W-1",
            "YardMain": "OS Switch 13",
            "YardRight": "OS Switch 7 (Barn)",
            "Yard": "S-1",
            "Yard2": "W-2",
            "Intermediate1": "Main West Brick–Plane",
            "Spur": "OS Switch 5",
            "Intermediate2": "East Main Ext",
        },
    )

    for x, y, text in (
        (4, 1, "HART Gate 1"),
        (5, 1, "Brick 100"),
        (13, 1, "Main West Brick–Plane"),
        (16, 1, "Plane 102"),
        (18, 2, "East Main Ext"),
        (5, 2, "Designer: LH100 continuing→east"),
        (8, 6, "yard OS101"),
    ):
        add_label(tp, x, y, text)

    center_trackplan(tp, pad_x=2, pad_y=1)
    cols = int(tp.get("COLUMNS") or "24")
    rows = int(tp.get("ROWS") or "10")
    finalize(
        root,
        mqtt=mqtt,
        width=max(1100, cols * 40),
        height=max(400, rows * 36),
        strip_turnout_io=True,
    )
    return root


def build_chassis(mqtt: bool) -> ET.Element:
    """Primary Digicon: full Armstrong TRACKPLAN + HART names by cell role.

    Keeps Armstrong SecEdge topology (load-safe). Main West Brick–Plane maps to
    Intermediate1 — a HORIZONTAL cell between Brick and Plane plants — not
    a turnout approach cell (the Chubb/Intermediate2 mistake).
    """
    plan = load_plan()
    root = ET.parse(TEMPLATE).getroot()
    for ops in root.iter("OPERATIONS"):
        ops.set("CONNECT", "false")
    tp = root.find("TRACKPLAN")
    assert tp is not None
    # Drop demo milepost labels on empty cells; HART chrome replaces them.
    for s in list(tp.findall("SECTION")):
        if s.find("TRACKGROUP") is None and s.find("SEC_NAME") is not None:
            tp.remove(s)
    clear_sec_names_on_track(list(tp.findall("SECTION")))
    rename_blocks(root, plan.get("chassis_block_map") or {})
    rename_labels(root, plan.get("chassis_label_map") or {})
    for lab in plan.get("chassis_extra_labels") or []:
        add_label(tp, int(lab["x"]), int(lab["y"]), lab["text"])
    center_trackplan(tp, pad_x=2, pad_y=1)
    cols = int(tp.get("COLUMNS") or "46")
    rows = int(tp.get("ROWS") or "10")
    finalize(
        root,
        mqtt=mqtt,
        width=max(1600, cols * 38),
        height=max(480, rows * 36),
        strip_turnout_io=True,
    )
    return root


def build_stacked(mqtt: bool) -> ET.Element:
    """Two-deck Digicon: Armstrong CTC spine + lower yard-body deck.

    Visually denser than a single 7-row strip; still clone-only.
    """
    plan = load_plan()
    src = ET.parse(TEMPLATE).getroot()
    src_tp = src.find("TRACKPLAN")
    assert src_tp is not None
    root, tp = header_shell()

    # Upper deck — full Armstrong (left margin X+=2)
    upper = clone_rect(src_tp, 1, 42, 1, 7, dx=2)
    upper = strip_label_row(upper, y=1)
    clear_sec_names_on_track(upper)
    for s in upper:
        tp.append(s)

    # Lower deck — ladder + siding bodies under the mains (dy=+9)
    lower_bits = [
        (8, 14, 1, 6, 3 - 8, 9),   # West/South yard ladder shape → X3-9
        (21, 26, 1, 6, 12 - 21, 9),  # classification siding → X12-17
        (15, 20, 1, 6, 20 - 15, 9),  # diverge / xover donor → X20-25
    ]
    lower_cells: list[ET.Element] = []
    for x0, x1, y0, y1, dx, dy in lower_bits:
        lower_cells.extend(clone_rect(src_tp, x0, x1, y0, y1, dx=dx, dy=dy))
    lower_cells = strip_label_row(lower_cells, y=1 + 9)
    # Also strip labels that landed on translated y=10 if any from y=1 source
    lower_cells = [
        s
        for s in lower_cells
        if not (
            s.find("TRACKGROUP") is None and s.find("SEC_NAME") is not None
        )
    ]
    clear_sec_names_on_track(lower_cells)
    for s in lower_cells:
        tp.append(s)

    prune_dangling_shared(root, tp)

    # Upper renames (HART spine)
    rename_blocks(root, plan.get("chassis_block_map") or {})
    # Lower deck only (y>=10) — yard body emphasis; do not touch upper spine
    _rename_blocks_in_x_range(
        tp,
        3,
        9,
        {
            "OS Switch 13": "S-1",
            "OS Switch 7 (Barn)": "S-2",
            "OS Switch 11": "S-3",
            "Scale": "S-4",
            "W-2": "S-5",
            "YardMain": "S-1",
            "YardRight": "S-2",
            "Intermediate1": "S-3",
            "Yard": "S-4",
            "Yard2": "S-5",
        },
        y0=10,
        y1=20,
    )
    _rename_blocks_in_x_range(
        tp,
        12,
        17,
        {
            "OS Switch 15": "Barn",
            "OS Switch 17": "EH-1",
            "OS Switch 19": "EH-2",
            "OS Switch 21": "EH-3",
            "SidingLeft": "Barn",
            "SidingSiding": "EH-1",
            "SidingMain": "EH-2",
            "SidingRight": "EH-3",
        },
        y0=10,
        y1=20,
    )
    _rename_blocks_in_x_range(
        tp,
        20,
        25,
        {
            "OS Switch 5": "OS Switch 9",
            "Main West Brick–Plane": "OS Switch 27",
            "Spur": "OS Switch 9",
            "Intermediate2": "OS Switch 27",
        },
        y0=10,
        y1=20,
    )

    add_label(tp, 3, 1, "HART RR")
    add_label(tp, 10, 1, "Brick / West Yard")
    add_label(tp, 17, 1, "Plane")
    add_label(tp, 25, 1, "South Yard")
    add_label(tp, 30, 1, "East End")
    add_label(tp, 38, 1, "Princess")
    add_label(tp, 40, 2, "Loops →")
    add_label(tp, 38, 6, "McKees Rocks")
    add_label(tp, 41, 6, "McKeesport")
    add_label(tp, 3, 9, "YARD BODY")
    add_label(tp, 5, 9, "YT 1-5 / West")
    add_label(tp, 14, 9, "T6/T9/T10/T11")
    add_label(tp, 22, 9, "OS Switch 9 / 108")

    tp.set("COLUMNS", "48")
    tp.set("ROWS", "17")
    finalize(root, mqtt=mqtt, width=1800, height=820)
    return root


def build_triple(mqtt: bool) -> ET.Element:
    """Three layout rows (Chubb-style density) from Armstrong clones only.

    Row 1 — MAIN / CTC spine (full Armstrong)
    Row 2 — YARDS (ladder + classification + diverge)
    Row 3 — EAST / LOOPS (east interlocking + Princess loop plant)
    """
    plan = load_plan()
    src = ET.parse(TEMPLATE).getroot()
    src_tp = src.find("TRACKPLAN")
    assert src_tp is not None
    root, tp = header_shell()

    def place(
        x0: int, x1: int, y0: int, y1: int, dx: int, dy: int
    ) -> tuple[int, int]:
        cells = clone_rect(src_tp, x0, x1, y0, y1, dx=dx, dy=dy)
        cells = [
            s
            for s in cells
            if not (
                s.find("TRACKGROUP") is None and s.find("SEC_NAME") is not None
            )
        ]
        clear_sec_names_on_track(cells)
        for s in cells:
            tp.append(s)
        if not cells:
            return 0, 0
        return (
            min(int(s.get("X")) for s in cells),
            max(int(s.get("X")) for s in cells),
        )

    # Row 1 — full CTC spine
    place(1, 42, 1, 7, dx=2, dy=0)

    # Row 2 — yards (dy=+8)
    place(1, 7, 1, 6, dx=3 - 1, dy=8)       # Brick throat
    place(8, 14, 1, 6, dx=11 - 8, dy=8)     # West Yard ladder
    place(21, 26, 1, 6, dx=19 - 21, dy=8)   # South Yard body
    place(15, 20, 1, 6, dx=26 - 15, dy=8)   # Plane / xover donor

    # Row 3 — east + loops (dy=+16)
    place(27, 32, 1, 6, dx=3 - 27, dy=16)   # East main bridge
    place(21, 26, 1, 6, dx=10 - 21, dy=16)  # East End plant
    place(15, 20, 1, 6, dx=17 - 15, dy=16)  # Xover 111/113 donor
    place(33, 42, 1, 7, dx=24 - 33, dy=16)  # Princess loops

    prune_dangling_shared(root, tp)

    # Global chassis names first (hits row 1 Armstrong names)
    rename_blocks(root, plan.get("chassis_block_map") or {})

    # Row 2 renames — yard body focus
    _rename_blocks_in_x_range(
        tp,
        3,
        9,
        {
            "OS Switch 1": "OS Switch 1",
            "OS Switch 3": "OS Switch 3",
            "Main West": "Main West",
            "W-1": "W-1",
            "Yardsiding": "OS Switch 1",
            "LeftLoop": "OS Switch 3",
            "YardLeft": "Main West",
            "YardInterchange": "W-1",
        },
        y0=9,
        y1=15,
    )
    _rename_blocks_in_x_range(
        tp,
        11,
        17,
        {
            "OS Switch 13": "OS Switch 13",
            "OS Switch 7 (Barn)": "OS Switch 7 (Barn)",
            "OS Switch 11": "OS Switch 11",
            "Scale": "Scale",
            "W-2": "W-2",
            "YardMain": "OS Switch 13",
            "YardRight": "OS Switch 7 (Barn)",
            "Intermediate1": "OS Switch 11",
            "Yard": "Scale",
            "Yard2": "W-2",
        },
        y0=9,
        y1=15,
    )
    _rename_blocks_in_x_range(
        tp,
        19,
        24,
        {
            "OS Switch 15": "S-1",
            "OS Switch 17": "S-2",
            "OS Switch 19": "S-3",
            "OS Switch 21": "S-4",
            "SidingLeft": "S-1",
            "SidingSiding": "S-2",
            "SidingMain": "S-3",
            "SidingRight": "S-4",
        },
        y0=9,
        y1=15,
    )
    _rename_blocks_in_x_range(
        tp,
        26,
        31,
        {
            "OS Switch 5": "S-5",
            "Main West Brick–Plane": "OS Switch 9",
            "Spur": "S-5",
            "Intermediate2": "OS Switch 9",
        },
        y0=9,
        y1=15,
    )

    # Row 3 renames — east / loops
    _rename_blocks_in_x_range(
        tp,
        3,
        8,
        {
            "OS Switch 25": "East Main Ext",
            "OS Switch 31": "Main East",
            "Intermediate3": "East Main Ext",
            "Intermediate4": "Main East",
        },
        y0=17,
        y1=24,
    )
    _rename_blocks_in_x_range(
        tp,
        10,
        15,
        {
            "S-1": "OS Switch 25",
            "S-2": "OS Switch 27",
            "S-3": "OS Switch 29",
            "S-4": "OS Switch 31",
            "OS Switch 15": "OS Switch 25",
            "OS Switch 17": "OS Switch 27",
            "OS Switch 19": "OS Switch 29",
            "OS Switch 21": "OS Switch 31",
            "SidingLeft": "OS Switch 25",
            "SidingSiding": "OS Switch 27",
            "SidingMain": "OS Switch 29",
            "SidingRight": "OS Switch 31",
        },
        y0=17,
        y1=24,
    )
    _rename_blocks_in_x_range(
        tp,
        17,
        22,
        {
            "S-5": "OS Switch 23a",
            "OS Switch 9": "OS Switch 33",
            "OS Switch 5": "OS Switch 23a",
            "Main West Brick–Plane": "OS Switch 33",
            "Spur": "OS Switch 23a",
            "Intermediate2": "OS Switch 33",
        },
        y0=17,
        y1=24,
    )
    # Princess loop plant on row 3 keeps chassis loop names if already mapped;
    # force McKees + Princess OS on that band.
    _rename_blocks_in_x_range(
        tp,
        24,
        40,
        {
            "OS Switch 23a": "OS Switch 35b",
            "OS Switch 35b": "OS Switch 35b",
            "East Lead": "East Lead",
            "OS Switch 37": "OS Switch 37",
            "OS Switch 39": "OS Switch 39",
            "McKees Rocks": "McKees Rocks",
            "McKeesport": "McKeesport",
            "WyeLeft": "OS Switch 35b",
            "WyeSiding": "OS Switch 37",
            "WyeMain": "East Lead",
            "WyeMiddle": "OS Switch 39",
            "WyeRight": "OS Switch 33",
            "Wye": "McKees Rocks",
            "WyeLoop": "McKeesport",
        },
        y0=17,
        y1=24,
    )

    # Deck banners + plant titles
    for x, y, text in (
        (2, 1, "ROW 1 — MAIN / CTC"),
        (12, 1, "Brick"),
        (17, 1, "West Yard"),
        (22, 1, "Plane"),
        (28, 1, "South Yard"),
        (33, 1, "East End"),
        (40, 1, "Princess"),
        (40, 2, "Loops →"),
        (2, 8, "ROW 2 — YARDS"),
        (5, 8, "Brick throat"),
        (13, 8, "West Yard ladder"),
        (20, 8, "S-1–S-4"),
        (27, 8, "YT5 / OS Switch 9"),
        (2, 16, "ROW 3 — EAST / LOOPS"),
        (5, 16, "East Main"),
        (12, 16, "East End OS"),
        (18, 16, "Xover 111"),
        (28, 16, "Princess loops"),
        (30, 22, "McKees Rocks"),
        (32, 23, "McKeesport"),
    ):
        add_label(tp, x, y, text)

    add_label(tp, 3, 2, "HART RR")

    tp.set("COLUMNS", "48")
    tp.set("ROWS", "25")
    finalize(root, mqtt=mqtt, width=1800, height=1100)
    return root


def build_ladder_frag(mqtt: bool) -> ET.Element:
    src = ET.parse(TEMPLATE).getroot()
    src_tp = src.find("TRACKPLAN")
    assert src_tp is not None
    root, tp = header_shell()
    for s in clone_rect(src_tp, 8, 14, 1, 6, dx=-7):
        tp.append(s)
    plan = load_plan()
    rename_blocks(root, plan.get("chassis_block_map") or {})
    add_label(tp, 2, 1, "HART ladder frag")
    tp.set("COLUMNS", "12")
    tp.set("ROWS", "7")
    finalize(root, mqtt=mqtt, width=900, height=360)
    return root


def build_chubb(mqtt: bool) -> ET.Element:
    """Native 3-row Digicon (Chubb Route chassis) with HART deck chrome.

    Topology is Chubb's SecEdge graph — classic 3-row CTC look (operator preferred).
    """
    if not CHUBB.is_file():
        raise SystemExit(f"Missing {CHUBB}")
    root = ET.parse(CHUBB).getroot()
    for ops in root.iter("OPERATIONS"):
        ops.set("CONNECT", "false")
    tp = root.find("TRACKPLAN")
    assert tp is not None

    # Drop all Chubb demo label-only cells (we place HART chrome ourselves).
    for s in list(tp.findall("SECTION")):
        if s.find("TRACKGROUP") is None and s.find("SEC_NAME") is not None:
            tp.remove(s)

    # Clear leftover lever/block callouts sitting on track cells.
    clear_sec_names_on_track(list(tp.findall("SECTION")))

    # Name stickers follow Digicon SecEdge adjacency (contiguous L→R on each
    # deck) AND JMRI block neighbors from hart_prod — not arbitrary plant labels.
    # Each HART name appears once (no duplicate MQTT cells / christmas-tree).
    rename_blocks(
        root,
        {
            # R1 spine a1→a9: JMRI path Main West → East Lead via Brick/Plane
            "aBlock 1": "Main West",
            "aBlock 2": "OS Switch 1",
            "aBlock 3": "Main West Brick–Plane",
            "aBlock 4": "OS Switch 5",
            "aBlock 5": "East Main Ext",
            # Main East ↔ East Main Ext uses TO117 bottom C/D = OS Switch 7b (M2S1303),
            # not top A/B OS Switch 7 (M2S1302 / Scale–Barn side).
            "aBlock 6": "OS Switch 7b (Barn)",
            "aBlock 7": "Main East",
            "aBlock 8": "OS Switch 33",
            "aBlock 9": "East Lead",
            # R1 diverge (Digicon-connected under the plant): South Yard → East End
            "aBlock10": "OS Switch 15",
            "aBlock 11": "OS Switch 17",
            "aBlock 16": "OS Switch 19",
            "aBlock 17": "OS Switch 21",
            "aBlock 18": "OS Switch 25",
            "aBlock 19": "OS Switch 27",
            # R2 yard body d1→d15 (Digicon-contiguous); no second East Lead
            "dBlock 1": "OS Switch 3",
            "dBlock 2": "OS Switch 13",
            "dBlock 3": "OS Switch 11",
            "dBlock 4": "OS Switch 9",
            "dBlock 5": "Barn",
            "dBlock 6": "OS Switch 7 (Barn)",  # TO117 top A/B (Scale/Barn side)
            "dBlock 7": "W-1",
            "dBlock 8": "W-2",
            "dBlock 9": "EH-1",
            "dBlock 10": "S-1",
            "dBlock 11": "S-2",
            "dBlock 12": "S-3",
            "dBlock 13": "S-4",
            "dBlock 14": "S-5",
            "dBlock 15": "OS Switch 23a",
            "dBlock 16": "OS Switch 29",
            "dBlack 17": "OS Switch 31",
            "dBlock 18": "OS Switch 23b",
            "dBlock 19": "EH-2",
            # EH-3: keep on leftover Chubb name via explicit rename of fBlock 8
            "fBlock 8": "EH-3",
            # R3 Princess reverse-loop chain (unique names; Digicon f1→f7)
            "fBlock 1": "West Main Ext",
            "fBlock 2": "OS Switch 35b",
            "fBlock 3": "OS Switch 35a",
            "fBlock 4": "OS Switch 37",
            "fBlock 5": "McKeesport",
            "fBlock 6": "OS Switch 39",
            "fBlock 7": "McKees Rocks",
            # f8/f9/f10/f11/f16 keep Chubb demo names (unwired) — clearing NAME NPEs CATS.
        },
    )

    # Chrome matches contiguous decks (spine / yard / loops).
    for x, y, text in (
        (3, 1, "R1 MAIN"),
        (7, 1, "HART RR"),
        (10, 1, "Brick"),
        (13, 1, "Plane"),
        (16, 1, "Barn/117b"),
        (19, 1, "East→Lead"),
        # Digicon turnout glyphs live at X≈7 and X≈14 (not under OS names).
        (7, 2, "◈ plant"),
        (14, 2, "◈ plant"),
        (10, 2, "100"),
        (13, 2, "102"),
        (16, 2, "EME·117b·ME"),
        (19, 2, "112·Lead"),
        (3, 0, "CTC schematic≠LE geography"),
        (3, 6, "R2 YARD"),
        (7, 6, "West Yard"),
        (12, 6, "Tracks 1-5"),
        (16, 6, "YT body"),
        (20, 6, "→111a"),
        (7, 7, "101·116·117top"),
        (12, 7, "YT1-5"),
        (20, 7, "East End"),
        (3, 11, "R3 LOOPS"),
        (7, 11, "Princess"),
        (12, 11, "113b→114"),
        (16, 11, "McKeesport"),
        (20, 11, "Rocks"),
        (7, 12, "W Main Ext"),
        (12, 12, "OS 113-115"),
        (16, 12, "← reverse"),
        (20, 12, "← reverse"),
        (3, 15, "1 name=1 cell"),
    ):
        add_label(tp, x, y, text)

    # Do NOT splice spacer track columns — that ClassCasts SecEdge.
    # Left "cutoff" was long SEC_NAME text centered on X=1 overflowing the
    # window; short titles at X>=3 fix it. Soft pad only for COLUMNS/ROWS.
    center_trackplan(tp, pad_x=2, pad_y=1)
    cols = int(tp.get("COLUMNS") or "26")
    rows = int(tp.get("ROWS") or "18")
    # Keep WIDTH close to painted board width — oversized WIDTH leaves a huge
    # empty black field on the right (CATS paints the grid top-left).
    width = max(980, cols * 40)
    height = max(560, rows * 34)
    finalize(root, mqtt=mqtt, width=width, height=height, strip_turnout_io=True)
    return root


def build_splice(mqtt: bool) -> ET.Element:
    """Experimental sparse plant concatenation (often looks like repeated spurs)."""
    # Minimal legacy splice: natural Armstrong plant bands with spacers
    src = ET.parse(TEMPLATE).getroot()
    src_tp = src.find("TRACKPLAN")
    assert src_tp is not None
    root, tp = header_shell()
    plan = load_plan()
    cursor = 3
    bands = [
        ("Brick / West Yard", 1, 14, 1, 6),
        ("Plane", 15, 20, 1, 6),
        ("South Yard", 21, 26, 1, 6),
        ("East End", 27, 32, 1, 6),
        ("Princess / Loops", 33, 42, 1, 7),
    ]
    titles: list[tuple[int, str]] = []
    for title, x0, x1, y0, y1 in bands:
        dx = cursor - x0
        cells = clone_rect(src_tp, x0, x1, y0, y1, dx)
        cells = strip_label_row(cells, y=1)
        clear_sec_names_on_track(cells)
        for s in cells:
            tp.append(s)
        x_lo = min(int(s.get("X")) for s in cells)
        x_hi = max(int(s.get("X")) for s in cells)
        titles.append(((x_lo + x_hi) // 2, title))
        cursor = x_hi + 2
    prune_dangling_shared(root, tp)
    rename_blocks(root, plan.get("chassis_block_map") or {})
    add_label(tp, 3, 1, "HART RR")
    for x, text in titles:
        add_label(tp, x, 1, text)
    add_label(tp, cursor - 8, 2, "Loops →")
    tp.set("COLUMNS", str(cursor + 2))
    tp.set("ROWS", "8")
    finalize(root, mqtt=mqtt, width=max(1600, cursor * 32), height=520)
    return root


def write(path: Path, root: ET.Element) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)
    nsec = len(list(root.iter("SECTION")))
    nsw = len(list(root.iter("SWITCHPOINTS")))
    nsig = len(list(root.iter("SECSIGNAL")))
    blocks = sorted({b.get("NAME") for b in root.iter("BLOCK") if b.get("NAME")})
    print(f"Wrote {path}  (sections={nsec} switches={nsw} signals={nsig} w={root.get('WIDTH')} h={root.get('HEIGHT')})")
    print(f"  blocks({len(blocks)}): {', '.join(blocks)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--only",
        choices=(
            "all",
            "gate1",
            "magnet",
            "triple",
            "stacked",
            "chubb",
            "splice",
            "ladder",
            "armstrong",
        ),
        default="all",
    )
    ap.add_argument(
        "--wire-only",
        type=Path,
        metavar="PANEL.xml",
        help="Add MQTT/occupancy/trains to existing panel; do not rebuild TRACKPLAN",
    )
    args = ap.parse_args()

    if args.wire_only is not None:
        wire_existing_panel(args.wire_only.resolve())
        return

    if not TEMPLATE.is_file():
        raise SystemExit(f"Missing {TEMPLATE} — run tools/cats/fetch_cats_3.2.sh")

    if args.only == "gate1":
        write(OUT_DIR / "HART_gate1_magnet.xml", build_gate1(mqtt=False))
        write(OUT_DIR / "HART_gate1.xml", build_gate1(mqtt=True))
    elif args.only == "stacked":
        write(OUT_DIR / "HART_stacked_magnet.xml", build_stacked(mqtt=False))
        write(OUT_DIR / "HART_magnet.xml", build_stacked(mqtt=False))
        write(OUT_DIR / "HART.xml", build_stacked(mqtt=True))
    elif args.only == "triple":
        write(OUT_DIR / "HART_triple_magnet.xml", build_triple(mqtt=False))
    elif args.only == "chubb":
        write(OUT_DIR / "HART_chubb_magnet.xml", build_chubb(mqtt=False))
    elif args.only in ("all", "magnet", "armstrong"):
        # Primary: full Armstrong Digicon — Brick→Plane→South Yard→East End→Princess
        write(OUT_DIR / "HART_magnet.xml", build_chassis(mqtt=False))
        write(OUT_DIR / "HART.xml", build_chassis(mqtt=True))
        write(OUT_DIR / "HART_armstrong_magnet.xml", build_chassis(mqtt=False))
        if args.only == "all":
            write(OUT_DIR / "HART_gate1_magnet.xml", build_gate1(mqtt=False))
            write(OUT_DIR / "HART_chubb_magnet.xml", build_chubb(mqtt=False))
            write(OUT_DIR / "HART_stacked_magnet.xml", build_stacked(mqtt=False))
            write(OUT_DIR / "HART_triple_magnet.xml", build_triple(mqtt=False))
            write(OUT_DIR / "HART_ladder_frag.xml", build_ladder_frag(mqtt=False))
            write(OUT_DIR / "HART_splice_magnet.xml", build_splice(mqtt=False))

    print()
    print("PRIMARY: cats/panels/HART.xml  (full Digicon — all plants)")
    print("DESIGNER west-end: python3 cats/scripts/wire_designer_ctc_rules.py")
    print("ALT:     --only gate1|stacked|chubb|triple")


if __name__ == "__main__":
    main()
