from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "reconcile_dispatcher_stations.py"
SPEC = importlib.util.spec_from_file_location("reconcile_dispatcher_stations", SCRIPT)
assert SPEC and SPEC.loader
reconciler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reconciler
SPEC.loader.exec_module(reconciler)


def add_sensor(manager: ET.Element, system_name: str, user_name: str) -> None:
    sensor = ET.SubElement(manager, "sensor", {"inverted": "false"})
    ET.SubElement(sensor, "systemName").text = system_name
    ET.SubElement(sensor, "userName").text = user_name


def fixture_tree() -> ET.ElementTree:
    root = ET.Element("layout-config")
    internal = ET.SubElement(
        root, "sensors", {"class": reconciler.INTERNAL_SENSOR_CLASS}
    )
    existing = (
        ("McKees Rocks", 1),
        ("McKeesport", 2),
        ("West Main Ext", 3),
    )
    for station, number in existing:
        move_to, progress = reconciler.sensor_names(station)
        add_sensor(internal, f"IS:DSMT:{number}", move_to)
        add_sensor(internal, f"IS:DSMP:{number}", progress)

    blocks = ET.SubElement(
        root, "blocks", {"class": "jmri.configurexml.BlockManagerXml"}
    )
    ET.SubElement(blocks, "defaultspeed").text = "Normal"
    for number, station in enumerate(reconciler.STATIONS, start=1):
        summary = ET.SubElement(blocks, "block", {"systemName": f"IB:{number}"})
        ET.SubElement(summary, "systemName").text = f"IB:{number}"
        ET.SubElement(summary, "userName").text = station

    for number, station in enumerate(reconciler.STATIONS, start=1):
        full = ET.SubElement(
            blocks,
            "block",
            {"systemName": f"IB:{number}", "length": "100.0", "curve": "0"},
        )
        ET.SubElement(full, "systemName").text = f"IB:{number}"
        ET.SubElement(full, "userName").text = station
        if station == "McKeesport":
            ET.SubElement(full, "comment").text = "existing note; stop"
        ET.SubElement(full, "permissive").text = "no"

    other = ET.SubElement(
        blocks,
        "block",
        {"systemName": "IB:99", "length": "100.0", "curve": "0"},
    )
    ET.SubElement(other, "systemName").text = "IB:99"
    ET.SubElement(other, "userName").text = "Not A Station"
    ET.SubElement(other, "comment").text = "keep this; stop"

    transits = ET.SubElement(
        root, "transits", {"class": "jmri.configurexml.TransitManagerXml"}
    )
    ET.SubElement(
        transits, "transit", {"systemName": "IZ:KEEP", "userName": "Keep Me"}
    )

    editor = ET.SubElement(root, "LayoutEditor", {"name": "My Layout"})
    for number, station in enumerate(reconciler.STATIONS):
        x, y = 100 + number * 150, 100 + (number % 2) * 100
        for _duplicate in range(2):
            ET.SubElement(
                editor,
                "BlockContentsIcon",
                {"blockcontents": station, "x": str(x), "y": str(y)},
            )

    # Force Main West away from its first candidate without affecting others.
    ET.SubElement(editor, "sensoricon", {"sensor": "Obstacle", "x": "100", "y": "120"})

    for station in ("McKees Rocks", "McKeesport", "West Main Ext"):
        anchor = next(
            icon
            for icon in editor.findall("BlockContentsIcon")
            if icon.get("blockcontents") == station
        )
        x, y = int(anchor.get("x", "0")), int(anchor.get("y", "0"))
        move_to, progress = reconciler.sensor_names(station)
        editor.append(reconciler.icon_element(move_to, station, x + 12, y + 20, True))
        editor.append(reconciler.icon_element(progress, station, x, y + 20, False))

    ET.SubElement(root, "LayoutEditor", {"name": "Dispatcher System"})
    return ET.ElementTree(root)


class ReconcileDispatcherStationsTest(unittest.TestCase):
    def test_reconcile_is_complete_idempotent_and_preserves_transit(self) -> None:
        tree = fixture_tree()
        root = tree.getroot()
        transit_before = ET.tostring(root.find("transits"))

        changes = reconciler.reconcile(tree)
        self.assertGreater(changes.total, 0)
        reconciler.validate(root)

        full_blocks = [
            block
            for block in root.find("blocks").findall("block")
            if reconciler.is_full_block(block)
        ]
        stopped = {
            reconciler.bean_user_name(block)
            for block in full_blocks
            if reconciler.comment_has_stop(block.findtext("comment") or "")
        }
        self.assertEqual(stopped, set(reconciler.STATIONS))
        summaries = [
            block
            for block in root.find("blocks").findall("block")
            if not reconciler.is_full_block(block)
        ]
        self.assertTrue(all(block.find("comment") is None for block in summaries))
        other = next(
            block
            for block in full_blocks
            if reconciler.bean_user_name(block) == "Not A Station"
        )
        self.assertEqual(other.findtext("comment"), "keep this")

        systems_by_user = {
            reconciler.bean_user_name(sensor): sensor.findtext("systemName")
            for sensor in root.find("sensors").findall("sensor")
        }
        self.assertEqual(
            systems_by_user["MoveToMcKees_Rocks_stored"], "IS:DSMT:1"
        )
        self.assertEqual(
            systems_by_user["MoveInProgressWest_Main_Ext"], "IS:DSMP:3"
        )
        self.assertEqual(ET.tostring(root.find("transits")), transit_before)

        editor = reconciler.main_layout_editor(root)
        managed = [
            icon
            for icon in editor.findall("sensoricon")
            if (icon.get("sensor") or "").startswith(("MoveTo", "MoveInProgress"))
        ]
        self.assertEqual(len(managed), 2 * len(reconciler.STATIONS))
        self.assertEqual(
            len({reconciler.xy(icon) for icon in managed}),
            2 * len(reconciler.STATIONS),
        )
        self.assertEqual(reconciler.PAIR_DX, 10)
        occupancy = [
            icon
            for icon in editor.findall("sensoricon")
            if (icon.get("sensor") or "") in reconciler.STATION_OCCUPANCY.values()
        ]
        self.assertEqual(len(occupancy), len(reconciler.STATIONS))
        progress = next(
            icon
            for icon in managed
            if icon.get("sensor") == "MoveInProgressMain_West"
        )
        move_to = next(
            icon
            for icon in managed
            if icon.get("sensor") == "MoveToMain_West_stored"
        )
        self.assertEqual(move_to.get("text"), reconciler.STATION_DISPLAY_NAMES["Main West"])
        px, py = reconciler.xy(progress)
        mx, my = reconciler.xy(move_to)
        self.assertEqual((mx - px, my - py), (reconciler.PAIR_DX, 0))
        occ = next(
            icon
            for icon in occupancy
            if icon.get("sensor") == reconciler.STATION_OCCUPANCY["Main West"]
        )
        ox, oy = reconciler.xy(occ)
        self.assertEqual(
            (ox - mx, oy - my),
            reconciler.OCCUPANCY_OFFSET,
        )
        eh_progress, eh_move, eh_occ = reconciler.cluster_positions(
            "EH-1"
        )
        self.assertEqual(eh_move[0] - eh_progress[0], reconciler.PAIR_DX)
        self.assertEqual(eh_progress[1], eh_occ[1])
        self.assertEqual(
            eh_occ[0],
            eh_move[0] - reconciler.PAIR_DX - reconciler.CIRCUIT_ICON_SIZE,
        )

        second = reconciler.reconcile(tree)
        self.assertEqual(second.total, 0)
        self.assertEqual(ET.tostring(root.find("transits")), transit_before)

    def test_check_never_writes_then_custom_run_becomes_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            panel = Path(temporary) / "fixture.xml"
            fixture_tree().write(panel, encoding="UTF-8", xml_declaration=True)
            original = panel.read_bytes()

            self.assertEqual(
                reconciler.main(["--panel", str(panel), "--check", "--no-sync"]),
                1,
            )
            self.assertEqual(panel.read_bytes(), original)

            self.assertEqual(
                reconciler.main(["--panel", str(panel), "--no-sync"]),
                0,
            )
            self.assertNotEqual(panel.read_bytes(), original)
            self.assertEqual(
                reconciler.main(["--panel", str(panel), "--check", "--no-sync"]),
                0,
            )


if __name__ == "__main__":
    unittest.main()
