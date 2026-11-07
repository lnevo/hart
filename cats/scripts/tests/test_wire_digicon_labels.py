"""Desk callouts show the short track name; the JMRI block name keeps `Track`."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPTS = Path(__file__).resolve().parents[1]


def load_wire_digicon():
    spec = importlib.util.spec_from_file_location("wire_digicon", SCRIPTS / "wire_digicon.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class CalloutLabels(unittest.TestCase):
    def test_callout_text_drops_track_prefix_only(self) -> None:
        wire = load_wire_digicon()
        self.assertEqual("S-1", wire.callout_text("Track S-1"))
        self.assertEqual("McKees Rocks, PA", wire.callout_text("Track McKees Rocks, PA"))
        self.assertEqual("PRINCESS", wire.callout_text("PRINCESS"))
        self.assertEqual("39", wire.station_plate("OS Switch 39"))

    def test_fix_labels_strips_track_from_callouts_not_blocks(self) -> None:
        wire = load_wire_digicon()
        tp = ET.fromstring(
            '<TRACKPLAN>'
            '<SECTION X="57" Y="6"><SEC_NAME LOC_NAME="UPCENT" NAME="Track K-1" FONT_NAME="FONT_LABEL"/>'
            '<SEC_EDGE EDGE="LEFT"><BLOCK NAME="Track K-1" STATION="K-1"/></SEC_EDGE></SECTION>'
            '</TRACKPLAN>'
        )
        wire.fix_labels(tp)
        self.assertEqual("K-1", tp.find("SECTION/SEC_NAME").get("NAME"))
        self.assertEqual("Track K-1", tp.find(".//BLOCK").get("NAME"))

    def test_designer_source_has_no_track_callouts(self) -> None:
        wire = load_wire_digicon()
        tree = ET.parse(wire.SRC)
        offenders = [nm.get("NAME") for nm in tree.iter("SEC_NAME") if nm.get("NAME", "").startswith("Track ")]
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
