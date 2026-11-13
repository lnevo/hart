from __future__ import annotations

import importlib.util
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "restore_manual_sml_pairs", SCRIPTS / "restore_manual_sml_pairs.py"
)
pairs = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(pairs)


def logic(*dests_by_source: tuple[str, list[str]]) -> ET.Element:
    root = ET.Element("layout-config")
    smls = ET.SubElement(root, "signalmastlogics")
    for source, dests in dests_by_source:
        sml = ET.SubElement(smls, "signalmastlogic", {"source": source})
        ET.SubElement(sml, "sourceSignalMast").text = source
        for dest in dests:
            d = ET.SubElement(sml, "destinationMast", {"destination": dest})
            ET.SubElement(d, "destinationSignalMast").text = dest
            ET.SubElement(d, "comment").text = f"from {source}"
    return root


class RestoreManualPairsTest(unittest.TestCase):
    def test_missing_pairs_come_back_from_reference(self):
        reference = logic(("Mast 36RA", ["Mast 40LA"]), ("Mast 36RB", ["Mast 38LA"]))
        after_stage1 = logic(("Mast 36RA", ["Mast 2036"]), ("Mast 36RB", ["Mast 38LA"]))
        self.assertEqual([("Mast 36RA", "Mast 40LA")], pairs.missing_pairs(after_stage1))
        self.assertEqual([("Mast 36RA", "Mast 40LA")], pairs.restore(after_stage1, reference))
        self.assertEqual([], pairs.missing_pairs(after_stage1))
        self.assertEqual([], pairs.restore(after_stage1, reference))

    def test_reference_without_the_pair_stops(self):
        with self.assertRaisesRegex(ValueError, "reference has no"):
            pairs.restore(logic(("Mast 36RA", []), ("Mast 36RB", [])), logic())

    def test_current_tables_have_both_pairs(self):
        self.assertEqual(0, pairs.main(["--check"]))


if __name__ == "__main__":
    unittest.main()
