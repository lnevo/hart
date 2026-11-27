"""hartlib.tables_sml: the discovered Signal Mast Logic written and merged, the masts it misses, and the Digicon boot
rule on a small Store."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import tables, tables_sml as sml  # noqa: E402
from hartlib.tables_sections import TablesBuildError  # noqa: E402

STORE = """<layout-config>
  <signalmasts>
    <signalmast class="x"><systemName>IF$shsm:basic:one-searchlight(IH432)</systemName><userName>Mast 6LB</userName>
      <properties><property><key>intermediateSignal</key></property></properties><unlit allowed="no" /></signalmast>
    <virtualsignalmast class="y"><systemName>IF$vsm:basic:one-low($1001)</systemName><userName>Mast 4LA</userName>
      <unlit allowed="yes" /></virtualsignalmast>
  </signalmasts>
  <signalmastlogics><logicDelay>500</logicDelay>
    <signalmastlogic source="Mast 6LB"><destinationMast destination="Mast 4LA"><enabled>yes</enabled>
      </destinationMast></signalmastlogic>
  </signalmastlogics>
</layout-config>"""


def bare() -> ET.Element:
    """STORE with its logic and mast properties taken out: what the build merges the discovered file into."""
    root = ET.fromstring(STORE)
    box = root.find("signalmastlogics")
    box.remove(box.find("signalmastlogic"))
    mast = root.find("signalmasts/signalmast")
    mast.remove(mast.find("properties"))
    return root


class Discovered(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_written_read_back_and_merged(self) -> None:
        path = self.tmp / "discovered.xml"
        self.assertTrue(sml.write_discovered(sml.discovered_from_store(ET.fromstring(STORE)), path))
        logics, props = sml.read_discovered(path)
        root = bare()
        self.assertEqual(["Mast 6LB", "Mast 4LA"], sml.missing_logic(root))
        sml.merge_discovered(root, logics, props)
        self.assertEqual([], sml.missing_logic(root))
        self.assertEqual(["systemName", "userName", "properties", "unlit"],
                         [c.tag for c in tables.elements(root.find("signalmasts/signalmast"))])

    def test_merging_twice_stops(self) -> None:
        logics, props = sml.read_discovered_root(sml.discovered_from_store(ET.fromstring(STORE)), "d.xml")
        with self.assertRaisesRegex(TablesBuildError, "hold logic already"):
            sml.merge_discovered(ET.fromstring(STORE), logics, props)

    def test_an_unwritable_document_is_not_written(self) -> None:
        with self.assertRaisesRegex(TablesBuildError, "not <discovered-sml>"):
            sml.write_discovered(ET.Element("other"), self.tmp / "d.xml")
        self.assertFalse((self.tmp / "d.xml").exists())


class Digicon(unittest.TestCase):
    def test_destinations_are_disabled_once(self) -> None:
        root = ET.fromstring(STORE)
        self.assertEqual([("Mast 6LB", "Mast 4LA")], sml.enabled_digicon(root, {"Mast 6LB"}))
        self.assertEqual((1, 0), sml.disable_digicon(root, {"Mast 6LB"}))
        self.assertEqual((0, 1), sml.disable_digicon(root, {"Mast 6LB"}))
        self.assertEqual([], sml.enabled_digicon(root, {"Mast 6LB"}))
        self.assertEqual((0, 0), sml.disable_digicon(root, {"Mast 4LA"}))      # no logic of its own

    def test_a_destination_without_enabled_stops(self) -> None:
        root = ET.fromstring(STORE)
        dest = root.find("signalmastlogics/signalmastlogic/destinationMast")
        dest.remove(dest.find("enabled"))
        with self.assertRaisesRegex(TablesBuildError, "Mast 6LB -> Mast 4LA has no <enabled>"):
            sml.disable_digicon(root, {"Mast 6LB"})


if __name__ == "__main__":
    unittest.main()
