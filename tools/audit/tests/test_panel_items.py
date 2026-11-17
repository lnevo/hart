"""panel_items.py: the fixed icons and labels of a Layout Editor panel, placed by rule (panel_items.json)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
import panel_items as pi  # noqa: E402

LAMP = '<sensoricon sensor="Track Power" class="jmri.jmrit.display.configurexml.SensorIconXml" />'
CAPTION = ('<positionablelabel text="Track Power" size="12" '
           'class="jmri.jmrit.display.configurexml.PositionableLabelXml" />')


def write(data) -> Path:
    tmp = Path(tempfile.mkdtemp()) / "panel_items.json"
    tmp.write_text(json.dumps(data), encoding="utf-8")
    return tmp


def items(*its):
    return {"panel": "HART Railroad", "items": list(its)}


class Load(unittest.TestCase):
    def test_a_good_file_loads(self):
        data = items({"id": "status", "anchor": {"to": "drawing", "at": "bottom-right", "dx": -60, "dy": 8},
                      "members": [{"dx": 0, "dy": 0, "size": [80, 20], "xml": CAPTION},
                                  {"dx": 83, "dy": 0, "size": [21, 21], "xml": LAMP}]},
                     {"id": "backdrop", "anchor": {"to": "origin", "dx": 9, "dy": 0}, "size": [0, 0], "xml": CAPTION})
        self.assertEqual(len(pi.load(write(data))["items"]), 2)

    def test_xml_with_a_place_stops(self):
        bad = items({"id": "x", "anchor": {"to": "origin"}, "size": [1, 1],
                     "xml": '<sensoricon sensor="S" x="3" y="4" />'})
        with self.assertRaisesRegex(pi.ItemsError, "holds x or y"):
            pi.load(write(bad))

    def test_an_unknown_tag_stops(self):
        bad = items({"id": "x", "anchor": {"to": "origin"}, "size": [1, 1], "xml": "<tracksegment />"})
        with self.assertRaisesRegex(pi.ItemsError, "is not one of"):
            pi.load(write(bad))

    def test_a_block_anchor_needs_its_block(self):
        bad = items({"id": "x", "anchor": {"to": "block", "at": "top"}, "size": [1, 1], "xml": LAMP})
        with self.assertRaisesRegex(pi.ItemsError, "names its block"):
            pi.load(write(bad))

    def test_an_unknown_point_stops(self):
        bad = items({"id": "x", "anchor": {"to": "drawing", "at": "middle"}, "size": [1, 1], "xml": LAMP})
        with self.assertRaisesRegex(pi.ItemsError, "anchor at must be one of"):
            pi.load(write(bad))

    def test_two_items_with_one_id_stop(self):
        one = {"id": "x", "anchor": {"to": "origin"}, "size": [1, 1], "xml": LAMP}
        with self.assertRaisesRegex(pi.ItemsError, "id of its own"):
            pi.load(write(items(one, dict(one))))


class Anchor(unittest.TestCase):
    def test_points_of_the_box(self):
        whole, blocks = (10, 20, 110, 220), {"Track A": (0, 0, 50, 10)}
        at = lambda a: pi.anchor_point(a, whole, blocks, "t")      # noqa: E731
        self.assertEqual(at({"to": "origin", "dx": 9, "dy": 1}), (9, 1))
        self.assertEqual(at({"to": "drawing", "at": "bottom-right", "dx": -5, "dy": 0}), (105, 220))
        self.assertEqual(at({"to": "drawing", "at": "top"}), (60, 20))
        self.assertEqual(at({"to": "block", "block": "Track A", "at": "centre"}), (25, 5))

    def test_a_block_not_drawn_stops(self):
        with self.assertRaisesRegex(pi.ItemsError, "not drawn"):
            pi.anchor_point({"to": "block", "block": "Track Z", "at": "top"}, (0, 0, 1, 1), {}, "t")


class Committed(unittest.TestCase):
    def test_the_status_cluster_keeps_panel_status_names(self):
        data = pi.load(ROOT / "jmri/layouts/hart/data/schematic/panel_items.json")
        status = next(it for it in data["items"] if it["id"] == "status")
        names = {ET.fromstring(m["xml"]).get("sensor") or ET.fromstring(m["xml"]).get("signalhead")
                 for m in status["members"]}
        self.assertTrue({"Bridge HBLOOP", "SML Mode", "Track Power", "IH9990"} <= names)

    def test_the_parked_lamps_load(self):
        data = pi.load(ROOT / "jmri/layouts/hart/parked/staging_panel_lamps.json")
        self.assertEqual(len(data["items"]), 79)


if __name__ == "__main__":
    unittest.main()
