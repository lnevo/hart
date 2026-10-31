#!/usr/bin/env python3
"""Rebuild hart_mqtt_tables_from_linear6.xml from linear6.xml (MQTT tables only)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "linear6.xml"
if not SRC.exists():
    SRC = ROOT / "jmri" / "layouts" / "linear6" / "linear6.xml"
OUT = ROOT / "jmri" / "layouts" / "hart" / "output" / "hart_mqtt_tables_from_linear6.xml"


def main() -> int:
    root = ET.parse(SRC).getroot()
    jmriv = root.find("jmriversion")
    sensors = turnouts = None
    for child in root:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        cls = child.get("class") or ""
        if tag == "sensors" and "MqttSensorManagerXml" in cls:
            sensors = child
        if tag == "turnouts" and "MqttTurnoutManagerXml" in cls:
            turnouts = child
    if sensors is None or turnouts is None:
        raise SystemExit("linear6 missing MqttSensor/MqttTurnout tables")

    cfg = ET.Element(
        "layout-config",
        {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation": "http://jmri.org/xml/schema/layout-5-5-5.xsd",
        },
    )
    if jmriv is not None:
        cfg.append(jmriv)
    cfg.append(sensors)
    cfg.append(turnouts)
    tree = ET.ElementTree(cfg)
    ET.indent(tree, space="  ")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tree.write(OUT, encoding="UTF-8", xml_declaration=True)
    n_fb = sum(1 for t in turnouts.findall("turnout") if t.get("feedback") == "TWOSENSOR")
    print(
        f"wrote {OUT} sensors={len(list(sensors.findall('sensor')))} "
        f"turnouts={len(list(turnouts.findall('turnout')))} TWOSENSOR={n_fb}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
