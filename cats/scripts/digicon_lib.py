#!/usr/bin/env python3
"""Helpers shared by wire_digicon.py and cats_turnout_io.py."""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HART = ROOT / "jmri/layouts/hart/output/tables.xml"
OCC_CSV = ROOT / "cats/data/occupancy_bindings.csv"

TRACK_ENDS = {
    "HORIZONTAL": frozenset({"LEFT", "RIGHT"}),
    "VERTICAL": frozenset({"TOP", "BOTTOM"}),
    "UPPERSLASH": frozenset({"LEFT", "TOP"}),
    "LOWERSLASH": frozenset({"RIGHT", "BOTTOM"}),
    "UPPERBACKSLASH": frozenset({"RIGHT", "TOP"}),
    "LOWERBACKSLASH": frozenset({"LEFT", "BOTTOM"}),
}


def points_edge(tracks: list[str]) -> str | None:
    if len(tracks) != 2:
        return None
    shared = TRACK_ENDS[tracks[0]] & TRACK_ENDS[tracks[1]]
    return next(iter(shared)) if len(shared) == 1 else None


def cell_edges(tracks: list[str]) -> list[str]:
    used: set[str] = set()
    for t in tracks:
        used |= TRACK_ENDS[t]
    return [e for e in ("LEFT", "RIGHT", "TOP", "BOTTOM") if e in used]


def load_disciplines() -> dict[str, str]:
    out: dict[str, str] = {}
    with OCC_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            disc = (row.get("cats_discipline") or "CTC").strip().upper()
            if disc not in {"UNDEFINED", "ABS", "APB", "CTC", "DTC"}:
                disc = "CTC"
            out[row["block_user_name"].strip()] = disc
    return out


def load_occupancy() -> dict[str, tuple[str, str]]:
    root = ET.parse(HART).getroot()
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
    with OCC_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = row["block_user_name"].strip()
            sens = row["occupancy_sensor_user_name"].strip()
            if name not in out and sens in sensor_addr:
                out[name] = (sensor_addr[sens], sens)
    return out


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

