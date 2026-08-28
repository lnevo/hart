from __future__ import annotations

import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
MAP = SCRIPTS.parent / "data" / "public_name_map.csv"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    import sys

    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


apply_public_names = load_module(
    "apply_public_names", SCRIPTS / "apply_public_names.py"
)

FIXTURE_XML = """<?xml version='1.0' encoding='UTF-8'?>
<layout-config>
  <blocks class="jmri.configurexml.BlockManagerXml">
    <block systemName="IB:TEST1">
      <systemName>IB:TEST1</systemName>
      <userName>OS East Lead</userName>
    </block>
  </blocks>
  <signalmasts class="jmri.managers.configurexml.DefaultSignalMastManagerXml">
    <signalmast class="jmri.implementation.configurexml.SignalHeadSignalMastXml">
      <systemName>IF$shsm:TEST:0001</systemName>
      <userName>East End East Lead</userName>
    </signalmast>
  </signalmasts>
  <sensors class="jmri.managers.configurexml.DefaultSensorManagerXml">
    <sensor inverted="false">
      <systemName>M2S1304</systemName>
      <userName>Block 13-5</userName>
    </sensor>
  </sensors>
  <signalmastlogics class="jmri.managers.configurexml.DefaultSignalMastLogicManagerXml">
    <signalmastlogic source="East End East Lead">
      <sourceSignalMast>East End East Lead</sourceSignalMast>
      <destinationMast destination="West Yard East Yard T6">
        <destinationSignalMast>West Yard East Yard T6</destinationSignalMast>
        <associatedSection>East End East Lead:West Yard East Yard T6</associatedSection>
      </destinationMast>
    </signalmastlogic>
  </signalmastlogics>
  <ctcCodeButtonData>
    <SIDI_LeftRightTrafficSignals>
      <signal>East End East Lead</signal>
    </SIDI_LeftRightTrafficSignals>
  </ctcCodeButtonData>
</layout-config>
"""


class ApplyPublicNamesTest(unittest.TestCase):
    def test_load_rename_map_skips_unchanged_rows(self):
        renames = apply_public_names.load_rename_map(MAP)
        self.assertTrue(all(entry.current != entry.proposed for entry in renames))
        currents = {entry.current for entry in renames}
        self.assertIn("OS 1", currents)
        self.assertIn("OS East Lead", currents)
        self.assertIn("Switch 100", currents)
        self.assertNotIn("Barn", currents)
        self.assertNotIn("S-1", currents)

    def test_apply_renames_preserves_system_names_and_sensor_usernames(self):
        renames = apply_public_names.load_rename_map(MAP)
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "tables.xml"
            target.write_text(FIXTURE_XML, encoding="utf-8")
            counts, system_names_ok = apply_public_names.apply_renames_to_xml_file(
                target, renames, apply=True
            )
            self.assertTrue(system_names_ok)
            self.assertGreater(counts[("OS East Lead", "Track East Lead")], 0)
            self.assertGreater(counts[("East End East Lead", "Mast 34L")], 0)

            root = ET.parse(target).getroot()
            block_user = root.find(".//blocks/block/userName")
            mast_user = root.find(".//signalmasts/signalmast/userName")
            sensor_user = root.find(".//sensors/sensor/userName")
            sensor_system = root.find(".//sensors/sensor/systemName")
            mast_system = root.find(".//signalmasts/signalmast/systemName")
            sml_source = root.find(".//sourceSignalMast")
            sidi_signal = root.find(".//SIDI_LeftRightTrafficSignals/signal")

            self.assertIsNotNone(block_user)
            self.assertIsNotNone(mast_user)
            self.assertIsNotNone(sensor_user)
            self.assertIsNotNone(sensor_system)
            self.assertIsNotNone(mast_system)
            self.assertIsNotNone(sml_source)
            self.assertIsNotNone(sidi_signal)

            self.assertEqual("Track East Lead", block_user.text)
            self.assertEqual("Mast 34L", mast_user.text)
            self.assertEqual("Block 13-5", sensor_user.text)
            self.assertEqual("M2S1304", sensor_system.text)
            self.assertEqual("IF$shsm:TEST:0001", mast_system.text)
            self.assertEqual("Mast 34L", sml_source.text)
            self.assertEqual("Mast 34L", sidi_signal.text)

    def test_alias_does_not_rewrite_south_yard_103_comment(self):
        renames = apply_public_names.load_rename_map(MAP)
        text = "Hand-throw west of South Yard 103; occupancy Block 3-1"
        updated, counts = apply_public_names.apply_renames_to_text(text, renames)
        self.assertEqual(text, updated)
        self.assertEqual(counts[("South Yard 1", "Track S-R")], 0)

    def test_south_yard_cascade_uses_placeholders(self):
        renames = apply_public_names.load_rename_map(MAP)
        text = "OS S-4 East and OS S-1 West and OS S-R stay distinct"
        updated, _counts = apply_public_names.apply_renames_to_text(text, renames)
        self.assertIn("Track S-4 East", updated)
        self.assertIn("Track S-1 West", updated)
        self.assertIn("Track S-R", updated)
        self.assertNotIn("OS S-4", updated)
        self.assertNotIn("OS S-1 West", updated)

    def test_isnx_system_names_are_frozen(self):
        renames = apply_public_names.load_rename_map(MAP)
        xml = (
            "<?xml version='1.0' encoding='UTF-8'?>\n"
            "<layout-config>"
            "<sensor><systemName>ISNX:100L</systemName>"
            "<userName>NX 100L</userName></sensor>"
            "<signalmast><systemName>IF$shsm:AAR-1946:SL-1-low(IH438)</systemName>"
            "<userName>100L</userName></signalmast>"
            "</layout-config>"
        )
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "tables.xml"
            target.write_text(xml, encoding="utf-8")
            _counts, system_names_ok = apply_public_names.apply_renames_to_xml_file(
                target, renames, apply=True
            )
            self.assertTrue(system_names_ok)
            out = target.read_text(encoding="utf-8")
            self.assertIn("<systemName>ISNX:100L</systemName>", out)
            self.assertIn("IF$shsm:AAR-1946:SL-1-low(IH438)", out)
            self.assertIn("<userName>Mast 2L</userName>", out)
            self.assertIn("<userName>NX Mast 2L</userName>", out)

    def test_dispatcher_os_prefix_and_south_yard_cascade(self):
        renames = apply_public_names.load_rename_map(MAP)
        text = "MoveToBarn_stored MoveToS-1_stored MoveToS-2_stored MoveToS-5_stored MoveToOS_Barn_stored"
        updated, _counts = apply_public_names.apply_renames_to_text(text, renames)
        self.assertIn("MoveToOS_Barn_stored", updated)
        self.assertIn("MoveToTrack_Barn_stored", updated)
        self.assertIn("MoveToOS_S-R_stored", updated)
        self.assertIn("MoveToOS_S-1_stored", updated)
        self.assertIn("MoveToOS_S-4_stored", updated)
        self.assertNotIn("MoveToBarn_stored", updated)
        self.assertNotIn("MoveToS-5_stored", updated)

    def test_already_os_prefixed_names_are_not_double_prefixed(self):
        renames = apply_public_names.load_rename_map(MAP)
        text = "OS McKeesport and OS S-1 and OS Barn and OS S-R"
        updated, _counts = apply_public_names.apply_renames_to_text(text, renames)
        self.assertEqual(
            "Track McKeesport and Track S-1 and Track Barn and Track S-R",
            updated,
        )

    def test_occupancy_refs_follow_bs_usernames(self):
        mapping = apply_public_names.load_sensor_username_map(MAP)
        xml = (
            "<block><occupancysensor>Block 13-1</occupancysensor></block>"
            '<layoutblock occupancysensor="Block 2-1"/>'
            '<sensoricon sensor="Block 13-1"/>'
            '<IOSPEC USER_NAME="Block 13-1"/>'
            "<comment>occupancy Block 13-1 / M2S1300; stop</comment>"
        )
        updated, hits = apply_public_names.apply_occupancy_refs_to_text(xml, mapping)
        self.assertGreater(hits, 0)
        self.assertIn("<occupancysensor>BS Barn</occupancysensor>", updated)
        self.assertIn('occupancysensor="BS Main West"', updated)
        self.assertIn('sensor="BS Barn"', updated)
        self.assertIn('USER_NAME="BS Barn"', updated)
        self.assertIn("occupancy Block 13-1 / M2S1300; stop", updated)

    def test_turnout_fb_and_sml_sensor_lookups_follow_usernames(self):
        mapping = apply_public_names.load_sensor_username_map(MAP)
        xml = (
            '<turnout sensor1="Switch 4-1 FB R" sensor2="Switch 4-1 FB N"/>'
            "<sensorName>Block 1-1</sensorName>"
            "<sensor>Block 1-1</sensor>"
            "<comment>same FB as MQTT hardware (Switch 4-1)</comment>"
        )
        updated, hits = apply_public_names.apply_sensor_lookups_to_text(xml, mapping)
        self.assertGreater(hits, 0)
        self.assertIn('sensor1="FB Switch 1 R"', updated)
        self.assertIn('sensor2="FB Switch 1 N"', updated)
        self.assertIn("<sensorName>BS McKees Rocks</sensorName>", updated)
        self.assertIn("<sensor>BS McKees Rocks</sensor>", updated)
        self.assertIn("same FB as MQTT hardware (Switch 4-1)", updated)

    def test_block_path_turnout_lookups_use_mqtt_system_names(self):
        mapping = apply_public_names.load_turnout_hardware_map(MAP)
        xml = (
            '<beansetting><turnout systemName="Switch 116" /></beansetting>'
            '<routeOutputTurnout systemName="Switch 114" state="CLOSED" />'
            '<routeOutputTurnout systemName="M2T411" state="CLOSED" />'
        )
        updated, hits = apply_public_names.apply_turnout_systemname_lookups_to_text(
            xml, mapping
        )
        self.assertGreater(hits, 0)
        self.assertIn('systemName="M2T411"', updated)
        self.assertIn('systemName="M2T109"', updated)
        self.assertNotIn('systemName="Switch 116"', updated)
        self.assertNotIn('systemName="Switch 114"', updated)


if __name__ == "__main__":
    unittest.main()
