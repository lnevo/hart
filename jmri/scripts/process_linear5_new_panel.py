#!/usr/bin/env python3
"""
Process a linear5 JMRI save with new yard turnouts (TO*) and AUTOBLK blocks.

- Renames layout AUTOBLK:N → Block_N (N matches JMRI auto-block id)
- Adds Block Sensor N + block/layoutblock entries for new blocks
- Assigns placeholder DCC addresses 116+ to new motor turnouts (west → east)
- Adds DCC labels on the panel for those addresses
- Merges geometry into output/linear5_blocked.xml at 1/display_scale
- Sets mainline on yard segments: engine-terminal sidings T1/T3/T4/T6/T7/T9–T13 → no;
  T5/T8 stay mainline yes (operator preference from Pi panel)
- Appends pending rows to data/turnout_mapping.csv

Usage:
  python3 jmri/scripts/process_linear5_new_panel.py \\
    jmri/layouts/linear6/linear5_new.xml
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import xml.etree.ElementTree as ET

JMRI_ROOT = Path(__file__).resolve().parents[1]
JMRI_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(JMRI_SCRIPTS))

from build_linear4_device_mapping import (  # noqa: E402
    _INTEGER_COORD_TAGS,
    _LAYOUT_COORD_ATTRS,
    _blocked_coord_from_prod,
    _find_layout_editor,
    _make_dcc_label,
    _write_jmri_panel_xml,
)

LAYOUT5 = JMRI_ROOT / "layouts" / "linear5"
VIEWPORT_JSON = LAYOUT5 / "data" / "viewport.json"
BLOCKED_PATH = LAYOUT5 / "output" / "linear5_blocked.xml"
TURNOUT_MAPPING_CSV = LAYOUT5 / "data" / "turnout_mapping.csv"
PENDING_JSON = LAYOUT5 / "data" / "pending_turnout_assignments.json"
YARD_HARDWARE_JSON = LAYOUT5 / "data" / "yard_turnout_hardware.json"
SENSOR_MAPPING_CSV = LAYOUT5 / "data" / "sensor_mapping.csv"

NEW_TURNOUT_IDENTS = frozenset({"TO1", "TO6", "TO8", "TO10", "TO11"})
YARD_TRACK_IDENTS = frozenset(
    {"T1", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "T13"}
)
# Engine terminal tracks drawn as sidings (sidetrack width) — operator set on Pi 2026-08.
ENGINE_TERMINAL_SIDETRACK = frozenset(
    {"T1", "T3", "T4", "T6", "T7", "T9", "T10", "T11", "T12", "T13"}
)
# Remaining yard segments that should stay mainline-styled.
YARD_MAINLINE_TRACK = YARD_TRACK_IDENTS - ENGINE_TERMINAL_SIDETRACK

# Curated placeholder DCC assignments (116–119) for west-yard turnouts.
PENDING_TURNOUT_DCC: dict[str, int] = {
    "TO1": 116,   # was 120
    "TO6": 117,   # was 116; shares label with TO8
    "TO8": 117,   # was 118
    "TO10": 119,  # was 117
    "TO11": 118,  # was 119
}


def apply_yard_mainline_flags(layout: ET.Element) -> int:
    """
    Apply yard track mainline flags from the curated operator panel.

    Engine-terminal sidings (``ENGINE_TERMINAL_SIDETRACK``) use ``mainline="no"``
    (sidetrack width). Other yard segments in ``YARD_MAINLINE_TRACK`` stay
    ``mainline="yes"``.

    NOTE: The JMRI schema only allows ``mainline`` on ``tracksegment`` — NOT on
    ``layoutturnout`` (a turnout's mainline status is derived from its connected
    segments). Setting it on a turnout produces a parse error on load, so we also
    strip any stray ``mainline`` attribute off layoutturnout elements here.
    """
    n = 0
    for ts in layout.findall("tracksegment"):
        ident = ts.get("ident") or ""
        if ident in ENGINE_TERMINAL_SIDETRACK:
            if ts.get("mainline") != "no":
                ts.set("mainline", "no")
                n += 1
        elif ident in YARD_MAINLINE_TRACK:
            if ts.get("mainline") != "yes":
                ts.set("mainline", "yes")
                n += 1
    for lt in layout.findall("layoutturnout"):
        if lt.get("mainline") is not None:
            del lt.attrib["mainline"]
            n += 1
    return n


def _load_yard_hardware() -> list[dict]:
    if not YARD_HARDWARE_JSON.is_file():
        raise SystemExit(f"Missing {YARD_HARDWARE_JSON}")
    data = json.loads(YARD_HARDWARE_JSON.read_text(encoding="utf-8"))
    return list(data.get("turnouts", []))


def _manager_by_class(root: ET.Element, tag: str, class_sub: str) -> ET.Element | None:
    for mgr in root.findall(tag):
        if class_sub in (mgr.get("class") or ""):
            return mgr
    return None


def _existing_system_names(mgr: ET.Element | None) -> set[str]:
    if mgr is None:
        return set()
    names: set[str] = set()
    for child in mgr:
        sn = child.get("systemName") or child.findtext("systemName")
        if sn:
            names.add(sn.strip())
    return names


def _append_mqtt_sensor(mgr: ET.Element, system: str, user: str) -> bool:
    if system in _existing_system_names(mgr):
        return False
    s = ET.SubElement(mgr, "sensor", {"inverted": "false"})
    ET.SubElement(s, "systemName").text = system
    ET.SubElement(s, "userName").text = user
    return True


def _append_mqtt_turnout(
    mgr: ET.Element, *, system: str, user: str, s_r: str, s_n: str
) -> bool:
    if system in _existing_system_names(mgr):
        return False
    t = ET.SubElement(
        mgr,
        "turnout",
        {
            "feedback": "TWOSENSOR",
            "sensor1": s_r,
            "sensor2": s_n,
            "inverted": "false",
            "automate": "Off",
        },
    )
    ET.SubElement(t, "systemName").text = system
    ET.SubElement(t, "userName").text = user
    return True


def _append_internal_turnout(
    mgr: ET.Element, *, system: str, user: str, s_r: str, s_n: str
) -> bool:
    if system in _existing_system_names(mgr):
        return False
    t = ET.SubElement(
        mgr,
        "turnout",
        {
            "feedback": "TWOSENSOR",
            "sensor1": s_r,
            "sensor2": s_n,
            "inverted": "false",
            "automate": "Off",
        },
    )
    ET.SubElement(t, "systemName").text = system
    ET.SubElement(t, "userName").text = user
    return True


def apply_yard_mqtt_hardware(root: ET.Element) -> dict[str, int]:
    """Wire yard TO* turnouts to MQTT/IT devices; update mapping CSVs."""
    layout = _find_layout_editor(root)
    if layout is None:
        raise SystemExit("LayoutEditor missing")

    yard = _load_yard_hardware()
    by_ident = {row["layout_ident"]: row for row in yard}

    for lt in layout.findall("layoutturnout"):
        ident = lt.get("ident") or ""
        row = by_ident.get(ident)
        if row is None:
            continue
        lt.set("turnoutname", row["panel_system"])

    mqtt_sensors = _manager_by_class(root, "sensors", "MqttSensorManagerXml")
    mqtt_turnouts = _manager_by_class(root, "turnouts", "MqttTurnoutManagerXml")
    internal_turnouts = _manager_by_class(root, "turnouts", "InternalTurnoutManagerXml")

    stats = {"sensors": 0, "mqtt_turnouts": 0, "internal_turnouts": 0}
    seen_sensor_systems: set[str] = set()

    for row in yard:
        s_n = row["feedback_sensor_n"]
        s_r = row["feedback_sensor_r"]
        for sensor in (s_n, s_r):
            sys_name = sensor["system"]
            if sys_name in seen_sensor_systems:
                continue
            seen_sensor_systems.add(sys_name)
            if mqtt_sensors is not None and _append_mqtt_sensor(
                mqtt_sensors, sys_name, sensor["user"]
            ):
                stats["sensors"] += 1

        if row["kind"] == "mqtt":
            if mqtt_turnouts is not None and _append_mqtt_turnout(
                mqtt_turnouts,
                system=row["panel_system"],
                user=row["panel_user"],
                s_r=s_r["user"],
                s_n=s_n["user"],
            ):
                stats["mqtt_turnouts"] += 1
        elif row["kind"] == "internal_mqtt_fb":
            if internal_turnouts is not None and _append_internal_turnout(
                internal_turnouts,
                system=row["panel_system"],
                user=row["panel_user"],
                s_r=s_r["user"],
                s_n=s_n["user"],
            ):
                stats["internal_turnouts"] += 1

    _update_yard_turnout_mapping_csv(layout, yard)
    _update_yard_sensor_mapping_csv(yard)
    _write_yard_pending_json(yard)
    return stats


def _update_yard_turnout_mapping_csv(layout: ET.Element, yard: list[dict]) -> None:
    coords = {
        lt.get("ident"): (float(lt.get("xcen", 0)), float(lt.get("ycen", 0)))
        for lt in layout.findall("layoutturnout")
    }
    rows = []
    if TURNOUT_MAPPING_CSV.is_file():
        with TURNOUT_MAPPING_CSV.open(encoding="utf-8") as f:
            rows = list(csv.reader(f))
    if not rows:
        return
    header, *data = rows
    kept = [r for r in data if r and r[0] not in NEW_TURNOUT_IDENTS]
    for row in yard:
        ident = row["layout_ident"]
        x, y = coords.get(ident, (0.0, 0.0))
        s_n = row["feedback_sensor_n"]
        s_r = row["feedback_sensor_r"]
        motor_sys = row.get("motor_system", "")
        motor_user = row.get("motor_user", "")
        if row["kind"] == "internal_mqtt_fb":
            kept.append(
                [
                    ident,
                    f"{x:.2f}",
                    f"{y:.2f}",
                    ident,
                    row["kind"],
                    row["panel_system"],
                    ident,
                    row["panel_system"],
                    motor_sys,
                    motor_user,
                    s_r["user"],
                    s_r["system"],
                    s_n["user"],
                    s_n["system"],
                    row["switch_id"],
                    str(row["dcc_address"]),
                    "0.0",
                    row.get("notes", ""),
                ]
            )
        else:
            kept.append(
                [
                    ident,
                    f"{x:.2f}",
                    f"{y:.2f}",
                    ident,
                    row["kind"],
                    row["panel_system"],
                    row["panel_user"],
                    "",
                    row["panel_system"],
                    row["panel_user"],
                    s_r["user"],
                    s_r["system"],
                    s_n["user"],
                    s_n["system"],
                    row["switch_id"],
                    str(row["dcc_address"]),
                    "0.0",
                    "",
                ]
            )
    with TURNOUT_MAPPING_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(kept)


def _update_yard_sensor_mapping_csv(yard: list[dict]) -> None:
    if not SENSOR_MAPPING_CSV.is_file():
        return
    with SENSOR_MAPPING_CSV.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header, *data = rows
    kept = [r for r in data if r and r[5] not in NEW_TURNOUT_IDENTS]
    for row in yard:
        ident = row["layout_ident"]
        s_n = row["feedback_sensor_n"]
        s_r = row["feedback_sensor_r"]
        for role, sensor, suffix in (
            ("turnout_feedback_thrown", s_r, "FB_R"),
            ("turnout_feedback_closed", s_n, "FB_N"),
        ):
            kept.append(
                [
                    role,
                    f"{ident} {suffix}",
                    "",
                    sensor["system"],
                    sensor["user"],
                    ident,
                    "",
                    f"Yard turnout {ident}",
                ]
            )
    with SENSOR_MAPPING_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(kept)


def _write_yard_pending_json(yard: list[dict]) -> None:
    PENDING_JSON.write_text(
        json.dumps(
            {
                "note": "West-yard MQTT hardware assignments (linear5).",
                "assignments": [
                    {
                        "layout_ident": row["layout_ident"],
                        "kind": row["kind"],
                        "panel_system": row["panel_system"],
                        "panel_user": row["panel_user"],
                        "motor_system": row.get("motor_system"),
                        "switch_id": row["switch_id"],
                        "dcc_address": row["dcc_address"],
                        "feedback_sensors": [
                            row["feedback_sensor_n"],
                            row["feedback_sensor_r"],
                        ],
                    }
                    for row in yard
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


TRACK_TAGS = frozenset({"positionablepoint", "layoutturnout", "tracksegment"})
AUTOBLK_RE = re.compile(r"^AUTOBLK:(\d+)$")
ROUTING_BLOCK_RE = re.compile(r"^IB\d+$")


def _local_tag(elem: ET.Element) -> str:
    return (elem.tag or "").split("}")[-1].lower()


def _load_viewport() -> dict:
    if not VIEWPORT_JSON.is_file():
        return {"display_scale": 1.5, "panel_x_shift_display": 25}
    return json.loads(VIEWPORT_JSON.read_text(encoding="utf-8"))


def _collect_layout_block_nums(layout: ET.Element) -> set[int]:
    nums: set[int] = set()
    for el in layout.iter():
        if _local_tag(el) not in ("tracksegment", "layoutturnout"):
            continue
        bn = el.get("blockname") or ""
        m = AUTOBLK_RE.match(bn)
        if m:
            nums.add(int(m.group(1)))
        elif bn.startswith("Block_"):
            try:
                nums.add(int(bn.split("_", 1)[1]))
            except ValueError:
                pass
    return nums


def _rename_autoblk_text(value: str, used: set[int]) -> str:
    m = AUTOBLK_RE.match(value.strip())
    if m and int(m.group(1)) in used:
        return f"Block_{m.group(1)}"
    return value


def _insert_occupancysensor(block: ET.Element, sensor_name: str) -> None:
    """JMRI schema: occupancysensor must appear before path elements."""
    existing = block.find("occupancysensor")
    if existing is not None:
        existing.text = sensor_name
        return
    occ = ET.Element("occupancysensor")
    occ.text = sensor_name
    insert_at = 0
    for i, child in enumerate(block):
        if _local_tag(child) in ("systemname", "username", "permissive", "comment"):
            insert_at = i + 1
    block.insert(insert_at, occ)


def _normalize_blocks_section(root: ET.Element) -> int:
    """
    Fix JMRI block XML: drop duplicate IB* stubs, remove occupancysensor from
    routing blocks (those with path children), fix element order elsewhere.
    """
    blocks_parent = root.find(".//blocks[@class='jmri.configurexml.BlockManagerXml']")
    if blocks_parent is None:
        return 0
    n = 0
    by_system: dict[str, list[ET.Element]] = {}
    for block in blocks_parent.findall("block"):
        sn = (block.get("systemName") or block.findtext("systemName") or "").strip()
        if sn:
            by_system.setdefault(sn, []).append(block)

    for sn, group in by_system.items():
        if len(group) < 2:
            continue
        with_paths = [b for b in group if b.findall("path")]
        without_paths = [b for b in group if not b.findall("path")]
        for stub in without_paths:
            if with_paths:
                blocks_parent.remove(stub)
                n += 1

    for block in blocks_parent.findall("block"):
        sn = (block.get("systemName") or block.findtext("systemName") or "").strip()
        paths = block.findall("path")
        occ = block.find("occupancysensor")
        if paths and occ is not None:
            if ROUTING_BLOCK_RE.match(sn):
                # Pure IB* routing stubs have no sensor; assigned Block_N keep occupancy.
                un = _block_username(block)
                if not un.startswith("Block_"):
                    block.remove(occ)
                    n += 1
                else:
                    text = (occ.text or "").strip()
                    block.remove(occ)
                    _insert_occupancysensor(block, text)
                    n += 1
            else:
                text = (occ.text or "").strip()
                block.remove(occ)
                _insert_occupancysensor(block, text)
                n += 1
            continue
        if occ is None:
            continue
        text = (occ.text or "").strip()
        block.remove(occ)
        _insert_occupancysensor(block, text)
        n += 1
    return n


def _restore_occupancy_from_reference(root: ET.Element, ref_path: Path) -> int:
    """Copy missing occupancysensor children from a known-good panel (e.g. linear5_prod)."""
    if not ref_path.is_file():
        return 0
    ref_blocks = ET.parse(ref_path).getroot().find(
        ".//blocks[@class='jmri.configurexml.BlockManagerXml']"
    )
    blocks_parent = root.find(".//blocks[@class='jmri.configurexml.BlockManagerXml']")
    if ref_blocks is None or blocks_parent is None:
        return 0
    ref_occ = {}
    for block in ref_blocks.findall("block"):
        sn = (block.get("systemName") or block.findtext("systemName") or "").strip()
        occ = block.find("occupancysensor")
        if sn and occ is not None and (occ.text or "").strip():
            ref_occ[sn] = (occ.text or "").strip()
    n = 0
    for block in blocks_parent.findall("block"):
        sn = (block.get("systemName") or block.findtext("systemName") or "").strip()
        if not sn or sn not in ref_occ or block.find("occupancysensor") is not None:
            continue
        if ROUTING_BLOCK_RE.match(sn):
            continue
        _insert_occupancysensor(block, ref_occ[sn])
        n += 1
    return n


def _fix_autoblk_names(root: ET.Element, used: set[int]) -> int:
    """Rename AUTOBLK:N → Block_N on layout + block tables."""
    n = 0
    layout = _find_layout_editor(root)
    if layout is not None:
        for el in layout.iter():
            if _local_tag(el) not in ("tracksegment", "layoutturnout"):
                continue
            bn = el.get("blockname") or ""
            m = AUTOBLK_RE.match(bn)
            if m and int(m.group(1)) in used:
                el.set("blockname", f"Block_{m.group(1)}")
                n += 1

    for lb in root.findall(".//layoutblocks/layoutblock"):
        un = (lb.findtext("userName") or lb.get("userName") or "").strip()
        m = AUTOBLK_RE.match(un)
        if m and int(m.group(1)) in used:
            num = int(m.group(1))
            for child in list(lb):
                if _local_tag(child) == "username":
                    child.text = f"Block_{num}"
            if lb.find("userName") is None:
                ET.SubElement(lb, "userName").text = f"Block_{num}"
            lb.set("occupancysensor", f"Block Sensor {num}")
            n += 1

    blocks_parent = root.find(".//blocks[@class='jmri.configurexml.BlockManagerXml']")
    if blocks_parent is not None:
        for block in list(blocks_parent.findall("block")):
            un_el = block.find("userName")
            un = (un_el.text if un_el is not None else "").strip()
            m = AUTOBLK_RE.match(un)
            if not m:
                continue
            num = int(m.group(1))
            if num in used:
                if un_el is not None:
                    un_el.text = f"Block_{num}"
                # Routing autoblocks (IB* with paths) keep userName only; ILB* carries occupancy.
                if num >= 48 and not block.findall("path"):
                    _insert_occupancysensor(block, f"Block Sensor {num}")
                n += 1
            elif num < 48 or num not in used:
                # Drop unused JMRI scratch autoblocks (49–52, 54, 56–58, …).
                blocks_parent.remove(block)
                n += 1
    return n


NEW_YARD_BLOCK_MIN = 48


def _turnout_block_occupancy_names(layout: ET.Element) -> dict[str, str]:
    """Block_N on a layout turnout -> BS <ident> (matches blocks 30–47)."""
    out: dict[str, str] = {}
    for lt in layout.findall("layoutturnout"):
        bn = (lt.get("blockname") or "").strip()
        if bn.startswith("Block_"):
            ident = (lt.get("ident") or "").strip()
            if ident:
                out[bn] = f"BS {ident}"
    return out


def _occupancy_sensor_for_block(block_name: str, turnout_occ: dict[str, str]) -> str:
    if block_name in turnout_occ:
        return turnout_occ[block_name]
    num = _block_num_from_username(block_name)
    if num is not None:
        return f"Block Sensor {num}"
    return ""


def _max_isis_index(sensors_parent: ET.Element) -> int:
    best = 0
    for sensor in sensors_parent.findall("sensor"):
        m = re.search(r"ISIS(\d+)$", (sensor.findtext("systemName") or "").strip())
        if m:
            best = max(best, int(m.group(1)))
    return best


def _sensor_by_username(sensors_parent: ET.Element, username: str) -> ET.Element | None:
    want = username.strip()
    for sensor in sensors_parent.findall("sensor"):
        if (sensor.findtext("userName") or "").strip() == want:
            return sensor
    return None


def _append_isis_sensor(
    sensors_parent: ET.Element, *, isis: int, username: str, comment: str = ""
) -> None:
    sen = ET.SubElement(sensors_parent, "sensor", {"inverted": "false"})
    ET.SubElement(sen, "systemName").text = f"ISIS{isis}"
    ET.SubElement(sen, "userName").text = username
    if comment:
        ET.SubElement(sen, "comment").text = comment


def ensure_yard_block_occupancy_sensors(root: ET.Element) -> dict[str, int]:
    """
    Create internal ISIS occupancy sensors for yard blocks (Block_48+).

    ISIS1–29 are track blocks; ISIS30–47 are BS <turnout> for main-line switches;
    ISIS48+ are turnout feedback — so new block sensors are allocated after the
    highest existing ISIS index. Turnout blocks use BS TO*; track segments use Block Sensor N.
    """
    layout = _find_layout_editor(root)
    if layout is None:
        return {"sensors": 0, "blocks": 0, "layoutblocks": 0}

    on_track = _track_blocknames(layout)
    yard_blocks = {
        bn
        for bn in on_track
        if (n := _block_num_from_username(bn)) is not None and n >= NEW_YARD_BLOCK_MIN
    }
    if not yard_blocks:
        return {"sensors": 0, "blocks": 0, "layoutblocks": 0}

    turnout_occ = _turnout_block_occupancy_names(layout)
    occ_by_block = {
        bn: _occupancy_sensor_for_block(bn, turnout_occ) for bn in yard_blocks
    }

    sensors_parent = root.find(
        ".//sensors[@class='jmri.jmrix.internal.configurexml.InternalSensorManagerXml']"
    )
    blocks_parent = root.find(".//blocks[@class='jmri.configurexml.BlockManagerXml']")
    lb_parent = root.find(".//layoutblocks")
    if sensors_parent is None:
        return {"sensors": 0, "blocks": 0, "layoutblocks": 0}

    stats = {"sensors": 0, "blocks": 0, "layoutblocks": 0}
    next_isis = _max_isis_index(sensors_parent) + 1
    for bn in sorted(yard_blocks, key=lambda x: int(x.split("_")[1])):
        occ = occ_by_block[bn]
        if not occ:
            continue
        if _sensor_by_username(sensors_parent, occ) is None:
            _append_isis_sensor(sensors_parent, isis=next_isis, username=occ, comment=bn)
            next_isis += 1
            stats["sensors"] += 1

    if blocks_parent is not None:
        for block in blocks_parent.findall("block"):
            un = _block_username(block)
            if un not in occ_by_block:
                continue
            occ = occ_by_block[un]
            existing = block.find("occupancysensor")
            if existing is not None and (existing.text or "").strip() == occ:
                continue
            _insert_occupancysensor(block, occ)
            stats["blocks"] += 1

    if lb_parent is not None:
        for lb in lb_parent.findall("layoutblock"):
            un = (lb.findtext("userName") or lb.get("userName") or "").strip()
            if un not in occ_by_block:
                continue
            want = occ_by_block[un]
            if (lb.get("occupancysensor") or "").strip() != want:
                lb.set("occupancysensor", want)
                stats["layoutblocks"] += 1

    return stats


def _block_username(block: ET.Element) -> str:
    return (block.findtext("userName") or "").strip()


def _block_system_name(block: ET.Element) -> str:
    return (block.get("systemName") or block.findtext("systemName") or "").strip()


def _block_num_from_username(name: str) -> int | None:
    if not name.startswith("Block_"):
        return None
    try:
        return int(name.split("_", 1)[1])
    except ValueError:
        return None


def _track_blocknames(layout: ET.Element) -> set[str]:
    """Block userNames required by track geometry (AUTOBLK resolved to Block_N)."""
    names: set[str] = set()
    for el in layout.iter():
        if _local_tag(el) not in ("tracksegment", "layoutturnout"):
            continue
        bn = (el.get("blockname") or "").strip()
        if not bn:
            continue
        m = AUTOBLK_RE.match(bn)
        names.add(f"Block_{m.group(1)}" if m else bn)
    return names


def _referenced_block_systems(block: ET.Element) -> set[str]:
    refs: set[str] = set()
    for path in block.findall("path"):
        ref = (path.get("block") or "").strip()
        if ref:
            refs.add(ref)
    return refs


def _index_blocks_by_system(parent: ET.Element | None) -> dict[str, ET.Element]:
    if parent is None:
        return {}
    out: dict[str, ET.Element] = {}
    for block in parent.findall("block"):
        sn = _block_system_name(block)
        if not sn:
            continue
        existing = out.get(sn)
        if existing is None or (
            block.findall("path") and not existing.findall("path")
        ):
            out[sn] = block
    return out


def sync_new_block_tables_to_blocked(
    source_root: ET.Element, blocked_root: ET.Element
) -> dict[str, int]:
    """
    Copy block, layoutblock, and internal sensor entries for yard trackwork
    (Block_48+) from the processed new panel into linear5_blocked.xml.
    """
    stats = {"blocks": 0, "layoutblocks": 0, "sensors": 0}
    blocked_layout = _find_layout_editor(blocked_root)
    if blocked_layout is None:
        return stats

    needed_names = _track_blocknames(blocked_layout)
    needed_nums = {
        n
        for name in needed_names
        for n in [_block_num_from_username(name)]
        if n is not None
    }
    if not needed_nums:
        return stats

    src_blocks_parent = source_root.find(
        ".//blocks[@class='jmri.configurexml.BlockManagerXml']"
    )
    dst_blocks_parent = blocked_root.find(
        ".//blocks[@class='jmri.configurexml.BlockManagerXml']"
    )
    if src_blocks_parent is None or dst_blocks_parent is None:
        return stats

    src_by_system = _index_blocks_by_system(src_blocks_parent)
    dst_by_system = _index_blocks_by_system(dst_blocks_parent)

    to_copy: dict[str, ET.Element] = {}
    queue: list[ET.Element] = []
    for block in src_blocks_parent.findall("block"):
        un = _block_username(block)
        num = _block_num_from_username(un)
        if un in needed_names or (num is not None and num in needed_nums):
            sn = _block_system_name(block)
            if sn and sn not in to_copy:
                to_copy[sn] = block
                queue.append(block)

    while queue:
        block = queue.pop()
        for ref in _referenced_block_systems(block):
            if ref in to_copy or ref not in src_by_system:
                continue
            ref_block = src_by_system[ref]
            to_copy[ref] = ref_block
            queue.append(ref_block)

    for sn, block in to_copy.items():
        existing = dst_by_system.get(sn)
        if existing is not None:
            if block.findall("path") and not existing.findall("path"):
                dst_blocks_parent.remove(existing)
                dst_blocks_parent.append(copy.deepcopy(block))
                stats["blocks"] += 1
            continue
        dst_blocks_parent.append(copy.deepcopy(block))
        stats["blocks"] += 1

    src_lb = source_root.find(".//layoutblocks")
    dst_lb = blocked_root.find(".//layoutblocks")
    if src_lb is not None and dst_lb is not None:
        dst_lb_names = {
            (lb.findtext("userName") or lb.get("userName") or "").strip()
            for lb in dst_lb.findall("layoutblock")
        }
        for lb in src_lb.findall("layoutblock"):
            un = (lb.findtext("userName") or lb.get("userName") or "").strip()
            num = _block_num_from_username(un)
            if un in needed_names or (num is not None and num in needed_nums):
                if un not in dst_lb_names:
                    dst_lb.append(copy.deepcopy(lb))
                    dst_lb_names.add(un)
                    stats["layoutblocks"] += 1

    return stats


def _ensure_ib_auto_blocks(root: ET.Element, block_nums: set[int]) -> int:
    """Add simple IB:AUTO entries for Block_48+ if missing."""
    blocks_parent = root.find(".//blocks[@class='jmri.configurexml.BlockManagerXml']")
    if blocks_parent is None:
        return 0
    by_user = {}
    for block in blocks_parent.findall("block"):
        un = (block.findtext("userName") or "").strip()
        if un:
            by_user[un] = block
    added = 0
    for num in sorted(n for n in block_nums if n >= 48):
        name = f"Block_{num}"
        if name in by_user:
            continue
        auto_id = f"IB:AUTO:{num:04d}"
        block = ET.SubElement(
            blocks_parent,
            "block",
            {"systemName": auto_id, "length": "0.0", "curve": "0"},
        )
        ET.SubElement(block, "systemName").text = auto_id
        ET.SubElement(block, "userName").text = name
        ET.SubElement(block, "permissive").text = "no"
        _insert_occupancysensor(block, f"Block Sensor {num}")
        added += 1
    return added


def _pending_turnout_dcc(_layout: ET.Element) -> dict[str, int]:
    """Curated DCC placeholders for new yard turnouts (116–119)."""
    return dict(PENDING_TURNOUT_DCC)


def _label_xy_for_text(layout: ET.Element, text: str) -> tuple[float, float] | None:
    for lb in layout.findall("positionablelabel"):
        if (lb.get("text") or "").strip() == text:
            try:
                return float(lb.get("x", 0)), float(lb.get("y", 0))
            except ValueError:
                return None
    return None


def tighten_yard_dcc_labels(layout: ET.Element) -> int:
    """Snap yard DCC labels 116–119 to turnout centers and shared rows."""
    turnouts = {
        lt.get("ident"): lt
        for lt in layout.findall("layoutturnout")
        if lt.get("ident") in NEW_TURNOUT_IDENTS
    }
    upper = _label_xy_for_text(layout, "100") or _label_xy_for_text(layout, "111")
    lower = _label_xy_for_text(layout, "103")
    upper_y = upper[1] if upper else 213.0
    lower_y = lower[1] if lower else 334.0

    targets: dict[int, tuple[float, float]] = {}
    to1 = turnouts.get("TO1")
    if to1 is not None:
        yc = float(to1.get("ycen", 315))
        targets[116] = (float(to1.get("xcen", 565)), yc - 37.0)
    to8 = turnouts.get("TO8")
    if to8 is not None:
        targets[117] = (float(to8.get("xcen", 502)), lower_y)
    to11 = turnouts.get("TO11")
    if to11 is not None:
        targets[118] = (float(to11.get("xcen", 526)), upper_y)
    to10 = turnouts.get("TO10")
    if to10 is not None:
        targets[119] = (float(to10.get("xcen", 484)) - 20.0, upper_y)

    n = 0
    for lb in layout.findall("positionablelabel"):
        text = (lb.get("text") or "").strip()
        if not text.isdigit():
            continue
        dcc = int(text)
        if dcc not in targets:
            continue
        x, y = targets[dcc]
        new_x, new_y = str(int(round(x))), str(int(round(y)))
        if lb.get("x") != new_x or lb.get("y") != new_y:
            lb.set("x", new_x)
            lb.set("y", new_y)
            n += 1
    return n


def apply_pending_dcc_assignments(layout: ET.Element) -> int:
    """
    Renumber/reposition yard DCC labels 116–119 per layout tuning.

    - 120→116 (TO1), old 116+118→117 at (x of 118, y of 103), 119↔118 swap on TO11/TO10.
    """
    label_size = _dcc_label_size_from_layout(layout)
    old_118 = _label_xy_for_text(layout, "118")
    old_103 = _label_xy_for_text(layout, "103")
    old_120 = _label_xy_for_text(layout, "120")
    old_119 = _label_xy_for_text(layout, "119")
    old_117 = _label_xy_for_text(layout, "117")

    label_xy: dict[int, tuple[float, float]] = {
        116: old_120 or (562.0, 288.0),
        117: (
            old_118[0] if old_118 else 504.0,
            old_103[1] if old_103 else 334.0,
        ),
        118: old_119 or (515.0, 256.0),
        119: old_117 or (484.0, 257.0),
    }

    removed = 0
    for lb in list(layout.findall("positionablelabel")):
        text = (lb.get("text") or "").strip()
        if text.isdigit() and 116 <= int(text) <= 120:
            layout.remove(lb)
            removed += 1

    for lt in layout.findall("layoutturnout"):
        ident = lt.get("ident") or ""
        dcc = PENDING_TURNOUT_DCC.get(ident)
        if dcc is not None:
            lt.set("turnoutname", f"Switch {dcc}")

    for dcc in sorted(label_xy):
        x, y = label_xy[dcc]
        layout.append(_make_dcc_label(x, y, dcc, size=label_size))

    tighten_yard_dcc_labels(layout)
    return removed


def _dcc_label_size_from_layout(layout: ET.Element) -> str:
    """Match size of existing switch DCC labels on this panel (prod coords)."""
    for lb in layout.findall("positionablelabel"):
        if lb.get("level") != "4":
            continue
        text = (lb.get("text") or "").strip()
        if text.isdigit() and int(text) < 116:
            size = (lb.get("size") or "").strip()
            if size:
                return size
    return "18"


def _fix_pending_dcc_label_sizes(layout: ET.Element) -> int:
    """Resize placeholder DCC labels 116+ to match existing switch labels."""
    target = _dcc_label_size_from_layout(layout)
    n = 0
    for lb in layout.findall("positionablelabel"):
        if lb.get("level") != "4":
            continue
        text = (lb.get("text") or "").strip()
        if not text.isdigit() or int(text) < 116:
            continue
        if lb.get("size") != target:
            lb.set("size", target)
            n += 1
    return n


def _add_pending_dcc_labels(
    layout: ET.Element, dcc_by_ident: dict[str, int], *, display_scale: float
) -> int:
    """Set turnoutname + append DCC labels for new turnouts."""
    label_size = _dcc_label_size_from_layout(layout)
    y_offset = -14.0
    added = 0
    existing_dcc = {
        (lb.get("text") or "").strip()
        for lb in layout.findall("positionablelabel")
        if (lb.get("text") or "").strip().isdigit()
    }
    for lt in layout.findall("layoutturnout"):
        ident = lt.get("ident") or ""
        if ident not in dcc_by_ident:
            continue
        dcc = dcc_by_ident[ident]
        lt.set("turnoutname", f"Switch {dcc}")
        if str(dcc) in existing_dcc:
            continue
        xc = float(lt.get("xcen", 0))
        yc = float(lt.get("ycen", 0))
        layout.append(
            _make_dcc_label(xc, yc + y_offset, dcc, size=label_size)
        )
        existing_dcc.add(str(dcc))
        added += 1
    return added


def _unscale_element(
    prod_el: ET.Element, factor: float, *, x_shift: float
) -> ET.Element:
    el = copy.deepcopy(prod_el)
    x_attrs = frozenset(a for a in _LAYOUT_COORD_ATTRS if a.startswith("x"))

    def _walk(node: ET.Element) -> None:
        tag = _local_tag(node)
        as_int = tag in _INTEGER_COORD_TAGS
        for attr in _LAYOUT_COORD_ATTRS:
            val = node.get(attr)
            if not val:
                continue
            try:
                node.set(
                    attr,
                    _blocked_coord_from_prod(
                        val, factor, x_shift=x_shift if attr in x_attrs else 0.0
                    ),
                )
            except ValueError:
                pass
        for cp in node.findall("controlpoints/controlpoint"):
            for attr in ("x", "y"):
                val = cp.get(attr)
                if not val:
                    continue
                cp.set(
                    attr,
                    _blocked_coord_from_prod(
                        val,
                        factor,
                        x_shift=x_shift if attr == "x" else 0.0,
                    ),
                )

    _walk(el)
    for child in el.iter():
        if child is not el:
            _walk(child)
    return el


def merge_prod_geometry_into_blocked(
    prod_path: Path,
    blocked_path: Path,
    *,
    display_scale: float,
    x_shift: float,
    backup: bool = True,
) -> dict[str, int]:
    prod_layout = _find_layout_editor(ET.parse(prod_path).getroot())
    blocked_root = ET.parse(blocked_path).getroot()
    blocked_layout = _find_layout_editor(blocked_root)
    if prod_layout is None or blocked_layout is None:
        raise SystemExit("LayoutEditor missing in prod or blocked panel")

    if backup:
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        ref = blocked_path.parent.parent / "reference"
        ref.mkdir(parents=True, exist_ok=True)
        dest = ref / f"linear5_blocked_pre_new_merge_{ts}.xml"
        dest.write_bytes(blocked_path.read_bytes())
        print(f"  Backup: {dest.name}")

    prod_by_key: dict[tuple[str, str], ET.Element] = {}
    for child in prod_layout:
        tag = _local_tag(child)
        if tag not in TRACK_TAGS:
            continue
        ident = child.get("ident")
        if ident:
            prod_by_key[(tag, ident)] = child

    counts = {"updated": 0, "added": 0, "removed": 0}
    seen: set[tuple[str, str]] = set()

    for child in list(blocked_layout):
        tag = _local_tag(child)
        if tag not in TRACK_TAGS:
            continue
        ident = child.get("ident")
        if not ident:
            continue
        key = (tag, ident)
        prod_el = prod_by_key.get(key)
        if prod_el is None:
            blocked_layout.remove(child)
            counts["removed"] += 1
            continue
        seen.add(key)
        idx = list(blocked_layout).index(child)
        blocked_layout.remove(child)
        blocked_layout.insert(idx, _unscale_element(prod_el, display_scale, x_shift=x_shift))
        counts["updated"] += 1

    for key, prod_el in prod_by_key.items():
        if key in seen:
            continue
        blocked_layout.append(
            _unscale_element(prod_el, display_scale, x_shift=x_shift)
        )
        counts["added"] += 1

    # blocked.xml is geometry-only
    for child in list(blocked_layout):
        if _local_tag(child) == "positionablelabel":
            blocked_layout.remove(child)

    _write_jmri_panel_xml(blocked_root, blocked_path)
    manual = blocked_path.parent.parent / "reference" / "linear5_manual_save.xml"
    manual.parent.mkdir(parents=True, exist_ok=True)
    manual.write_bytes(blocked_path.read_bytes())
    return counts


def _append_turnout_mapping_csv(
    blocked_path: Path, dcc_by_ident: dict[str, int]
) -> None:
    root = ET.parse(blocked_path).getroot()
    layout = _find_layout_editor(root)
    if layout is None:
        return
    coords = {}
    for lt in layout.findall("layoutturnout"):
        ident = lt.get("ident") or ""
        if ident in dcc_by_ident:
            coords[ident] = (
                float(lt.get("xcen", 0)),
                float(lt.get("ycen", 0)),
            )

    rows = []
    if TURNOUT_MAPPING_CSV.is_file():
        with TURNOUT_MAPPING_CSV.open(encoding="utf-8") as f:
            rows = list(csv.reader(f))
    if not rows:
        return

    header, *data = rows
    existing_idents = {r[0] for r in data if r}
    new_rows = []
    for ident, dcc in sorted(dcc_by_ident.items(), key=lambda x: x[1]):
        if ident in existing_idents:
            continue
        x, y = coords.get(ident, (0.0, 0.0))
        new_rows.append(
            [
                ident,
                f"{x:.2f}",
                f"{y:.2f}",
                ident,
                "pending_mqtt",
                "",
                f"Switch {dcc}",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                str(dcc),
                "0.0",
                f"New yard turnout — assign MQTT hardware later (placeholder DCC {dcc})",
            ]
        )

    if not new_rows:
        return

    with TURNOUT_MAPPING_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(data)
        w.writerows(new_rows)
    print(f"  Appended {len(new_rows)} row(s) to {TURNOUT_MAPPING_CSV.name}")


def _update_pending_metadata(panel_path: Path) -> None:
    """Refresh pending_turnout_assignments.json and turnout_mapping.csv rows."""
    root = ET.parse(panel_path).getroot()
    layout = _find_layout_editor(root)
    if layout is None:
        return
    dcc_by_ident = _pending_turnout_dcc(layout)
    coords = {
        lt.get("ident"): (float(lt.get("xcen", 0)), float(lt.get("ycen", 0)))
        for lt in layout.findall("layoutturnout")
        if lt.get("ident") in dcc_by_ident
    }
    PENDING_JSON.write_text(
        json.dumps(
            {
                "note": "Placeholder DCC 116–119 for west-yard turnouts. "
                "TO6 and TO8 share Switch 117.",
                "assignments": [
                    {
                        "layout_ident": ident,
                        "placeholder_dcc": dcc,
                        "panel_turnout_user": f"Switch {dcc}",
                        "block_on_turnout": next(
                            (
                                lt.get("blockname")
                                for lt in layout.findall("layoutturnout")
                                if lt.get("ident") == ident
                            ),
                            "",
                        ),
                    }
                    for ident, dcc in sorted(
                        dcc_by_ident.items(), key=lambda x: (x[1], x[0])
                    )
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if not TURNOUT_MAPPING_CSV.is_file():
        return
    with TURNOUT_MAPPING_CSV.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header, *data = rows
    kept = [r for r in data if r and r[0] not in NEW_TURNOUT_IDENTS]
    for ident, dcc in sorted(dcc_by_ident.items(), key=lambda x: (x[1], x[0])):
        x, y = coords.get(ident, (0.0, 0.0))
        kept.append(
            [
                ident,
                f"{x:.2f}",
                f"{y:.2f}",
                ident,
                "pending_mqtt",
                "",
                f"Switch {dcc}",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                str(dcc),
                "0.0",
                f"New yard turnout — assign MQTT hardware later (placeholder DCC {dcc})",
            ]
        )
    with TURNOUT_MAPPING_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(kept)


def repair_block_xml(path: Path, *, ref_path: Path | None = None) -> int:
    """Fix block element ordering / duplicates in an existing panel file."""
    root = ET.parse(path).getroot()
    fixed = _normalize_blocks_section(root)
    ref = ref_path or (LAYOUT5 / "output" / "linear5_prod.xml")
    fixed += _restore_occupancy_from_reference(root, ref)
    if fixed:
        _write_jmri_panel_xml(root, path)
    return fixed


def process_panel(
    input_path: Path,
    output_path: Path | None = None,
    *,
    merge_blocked: bool = True,
) -> dict:
    viewport = _load_viewport()
    factor = float(viewport.get("display_scale", 1.5))
    x_shift = float(viewport.get("panel_x_shift_display", 25))

    root = ET.parse(input_path).getroot()
    layout = _find_layout_editor(root)
    if layout is None:
        raise SystemExit(f"No LayoutEditor in {input_path}")

    used_blocks = _collect_layout_block_nums(layout)
    stats = {
        "block_renames": _fix_autoblk_names(root, used_blocks),
        "ib_auto_added": _ensure_ib_auto_blocks(root, used_blocks),
        "block_xml_fixed": 0,
    }

    dcc_by_ident = _pending_turnout_dcc(layout)
    stats["dcc_labels"] = apply_pending_dcc_assignments(layout)

    stats["block_xml_fixed"] = _normalize_blocks_section(root)
    stats["yard_sensors"] = ensure_yard_block_occupancy_sensors(root)
    stats["yard_mainline"] = apply_yard_mainline_flags(layout)

    out = output_path or input_path
    _write_jmri_panel_xml(root, out)
    stats["output"] = str(out)

    _update_pending_metadata(out)

    if merge_blocked and BLOCKED_PATH.is_file():
        merge_stats = merge_prod_geometry_into_blocked(
            out, BLOCKED_PATH, display_scale=factor, x_shift=x_shift
        )
        stats["blocked_merge"] = merge_stats
        # Refresh turnout names + copy Block_48+ tables into blocked (1:1 geometry).
        blocked_root = ET.parse(BLOCKED_PATH).getroot()
        blocked_layout = _find_layout_editor(blocked_root)
        if blocked_layout is not None:
            for lt in blocked_layout.findall("layoutturnout"):
                ident = lt.get("ident") or ""
                dcc = PENDING_TURNOUT_DCC.get(ident)
                if dcc is not None:
                    lt.set("turnoutname", f"Switch {dcc}")
            stats["blocked_mainline"] = apply_yard_mainline_flags(blocked_layout)
        source_root = ET.parse(out).getroot()
        stats["blocked_block_tables"] = sync_new_block_tables_to_blocked(
            source_root, blocked_root
        )
        stats["blocked_block_tables"]["xml_fixed"] = _normalize_blocks_section(
            blocked_root
        )
        stats["blocked_yard_sensors"] = ensure_yard_block_occupancy_sensors(
            blocked_root
        )
        _write_jmri_panel_xml(blocked_root, BLOCKED_PATH)

    # Keep linear5/output copy in sync
    sync_out = LAYOUT5 / "output" / "linear5_new.xml"
    if out.resolve() != sync_out.resolve():
        sync_out.write_bytes(out.read_bytes())

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=JMRI_ROOT / "layouts" / "linear6" / "linear5_new.xml",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write processed panel here (default: update input file)",
    )
    parser.add_argument(
        "--no-merge-blocked",
        action="store_true",
        help="Do not update linear5_blocked.xml",
    )
    parser.add_argument(
        "--repair-only",
        action="store_true",
        help="Only fix block XML ordering/duplicates (no full reprocess)",
    )
    parser.add_argument(
        "--apply-mqtt",
        action="store_true",
        help="Assign yard TO* turnouts to MQTT/IT hardware (yard_turnout_hardware.json)",
    )
    parser.add_argument(
        "--align-dcc-labels",
        action="store_true",
        help="Snap yard DCC labels 116–119 to turnout centers and label rows",
    )
    parser.add_argument(
        "--remap-dcc",
        action="store_true",
        help="Only renumber/reposition yard DCC labels 116–119",
    )
    args = parser.parse_args()
    if not args.input.is_file():
        raise SystemExit(f"Missing input: {args.input}")

    if args.apply_mqtt:
        root = ET.parse(args.input).getroot()
        stats = apply_yard_mqtt_hardware(root)
        _write_jmri_panel_xml(root, args.input)
        sync_out = LAYOUT5 / "output" / "linear5_new.xml"
        if sync_out.resolve() != args.input.resolve():
            sync_out.write_bytes(args.input.read_bytes())
        blocked = BLOCKED_PATH
        if blocked.is_file():
            broot = ET.parse(blocked).getroot()
            blayout = _find_layout_editor(broot)
            if blayout is not None:
                by_ident = {r["layout_ident"]: r for r in _load_yard_hardware()}
                for lt in blayout.findall("layoutturnout"):
                    row = by_ident.get(lt.get("ident") or "")
                    if row:
                        lt.set("turnoutname", row["panel_system"])
                _write_jmri_panel_xml(broot, blocked)
        print(
            f"Applied yard MQTT in {args.input}: "
            f"{stats['sensors']} sensor(s), "
            f"{stats['mqtt_turnouts']} MQTT turnout(s), "
            f"{stats['internal_turnouts']} internal turnout(s)"
        )
        return

    if args.align_dcc_labels:
        root = ET.parse(args.input).getroot()
        layout = _find_layout_editor(root)
        if layout is None:
            raise SystemExit(f"No LayoutEditor in {args.input}")
        n = tighten_yard_dcc_labels(layout)
        _write_jmri_panel_xml(root, args.input)
        sync_out = LAYOUT5 / "output" / "linear5_new.xml"
        if sync_out.resolve() != args.input.resolve():
            sync_out.write_bytes(args.input.read_bytes())
        print(f"Aligned yard DCC labels in {args.input} ({n} label(s) adjusted)")
        return

    if args.remap_dcc:
        root = ET.parse(args.input).getroot()
        layout = _find_layout_editor(root)
        if layout is None:
            raise SystemExit(f"No LayoutEditor in {args.input}")
        n = apply_pending_dcc_assignments(layout)
        _write_jmri_panel_xml(root, args.input)
        sync_out = LAYOUT5 / "output" / "linear5_new.xml"
        if sync_out.resolve() != args.input.resolve():
            sync_out.write_bytes(args.input.read_bytes())
        _update_pending_metadata(args.input)
        print(f"Remapped yard DCC labels in {args.input} ({n} old label(s) replaced)")
        return

    if args.repair_only:
        root = ET.parse(args.input).getroot()
        layout = _find_layout_editor(root)
        fixed = repair_block_xml(args.input)
        yard = ensure_yard_block_occupancy_sensors(root)
        mainline = apply_yard_mainline_flags(layout) if layout is not None else 0
        if yard["sensors"] or yard["blocks"] or yard["layoutblocks"] or mainline:
            _write_jmri_panel_xml(root, args.input)
        sync_out = LAYOUT5 / "output" / "linear5_new.xml"
        if sync_out.resolve() != args.input.resolve() and sync_out.is_file():
            broot = ET.parse(sync_out).getroot()
            repair_block_xml(sync_out)
            ensure_yard_block_occupancy_sensors(broot)
            _write_jmri_panel_xml(broot, sync_out)
        if BLOCKED_PATH.is_file():
            broot = ET.parse(BLOCKED_PATH).getroot()
            blayout = _find_layout_editor(broot)
            repair_block_xml(BLOCKED_PATH)
            byard = ensure_yard_block_occupancy_sensors(broot)
            bmain = apply_yard_mainline_flags(blayout) if blayout is not None else 0
            _write_jmri_panel_xml(broot, BLOCKED_PATH)
            yard = {
                k: yard.get(k, 0) + byard.get(k, 0) for k in ("sensors", "blocks", "layoutblocks")
            }
            mainline += bmain
        print(
            f"Repaired block XML in {args.input} ({fixed} fix(es)); "
            f"yard sensors: {yard['sensors']} ISIS, "
            f"{yard['blocks']} block occ, {yard['layoutblocks']} layoutblock(s); "
            f"mainline flags: {mainline}"
        )
        return

    stats = process_panel(
        args.input,
        args.output,
        merge_blocked=not args.no_merge_blocked,
    )
    print(f"Processed: {stats['output']}")
    print(
        f"  Blocks renamed: {stats['block_renames']}, "
        f"block XML fixed: {stats['block_xml_fixed']}, "
        f"yard sensors: {stats['yard_sensors']['sensors']} ISIS / "
        f"{stats['yard_sensors']['blocks']} block occ, "
        f"yard mainline: {stats.get('yard_mainline', 0)}, "
        f"DCC labels: {stats['dcc_labels']}"
    )
    if "blocked_merge" in stats:
        m = stats["blocked_merge"]
        print(
            f"  blocked merge: {m['updated']} updated, "
            f"{m['added']} added, {m['removed']} removed"
        )
    if "blocked_block_tables" in stats:
        b = stats["blocked_block_tables"]
        print(
            f"  blocked block tables: {b['blocks']} block(s), "
            f"{b['layoutblocks']} layoutblock(s), "
            f"{b.get('xml_fixed', 0)} XML fix(es)"
        )
    if "blocked_mainline" in stats:
        print(f"  blocked yard mainline flags: {stats['blocked_mainline']}")
    if "blocked_yard_sensors" in stats:
        y = stats["blocked_yard_sensors"]
        print(
            f"  blocked yard sensors: {y['sensors']} ISIS, "
            f"{y['blocks']} block occ, {y['layoutblocks']} layoutblock(s)"
        )
    print(f"  Pending map: {PENDING_JSON}")


if __name__ == "__main__":
    main()
