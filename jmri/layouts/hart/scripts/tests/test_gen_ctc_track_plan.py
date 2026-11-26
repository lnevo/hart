"""gen_ctc_track_plan (the USS CTC board generator): golden outputs and unit tests on its pieces and error paths.

Who uses it: the USS CTC machine is parked (hartlib.parked), so nothing live runs it as a build step. The one live
caller is tools/audit/check_layout_facts.py (in tools/check.sh), which imports it for build_geometry() and CREAM.
The other callers are tests: test_uss_switch_levers.py (rebuild of the committed files, byte-identical),
test_ctc_signal_heads.py, test_uss_board_cells.py, parked/tests/test_occupancy_lamps_display_only.py, and
cats/scripts/tests/test_generated_desk_from_scratch.py (runs it with --xml-only and expects the files unchanged).
check_bean_comments.py only lists the file as a path it edits. These tests cover the importer's parts and the rest
of the generator, so it keeps working until the machine is unparked.

The input is a small fixture, not the live board: the module's data tables (PLANTS, SIGNALS, the lever columns) are
patched for each test, and the writes go into temp dirs, so a change to switches.csv, mast_cells.csv or the frozen
board grid does not move these tests. (The live data is held by test_uss_switch_levers, test_ctc_signal_heads and
test_uss_board_cells, including a rebuild of the committed files that must be byte-identical.)

The golden file golden/gen_ctc_track_plan.json holds what the generator writes for the fixture today: the board's
XML block, line by line, and a pixel digest of each icon GIF it draws. Refresh it after an intended change to the
script with
`UPDATE_GOLDEN=1 python3 -m unittest discover -s jmri/layouts/hart/scripts/tests -p test_gen_ctc_track_plan.py`
and read the diff before committing it.

The board's geometry, jewel, panel-edit, apply and lever tests are in test_gen_ctc_track_plan_board.py (split for
size, 2026-11-26), which imports the fixture board from here.

Not covered: render_preview's drawing (only that it writes a PNG of the right size); it needs a JMRI install for its
icons and fonts.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import gen_ctc_track_plan as gen  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden/gen_ctc_track_plan.json"

# The generator leaves the icon GIFs it opens with PIL unclosed, so each test run printed a ResourceWarning per
# icon. It serves the parked USS CTC machine: the fix waits for its wake-up (docs/parked/UNPARK.md), and only these
# GIF warnings are hidden, for this module's tests only.
_QUIET = warnings.catch_warnings()


def setUpModule() -> None:
    _QUIET.__enter__()
    warnings.filterwarnings("ignore", r"unclosed file <_io\.BufferedReader name='[^']*\.gif'>", ResourceWarning)


def tearDownModule() -> None:
    _QUIET.__exit__(None, None, None)

# the fixture board: three lever slots (slot 1 has no switch: a blank plate; slot 2 has no signal levers), one
# plant (Switch 1 on OS Switch 1) and two signals
FIXTURE_COLUMNS = dict(
    N_SLOTS=3,
    BLANK_SLOTS={1},
    SWITCH_ONLY_SLOTS={2},
    SLOT_SW_NUM={0: 1, 2: 5},
    SLOT_LOCK_UID={0: 2, 2: 6},
    UID_SLOT={1: 0, 2: 0, 5: 2, 6: 2},
    PLANTS={(4, 7): ("Switch 1", False)},
    OS_FROG={"OS Switch 1": (4, 7)},
    SIGNALS=[("Mast 1", 3, 7, "E", "h2", None), ("Mast 2", 2, 6, "W", "d1", "IH9")],
    STATION_NAMES={"BRICK"},
)
FIXTURE_CELLS = {
    (1, 6): dict(tracks=["HORIZONTAL"], name="Track A", blocks=[("LEFT", "Track A", "BS A")]),
    (2, 6): dict(tracks=["HORIZONTAL", "UPPERSLASH"], name=None, blocks=[("RIGHT", "Track A", "BS A")]),
    (3, 7): dict(tracks=["HORIZONTAL"], name=None, blocks=[("LEFT", "OS Switch 1", "BS OS 1")]),
    (4, 7): dict(tracks=["HORIZONTAL", "LOWERBACKSLASH"], name=None, blocks=[("RIGHT", "OS Switch 1", "BS OS 1")]),
    (5, 8): dict(tracks=["VERTICAL"], name="Track B, PA", blocks=[("TOP", "Track B", "BS B")]),
    (6, 2): dict(tracks=[], name="BRICK", blocks=[]),
    (7, 2): dict(tracks=[], name="DS-CTC  Rev A  Eff 2026-11-12", blocks=[]),
    (8, 9): dict(tracks=["HORIZONTAL"], name="Track Main East", blocks=[]),
    (1, 20): dict(tracks=["HORIZONTAL"], name=None, blocks=[("RIGHT", "Track Far", "BS Far")]),  # off the board rows
}


def fixture_board():
    """Patch the module's board data to the fixture; use as a context manager."""
    stack = contextlib.ExitStack()
    for name, value in FIXTURE_COLUMNS.items():
        stack.enter_context(mock.patch.object(gen, name, value))
    return stack


def sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:12]


def icon_digest(folder: Path) -> dict:
    """File name -> size and a hash of the decoded pixels (so it does not depend on the GIF encoder's bytes)."""
    from PIL import Image
    out = {}
    for p in sorted(folder.glob("*.gif")):
        with Image.open(p) as raw:
            im = raw.convert("RGBA")
        out[p.name] = dict(size=list(im.size), pixels=sha(im.tobytes()))
    return out


def written_icons(folder: Path) -> dict:
    """write_cell_icons into folder, with no JMRI install to copy stock icons from."""
    with mock.patch.object(gen, "THIN_DIR", folder), mock.patch.object(gen, "JMRI_RES", folder / "no-jmri"):
        gen.write_cell_icons()
    return icon_digest(folder)


def current_golden() -> dict:
    with fixture_board():
        block = gen.build_block(FIXTURE_CELLS)
    with tempfile.TemporaryDirectory() as t:
        icons = written_icons(Path(t))
    return dict(block=block.split("\n"), icons=icons)


class Golden(unittest.TestCase):
    def test_board_block_and_icons_match_the_golden_snapshot(self):
        got = current_golden()
        if os.environ.get("UPDATE_GOLDEN") == "1":
            GOLDEN.parent.mkdir(exist_ok=True)
            GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            self.skipTest(f"UPDATE_GOLDEN set: wrote {GOLDEN}")
        self.assertTrue(GOLDEN.is_file(), f"{GOLDEN} is missing: UPDATE_GOLDEN=1 writes it")
        want = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(got["icons"], want["icons"],
                         "an icon GIF differs from the golden snapshot (UPDATE_GOLDEN=1 refreshes it after an intended change)")
        bad = [i + 1 for i, (a, b) in enumerate(zip(got["block"], want["block"])) if a != b]
        self.assertFalse(bad, f"board XML lines differ from the golden snapshot: {bad[:10]} "
                              f"(UPDATE_GOLDEN=1 refreshes it after an intended change)")
        self.assertEqual(len(got["block"]), len(want["block"]), "the board XML has a different number of lines")

    def test_block_has_the_expected_parts(self):
        with fixture_board():
            block = gen.build_block(FIXTURE_CELLS)
        counts = {tag: len(re.findall(rf"<{tag}\b", block))
                  for tag in ("turnouticon", "sensoricon", "signalmasticon", "signalheadicon", "multisensoricon")}
        # one turnout dot; the signals draw one mast and one head icon
        self.assertEqual(counts["turnouticon"], 1)
        self.assertEqual(counts["signalmasticon"], 1)
        self.assertEqual(counts["signalheadicon"], 1)
        # the blank slot 1 has no levers: only slots 0 and 2 get a lock toggle
        self.assertEqual(sorted(re.findall(r'sensor="IS(\d+):LOCKTOGGLE"', block)), ["2", "6"])
        # slot 2 is switch-only: its signal plate (6) is not drawn, the switch plate (5) is
        self.assertIn('text="5"', block)
        self.assertNotIn('text="6"', block)
        self.assertIn('text="1"', block)
        self.assertIn('text="2"', block)

    def test_icons_are_written_for_every_cell_kind(self):
        with tempfile.TemporaryDirectory() as t:
            names = set(written_icons(Path(t)))
        self.assertEqual(names, {"cell-us.gif", "cell-ls.gif", "cell-ub.gif", "cell-lb.gif", "stock-h.gif",
                                 "stock-v.gif", "stock-end.gif", "pts-closed.gif", "pts-thrown.gif",
                                 "pts-unknown.gif", "pts-inconsistent.gif"})


class Icons(unittest.TestCase):
    def test_resolve_icon(self):
        self.assertEqual(gen.resolve_icon("program:resources/icons/a.gif"), gen.JMRI_RES / "icons/a.gif")
        self.assertEqual(gen.resolve_icon("preference:ctc/icons/pts-closed.gif"), gen.THIN_DIR / "pts-closed.gif")
        self.assertIsNone(gen.resolve_icon("http://x/a.gif"))

    def test_stock_icons_are_cut_from_the_jmri_install_when_it_is_there(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            res = Path(t) / "res"
            block = res / "icons/USS/track/block"
            block.mkdir(parents=True)
            line = Image.new("RGBA", (24, 8), (0, 0, 0, 255))        # black background is punched out
            line.paste((255, 255, 255, 255), (0, 2, 24, 5))
            line.save(block / "line025.gif")
            Image.new("RGBA", (26, 16), (255, 255, 255, 255)).save(block / "eotwht.gif")
            out = Path(t) / "out"
            with mock.patch.object(gen, "THIN_DIR", out), mock.patch.object(gen, "JMRI_RES", res):
                gen.write_cell_icons()
            with Image.open(out / "stock-h.gif") as raw:
                h = raw.convert("RGBA")
            self.assertEqual(h.size, (24, 8))
            self.assertEqual(h.getpixel((5, 0))[3], 0)               # background transparent
            self.assertEqual(h.getpixel((5, 3))[3], 255)             # the white bar stays
            for name, size in (("stock-v.gif", (8, 24)), ("stock-end.gif", (26, 16))):
                with Image.open(out / name) as im:
                    self.assertEqual(im.size, size, name)

    def test_save_gif_maps_colours_to_the_palette(self):
        from PIL import Image
        im = Image.new("RGBA", (4, 1), (0, 0, 0, 0))
        for x, rgba in enumerate([(255, 255, 255, 255), (255, 170, 40, 255), (255, 40, 40, 255)], start=1):
            im.putpixel((x, 0), rgba)
        with tempfile.TemporaryDirectory() as t:
            gen._save_gif(im, Path(t) / "a.gif")
            with Image.open(Path(t) / "a.gif") as back:
                back = back.convert("RGBA")
                got = [back.getpixel((x, 0)) for x in range(4)]
        self.assertEqual(got[0][3], 0, "pixel 0 is transparent")
        self.assertEqual(got[1:], [(255, 255, 255, 255), (255, 170, 40, 255), (255, 40, 40, 255)])

    def test_install_preference_icons_copies_into_user_files_and_profiles(self):
        with tempfile.TemporaryDirectory() as t:
            home = Path(t) / "home"
            thin = Path(t) / "thin"
            gui = Path(t) / "GUIObjects.xml"
            thin.mkdir()
            (thin / "a.gif").write_bytes(b"GIF-A")
            gui.write_bytes(b"<gui/>")
            (home / "JMRI_UserFiles" / "x.jmri").mkdir(parents=True)
            with mock.patch.object(Path, "home", return_value=home), \
                    mock.patch.object(gen, "THIN_DIR", thin), mock.patch.object(gen, "GUI_XML", gui):
                written = gen.install_preference_icons()
            base = home / "JMRI_UserFiles"
            self.assertEqual(sorted(written), sorted([base / "ctc/icons/a.gif", base / "ctc/GUIObjects.xml",
                                                      base / "x.jmri/ctc/icons/a.gif",
                                                      base / "x.jmri/ctc/GUIObjects.xml"]))
            self.assertEqual((base / "ctc/icons/a.gif").read_bytes(), b"GIF-A")
            self.assertEqual((base / "x.jmri/ctc/GUIObjects.xml").read_bytes(), b"<gui/>")

    def test_install_preference_icons_with_nothing_to_copy_or_nowhere_to_copy(self):
        with tempfile.TemporaryDirectory() as t:
            home, thin = Path(t) / "home", Path(t) / "thin"
            thin.mkdir()
            with mock.patch.object(Path, "home", return_value=home), mock.patch.object(gen, "THIN_DIR", thin):
                self.assertEqual(gen.install_preference_icons(), [])          # no JMRI_UserFiles
                (home / "JMRI_UserFiles").mkdir(parents=True)
                self.assertEqual(gen.install_preference_icons(), [])          # no GIFs
                self.assertFalse((home / "JMRI_UserFiles/ctc").exists())

    def test_render_preview_writes_a_png_at_double_scale(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "sub" / "p.png"
            with mock.patch.object(gen, "JMRI_RES", Path(t) / "no-jmri"), \
                    mock.patch.object(gen, "THIN_DIR", Path(t) / "no-thin"), \
                    contextlib.redirect_stdout(io.StringIO()) as printed:
                gen.render_preview('<sensoricon sensor="IS1:LEVER" x="1" y="2"/>', out)
            with Image.open(out) as png:
                self.assertEqual(png.size, (gen.PANEL_W * 2, 560 * 2))
            self.assertIn("preview", printed.getvalue())


class Main(unittest.TestCase):
    """main() on temp copies: the arguments, the refusals and what it writes."""

    GUI_TEXT = '<layout>\n  <paneleditor name="USS CTC" x="1" y="1" height="1" width="1">\n  </paneleditor>\n</layout>\n'
    TABLES_TEXT = ('<tables>\n<other/>\n  <paneleditor name="USS CTC" x="1" y="1" height="1" width="1">\n'
                   '  </paneleditor>\n</tables>\n')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.gui = self.dir / "GUIObjects.xml"
        self.tables = self.dir / "tables.xml"
        self.gui.write_text(self.GUI_TEXT, encoding="utf-8")
        self.tables.write_text(self.TABLES_TEXT, encoding="utf-8")
        repo_before = gen.OUTPUT_TABLES.read_bytes()
        self.addCleanup(lambda: self.assertEqual(gen.OUTPUT_TABLES.read_bytes(), repo_before,
                                                 "a test changed the repo's tables.xml"))

    def run_main(self, *argv, running=False, cells=None, **patches):
        with contextlib.ExitStack() as stack:
            stack.enter_context(fixture_board())
            stack.enter_context(mock.patch.object(sys, "argv", ["gen_ctc_track_plan.py", *argv]))
            stack.enter_context(mock.patch.object(gen.hl_tables, "jmri_running", return_value=running))
            stack.enter_context(mock.patch.object(gen.facts, "load_uss_cells", return_value=FIXTURE_CELLS if cells is None else cells))
            stack.enter_context(mock.patch.object(gen, "ensure_columns", side_effect=lambda t: t))
            # whatever PARKED says, a run without --tables must land on the temp copy, never the repo's tables.xml
            patches.setdefault("OUTPUT_TABLES", self.tables)
            patches.setdefault("parked_target", lambda p: False)
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(gen, name, value))
            out = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            gen.main()
        return out.getvalue()

    def test_xml_only_rewrites_the_gui_and_the_tables_panel(self):
        out = self.run_main("--xml-only", "--gui", str(self.gui), "--tables", str(self.tables),
                            parked_target=lambda p: False)
        for path in (self.gui, self.tables):
            text = path.read_text(encoding="utf-8")
            self.assertIn("Panel-left-7.gif", text, path)
            self.assertIn('<turnouticon turnout="Switch 1"', text, path)
        self.assertIn("<other/>", self.tables.read_text(encoding="utf-8"))      # outside the panel untouched
        self.assertIn('editable="false"', self.tables.read_text(encoding="utf-8"))     # the Store's form
        self.assertIn('editable="true"', self.gui.read_text(encoding="utf-8"))         # the generator's own form
        self.assertIn(f"{self.gui}: Digicon track plan regenerated", out)
        self.assertIn("paneleditor replaced, Brick SIDI updated", out)

    def test_a_second_run_changes_nothing(self):
        args = ("--xml-only", "--gui", str(self.gui), "--tables", str(self.tables))
        self.run_main(*args, parked_target=lambda p: False)
        first = (self.gui.read_bytes(), self.tables.read_bytes())
        self.run_main(*args, parked_target=lambda p: False)
        self.assertEqual((self.gui.read_bytes(), self.tables.read_bytes()), first)

    def test_a_running_jmri_stops_a_full_run_before_anything_is_written(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--gui", str(self.gui), running=True)
        self.assertIn("PanelPro or CATS is open", str(cm.exception.code))
        self.assertEqual(self.gui.read_text(encoding="utf-8"), self.GUI_TEXT)

    def test_xml_only_does_not_care_that_jmri_runs(self):
        self.run_main("--xml-only", "--gui", str(self.gui), running=True)
        self.assertIn("Panel-left-7.gif", self.gui.read_text(encoding="utf-8"))

    def test_the_source_tables_are_refused(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main("--xml-only", "--gui", str(self.gui), "--tables", str(gen.SOURCE_TABLES))
        self.assertEqual(str(cm.exception.code), "refusing to write tables/tables.xml")
        self.assertEqual(self.gui.read_text(encoding="utf-8"), self.GUI_TEXT)

    def test_a_gui_without_a_panel_fails_loudly(self):
        # apply() adds the block before the close tag, so a file with no panel at all cannot be regenerated
        self.gui.write_text("<layout/>", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_main("--xml-only", "--gui", str(self.gui))

    def test_tables_without_a_panel_fail_loudly(self):
        self.tables.write_text("<tables/>", encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "no paneleditor in"):
            self.run_main("--xml-only", "--gui", str(self.gui), "--tables", str(self.tables),
                          parked_target=lambda p: False)

    def test_a_parked_target_is_left_alone(self):
        out = self.run_main("--xml-only", "--gui", str(self.gui), "--tables", str(self.tables),
                            parked_target=lambda p: True)
        self.assertEqual(self.tables.read_text(encoding="utf-8"), self.TABLES_TEXT)
        self.assertNotIn("paneleditor replaced", out)

    def test_the_default_tables_are_used_when_none_is_given(self):
        self.run_main("--xml-only", "--gui", str(self.gui), OUTPUT_TABLES=self.tables, parked_target=lambda p: False)
        self.assertIn("Panel-left-7.gif", self.tables.read_text(encoding="utf-8"))

    def test_the_preview_is_written_when_asked(self):
        png = self.dir / "p.png"
        with mock.patch.object(gen, "JMRI_RES", self.dir / "no-jmri"):
            out = self.run_main("--xml-only", "--gui", str(self.gui), "--preview", str(png))
        self.assertTrue(png.is_file())
        self.assertIn("preview", out)


if __name__ == "__main__":
    unittest.main()
