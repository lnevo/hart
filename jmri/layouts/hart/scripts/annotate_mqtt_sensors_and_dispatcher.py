#!/usr/bin/env python3
"""Annotate MQTT sensors and add Dispatcher sections/transit for 2091.

Edits tables/new_tables.xml in place (SoR). Does not invent SML.
"""
from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
TABLES = ROOT / "tables" / "new_tables.xml"
OUTPUT_TABLES = ROOT / "jmri" / "layouts" / "hart" / "output" / "tables.xml"
OCC_CSV = ROOT / "cats" / "data" / "occupancy_bindings.csv"
TRAININFO_DIR = ROOT / "jmri" / "layouts" / "hart" / "dispatcher" / "traininfo"
MAC_PROFILE = Path.home() / "Library" / "Preferences" / "JMRI" / "My_JMRI_Railroad.jmri"

FORWARD = 4  # jmri.Section.FORWARD / EntryPoint.FORWARD (JMRI 5.x)
REVERSE = 8  # jmri.Section.REVERSE / EntryPoint.REVERSE

PATH_NORTH, PATH_SOUTH, PATH_EAST, PATH_WEST = 16, 32, 64, 128

# LCOS Switch {node}-{slot} → railroad plant turnout userName.
# From MQTT turnout sensor1/sensor2 bindings. 13-x reserved for 117–119
# even though those turnouts are currently DIRECT (FB not attached).
HW_TO_PLANT = {
    "1-1": "Switch 35",
    "1-2": "Switch 37",
    "1-3": "Switch 39",
    "3-1": "Switch 15",
    "3-2": "Switch 17",
    "3-3": "Switch 19",
    "3-4": "Switch 21",
    "4-1": "Switch 1",
    "4-2": "Switch 3",
    "4-3": "Switch 5",
    "12-1": "Switch 25",
    "12-2": "Switch 27",
    "12-3": "Switch 29",
    "12-4": "Switch 31",
    "12-5": "Switch 23",
    "12-6": "Switch 33",
    "13-1": "Switch 7",
    "13-2": "Switch 11",
    "13-3": "Switch 9",
}

UNUSED_FB = {
    "4-4": "unused LCOS node 4 switch-4 FB (no plant turnout)",
}

UNUSED_OCC = {
    "M2S201": "unused LCOS node 2 occupancy ch 1 (would be Block 2-2; no track circuit)",
    "M2S307": "unused LCOS node 3 occupancy ch 7 (would be Block 3-8; no track circuit)",
}

# 2091 circuit. Tuple: (block, enter-from along lap, enter-from opposite).
# FORWARD = lap direction (WME west → Brick → Plane → OS Barn → OS Main East →
# 112 → OS East Lead → 113a → 114 → OS McKeesport → Rocks → 115 → 113b → WME).
LAP_SECTIONS = [
    ("OS West Main Ext", "OS 35b", "OS 23a"),
    ("OS 23a", "OS West Main Ext", "OS Main West"),
    ("OS Main West", "OS 23a", "OS 1"),
    ("OS 1", "OS Main West", "OS Brick-Plane"),
    ("OS Brick-Plane", "OS 1", "OS 5"),
    ("OS 5", "OS Brick-Plane", "OS East Main Ext"),
    ("OS East Main Ext", "OS 5", "OS 7b"),
    ("OS 7b", "OS East Main Ext", "OS Main East"),
    ("OS Main East", "OS 7b", "OS 33"),
    ("OS 33", "OS Main East", "OS East Lead"),
    ("OS East Lead", "OS 33", "OS 35a"),
    ("OS 35a", "OS East Lead", "OS 37"),
    ("OS 37", "OS 35a", "OS McKeesport"),
    ("OS McKeesport", "OS 37", "OS McKees Rocks"),
    ("OS McKees Rocks", "OS McKeesport", "OS 39"),
    ("OS 39", "OS McKees Rocks", "OS 35b"),
    ("OS 35b", "OS 39", "OS West Main Ext"),
]

# First and last section are the same (continuous lap).
TRANSIT_SEQ = [
    ("OS West Main Ext", FORWARD),
    ("OS 23a", FORWARD),
    ("OS Main West", FORWARD),
    ("OS 1", FORWARD),
    ("OS Brick-Plane", FORWARD),
    ("OS 5", FORWARD),
    ("OS East Main Ext", FORWARD),
    ("OS 7b", FORWARD),
    ("OS Main East", FORWARD),
    ("OS 33", FORWARD),
    ("OS East Lead", FORWARD),
    ("OS 35a", FORWARD),
    ("OS 37", FORWARD),
    ("OS McKeesport", FORWARD),
    ("OS McKees Rocks", FORWARD),
    ("OS 39", FORWARD),
    ("OS 35b", FORWARD),
    ("OS West Main Ext", FORWARD),
]


def decode_path_dir(mask: int) -> str:
    parts = []
    if mask & PATH_NORTH:
        parts.append("North")
    if mask & PATH_SOUTH:
        parts.append("South")
    if mask & PATH_EAST:
        parts.append("East")
    if mask & PATH_WEST:
        parts.append("West")
    return "-".join(parts) if parts else ""


def load_occ_names() -> dict[str, list[str]]:
    by_sensor: dict[str, list[str]] = {}
    with OCC_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sensor = (row.get("occupancy_sensor_user_name") or "").strip()
            block = (row.get("block_user_name") or "").strip()
            if sensor and block and block not in by_sensor.setdefault(sensor, []):
                by_sensor[sensor].append(block)
    return by_sensor


def last_blocks_by_user(root: ET.Element) -> dict[str, ET.Element]:
    """Last <block> wins (stubs are listed first, path copies second)."""
    out: dict[str, ET.Element] = {}
    for blocks in root.findall("blocks"):
        for blk in blocks.findall("block"):
            un = blk.findtext("userName")
            if un:
                out[un] = blk
    return out


def block_sys(blk: ET.Element) -> str:
    return (blk.findtext("systemName") or blk.get("systemName") or "").strip()


def neighbor_fromdir(blk: ET.Element, neighbor_sys: str) -> str:
    for path in blk.findall("path"):
        if path.get("block") == neighbor_sys:
            try:
                return decode_path_dir(int(path.get("fromdir") or "0"))
            except ValueError:
                return ""
    return ""


def set_comment(sensor: ET.Element, text: str) -> None:
    comment = sensor.find("comment")
    if comment is None:
        comment = ET.Element("comment")
        un = sensor.find("userName")
        sysn = sensor.find("systemName")
        if un is not None:
            idx = list(sensor).index(un) + 1
        elif sysn is not None:
            idx = list(sensor).index(sysn) + 1
        else:
            idx = len(list(sensor))
        sensor.insert(idx, comment)
    comment.text = text


def annotate_mqtt_sensors(root: ET.Element) -> tuple[int, int, list[str]]:
    occ_names = load_occ_names()
    fb_n = 0
    occ_n = 0
    unnamed: list[str] = []
    mqtt = None
    for sensors in root.findall("sensors"):
        cls = sensors.get("class") or ""
        if "MqttSensor" in cls:
            mqtt = sensors
            break
    if mqtt is None:
        raise SystemExit("no MQTT sensor table")

    for sensor in mqtt.findall("sensor"):
        sysn = (sensor.findtext("systemName") or "").strip()
        un = sensor.findtext("userName")
        if not un:
            if sysn in UNUSED_OCC:
                set_comment(sensor, UNUSED_OCC[sysn])
            elif re.fullmatch(r"M2S41[0-9]", sysn) or sysn in {f"M2S{n}" for n in range(408, 420)}:
                ch = int(sysn[3:]) - 400
                set_comment(
                    sensor,
                    f"unused LCOS node 4 occupancy extra ch {ch} (no track circuit)",
                )
            else:
                set_comment(sensor, f"unused MQTT sensor {sysn} (no userName; not a named occupancy or FB)")
            unnamed.append(sysn)
            continue

        m = re.fullmatch(r"Switch (\d+-\d+) FB ([NR])", un)
        if m:
            hw, nr = m.group(1), m.group(2)
            plant = HW_TO_PLANT.get(hw)
            extra = UNUSED_FB.get(hw)
            if plant:
                note = f"{plant} FB{nr}"
                if hw.startswith("13-"):
                    note += " (LCOS present; turnout currently DIRECT)"
                set_comment(sensor, note)
            elif extra:
                set_comment(sensor, f"{extra} {nr}")
            else:
                set_comment(sensor, f"LCOS {un} (no plant turnout mapped)")
            fb_n += 1
            continue

        if un.startswith("Block "):
            names = occ_names.get(un, [])
            if names:
                set_comment(sensor, "; ".join(names))
            occ_n += 1

    return fb_n, occ_n, unnamed


def build_sections_xml(root: ET.Element) -> str:
    blocks = last_blocks_by_user(root)
    missing = [name for name, *_ in LAP_SECTIONS if name not in blocks]
    if missing:
        raise SystemExit(f"missing blocks: {missing}")

    lines = [
        '  <sections class="jmri.configurexml.SectionManagerXml">',
    ]
    for i, (name, from_westbound, from_eastbound) in enumerate(LAP_SECTIONS, start=1):
        blk = blocks[name]
        sysn = block_sys(blk)
        iy = f"IY:HART:{i:04d}"
        lines.append(
            f'    <section systemName="{iy}" userName="{name}" creationtype="userdefined">'
        )
        lines.append(f"      <systemName>{iy}</systemName>")
        lines.append(f"      <userName>{name}</userName>")
        lines.append(f'      <blockentry sName="{sysn}" order="0" />')
        if from_westbound:
            wsys = block_sys(blocks[from_westbound])
            lines.append(
                f'      <entrypoint fromblock="{wsys}" toblock="{sysn}" '
                f'direction="{FORWARD}" fixed="yes" '
                f'fromblockdirection="{neighbor_fromdir(blk, wsys)}" />'
            )
        if from_eastbound:
            esys = block_sys(blocks[from_eastbound])
            lines.append(
                f'      <entrypoint fromblock="{esys}" toblock="{sysn}" '
                f'direction="{REVERSE}" fixed="yes" '
                f'fromblockdirection="{neighbor_fromdir(blk, esys)}" />'
            )
        lines.append("    </section>")
    lines.append("  </sections>")
    return "\n".join(lines) + "\n"


def section_sys_by_user() -> dict[str, str]:
    return {name: f"IY:HART:{i:04d}" for i, (name, *_rest) in enumerate(LAP_SECTIONS, start=1)}


def build_transits_xml() -> str:
    sys_by_user = section_sys_by_user()
    lines = [
        '  <transits class="jmri.configurexml.TransitManagerXml">',
        '    <transit systemName="IZ:HART:2091" userName="2091 OS West Main Ext lap">',
        "      <systemName>IZ:HART:2091</systemName>",
        "      <userName>2091 OS West Main Ext lap</userName>",
        "      <comment>WME → 111 → Brick → Plane → OS Barn 117 → OS Main East → 112 → OS East Lead → 113a → 114 → OS McKeesport → Rocks → 115 → 113b → WME. Line CATS: 111 N, 100 R, 102 N, 117 N, 112 R, 113 N, 114 R, 115 R. Auto Turnouts off.</comment>",
    ]
    for seq, (name, direction) in enumerate(TRANSIT_SEQ, start=1):
        iy = sys_by_user[name]
        lines.append(
            f'      <transitsection sectionname="{iy}" sequence="{seq}" '
            f'direction="{direction}" alternate="no" safe="no" '
            f'stopallocatingsensor="" fwdstoppercent="1.0" revstoppercent="1.0" />'
        )
    lines.append("    </transit>")
    lines.append("  </transits>")
    return "\n".join(lines) + "\n"


def write_traininfo() -> Path:
    TRAININFO_DIR.mkdir(parents=True, exist_ok=True)
    path = TRAININFO_DIR / "2091_WME_to_OS McKeesport.xml"
    blocks = {
        "OS West Main Ext": "IB:AUTO:0050",
        "OS McKeesport": "IB:AUTO:0048",
    }
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet href="/xml/XSLT/dispatcher-traininfo.xsl" type="text/xsl"?>
<traininfofile>
  <traininfo version="8"
    transitname="2091 OS West Main Ext lap"
    transitid="IZ:HART:2091"
    dynamictransit="no"
    trainname="2091"
    trainusername="POHC 2091"
    rosterid="2091"
    dccaddress="2091"
    trainintransit="yes"
    startblockname="OS West Main Ext-1"
    startblockid="{blocks['OS West Main Ext']}"
    startblockseq="1"
    endblockname="OS West Main Ext-18"
    endblockid="{blocks['OS West Main Ext']}"
    endblockseq="18"
    viablockname=""
    trainfromroster="yes"
    trainfromtrains="no"
    trainfromuser="no"
    trainfromsetlater="no"
    priority="5"
    traindetection="WHOLETRAIN"
    resetwhendone="yes"
    delayedrestart="no"
    reverseatend="no"
    reversedelayedrestart="no"
    delayedstart="no"
    terminatewhendone="yes"
    departuretimehr="0"
    departuretimemin="0"
    traintype="LOCAL_PASSENGER"
    autorun="yes"
    loadatstartup="no"
    allocatealltheway="no"
    allocationmethod="3"
    nexttrain="None"
    speedfactor="0.6"
    maxspeed="0.4"
    minreliableoperatingspeed="0.1"
    ramprate="MEDIUM"
    runinreverse="no"
    sounddecoder="no"
    maxtrainlengthscalemeters="18.0"
    trainlengthunits="SCALEFEET"
    usespeedprofile="no"
    stopbyspeedprofile="no"
    stopbyspeedprofileadjust="1.0"
    usestopsensor="no"
    overridestopsensor="yes"
    waittime="0.0"
    blockname=""
    fnumberlight="0"
    fnumberbell="1"
    fnumberhorn="2" />
</traininfofile>
"""
    path.write_text(xml, encoding="utf-8")
    return path


def main() -> None:
    text = TABLES.read_text(encoding="utf-8")
    root = ET.fromstring(text)
    fb_n, occ_n, unnamed = annotate_mqtt_sensors(root)

    # Re-serialize MQTT sensors only: splice modified MQTT <sensors> block back.
    mqtt = None
    for sensors in root.findall("sensors"):
        if "MqttSensor" in (sensors.get("class") or ""):
            mqtt = sensors
            break
    assert mqtt is not None
    ET.indent(mqtt, space="    ")
    mqtt_xml = ET.tostring(mqtt, encoding="unicode")
    # indent() added 4 spaces at the sensors root; file uses 2.
    mqtt_xml = mqtt_xml.replace("\n    ", "\n  ")
    if mqtt_xml.startswith("<sensors"):
        mqtt_xml = "  " + mqtt_xml
    if not mqtt_xml.endswith("\n"):
        mqtt_xml += "\n"

    text2, n = re.subn(
        r"  <sensors class=\"jmri\.jmrix\.mqtt\.configurexml\.MqttSensorManagerXml\">.*?</sensors>\n",
        mqtt_xml,
        text,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise SystemExit(f"MQTT sensors splice failed ({n})")

    if "<sections " in text2:
        text2 = re.sub(
            r"  <sections class=\"jmri\.configurexml\.SectionManagerXml\">.*?</sections>\n",
            "",
            text2,
            count=1,
            flags=re.S,
        )
    if "<transits " in text2:
        text2 = re.sub(
            r"  <transits class=\"jmri\.configurexml\.TransitManagerXml\">.*?</transits>\n",
            "",
            text2,
            count=1,
            flags=re.S,
        )

    insert = build_sections_xml(root) + build_transits_xml()
    marker = "  <layoutblocks "
    if marker not in text2:
        raise SystemExit("layoutblocks marker missing")
    text2 = text2.replace(marker, insert + marker, 1)

    TABLES.write_text(text2, encoding="utf-8")
    shutil.copy2(TABLES, OUTPUT_TABLES)
    traininfo = write_traininfo()

    mac_tables = MAC_PROFILE / "tables.xml"
    if mac_tables.exists():
        shutil.copy2(TABLES, mac_tables)
        dest = MAC_PROFILE / "dispatcher" / "traininfo"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(traininfo, dest / traininfo.name)

    print(f"FB comments: {fb_n}")
    print(f"occupancy comments: {occ_n}")
    print(f"unnamed MQTT sensors: {len(unnamed)} -> {', '.join(unnamed)}")
    print(f"wrote {TABLES}")
    print(f"copied {OUTPUT_TABLES}")
    print(f"traininfo {traininfo}")
    if mac_tables.exists():
        print(f"copied Mac profile tables + traininfo")


if __name__ == "__main__":
    main()
