"""The checks audit_panel_contracts runs from audit_panel_tables.py and audit_panel_base.py, on small tables of
their own: MQTT sensor names, turnout feedback names, turnout lookups, placeholder labels and the reporter that
sends a problem to the errors or the warnings. Also: a panel with two generated-panel markers is one error."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_panel_contracts as apc  # noqa: E402
from hartlib import paths, tables  # noqa: E402


def audit() -> apc.Audit:
    return apc.Audit("test", Path("test.xml"))


def sensors_root(cls: str, *names: str) -> ET.Element:
    root = ET.Element("layout-config")
    group = ET.SubElement(root, "sensors", {"class": cls})
    for name in names:
        ET.SubElement(ET.SubElement(group, "sensor"), "systemName").text = name
    return root


class Reporter(unittest.TestCase):
    def test_a_required_check_errors_and_another_warns(self) -> None:
        a = audit()
        a.reporter(True)("hard")
        a.reporter(False)("soft")
        self.assertEqual((a.errors, a.warnings), (["hard"], ["soft"]))


class MqttSensors(unittest.TestCase):
    MQTT = "jmri.jmrix.mqtt.configurexml.MqttSensorManagerXml"

    def test_packed_names_pass(self) -> None:
        a = audit()
        apc.audit_forbidden_mqtt_sensors(sensors_root(self.MQTT, "M2S1567", "M2S432"), a)
        self.assertEqual(a.errors, [])

    def test_the_forbidden_and_the_malformed_are_errors(self) -> None:
        a = audit()
        apc.audit_forbidden_mqtt_sensors(sensors_root(self.MQTT, "M2S467", "M2SBlock 1-1", "M2S432"), a)
        self.assertEqual(len(a.errors), 2, a.errors)
        self.assertIn("found ['M2S467']", a.errors[0])
        self.assertIn("found ['M2SBlock 1-1']", a.errors[1])

    def test_other_connections_are_not_read(self) -> None:
        a = audit()
        apc.audit_forbidden_mqtt_sensors(sensors_root("jmri.jmrix.internal.Sensors", "M2S467"), a)
        self.assertEqual(a.errors, [])


def turnouts_root(sensor1: str) -> ET.Element:
    """One turnout, MTT100 (DCC Switch 1), whose sensor1 is `sensor1`; the only sensor is FB Switch 1 R."""
    root = ET.Element("layout-config")
    sensor = ET.SubElement(ET.SubElement(root, "sensors"), "sensor")
    ET.SubElement(sensor, "systemName").text = "IS1"
    ET.SubElement(sensor, "userName").text = "FB Switch 1 R"
    group = ET.SubElement(root, "turnouts")
    turnout = ET.SubElement(group, "turnout", sensor1=sensor1)
    ET.SubElement(turnout, "systemName").text = "MTT100"
    ET.SubElement(turnout, "userName").text = "DCC Switch 1"
    return root


class TurnoutFeedback(unittest.TestCase):
    def test_a_sensor_user_name_passes(self) -> None:
        a = audit()
        apc.audit_turnout_feedback_sensors(turnouts_root("FB Switch 1 R"), a, required=True)
        self.assertEqual((a.errors, a.facts["turnout_feedback"]), ([], ()))

    def test_an_old_convert_name_is_named(self) -> None:
        a = audit()
        apc.audit_turnout_feedback_sensors(turnouts_root("Switch 4-1 FB R"), a, required=True)
        self.assertEqual(a.errors, ["turnout feedback still uses pre-convert FB userNames: "
                                    "DCC Switch 1 sensor1=Switch 4-1 FB R"])

    def test_a_name_no_sensor_has_warns_when_not_required(self) -> None:
        a = audit()
        apc.audit_turnout_feedback_sensors(turnouts_root("FB Switch 9 R"), a, required=False)
        self.assertEqual(a.errors, [])
        self.assertEqual(a.warnings, ["turnout feedback sensors are not sensor userNames: "
                                      "DCC Switch 1 sensor1=FB Switch 9 R"])


class TurnoutLookups(unittest.TestCase):
    def test_paths_and_routes_resolve_by_system_or_user_name(self) -> None:
        root = turnouts_root("FB Switch 1 R")
        for name in ("MTT100", "DCC Switch 1", "Switch 116"):
            setting = ET.SubElement(root, "beansetting")
            ET.SubElement(setting, "turnout", systemName=name)
        ET.SubElement(root, "routeOutputTurnout", systemName="MTSwitch 116")
        a = audit()
        apc.audit_turnout_systemname_lookups(root, a, required=True)
        self.assertEqual(a.facts["turnout_lookups"], ("path Switch 116", "route MTSwitch 116"))
        self.assertEqual(len(a.errors), 1)


class Placeholders(unittest.TestCase):
    def test_sig_labels_warn_and_lamp_captions_do_not(self) -> None:
        panel = ET.Element("LayoutEditor", name="HART Railroad")
        for caption in ("SIG 12", "Signals", "LCOS"):
            ET.SubElement(panel, "positionablelabel", text=caption)
        ET.SubElement(panel, "sensoricon", sensor="Block 1-1")
        a = audit()
        apc.audit_placeholders(panel, a)
        self.assertEqual(a.warnings, ["stale SIG placeholder labels remain: ['SIG 12']"])
        self.assertEqual(len(a.errors), 1)
        self.assertIn("['Block 1-1']", a.errors[0])


@unittest.skipUnless(os.environ.get("SCHEMATIC_PLUGIN")
                     or (paths.REPO_ROOT / "external/model-railroad-skills/plugins/schematic-maps").is_dir(),
                     "needs the schematic-maps plugin (SCHEMATIC_PLUGIN or the submodule)")
class DoubledMarker(unittest.TestCase):
    def test_two_markers_are_one_error(self) -> None:
        root = tables.read(paths.TABLES_XML)
        panel = next(p for p in root.iter("LayoutEditor") if p.get("name") in apc.PANEL_NAMES)
        marker = next(l for l in panel.findall("positionablelabel") if l.get("text") == tables.GENERATED_PANEL_MARKER)
        panel.append(ET.fromstring(ET.tostring(marker)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
            result = apc.audit_source("deployment", path, apc.load_staging_masts())
        doubled = [e for e in result.errors if "generated-panel markers" in e]
        self.assertEqual(len(doubled), 1, result.errors)
        self.assertTrue(result.facts["generated_panel"])


if __name__ == "__main__":
    unittest.main()
