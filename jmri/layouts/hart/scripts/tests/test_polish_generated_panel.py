"""polish_hart_layout_editor.py on a generated Layout Editor panel (LE cut-over, Phase 3).

A generated panel holds the hidden marker label (hartlib.tables.GENERATED_PANEL_MARKER). There the hand-drawn
panel's pixel tables do not apply: positions come from the panel itself, or from --reference (the tables before
Stage 1). The fixture is the live tables with the marker added, so "positions from the panel" must leave it as is.
"""
from __future__ import annotations

import contextlib
import copy
import io
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import paths, tables  # noqa: E402

from test_polish_hart_layout_editor import polish  # noqa: E402

LIVE = paths.REPO_TABLES_XML


def marked(root: ET.Element) -> ET.Element:
    """`root` with the generated-panel marker added to its main panel."""
    root = copy.deepcopy(root)
    tables.layout_editor(root).insert(1, tables.generated_marker_label())
    return root


def write(root: ET.Element, folder: Path, name: str = "tables.xml") -> Path:
    path = folder / name
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    return path


def stage1_scramble(root: ET.Element) -> ET.Element:
    """What a Stage 1 Store does to the panel's lamps and train-name labels: deletes them and adds its own copies
    at its own spots (here: all moved 37 px right and down, and one lamp doubled)."""
    root = copy.deepcopy(root)
    le = tables.layout_editor(root)
    lamps = [i for i in le.findall("sensoricon") if polish._is_circuit_lamp(i) and i.get("level") != "12"]
    for icon in lamps + le.findall("BlockContentsIcon"):
        icon.set("x", str(int(float(icon.get("x"))) + 37))
        icon.set("y", str(int(float(icon.get("y"))) + 37))
    le.append(copy.deepcopy(lamps[0]))
    for icon in le.findall("BlockContentsIcon"):
        icon.set("level", "0")
    return root


def spots(root: ET.Element) -> list[tuple]:
    le = tables.layout_editor(root)
    return sorted((el.tag, el.get("sensor") or el.get("blockcontents") or el.get("text") or el.get("signalmast")
                   or "", el.get("x") or "", el.get("y") or "", el.get("level") or "")
                  for el in le if el.tag in {"sensoricon", "BlockContentsIcon", "positionablelabel",
                                             "signalmasticon"})


def run(fn, path: Path, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn(path, **kw)
    return result, out.getvalue()


class GeneratedPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.live = tables.read(LIVE)
        cls.gen = marked(cls.live)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_marker_is_found_and_the_live_panel_is_hand_drawn(self) -> None:
        self.assertFalse(tables.generated_panel(tables.layout_editor(self.live)))
        self.assertTrue(tables.generated_panel(tables.layout_editor(self.gen)))
        self.assertIs(polish.find_layout_editor(self.gen), tables.layout_editor(self.gen))

    def test_every_mode_checks_clean_and_writes_nothing_on_a_generated_panel(self) -> None:
        path = write(self.gen, self.dir)
        before = path.read_bytes()
        for fn in (polish.apply_visual_standard, polish.apply_overlap_cleanup, polish.apply_block_labels_only):
            (_n, errors), _ = run(fn, path, check=True)
            self.assertEqual([], errors, fn.__name__)
            run(fn, path, check=False)
        self.assertEqual(spots(self.gen), spots(tables.read(path)))
        self.assertEqual(ET.tostring(tables.layout_editor(tables.read(path))),
                         ET.tostring(tables.layout_editor(tables.loads(before).root)))

    def test_hand_pixels_are_not_enforced_on_a_generated_panel(self) -> None:
        root = copy.deepcopy(self.gen)
        le = tables.layout_editor(root)
        moved = {"signalmasticon": "Mast 2L", "positionablepoint": "A55", "positionablelabel": "Track S-1"}
        for icon in le.findall("signalmasticon"):
            if icon.get("signalmast") == moved["signalmasticon"]:
                icon.set("x", "900")
        for point in le.findall("positionablepoint"):
            if point.get("ident") == moved["positionablepoint"]:
                point.set("x", "1700.0")
        for label in le.findall("positionablelabel"):
            if label.get("text") == moved["positionablelabel"]:
                label.set("x", "10")
        path = write(root, self.dir)
        for fn in (polish.apply_visual_standard, polish.apply_overlap_cleanup):
            (_n, errors), _ = run(fn, path, check=True)
            self.assertEqual([], errors, fn.__name__)
        run(polish.apply_visual_standard, path, check=False)
        run(polish.apply_overlap_cleanup, path, check=False)
        self.assertEqual(spots(root), spots(tables.read(path)))
        # the same edits on the hand-drawn panel are errors, as before
        hand = copy.deepcopy(root)
        lab = tables.layout_editor(hand).find(f"positionablelabel[@text='{tables.GENERATED_PANEL_MARKER}']")
        tables.layout_editor(hand).remove(lab)
        (_n, errors), _ = run(polish.apply_visual_standard, write(hand, self.dir, "hand.xml"), check=True)
        self.assertTrue(any("Mast 2L" in e for e in errors))
        self.assertTrue(any("A55" in e for e in errors))

    def test_reference_puts_stage1_lamps_and_labels_back(self) -> None:
        reference = write(self.gen, self.dir, "before.xml")
        after = stage1_scramble(self.gen)
        path = write(after, self.dir)
        (_n, errors), _ = run(polish.apply_overlap_cleanup, path, check=True, reference=reference)
        self.assertTrue(errors)
        run(polish.apply_visual_standard, path, check=False, reference=reference)
        run(polish.apply_overlap_cleanup, path, check=False, reference=reference)
        self.assertEqual(spots(self.gen), spots(tables.read(path)))

    def test_without_reference_a_lamp_is_kept_where_it_stands(self) -> None:
        root = stage1_scramble(self.gen)
        le = tables.layout_editor(root)
        le.remove(le[-1])          # no doubled lamp: every sensor has one lamp, at Stage 1's spot
        path = write(root, self.dir)
        (_n, errors), _ = run(polish.apply_block_labels_only, path, check=True)
        self.assertEqual([], [e for e in errors if "Stage 1 lamp" in e or "expected (" in e])

    def test_a_doubled_lamp_with_no_reference_goes_to_its_computed_spot_with_a_note(self) -> None:
        root = copy.deepcopy(self.gen)
        le = tables.layout_editor(root)
        lamp = next(i for i in le.findall("sensoricon")
                    if i.get("sensor") == "BS Switch 21" and polish._is_circuit_lamp(i))
        le.append(copy.deepcopy(lamp))
        path = write(root, self.dir)
        (_n, _errors), out = run(polish.apply_overlap_cleanup, path, check=False)
        self.assertIn("lamp BS Switch 21: 2 on the panel", out)
        target = polish.stage1_lamp_targets(root, le, fixed=False)["BS Switch 21"]
        kept = [i for i in tables.layout_editor(tables.read(path)).findall("sensoricon")
                if i.get("sensor") == "BS Switch 21" and polish._is_circuit_lamp(i)]
        self.assertEqual([(str(target[0]), str(target[1]))], [(i.get("x"), i.get("y")) for i in kept])

    def test_a_hand_drawn_reference_is_refused_for_a_generated_panel(self) -> None:
        path = write(self.gen, self.dir)
        with self.assertRaisesRegex(ValueError, "not a generated one"):
            run(polish.apply_block_labels_only, path, check=True, reference=LIVE)

    def test_a_reference_on_the_hand_drawn_panel_is_noted_and_changes_nothing(self) -> None:
        path = write(self.live, self.dir)
        (_n, errors), out = run(polish.apply_visual_standard, path, check=True, reference=write(self.gen, self.dir,
                                                                                                "ref.xml"))
        self.assertEqual([], errors)
        self.assertIn("--reference not used", out)

    def test_a_doubled_marker_stops_with_a_clear_error(self) -> None:
        root = marked(self.gen)
        with self.assertRaisesRegex(ValueError, "2 generated-panel markers"):
            tables.generated_panel(tables.layout_editor(root))

    def test_a_track_named_like_a_caption_keeps_its_own_style(self) -> None:
        root = copy.deepcopy(self.gen)
        le = tables.layout_editor(root)
        track = copy.deepcopy(next(l for l in le.findall("positionablelabel") if l.get("text") == "Barn"))
        track.set("size", "10")
        track.set("style", "0")
        le.append(track)
        path = write(root, self.dir)
        (_n, errors), _ = run(polish.apply_visual_standard, path, check=True)
        self.assertEqual([], errors)
        # with no styled caption at all, two "Barn" labels are an error, not a guess
        for label in le.findall("positionablelabel"):
            if label.get("text") == "Barn":
                label.set("size", "10")
        (_n, errors), _ = run(polish.apply_visual_standard, write(root, self.dir, "two.xml"), check=True)
        self.assertTrue(any("none has the caption style" in e for e in errors))

    def test_main_reports_a_bad_reference_as_a_failure(self) -> None:
        path = write(self.gen, self.dir)
        argv = sys.argv
        sys.argv = ["polish", "--panel", str(path), "--check", "--reference", str(LIVE)]
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = polish.main()
        finally:
            sys.argv = argv
        self.assertEqual(1, rc)
        self.assertIn("not a generated one", out.getvalue())


if __name__ == "__main__":
    unittest.main()
