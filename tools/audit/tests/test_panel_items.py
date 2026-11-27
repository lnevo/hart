"""panel_items.py: the fixed icons and labels of a Layout Editor panel, placed by rule (panel_items.json)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

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
    return {"items": list(its)}


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


class RightEdge(unittest.TestCase):
    """A caption placed by its right edge (`right`): its width as JMRI draws Dialog on the Pi (pi_dialog)."""

    def caption(self, text, **attrs):
        extra = "".join(f' {k}="{v}"' for k, v in attrs.items())
        return (f'<positionablelabel text="{text}" fontFamily="Dialog" fontname="Dialog" size="12" style="0"{extra} '
                'class="jmri.jmrit.display.configurexml.PositionableLabelXml" />')

    def test_the_pi_widths_are_what_java_measured_there(self):
        # FontMetrics.stringWidth on the Pi (OpenJDK 17.0.21, Dialog = DejaVu Sans), 2026-11-21
        self.assertEqual([pi.pi_dialog.width(t, 12) for t in ("LCOS", "Turnouts", "Signals", "Track Power")],
                         [31, 56, 45, 76])
        self.assertEqual(pi.pi_dialog.height(12), 15)
        for (style, size), (_h, adv) in pi.pi_dialog.DIALOG.items():
            self.assertEqual(len(adv), 95, (style, size))

    def test_captions_line_up_on_their_right_edges(self):
        members = [{"right": 76, "dy": 28 * k, "xml": self.caption(t)}
                   for k, t in enumerate(("LCOS", "Turnouts", "Signals", "Track Power"))]
        members.append({"dx": 80, "dy": 0, "size": [21, 21], "xml": LAMP})
        data = pi.load(write(items({"id": "status", "anchor": {"to": "origin", "dx": 100, "dy": 50},
                                    "members": members})))
        panel = ET.Element("layout-config", panelwidth="10", panelheight="10")
        with mock.patch.object(pi, "drawn_boxes", return_value=((0, 0, 1, 1), {})):
            got = pi.place(panel, data, None, None, (2000, 2000), (0, 0))
        labels = [el for el in panel if el.tag == "positionablelabel"]
        rights = {int(el.get("x")) + pi.pi_dialog.width(el.get("text"), 12) for el in labels}
        self.assertEqual(rights, {176})                                   # 4 px left of the lamp at 180
        self.assertEqual([int(el.get("x")) for el in labels], [145, 120, 131, 100])
        self.assertEqual(got["count"], 5)

    def test_a_bad_right_member_stops_naming_it(self):
        cases = [({"right": 76, "dx": 0, "xml": self.caption("A")}, "give no dx or size"),
                 ({"right": 76, "size": [1, 1], "xml": self.caption("A")}, "give no dx or size"),
                 ({"right": "76", "xml": self.caption("A")}, "is not a number"),
                 ({"right": 76, "xml": LAMP}, "positionablelabel with text"),
                 ({"right": 76, "xml": self.caption("A").replace('fontFamily="Dialog"', 'fontFamily="Serif"')},
                  "measures the Dialog font"),
                 ({"right": 76, "xml": self.caption("A").replace(' fontFamily="Dialog" fontname="Dialog"', "")},
                  "must name fontFamily and fontname Dialog"),
                 ({"right": 76, "xml": self.caption("A").replace('size="12"', 'size="13"')},
                  "no Pi Dialog widths for size 13"),
                 ({"right": 76, "xml": self.caption("A\u00e9")}, "not printable ASCII")]
        for m, msg in cases:
            with self.subTest(m=m), self.assertRaisesRegex(pi.ItemsError, msg):
                pi.load(write(items({"id": "status", "anchor": {"to": "origin"}, "members": [m]})))


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
        # the four captions stand by their right edges, on one line 4 px left of their lamps
        captions = [m for m in status["members"] if ET.fromstring(m["xml"]).tag == "positionablelabel"]
        lamps = {m["dx"] for m in status["members"] if ET.fromstring(m["xml"]).tag != "positionablelabel"}
        self.assertEqual(len(captions), 4)
        self.assertEqual({m["right"] for m in captions}, {min(lamps) - 4})

    def test_the_parked_lamps_load(self):
        data = pi.load(ROOT / "jmri/layouts/hart/parked/staging_panel_lamps.json")
        self.assertEqual(len(data["items"]), 79)


class StatusRows(unittest.TestCase):
    """The status beans' devices.csv rows (written_by panel_items.json) follow the items file."""

    def committed(self):
        return pi.load(pi.ITEMS)

    def test_the_committed_file_gives_one_row_per_status_bean_held_by_it(self):
        rows = pi.status_rows(self.committed())
        self.assertEqual([r["user_name"] for r in rows], ["Bridge HBLOOP", "SML Mode", "Track Power", "Turnout FB status"])
        self.assertEqual({r["written_by"] for r in rows}, {"panel_items.json"})
        self.assertEqual({r["role"] for r in rows}, {"panel_status"})
        self.assertTrue(all(r["description"] for r in rows))

    def test_a_status_bean_the_items_file_does_not_show_stops(self):
        data = self.committed()
        for it in data["items"]:
            for m in it.get("members", []):
                m["xml"] = m["xml"].replace('sensor="SML Mode"', 'sensor="Other"')
        with self.assertRaisesRegex(pi.ItemsError, "status bean 'SML Mode' .* has no sensoricon"):
            pi.status_rows(data)

    def test_a_status_bean_in_two_items_stops(self):
        data = self.committed()
        first = next(it for it in data["items"] if any('sensor="SML Mode"' in m["xml"] for m in it.get("members", [])))
        data["items"].append(dict(first, id="copy"))
        with self.assertRaisesRegex(pi.ItemsError, r"sensoricon '[^']+' is in items 'status' and 'copy'"):
            pi.status_rows(data)

    def test_the_rows_are_the_ones_the_code_table_gave(self):
        # (layer, user name, system name, assignment, JMRI comment, description) as the table in panel_items.py
        # gave them before they moved to panel_lamps.csv
        want = [
            ("sensor", "Bridge HBLOOP", "M2S1567", "field", "LCOS lamp; ACTIVE=link up",
             "Panel lamp sensor Bridge HBLOOP: lit when the link is up."),
            ("sensor", "SML Mode", "IS:SML_MODE", "virtual", "Signals lamp; ACTIVE=SML on",
             "Panel lamp sensor SML Mode: lit when signal mast logic is on."),
            ("sensor", "Track Power", "IS:TRACK_POWER", "virtual", "Track Power lamp; ACTIVE=on",
             "Panel lamp sensor Track Power: lit when track power is on."),
            ("head", "Turnout FB status", "IH9990", "field", "Turnouts lamp: green feedback; red direct",
             "Panel lamp head: green shows turnout feedback, red shows a direct turnout."),
        ]
        rows = pi.status_rows(self.committed())
        self.assertEqual([(r["layer"], r["user_name"], r["system_name"], r["assignment"], r["jmri_comment"],
                           r["description"]) for r in rows], want)
        self.assertEqual([r["jmri_name"] for r in rows], [w[2] for w in want])
        self.assertEqual([r["id"] for r in rows], [f"panel:status:{w[2]}" for w in want])

    def test_a_lamp_the_items_file_does_not_show_stops(self):
        tmp = Path(tempfile.mkdtemp()) / pi.LAMPS.name
        tmp.write_text(pi.LAMPS.read_text(encoding="utf-8") + "IS:OTHER,sensor,Other,virtual,sensor,c,d\n",
                       encoding="utf-8")
        with self.assertRaisesRegex(pi.ItemsError, "status bean 'Other' .* has no sensoricon naming 'Other'"):
            pi.status_rows(self.committed(), tmp)

    def test_a_bad_lamps_file_stops(self):
        with self.assertRaisesRegex(pi.hand_lists.HandListError, "cannot read none.csv"):
            pi.status_rows(self.committed(), Path(tempfile.mkdtemp()) / "none.csv")

    def test_the_committed_master_holds_them(self):
        self.assertEqual(pi.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
