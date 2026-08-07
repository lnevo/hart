#!/usr/bin/env python3
"""
Merge LogixNG, OpenLCB (LCC) devices, routes, and related live-panel extras from
tables.xml into linear4_devices.xml for production load.

Output: jmri/layouts/linear4/output/linear4_prod.xml

Usage:
  python3 jmri/scripts/merge_linear4_prod_panel.py
  python3 jmri/scripts/merge_linear4_prod_panel.py --base path/to/linear4_devices.xml
"""
from __future__ import annotations

import argparse
import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

JMRI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = JMRI_ROOT.parent
sys.path.insert(0, str(JMRI_ROOT / "scripts"))
from build_linear4_device_mapping import _write_jmri_panel_xml  # noqa: E402

BASE_PANEL = JMRI_ROOT / "layouts/linear4/output/linear4_devices.xml"
LIVE_PANEL = REPO_ROOT / "tables.xml"
LOGIXNG_PANEL = JMRI_ROOT / "layouts/linear4/output/linear4_prod.xml"
OUT_PROD = JMRI_ROOT / "layouts/linear4/output/linear4_prod.xml"
LINEAR5_REFERENCE = JMRI_ROOT / "layouts/linear5/reference/tables.xml"
LINEAR5_BG_PREF_URL = "preference:resources/misc/linear5_panel_bg.jpg"

# memories before signalheads; routes/timebase from tables.xml; LogixNG from linear4_prod
# (tables.xml may carry extra startup actions that fail with "Item has no parent" on load).
PROD_BEFORE_SIGNALHEADS = ("memories",)
PROD_FROM_LIVE = ("routes", "signalmastlogics", "timebase")
LOGIXNG_TAGS = ("LogixNGs", "LogixNGConditionalNGs", "LogixNGDigitalActions")
PROD_BEFORE_LAYOUT = PROD_FROM_LIVE + LOGIXNG_TAGS

MQTT_SENSOR_CLASS = "jmri.jmrix.mqtt.configurexml.MqttSensorManagerXml"
OLCB_SENSOR_CLASS = "jmri.jmrix.openlcb.configurexml.OlcbSensorManagerXml"
MQTT_TURNOUT_CLASS = "jmri.jmrix.mqtt.configurexml.MqttTurnoutManagerXml"
OLCB_TURNOUT_CLASS = "jmri.jmrix.openlcb.configurexml.OlcbTurnoutManagerXml"


def _local_tag(elem: ET.Element) -> str:
    return (elem.tag or "").split("}")[-1]


def _find_child(root: ET.Element, tag: str, manager_class: str | None = None) -> ET.Element | None:
    for child in root:
        if _local_tag(child) != tag:
            continue
        if manager_class is None or child.get("class") == manager_class:
            return child
    return None


def _remove_children(root: ET.Element, tag: str, manager_class: str | None = None) -> None:
    for child in list(root):
        if _local_tag(child) != tag:
            continue
        if manager_class is None or child.get("class") == manager_class:
            root.remove(child)


def _insert_after_child(root: ET.Element, anchor: ET.Element, new_child: ET.Element) -> None:
    for i, child in enumerate(root):
        if child is anchor:
            root.insert(i + 1, copy.deepcopy(new_child))
            return
    raise SystemExit(f"Anchor element { _local_tag(anchor) } not found in base panel")


def _insert_after_last_tag(root: ET.Element, tag: str, new_child: ET.Element) -> None:
    idx = -1
    for i, child in enumerate(root):
        if _local_tag(child) == tag:
            idx = i
    if idx < 0:
        raise SystemExit(f"{tag} not found in base panel")
    root.insert(idx + 1, copy.deepcopy(new_child))


def _merge_openlcb_from_live(base_root: ET.Element, live_root: ET.Element) -> list[str]:
    """Copy OpenLCB sensor/turnout managers from production tables.xml."""
    merged: list[str] = []

    _remove_children(base_root, "sensors", OLCB_SENSOR_CLASS)
    live_sensors = _find_child(live_root, "sensors", OLCB_SENSOR_CLASS)
    if live_sensors is not None:
        mqtt_sensors = _find_child(base_root, "sensors", MQTT_SENSOR_CLASS)
        if mqtt_sensors is None:
            raise SystemExit("MQTT sensors block not found in base panel")
        _insert_after_child(base_root, mqtt_sensors, live_sensors)
        merged.append("OpenLCB sensors")

    _remove_children(base_root, "turnouts", OLCB_TURNOUT_CLASS)
    live_turnouts = _find_child(live_root, "turnouts", OLCB_TURNOUT_CLASS)
    if live_turnouts is not None:
        _insert_after_last_tag(base_root, "turnouts", live_turnouts)
        merged.append("OpenLCB turnouts")

    return merged


def _sync_route_turnout_usernames(base_root: ET.Element, live_root: ET.Element) -> list[str]:
    """Routes reference turnout userNames (e.g. Switch 114); align MQTT names with live panel."""
    live_routes = _find_child(live_root, "routes")
    live_mqtt = _find_child(live_root, "turnouts", MQTT_TURNOUT_CLASS)
    base_mqtt = _find_child(base_root, "turnouts", MQTT_TURNOUT_CLASS)
    if live_routes is None or live_mqtt is None or base_mqtt is None:
        return []

    route_names: set[str] = set()
    for route in live_routes.findall("route"):
        for out in route.findall("routeOutputTurnout"):
            name = out.get("systemName", "") or ""
            if name:
                route_names.add(name)

    base_by_sys = {
        (t.findtext("systemName") or ""): t for t in base_mqtt.findall("turnout")
    }
    changes: list[str] = []
    for route_name in sorted(route_names):
        live_turnout = next(
            (t for t in live_mqtt.findall("turnout") if t.findtext("userName") == route_name),
            None,
        )
        if live_turnout is None:
            continue
        sys_name = live_turnout.findtext("systemName") or ""
        base_turnout = base_by_sys.get(sys_name)
        if base_turnout is None:
            continue
        old_name = base_turnout.findtext("userName") or ""
        if old_name == route_name:
            continue
        user_el = base_turnout.find("userName")
        if user_el is None:
            user_el = ET.SubElement(base_turnout, "userName")
        user_el.text = route_name
        changes.append(f"{sys_name}: {old_name!r} -> {route_name!r}")
    return changes


def _ensure_clock_running_sensor(root: ET.Element, live_root: ET.Element) -> bool:
    for mgr in root.findall("sensors"):
        if "internal" not in (mgr.get("class") or "").lower():
            continue
        if any(
            (s.findtext("systemName") or "") == "ISCLOCKRUNNING"
            for s in mgr.findall("sensor")
        ):
            return False
        for live_mgr in live_root.findall("sensors"):
            if "internal" not in (live_mgr.get("class") or "").lower():
                continue
            for s in live_mgr.findall("sensor"):
                if (s.findtext("systemName") or "") == "ISCLOCKRUNNING":
                    mgr.insert(0, copy.deepcopy(s))
                    return True
    return False


def finalize_linear5_prod_panel(root: ET.Element, reference_path: Path) -> list[str]:
    """
    Match reference/tables.xml so JMRI loads without background/icon errors.
    """
    fixes: list[str] = []
    if not reference_path.is_file():
        return fixes

    ref_root = ET.parse(reference_path).getroot()
    ref_layout = ref_root.find(".//LayoutEditor")
    layout = root.find(".//LayoutEditor")
    if ref_layout is None or layout is None:
        return fixes

    ref_version = ref_root.find("jmriversion")
    version = root.find("jmriversion")
    if ref_version is not None and version is not None:
        idx = list(root).index(version)
        root.remove(version)
        new_version = ET.Element("jmriversion")
        for tag in ("major", "minor", "test", "modifier"):
            val = ref_version.findtext(tag)
            el = ET.SubElement(new_version, tag)
            if val is not None:
                el.text = val
        root.insert(idx, new_version)
        fixes.append("jmriversion")

    for attr in (
        "x",
        "y",
        "windowheight",
        "windowwidth",
        "panelheight",
        "panelwidth",
        "sliders",
        "scrollable",
    ):
        val = ref_layout.get(attr)
        if val is not None:
            layout.set(attr, val)
    for attr in ("height", "width"):
        if ref_layout.get(attr) is None and attr in layout.attrib:
            del layout.attrib[attr]
    fixes.append("LayoutEditor viewport")

    for label in layout.findall("positionablelabel"):
        if label.get("icon") != "yes":
            continue
        label.set("x", "0")
        label.set("y", "0")
        label.set("level", "1")
        label.set("editable", "true")
        icon = label.find("icon")
        if icon is not None:
            icon.set("url", LINEAR5_BG_PREF_URL)
            icon.set("scale", "1.0")
            if icon.find("rotation") is None:
                ET.SubElement(icon, "rotation").text = "0"
        fixes.append("background icon")

    from build_linear4_device_mapping import (  # noqa: E402
        _finalize_layout_editor_order,
    )

    _finalize_layout_editor_order(layout)
    fixes.append("layout child order")

    if _ensure_clock_running_sensor(root, ref_root):
        fixes.append("ISCLOCKRUNNING sensor")

    if root.find("filehistory") is None and ref_root.find("filehistory") is not None:
        fh = copy.deepcopy(ref_root.find("filehistory"))
        for op in list(fh.findall("operation")):
            if (op.findtext("type") or "").strip() == "Load with errors":
                fh.remove(op)
        root.append(fh)
        fixes.append("filehistory")

    return fixes


def merge_prod_panel(
    base_path: Path,
    live_path: Path,
    out_path: Path,
    logixng_path: Path | None = None,
    *,
    finalize_linear5: bool = False,
    reference_path: Path | None = None,
) -> None:
    base_root = ET.parse(base_path).getroot()
    live_root = ET.parse(live_path).getroot()
    logixng_root = ET.parse(logixng_path or LOGIXNG_PANEL).getroot()

    openlcb_merged = _merge_openlcb_from_live(base_root, live_root)
    turnout_renames = _sync_route_turnout_usernames(base_root, live_root)

    for tag in PROD_BEFORE_SIGNALHEADS + PROD_BEFORE_LAYOUT:
        for el in list(base_root):
            if _local_tag(el) == tag:
                base_root.remove(el)

    def _insert_index(anchor: str) -> int:
        for i, child in enumerate(base_root):
            if _local_tag(child) == anchor:
                return i
        raise SystemExit(f"{anchor} not found in base panel")

    layout_idx = _insert_index("LayoutEditor")
    signalheads_idx = _insert_index("signalheads")

    inserted: list[str] = []
    for tag in PROD_BEFORE_SIGNALHEADS:
        live_el = next(
            (c for c in live_root if _local_tag(c) == tag),
            None,
        )
        if live_el is None:
            continue
        base_root.insert(signalheads_idx, copy.deepcopy(live_el))
        signalheads_idx += 1
        layout_idx += 1
        inserted.append(f"{tag} ({live_path.name})")

    for tag in PROD_FROM_LIVE:
        live_el = next(
            (c for c in live_root if _local_tag(c) == tag),
            None,
        )
        if live_el is None:
            continue
        base_root.insert(layout_idx, copy.deepcopy(live_el))
        layout_idx += 1
        inserted.append(f"{tag} ({live_path.name})")

    logix_src = logixng_path or LOGIXNG_PANEL
    for tag in LOGIXNG_TAGS:
        logix_el = next(
            (c for c in logixng_root if _local_tag(c) == tag),
            None,
        )
        if logix_el is None:
            continue
        base_root.insert(layout_idx, copy.deepcopy(logix_el))
        layout_idx += 1
        inserted.append(f"{tag} ({logix_src.name})")

    if finalize_linear5:
        ref = reference_path or LINEAR5_REFERENCE
        applied = finalize_linear5_prod_panel(base_root, ref)
        if applied:
            print(f"  Linear5 finalize: {', '.join(applied)}")

    _write_jmri_panel_xml(base_root, out_path)
    print(f"Wrote {out_path}")
    print(f"  Base: {base_path.name}")
    print(f"  Live extras from: {live_path.name}")
    print(f"  LogixNG from: {logix_src.name}")
    if openlcb_merged:
        print(f"  OpenLCB: {', '.join(openlcb_merged)}")
    if turnout_renames:
        print(f"  Route turnout names: {', '.join(turnout_renames)}")
    print(f"  Inserted: {', '.join(inserted)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build linear4_prod.xml for production JMRI load")
    parser.add_argument("--base", type=Path, default=BASE_PANEL, help="linear4_devices.xml")
    parser.add_argument("--live", type=Path, default=LIVE_PANEL, help="tables.xml (routes, OpenLCB, memories)")
    parser.add_argument(
        "--logixng",
        type=Path,
        default=LOGIXNG_PANEL,
        help="Known-good LogixNG source (default: linear4_prod.xml)",
    )
    parser.add_argument("--output", type=Path, default=OUT_PROD, help="Output panel path")
    parser.add_argument(
        "--finalize-linear5",
        action="store_true",
        help="Apply reference/tables.xml load fixes (background URL, order, ISCLOCK)",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=LINEAR5_REFERENCE,
        help="Reference panel for linear5 finalize",
    )
    args = parser.parse_args()

    if not args.base.is_file():
        raise SystemExit(f"Base panel not found: {args.base}")
    if not args.live.is_file():
        raise SystemExit(f"Live panel not found: {args.live}")
    if not args.logixng.is_file():
        raise SystemExit(f"LogixNG panel not found: {args.logixng}")

    merge_prod_panel(
        args.base,
        args.live,
        args.output,
        logixng_path=args.logixng,
        finalize_linear5=args.finalize_linear5,
        reference_path=args.reference,
    )


if __name__ == "__main__":
    main()
