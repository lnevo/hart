"""USS CTC signal icons and the generator that draws them
must follow the masts and heads in tables.xml and the CATS desk."""
from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[3]
TABLES = SCRIPTS.parent / "output" / "tables.xml"
GUI = SCRIPTS.parent / "ctc" / "GUIObjects.xml"
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import parked  # noqa: E402

# the tables with the USS CTC machine put back while it is parked (hartlib.parked): its panel and code buttons stay
# checked against the active masts and heads in the parked file
USS_TABLES = parked.with_parked_file({"uss"}, TABLES)

# the live CATS desks (generated from the schematic): each USS mast icon is drawn as its desk lamp is
DESKS = (ROOT / "cats/panels/HART_CTC.xml", ROOT / "cats/panels/HART_ABS.xml")

sys.path.insert(0, str(SCRIPTS))
import gen_ctc_track_plan as gen  # noqa: E402


def mast_heads() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for el in ET.parse(TABLES).getroot().iter("signalmast"):
        sn = el.findtext("systemName") or ""
        if sn.startswith("IF$shsm:"):
            out[el.findtext("userName")] = re.findall(r"IH\d+", sn)
    return out


def head_icons(path: Path) -> set[tuple[str, str, str]]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r'<signalheadicon signalhead="(IH\d+)" x="(\d+)" y="(\d+)"', text))


def signal_icons(path: Path) -> set[tuple[str, str, str, str]]:
    text = path.read_text(encoding="utf-8")
    pe = re.search(r"<paneleditor\b.*?</paneleditor>", text, re.S).group(0)
    out = set()
    for kind, name, x, y in re.findall(
        r'<signal(mast|head)icon signal(?:mast|head)="([^"]+)" x="(\d+)" y="(\d+)"', pe
    ):
        out.add((kind, name, x, y))
    return out


def desk_lamps(desk: Path) -> dict[str, tuple[str, str | None]]:
    """Mast -> (kind, facing) of its lamp on a live desk: LAMP2 draws as h2, LAMP1 as d1; SIGORIENT RIGHT faces E,
    LEFT W (None for the TOP/BOTTOM lamps on diagonals)."""
    out = {}
    for sig in ET.parse(desk).getroot().iter("SECSIGNAL"):
        pan = sig.find("PANELSIGNAL")
        orient = pan.get("SIGORIENT")
        out[(sig.text or "").strip()] = ("h2" if pan.get("SIGPANTYPE") == "LAMP2" else "d1",
                                         {"RIGHT": "E", "LEFT": "W"}.get(orient))
    return out


class CtcSignalHeadsTest(unittest.TestCase):
    def test_icon_kind_follows_mast_head_count(self) -> None:
        """d1 (head icon) only for one-head masts, on that head; h2 (mast icon) only for two-head masts."""
        self.skipTest("USS CTC is parked (hartlib.parked); its SIGNALS predate the ADR-024 staging masts "
                      "(Mast 67/68, head counts, 8L/40L letters) and are redrawn on unpark")
        masts = mast_heads()
        for mast, _x, _y, _facing, kind, head in gen.SIGNALS:
            with self.subTest(mast=mast):
                self.assertIn(mast, masts)
                heads = masts[mast]
                if kind == "d1":
                    self.assertEqual(len(heads), 1, "d1 drawn for a two-head mast")
                    self.assertEqual(head, heads[0])
                else:
                    self.assertEqual(kind, "h2")
                    self.assertEqual(len(heads), 2, "h2 drawn for a one-head mast")
                    self.assertIsNone(head)

    def test_icons_sit_on_board_track_cells(self) -> None:
        cells = gen.facts.load_uss_cells()
        for mast, x, y, _facing, _kind, _head in gen.SIGNALS:
            with self.subTest(mast=mast):
                self.assertIn((x, y), cells)
                self.assertTrue(cells[(x, y)]["tracks"], "the icon's cell holds no track")

    def test_icons_are_drawn_and_face_as_on_the_live_desks(self) -> None:
        self.skipTest("USS CTC is parked (hartlib.parked); its SIGNALS predate the ADR-024 staging masts "
                      "(Mast 67/68, head counts, 8L/40L letters) and are redrawn on unpark")
        for desk in DESKS:
            lamps = desk_lamps(desk)
            for mast, _x, _y, face, kind, _head in gen.SIGNALS:
                with self.subTest(desk=desk.name, mast=mast):
                    self.assertIn(mast, lamps)
                    desk_kind, desk_face = lamps[mast]
                    self.assertEqual(kind, desk_kind)
                    if desk_face is not None:
                        self.assertEqual(face, desk_face)

    def test_gui_objects_head_icons_match_tables(self) -> None:
        tables = head_icons(USS_TABLES)
        gui = head_icons(GUI)
        self.assertEqual(gui, {i for i in tables if i[0] != "IH9990"})

    def test_uss_signal_icons_match_generator(self) -> None:
        """Both copies of the USS panel carry exactly the icons SIGNALS describes."""
        want = set()
        for mast, cx, cy, facing, kind, head in gen.SIGNALS:
            x, y = gen.signal_pos(cx, cy, facing, kind)
            want.add(("mast", mast, str(x), str(y)) if kind == "h2" else ("head", head, str(x), str(y)))
        self.assertEqual(signal_icons(GUI), want)
        self.assertEqual(signal_icons(USS_TABLES), want)


def uss_panel(path: Path) -> str:
    return re.search(r"<paneleditor\b.*?</paneleditor>", path.read_text(encoding="utf-8"), re.S).group(0)


def track_lamps(pe: str) -> list[tuple[str, tuple[int, int, int, int], int]]:
    """Every sensor icon on the track diagram (above the lever machine), any name."""
    out = []
    for name, x, y, level in re.findall(
        r'<sensoricon sensor="([^"]+)" x="(-?\d+)" y="(-?\d+)" level="(\d+)"', pe
    ):
        if int(y) < gen.OS_Y - 5:
            out.append((name, (int(x), int(y), gen.JEWEL, gen.JEWEL), int(level)))
    return out


class SignalVisibilityTest(unittest.TestCase):
    def test_every_signal_icon_is_visible(self) -> None:
        """No lamp drawn at or above a signal's level covers it, in either panel copy."""
        for path in (GUI, USS_TABLES):
            pe = uss_panel(path)
            levels = [int(v) for v in re.findall(r'<signal(?:mast|head)icon [^>]*level="(\d+)"', pe)]
            self.assertEqual(len(levels), len(gen.SIGNALS), path.name)
            for sensor, rect, level in track_lamps(pe):
                for sig in gen.signal_rects():
                    if gen._overlaps(rect, sig):
                        with self.subTest(panel=path.name, sensor=sensor, signal=sig):
                            self.assertLess(level, min(levels))

    def test_jewels_clear_the_points(self) -> None:
        # Neighbouring jewels may touch (the +-6 px OS nudge); points icons stay clear.
        points = gen.points_rects()
        for name, rect, _level in track_lamps(uss_panel(GUI)):
            for pt in points:
                with self.subTest(jewel=name, points=pt):
                    self.assertFalse(gen._overlaps(rect, pt))

    def test_only_the_tight_plants_keep_a_signal_over_a_jewel(self) -> None:
        """Where an OS has room, the placer clears the signal; these three have none."""
        covered = set()
        for sensor, rect, _level in track_lamps(uss_panel(GUI)):
            if any(gen._overlaps(rect, s) for s in gen.signal_rects()):
                covered.add(sensor)
        self.assertEqual(covered, {"BS Switch 7", "BS Switch 23a", "BS Switch 33"})

    def test_icon_sizes_match_the_images(self) -> None:
        raw = (SCRIPTS.parent / "ctc/icons/sig-d1-stop.gif").read_bytes()
        head = (int.from_bytes(raw[6:8], "little"), int.from_bytes(raw[8:10], "little"))
        self.assertEqual(head, gen.HEAD_ICON)
        raw = (SCRIPTS.parent / "ctc/icons/pts-closed.gif").read_bytes()
        self.assertEqual((raw[6], raw[8]), gen.POINTS_ICON)
        # Basic two-searchlight images are 12x40 (JMRI AAR-1946 SL-2-high-abs) at the MAST scale.
        scale = float(re.search(r'scale="([\d.]+)"', gen.MAST).group(1))
        self.assertEqual(gen.MAST_ICON, (round(12 * scale), round(40 * scale)))


class GeneratorTest(unittest.TestCase):
    def test_apply_is_idempotent(self) -> None:
        """A second regen strips what the first drew (occupancy jewels are BS sensors)."""
        cells = gen.facts.load_uss_cells()
        text = GUI.read_text(encoding="utf-8")
        once = gen.apply(text, cells)
        self.assertEqual(gen.apply(once, cells), once)
        self.assertEqual(once.count('<sensoricon sensor="BS Barn"'), 1)

    def test_brick_sidi_patch_keeps_tables(self) -> None:
        """Switch 1 (Mast 2L) codes from R and Switch 3 (4RA/4RB) from L, as stored."""
        text = USS_TABLES.read_text(encoding="utf-8")
        self.assertEqual(gen.patch_brick_sidi(text), text)



if __name__ == "__main__":
    unittest.main()
