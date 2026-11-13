from __future__ import annotations

import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


polish = load_module("polish_hart_layout_editor", SCRIPTS / "polish_hart_layout_editor.py")
icons = load_module(
    "add_digicon_le_signal_icons",
    ROOT / "jmri/layouts/hart/scripts/add_digicon_le_signal_icons.py",
)


class PolishHartLayoutEditorTest(unittest.TestCase):
    def test_signal_generators_share_exact_placements(self):
        generated = {name: (x, y, degrees) for name, x, y, degrees in icons.PLACEMENTS}
        self.assertEqual(polish.SIGNAL_PLACEMENTS, generated)
        self.assertEqual(23, len(generated))

    def test_nx_layer_mast_positions_agree_with_placements(self):
        nx = load_module("apply_nx_layer", SCRIPTS / "apply_nx_layer.py")
        differ = {
            name: (xy, polish.SIGNAL_PLACEMENTS[name][:2])
            for name, xy in nx.MAST_ALIGN.items()
            if name in polish.SIGNAL_PLACEMENTS and xy != polish.SIGNAL_PLACEMENTS[name][:2]
        }
        self.assertEqual({}, differ)

    def test_visual_polish_is_idempotent_and_preserves_topology(self):
        source = ROOT / "jmri/layouts/hart/output/tables.xml"
        before_root = ET.parse(source).getroot()
        before_le = polish.find_layout_editor(before_root)
        before_topology = [
            (
                el.tag,
                el.get("ident"),
                el.get("connect1name"),
                el.get("connect2name"),
                el.get("connectaname"),
                el.get("connectbname"),
                el.get("connectcname"),
                el.get("connectdname"),
            )
            for el in before_le
            if el.tag in {"tracksegment", "layoutturnout", "positionablepoint"}
        ]

        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "tables.xml"
            target.write_bytes(source.read_bytes())
            polish.apply_visual_standard(target)
            _changes, errors = polish.apply_visual_standard(target, check=True)
            self.assertEqual([], errors)

            after_root = ET.parse(target).getroot()
            after_le = polish.find_layout_editor(after_root)
            leftover = [
                icon.get("sensor")
                for icon in after_le.findall("sensoricon")
                if polish.REDUNDANT_OCCUPANCY_SENSOR.fullmatch(
                    (icon.get("sensor") or "").strip()
                )
                and (icon.get("sensor") or "").strip()
                not in polish.OS_OCCUPANCY_ICONS
            ]
            self.assertFalse(leftover)
            os_present = {
                (icon.get("sensor") or "").strip()
                for icon in after_le.findall("sensoricon")
                if (icon.get("sensor") or "").strip() in polish.OS_OCCUPANCY_ICONS
            }
            self.assertEqual(os_present, set(polish.OS_OCCUPANCY_ICONS))
            after_topology = [
                (
                    el.tag,
                    el.get("ident"),
                    el.get("connect1name"),
                    el.get("connect2name"),
                    el.get("connectaname"),
                    el.get("connectbname"),
                    el.get("connectcname"),
                    el.get("connectdname"),
                )
                for el in after_le
                if el.tag in {"tracksegment", "layoutturnout", "positionablepoint"}
            ]
            self.assertEqual(before_topology, after_topology)

    def test_block_contents_icons_move_to_label_layer(self):
        xml = """<?xml version='1.0' encoding='UTF-8'?>
        <layout-config>
          <LayoutEditor name="HART Railroad">
            <BlockContentsIcon blockcontents="Track West Main Ext" x="1394" y="232" level="0" fontFamily="Lucida Grande" fontname="LucidaGrande-Bold" size="12" red="51" green="51" blue="51" />
            <tracksegment ident="T1" />
          </LayoutEditor>
        </layout-config>
        """
        root = ET.fromstring(xml)
        le = root.find("LayoutEditor")
        assert le is not None
        changes, errors = polish.ensure_block_contents_visible(le, check=False)
        self.assertEqual([], errors)
        self.assertGreater(changes, 0)
        icon = le.find("BlockContentsIcon")
        assert icon is not None
        self.assertEqual("4", icon.get("level"))
        self.assertEqual("0", icon.get("red"))
        self.assertNotIn("fontFamily", icon.attrib)
        self.assertNotIn("fontname", icon.attrib)
        _, leftover = polish.ensure_block_contents_visible(le, check=True)
        self.assertEqual([], leftover)

    def test_engine_house_train_names_move_off_switch_9(self):
        le = ET.fromstring(
            '<LayoutEditor name="HART Railroad">'
            '<BlockContentsIcon blockcontents="Track EH-3" x="603" y="269" level="4" red="0" green="0" blue="0" />'
            '<BlockContentsIcon blockcontents="OS Switch 9" x="600" y="269" level="4" red="0" green="0" blue="0" />'
            "</LayoutEditor>"
        )
        _, errors = polish.ensure_block_contents_visible(le, check=True)
        self.assertEqual(1, len(errors))
        self.assertEqual((1, []), polish.ensure_block_contents_visible(le, check=False))
        spots = {i.get("blockcontents"): (i.get("x"), i.get("y")) for i in le}
        self.assertEqual(("794", "284"), spots["Track EH-3"])
        self.assertEqual(("600", "269"), spots["OS Switch 9"])
        self.assertEqual((0, []), polish.ensure_block_contents_visible(le, check=True))

    def test_south_yard_track_names_are_labelled_once(self):
        le = ET.fromstring('<LayoutEditor name="HART Railroad"><positionablelabel text="Track S-1" x="1" y="1" /></LayoutEditor>')
        self.assertEqual(len(polish.TRACK_NAME_LABELS), len(polish.ensure_track_name_labels(le, check=True)[1]))
        polish.ensure_track_name_labels(le, check=False)
        spots = sorted((l.get("text"), l.get("x"), l.get("y")) for l in le.findall("positionablelabel"))
        self.assertEqual(sorted((t, str(x), str(y)) for t, (x, y) in polish.TRACK_NAME_LABELS.items()), spots)
        self.assertEqual((0, []), polish.ensure_track_name_labels(le, check=True))

    def test_stage1_copies_of_a_south_yard_lamp_end_up_as_one(self):
        le = ET.fromstring(
            '<LayoutEditor name="HART Railroad">'
            '<sensoricon sensor="BS S-1" x="762" y="376" level="10" />'
            '<sensoricon sensor="BS S-1" x="1010" y="376" level="10" />'
            '<sensoricon sensor="BS S-1" x="1204" y="376" level="10" />'
            '<sensoricon sensor="BS S-1" x="943" y="354" level="12" />'
            "</LayoutEditor>"
        )
        # one lamp off its spot plus two extra copies
        self.assertEqual(3, len(polish.place_stage1_lamps(le, check=True, targets=polish.STAGE1_LAMP_PLACEMENTS)[1]))
        polish.place_stage1_lamps(le, check=False, targets=polish.STAGE1_LAMP_PLACEMENTS)
        polish.dedupe_shared_occupancy_icons(le, check=False, targets=polish.STAGE1_LAMP_PLACEMENTS)
        lamps = sorted((i.get("level"), i.get("x"), i.get("y")) for i in le.findall("sensoricon"))
        x, y = polish.SOUTH_YARD_LAMPS["BS S-1"]
        self.assertEqual([("10", str(x), str(y)), ("12", "943", "354")], lamps)
        self.assertEqual((0, []), polish.place_stage1_lamps(le, check=True, targets=polish.STAGE1_LAMP_PLACEMENTS))

    def test_switch_lamps_centre_on_circles_and_track_lamps_sit_on_track(self):
        import math
        root = ET.parse(ROOT / "jmri/layouts/hart/output/tables.xml").getroot()
        le = polish.find_layout_editor(root)
        targets = polish.stage1_lamp_targets(root, le)
        half = polish.LAMP_SIZE / 2
        circles = {t.get("blockname"): t for t in le.findall("layoutturnout")}
        blocks = {}
        for b in root.iter("block"):
            if b.findtext("occupancysensor"):
                blocks.setdefault(b.findtext("occupancysensor"), []).append(b.findtext("userName"))
        segments = polish._segment_ends(le)

        def on_segment(px, py, a, b):
            """Distance to the segment itself, not the line through it."""
            (ax, ay), (bx, by) = a, b
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ((dx * dx + dy * dy) or 1)))
            return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

        for sensor, (x, y) in targets.items():
            if sensor in polish.STAGE1_LAMP_PLACEMENTS:
                continue
            cx, cy = x + half, y + half
            os_turnouts = [circles[n] for n in blocks.get(sensor, []) if n in circles]
            if os_turnouts:
                t = os_turnouts[0]
                self.assertLessEqual(math.hypot(cx - float(t.get("xcen")), cy - float(t.get("ycen"))), 1, sensor)
            else:
                mine = [seg for seg in segments if seg[0] in blocks[sensor]]
                self.assertLessEqual(min(on_segment(cx, cy, s[1], s[2]) for s in mine), 1, sensor)

        # every Stage 1 lamp on the panel is at its target
        _, errors = polish.place_stage1_lamps(le, check=True, targets=targets)
        self.assertEqual([], errors)

    def lamp_fixture(self) -> ET.Element:
        return ET.fromstring(
            "<layout-config><blocks>"
            '<block systemName="IB1" length="1"><userName>OS Switch 3</userName><occupancysensor>BS Switch 3</occupancysensor></block>'
            '<block systemName="IB2" length="1"><userName>Track K-1</userName><occupancysensor>BS K-1</occupancysensor></block>'
            '<block systemName="IB3" length="1"><userName>Track K-1 West</userName><occupancysensor>BS K-1</occupancysensor></block>'
            "</blocks>"
            '<LayoutEditor name="HART Railroad">'
            '<layoutturnout ident="T3" blockname="OS Switch 3" blocknameb="Track K-1" xcen="250" ycen="252" xa="240" ya="252" xb="260" yb="252" />'
            '<positionablepoint ident="P1" x="100" y="200" /><positionablepoint ident="P2" x="300" y="200" />'
            '<positionablepoint ident="P3" x="300" y="200" /><positionablepoint ident="P4" x="320" y="200" />'
            '<tracksegment ident="S1" blockname="Track K-1" connect1name="P1" type1="POS_POINT" connect2name="P2" type2="POS_POINT" />'
            '<tracksegment ident="S2" blockname="Track K-1 West" connect1name="P3" type1="POS_POINT" connect2name="P4" type2="POS_POINT" />'
            '<tracksegment ident="S3" blockname="Track K-1 West" connect1name="P1" type1="POS_POINT" connect2name="P4" type2="POS_POINT" hidden="yes" />'
            "</LayoutEditor></layout-config>"
        )

    def test_targets_use_turnout_block_and_skip_throats_without_comments(self):
        root = self.lamp_fixture()
        targets = polish.stage1_lamp_targets(root, root.find("LayoutEditor"))
        self.assertEqual((245, 247), targets["BS Switch 3"])  # circle centre minus half a lamp
        self.assertEqual((195, 195), targets["BS K-1"])  # middle of S1, not the throat

    def test_missing_switch_lamp_is_created_on_its_circle(self):
        root = self.lamp_fixture()
        le = root.find("LayoutEditor")
        targets = polish.stage1_lamp_targets(root, le)
        polish.ensure_os_occupancy_icons(le, check=False, targets=targets)
        lamp = [i for i in le.findall("sensoricon") if i.get("sensor") == "BS Switch 3"]
        self.assertEqual([("245", "247")], [(i.get("x"), i.get("y")) for i in lamp])

    def test_copy_already_on_target_is_the_one_kept(self):
        le = ET.fromstring(
            '<LayoutEditor><sensoricon sensor="BS K-1" x="1" y="1" level="10" />'
            '<sensoricon sensor="BS K-1" x="195" y="195" level="10" /></LayoutEditor>'
        )
        polish.place_stage1_lamps(le, check=False, targets={"BS K-1": (195, 195)})
        self.assertEqual([("195", "195")], [(i.get("x"), i.get("y")) for i in le.findall("sensoricon")])

    def test_shared_occupancy_dedupe_keeps_body_dot(self):
        xml = """<?xml version='1.0' encoding='UTF-8'?>
        <layout-config>
          <LayoutEditor name="HART Railroad">
            <sensoricon sensor="BS S-1" x="762" y="376" />
            <sensoricon sensor="BS S-1" x="985" y="361" />
            <sensoricon sensor="BS S-1" x="1204" y="376" />
            <sensoricon sensor="BS S-1" x="943" y="354" level="12" />
            <tracksegment ident="T1" />
          </LayoutEditor>
        </layout-config>
        """
        root = ET.fromstring(xml)
        le = root.find("LayoutEditor")
        assert le is not None
        changes, errors = polish.dedupe_shared_occupancy_icons(le, check=False, targets=polish.STAGE1_LAMP_PLACEMENTS)
        self.assertEqual([], errors)
        self.assertEqual(2, changes)
        kept = [
            (icon.get("x"), icon.get("y"))
            for icon in le.findall("sensoricon")
            if icon.get("sensor") == "BS S-1"
        ]
        self.assertEqual([("985", "361"), ("943", "354")], kept)

    def test_stage1_lamps_move_off_switch_9_but_cluster_lamps_stay(self):
        xml = """<layout-config><LayoutEditor name="HART Railroad">
            <sensoricon sensor="BS EH-1" x="658" y="256" level="12" />
            <sensoricon sensor="BS EH-1" x="612" y="276" level="10" />
            <sensoricon sensor="BS EH-2" x="604" y="287" level="10" />
            <sensoricon sensor="BS EH-3" x="603" y="299" level="10" />
            <sensoricon sensor="BS Switch 9" x="600" y="299" level="10" />
        </LayoutEditor></layout-config>"""
        le = ET.fromstring(xml).find("LayoutEditor")
        assert le is not None
        _, errors = polish.place_stage1_lamps(le, check=True, targets=polish.STAGE1_LAMP_PLACEMENTS)
        self.assertEqual(3, len(errors))
        changes, errors = polish.place_stage1_lamps(le, check=False, targets=polish.STAGE1_LAMP_PLACEMENTS)
        self.assertEqual((3, []), (changes, errors))
        placed = [
            (i.get("sensor"), i.get("x"), i.get("y"), i.get("level"))
            for i in le.findall("sensoricon")
        ]
        self.assertEqual(
            [
                ("BS EH-1", "658", "256", "12"),
                ("BS EH-1", "576", "261", "10"),
                ("BS EH-2", "576", "272", "10"),
                ("BS EH-3", "576", "284", "10"),
                ("BS Switch 9", "600", "299", "10"),
            ],
            placed,
        )
        self.assertEqual((0, []), polish.place_stage1_lamps(le, check=True, targets=polish.STAGE1_LAMP_PLACEMENTS))


if __name__ == "__main__":
    unittest.main()
