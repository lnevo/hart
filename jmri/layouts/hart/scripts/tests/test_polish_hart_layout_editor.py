"""polish_hart_layout_editor.py: the Stage 1 repair of the generated Layout Editor panel (Dispatcher System, parked).

The fixture is this checkout's tables with the Dispatcher System put back from the parked file
(hartlib.parked.with_parked) and a Stage 1 occupancy lamp at its computed spot on each sensor the parked staging lamps
show (jmri/layouts/hart/parked/staging_panel_lamps.json): the generated panel as it stands once the Dispatcher System
is unparked. Stage 1 then deletes and re-adds the lamps and block
contents labels at its own spots; the repair puts them back.
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import math
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import parked, paths, tables  # noqa: E402

_spec = importlib.util.spec_from_file_location("polish_hart_layout_editor", SCRIPTS / "polish_hart_layout_editor.py")
polish = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(polish)


PARKED_LAMPS = paths.LAYOUT_DIR / "parked" / "staging_panel_lamps.json"


def lamp_sensors() -> set[str]:
    """The block sensors the parked staging lamps show."""
    items = json.loads(PARKED_LAMPS.read_text(encoding="utf-8"))["items"]
    return {s for it in items for s in re.findall(r'sensor="(BS [^"]+)"', it["xml"])}


def unparked() -> ET.Element:
    """This checkout's tables with the Dispatcher System put back, and a Stage 1 lamp on each staging lamp sensor."""
    root = copy.deepcopy(parked.with_parked({"dispatcher"}, paths.REPO_TABLES_XML))
    le = tables.layout_editor(root)
    shown = lamp_sensors()
    for sensor, (x, y) in sorted(polish.computed_lamp_targets(root, le).items()):
        if sensor in shown:
            le.append(polish._circuit_occupancy_icon(sensor, x, y))
    return root


FIXTURE = unparked()


def write(root: ET.Element, folder: Path, name: str = "tables.xml") -> Path:
    path = folder / name
    path.write_bytes(tables.Tables(root=root).tobytes())
    return path


def spots(root: ET.Element) -> list[tuple]:
    le = tables.layout_editor(root)
    return sorted((el.tag, el.get("sensor") or el.get("blockcontents") or "", el.get("x") or "", el.get("y") or "",
                   el.get("level") or "", el.get("forcecontroloff") or "")
                  for el in le if el.tag in {"sensoricon", "BlockContentsIcon"})


def stage1_scramble(root: ET.Element) -> ET.Element:
    """What a Stage 1 Store does to the panel's lamps and train-name labels: deletes them and adds its own copies
    at its own spots (here: all moved 37 px right and down, one lamp doubled, the labels on level 0 and the lamps
    clickable)."""
    root = copy.deepcopy(root)
    le = tables.layout_editor(root)
    lamps = [i for i in le.findall("sensoricon") if polish._is_circuit_lamp(i) and i.get("level") != "12"]
    for icon in lamps + le.findall("BlockContentsIcon"):
        icon.set("x", str(int(float(icon.get("x"))) + 37))
        icon.set("y", str(int(float(icon.get("y"))) + 37))
    for icon in lamps:
        icon.set("forcecontroloff", "false")
    le.append(copy.deepcopy(lamps[0]))
    for icon in le.findall("BlockContentsIcon"):
        icon.set("level", "0")
    return root


def run(path: Path, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = polish.repair(path, **kw)
    return result, out.getvalue()


class Repair(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_the_fixture_is_the_generated_panel_with_its_lamps(self) -> None:
        le = tables.layout_editor(FIXTURE)
        self.assertTrue(tables.generated_panel(le))
        self.assertNotIn("dispatcher", parked.parked_in(FIXTURE))
        lamps = {i.get("sensor") for i in le.findall("sensoricon") if i.get("level") == "10"}
        self.assertLessEqual(set(polish.OS_OCCUPANCY_ICONS), lamps)

    def test_a_panel_as_built_needs_no_repair_and_is_not_written(self) -> None:
        path = write(FIXTURE, self.dir)
        before = path.read_bytes()
        (_n, errors), _ = run(path, check=True)
        self.assertEqual([], errors)
        (n, errors), _ = run(path)
        self.assertEqual((0, []), (n, errors))
        self.assertEqual(before, path.read_bytes())

    def test_reference_puts_stage1_lamps_and_labels_back(self) -> None:
        reference = write(FIXTURE, self.dir, "before.xml")
        path = write(stage1_scramble(FIXTURE), self.dir)
        (_n, errors), _ = run(path, check=True, reference=reference)
        self.assertTrue(any("more than one Stage 1 lamp" in e for e in errors))
        self.assertTrue(any("level='0'" in e for e in errors))
        self.assertTrue(any("can be clicked" in e for e in errors))
        run(path, reference=reference)
        self.assertEqual(spots(FIXTURE), spots(tables.read(path)))
        (_n, errors), _ = run(path, check=True, reference=reference)
        self.assertEqual([], errors)

    def test_without_reference_a_lamp_is_kept_where_it_stands(self) -> None:
        root = stage1_scramble(FIXTURE)
        le = tables.layout_editor(root)
        le.remove(le[-1])          # no doubled lamp: every sensor has one lamp, at Stage 1's spot
        (_n, errors), _ = run(write(root, self.dir), check=True)
        self.assertEqual([], [e for e in errors if "Stage 1 lamp" in e or "expected (" in e])

    def test_a_doubled_lamp_with_no_reference_goes_to_its_computed_spot_with_a_note(self) -> None:
        root = copy.deepcopy(FIXTURE)
        le = tables.layout_editor(root)
        lamp = next(i for i in le.findall("sensoricon") if i.get("sensor") == "BS Switch 21")
        le.append(copy.deepcopy(lamp))
        path = write(root, self.dir)
        _result, out = run(path)
        self.assertIn("lamp BS Switch 21: 2 on the panel", out)
        target = polish.computed_lamp_targets(root, le)["BS Switch 21"]
        kept = [i for i in tables.layout_editor(tables.read(path)).findall("sensoricon")
                if i.get("sensor") == "BS Switch 21"]
        self.assertEqual([(str(target[0]), str(target[1]))], [(i.get("x"), i.get("y")) for i in kept])

    def test_a_missing_switch_lamp_is_added_where_the_reference_had_it(self) -> None:
        reference = write(FIXTURE, self.dir, "before.xml")
        root = copy.deepcopy(FIXTURE)
        le = tables.layout_editor(root)
        le.remove(next(i for i in le.findall("sensoricon") if i.get("sensor") == "BS Switch 9"))
        path = write(root, self.dir)
        (_n, errors), _ = run(path, check=True, reference=reference)
        self.assertEqual(["tables.xml: missing OS occupancy icon 'BS Switch 9'"], errors)
        run(path, reference=reference)
        self.assertEqual(spots(FIXTURE), spots(tables.read(path)))

    def test_a_stage1_lamp_the_reference_panel_does_not_show_is_removed(self) -> None:
        # Stage 1 adds a lamp on every block sensor, the main and upper levels' too; the reference panel has none there
        reference = write(FIXTURE, self.dir, "before.xml")
        root = copy.deepcopy(FIXTURE)
        le = tables.layout_editor(root)
        targets = polish.computed_lamp_targets(root, le)
        level = sorted(set(targets) - lamp_sensors())
        self.assertTrue(level)
        for sensor in level:
            le.append(polish._circuit_occupancy_icon(sensor, *targets[sensor]))
        path = write(root, self.dir)
        (_n, errors), _ = run(path, check=True, reference=reference)
        self.assertEqual(len(level), len([e for e in errors if "none on the reference panel" in e]))
        run(path, reference=reference)
        self.assertEqual(spots(FIXTURE), spots(tables.read(path)))
        # without a reference such a lamp is the panel's own, and stays
        path = write(root, self.dir, "own.xml")
        (_n, errors), _ = run(path, check=True)
        self.assertEqual([], errors)

    def test_masts_captions_and_panel_attributes_are_left_alone(self) -> None:
        # Stage 1 does not touch them (CreateIcons), so the repair does not either
        reference = write(FIXTURE, self.dir, "before.xml")
        root = stage1_scramble(FIXTURE)
        le = tables.layout_editor(root)
        mast = le.find("signalmasticon")
        mast.set("hidden", "yes" if mast.get("hidden") == "no" else "no")
        caption = next(l for l in le.findall("positionablelabel") if l.get("text") == "HART RAILROAD")
        caption.set("size", "20")
        le.set("mainlinetrackwidth", "9")
        path = write(root, self.dir)
        run(path, reference=reference)
        after = tables.layout_editor(tables.read(path))
        self.assertEqual(mast.get("hidden"), after.find("signalmasticon").get("hidden"))
        self.assertEqual("20", next(l for l in after.findall("positionablelabel")
                                    if l.get("text") == "HART RAILROAD").get("size"))
        self.assertEqual("9", after.get("mainlinetrackwidth"))

    def test_the_cluster_lamps_are_left_alone(self) -> None:
        root = copy.deepcopy(FIXTURE)
        le = tables.layout_editor(root)
        cluster = next(i for i in le.findall("sensoricon") if i.get("level") == polish.CLUSTER_LAMP_LEVEL)
        cluster.set("x", "3")
        path = write(root, self.dir)
        run(path, reference=write(FIXTURE, self.dir, "before.xml"))
        self.assertIn(("sensoricon", cluster.get("sensor"), "3"),
                      [s[:3] for s in spots(tables.read(path))])

    def test_switch_lamps_centre_on_circles_and_track_lamps_sit_on_track(self) -> None:
        le = tables.layout_editor(FIXTURE)
        half = polish.LAMP_SIZE / 2
        circles: dict[str, ET.Element] = {}
        for t in le.findall("layoutturnout"):          # a crossover's two halves on one block: the first
            circles.setdefault(t.get("blockname"), t)
        blocks: dict[str, list[str]] = {}
        for b in FIXTURE.iter("block"):
            if b.findtext("occupancysensor"):
                blocks.setdefault(b.findtext("occupancysensor"), []).append(b.findtext("userName"))
        segments = polish._segment_ends(le)

        def on_segment(px, py, a, b):
            (ax, ay), (bx, by) = a, b
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ((dx * dx + dy * dy) or 1)))
            return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

        targets = polish.computed_lamp_targets(FIXTURE, le)
        self.assertLessEqual(set(polish.OS_OCCUPANCY_ICONS), set(targets))
        for sensor, (x, y) in targets.items():
            cx, cy = x + half, y + half
            os_turnouts = [circles[n] for n in blocks.get(sensor, []) if n in circles]
            if os_turnouts:
                t = os_turnouts[0]
                self.assertLessEqual(math.hypot(cx - float(t.get("xcen")), cy - float(t.get("ycen"))), 1, sensor)
            else:
                mine = [seg for seg in segments if seg[0] in blocks[sensor]]
                self.assertLessEqual(min(on_segment(cx, cy, s[1], s[2]) for s in mine), 1, sensor)


class Refusals(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def unmarked(self) -> ET.Element:
        root = copy.deepcopy(FIXTURE)
        le = tables.layout_editor(root)
        le.remove(le.find(f"positionablelabel[@text='{tables.GENERATED_PANEL_MARKER}']"))
        return root

    def test_a_panel_that_is_not_generated_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "'HART Railroad' panel is not a generated one"):
            polish.repair(write(self.unmarked(), self.dir), check=True)

    def test_a_reference_that_is_not_generated_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "--reference .*not a generated one"):
            polish.repair(write(FIXTURE, self.dir), check=True,
                          reference=write(self.unmarked(), self.dir, "hand.xml"))

    def test_tables_with_the_dispatcher_system_parked_are_refused_by_repair_and_skipped_by_main(self) -> None:
        with self.assertRaisesRegex(ValueError, "Dispatcher System is parked"):
            polish.repair(paths.REPO_TABLES_XML, check=True)
        for argv in (["--check"], []):
            with self.subTest(argv=argv), mock.patch.object(polish.paths, "exit_if_overridden"), \
                    mock.patch.object(polish.tables.Tables, "save", side_effect=AssertionError("written")), \
                    mock.patch.object(sys, "argv", ["polish", "--panel", str(paths.REPO_TABLES_XML), *argv]), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(0, polish.main())
            self.assertIn("SKIPPED: the Dispatcher System is parked", out.getvalue())

    def test_a_doubled_marker_stops(self) -> None:
        root = copy.deepcopy(FIXTURE)
        tables.layout_editor(root).append(tables.generated_marker_label())
        with self.assertRaisesRegex(ValueError, "2 generated-panel markers"):
            polish.repair(write(root, self.dir), check=True)

    def test_main_reports_a_refusal_and_a_failed_save_as_failures(self) -> None:
        path = write(FIXTURE, self.dir)
        hand = write(self.unmarked(), self.dir, "hand.xml")
        for argv, said in ((["--panel", str(path), "--check", "--reference", str(hand)], "not a generated one"),
                           (["--panel", str(hand), "--check"], "not a generated one")):
            with self.subTest(said=said), mock.patch.object(sys, "argv", ["polish", *argv]), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(1, polish.main())
            self.assertIn(said, out.getvalue())
        broken = write(stage1_scramble(FIXTURE), self.dir, "scrambled.xml")
        with mock.patch.object(polish.tables.Tables, "save", side_effect=RuntimeError("save refused")), \
                mock.patch.object(polish.paths, "exit_if_overridden"), \
                mock.patch.object(sys, "argv", ["polish", "--panel", str(broken)]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(1, polish.main())
        self.assertIn("not changed: save refused", out.getvalue())


class Lamps(unittest.TestCase):
    def lamp_fixture(self) -> ET.Element:
        return ET.fromstring(
            "<layout-config><blocks>"
            '<block systemName="IB1" length="1"><userName>OS Switch 3</userName><occupancysensor>BS Switch 3</occupancysensor></block>'
            '<block systemName="IB2" length="1"><userName>Track T-1</userName><occupancysensor>BS T-1</occupancysensor></block>'
            '<block systemName="IB3" length="1"><userName>Track T-1 West</userName><occupancysensor>BS T-1</occupancysensor></block>'
            "</blocks>"
            '<LayoutEditor name="HART Railroad">'
            '<layoutturnout ident="T3" blockname="OS Switch 3" blocknameb="Track T-1" xcen="250" ycen="252" xa="240" ya="252" xb="260" yb="252" />'
            '<positionablepoint ident="P1" x="100" y="200" /><positionablepoint ident="P2" x="300" y="200" />'
            '<positionablepoint ident="P3" x="300" y="200" /><positionablepoint ident="P4" x="320" y="200" />'
            '<tracksegment ident="S1" blockname="Track T-1" connect1name="P1" type1="POS_POINT" connect2name="P2" type2="POS_POINT" />'
            '<tracksegment ident="S2" blockname="Track T-1 West" connect1name="P3" type1="POS_POINT" connect2name="P4" type2="POS_POINT" />'
            '<tracksegment ident="S3" blockname="Track T-1 West" connect1name="P1" type1="POS_POINT" connect2name="P4" type2="POS_POINT" hidden="yes" />'
            "</LayoutEditor></layout-config>"
        )

    def test_targets_use_turnout_block_and_skip_throats(self) -> None:
        root = self.lamp_fixture()
        targets = polish.computed_lamp_targets(root, root.find("LayoutEditor"))
        self.assertEqual((245, 247), targets["BS Switch 3"])  # circle centre minus half a lamp
        self.assertEqual((195, 195), targets["BS T-1"])  # middle of S1, not the throat

    def test_curve_only_track_uses_its_straight_throat(self) -> None:
        root = self.lamp_fixture()
        le = root.find("LayoutEditor")
        next(t for t in le.findall("tracksegment") if t.get("ident") == "S1").set("arc", "yes")
        self.assertEqual((305, 195), polish.computed_lamp_targets(root, le)["BS T-1"])  # middle of throat S2

    def test_missing_switch_lamp_is_created_on_its_circle_before_the_turnouts(self) -> None:
        root = self.lamp_fixture()
        le = root.find("LayoutEditor")
        targets = polish.computed_lamp_targets(root, le)
        polish.ensure_os_occupancy_icons(le, check=False, targets=targets)
        lamp = [i for i in le.findall("sensoricon") if i.get("sensor") == "BS Switch 3"]
        self.assertEqual([("245", "247", "true")], [(i.get("x"), i.get("y"), i.get("forcecontroloff")) for i in lamp])
        self.assertEqual("sensoricon", le[0].tag)
        # the switch OS lamps without a target are named
        _n, errors = polish.ensure_os_occupancy_icons(ET.Element("LayoutEditor"), check=False, targets={})
        self.assertIn("no target for missing OS occupancy icon 'BS Switch 3'", errors)

    def test_copy_already_on_target_is_the_one_kept(self) -> None:
        le = ET.fromstring(
            '<LayoutEditor><sensoricon sensor="BS K-1" x="1" y="1" level="10" />'
            '<sensoricon sensor="BS K-1" x="195" y="195" level="10" />'
            '<sensoricon sensor="BS K-1" x="943" y="354" level="12" /></LayoutEditor>'
        )
        polish.place_stage1_lamps(le, check=False, targets={"BS K-1": (195, 195)})
        self.assertEqual([("195", "195", "10"), ("943", "354", "12")],
                         [(i.get("x"), i.get("y"), i.get("level")) for i in le.findall("sensoricon")])


if __name__ == "__main__":
    unittest.main()
