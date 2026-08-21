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
      <userName>East Lead</userName>
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
        self.assertIn("East Lead", currents)
        self.assertNotIn("Switch 100", currents)

    def test_apply_renames_preserves_system_names_and_sensor_usernames(self):
        renames = apply_public_names.load_rename_map(MAP)
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "tables.xml"
            target.write_text(FIXTURE_XML, encoding="utf-8")
            counts, system_names_ok = apply_public_names.apply_renames_to_xml_file(
                target, renames, apply=True
            )
            self.assertTrue(system_names_ok)
            self.assertGreater(counts[("East Lead", "South Yard East")], 0)
            self.assertGreater(counts[("East End East Lead", "112L")], 0)

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

            self.assertEqual("South Yard East", block_user.text)
            self.assertEqual("112L", mast_user.text)
            self.assertEqual("Block 13-5", sensor_user.text)
            self.assertEqual("M2S1304", sensor_system.text)
            self.assertEqual("IF$shsm:TEST:0001", mast_system.text)
            self.assertEqual("112L", sml_source.text)
            self.assertEqual("112L", sidi_signal.text)


if __name__ == "__main__":
    unittest.main()
