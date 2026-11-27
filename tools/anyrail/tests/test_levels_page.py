"""tools/anyrail/levels_page.py on the committed drawings (tools/anyrail/levels/) and data (block_lengths.csv,
the helix tracks of the plan overrides): the article www/build/track-plan.html is what the generator builds, its numbers come from those
files, and a figure that disagrees with its source stops the build. None of this needs the owner's plan."""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import levels_page as LP  # noqa: E402

LEVELS = HERE.parent / "levels"
PAGE = LP.SITE_HTML


def text_of(html):
    body = html[html.index('<div class="feature-body lv">'):]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<svg.*?</svg>", "", body, flags=re.S)))


class TheArticleIsWhatTheGeneratorBuilds(unittest.TestCase):
    def test_the_committed_article_is_current(self) -> None:
        site, _ = LP.render(LEVELS)
        self.assertEqual(PAGE.read_text(), site, "rerun tools/anyrail/levels_page.py")

    def test_the_plan_version_is_printed_and_nothing_is_left_to_fill(self) -> None:
        html = PAGE.read_text()
        self.assertIn("plan version 5.3c", html)
        self.assertNotIn("@PLAN@", html)

    def test_the_levels_counts_in_the_text_are_the_drawings(self) -> None:
        meta = json.loads((LEVELS / "levels_meta.json").read_text())
        html = PAGE.read_text()
        for level, name in LP.LEVEL_NAMES.items():
            found = re.search(r'<section id="%s">(.*?)</section>' % level, html, re.S)
            assert found is not None, f"the article has no {level} section"
            sec = found.group(1)
            self.assertEqual(len(re.findall(r'<text class="tl"', sec)), meta["levels"][level]["switches"])
            self.assertIn("%d switch parts" % meta["levels"][level]["switches"], sec)

    def test_the_article_does_not_describe_the_5_3b_corrections(self) -> None:
        text = text_of(PAGE.read_text())
        for gone in ("placeholder", "T300", "T41", "not in the plan", "were filled in"):
            self.assertNotIn(gone, text)

    def test_the_artifact_copy_takes_a_panel_picture_only_there(self) -> None:
        _site, art = LP.render(LEVELS)
        self.assertIn("@PANEL@", art)
        self.assertNotIn("data:image", PAGE.read_text())


class TheTablesComeFromTheData(unittest.TestCase):
    def test_the_loop_runs_from_switch_5_and_adds_up(self) -> None:
        blocks, notes = LP.block_rows()
        names = LP.loop_names()
        self.assertEqual(names[0], LP.LOOP_START)
        rows = LP.timed_rows(blocks, notes, names)
        html = LP.length_table(rows, "Loop total")
        self.assertIn("<b>%.1f</b>" % sum(r[1] for r in rows), html)
        self.assertIn("<b>%.1f</b>" % sum(r[2] for r in rows), html)

    def test_a_block_that_was_not_timed_stops_the_table(self) -> None:
        blocks, notes = LP.block_rows()
        with self.assertRaisesRegex(LP.LevelsPageError, "Track W-1 is not a timed block"):
            LP.timed_rows(blocks, notes, ["Track W-1"])

    def test_the_run_table_holds_the_timed_blocks_outside_the_loop_in_running_order(self) -> None:
        text = text_of(PAGE.read_text())
        at = [text.index(name) for name in ("Track Scale", "Track Barn", "OS Switch 13", "OS Switch 15")]
        self.assertEqual(at, sorted(at))

    def test_the_run_passes_come_from_the_block_notes(self) -> None:
        notes = {"Track Scale": "timed passes of 2026-11-13 (CSX 2121, Switch 5 to Switch 15, steps 24 and 48): ...",
                 "Track Barn": "timed passes of 2026-11-13: ..."}
        rows = ["Track Scale", "Track Barn"]
        self.assertEqual(LP.run_passes(rows, notes), ("CSX 2121", "24", "48"))
        self.assertIn("CSX 2121 timed the Switch 5 to Switch 15 run on two passes at different speeds (steps 24 and 48)",
                      text_of(PAGE.read_text()))
        with self.assertRaisesRegex(LP.LevelsPageError, "name no timed passes"):
            LP.run_passes(rows[1:], notes)
        notes["Track Barn"] = "timed passes (CSX 2738, Switch 5 to Switch 15, steps 32 and 64)"
        with self.assertRaisesRegex(LP.LevelsPageError, "expected one"):
            LP.run_passes(rows, notes)
        notes["Track Barn"] = "timed passes (P&CV 2121, Switch 5 to 15, steps 32 and 64)"
        with self.assertRaisesRegex(LP.LevelsPageError, "Track Barn's note names passes as"):
            LP.run_passes(rows, notes)
        self.assertEqual(LP.run_passes(["x"], {"x": "(P&CV 2121, Switch 5 to Switch 15, steps 48 and 24)"}),
                         ("P&CV 2121", "48", "24"))
        with self.assertRaisesRegex(LP.LevelsPageError, "both at step 24"):
            LP.run_passes(["x"], {"x": "(CSX 2121, Switch 5 to Switch 15, steps 24 and 24)"})

    def test_a_timed_block_on_neither_route_stops(self) -> None:
        blocks, measured = LP.block_rows()
        stray = mock.Mock(note="")
        with mock.patch.object(LP, "block_rows", return_value=(blocks, {**measured, "Track Helix Inner X": stray})), \
                self.assertRaisesRegex(LP.LevelsPageError, "neither the test loop nor the Switch 5 to 15 run: Track Helix Inner X"):
            LP.render(LEVELS)

    def test_main_exits_with_the_render_error(self) -> None:
        with mock.patch.object(LP, "render", side_effect=LP.LevelsPageError("levels_meta.json has no 'x'")), \
                self.assertRaises(SystemExit) as cm:
            LP.main(["--check"])
        self.assertEqual(cm.exception.code, "levels_meta.json has no 'x'")

    def test_a_panel_without_the_artifact_is_refused(self) -> None:
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            LP.main(["--panel", "x.png"])

    def test_the_staging_helix_figure_is_what_staging_draws(self) -> None:
        meta = json.loads((LEVELS / "levels_meta.json").read_text())
        self.assertIn("%.1f m of helix below its top layer" % meta["levels"]["staging"]["ramp_m"], text_of(PAGE.read_text()))

    def test_the_loop_fit_plan_comes_from_the_notes(self) -> None:
        blocks, measured = LP.block_rows()
        names = [r.name for r in LP.timed_rows(blocks, measured, LP.loop_names())]
        notes = {name: m.note for name, m in measured.items()}
        self.assertEqual(LP.loop_fit_plan(names, notes), "5.3b")
        mixed = dict(notes, **{"Track K-1": notes["Track K-1"].replace("5.3b", "5.3c")})
        with self.assertRaisesRegex(LP.LevelsPageError, "expected one"):
            LP.loop_fit_plan(names, mixed)

    def test_laps_are_the_common_count_and_the_exceptions(self) -> None:
        rows = [LP.TimedRow("Track A", 1, 1, 0.5, 33), LP.TimedRow("Track East Ext", 1, 1, 0.5, 16),
                LP.TimedRow("OS B", 1, 1, 0.5, 33)]
        self.assertEqual(LP.laps_note(rows), "33 laps (16 for East Ext)")
        with self.assertRaisesRegex(LP.LevelsPageError, "gives its laps"):
            LP.laps_note([LP.TimedRow("Track A", 1, 1, None, None)])

    def test_a_helix_run_that_differs_from_its_block_stops(self) -> None:
        meta = LP.read_meta(LEVELS)
        blocks, _ = LP.block_rows()
        rows = LP.helix_rows(meta, blocks)
        self.assertEqual(sorted(r.shown for r in rows), ["McKees Rocks", "McKeesport"])
        meta["helix"][0]["cm"] += 100
        with self.assertRaisesRegex(LP.LevelsPageError, "block_lengths.csv has"):
            LP.helix_rows(meta, blocks)

    def test_a_helix_track_nobody_named_stops(self) -> None:
        meta = LP.read_meta(LEVELS)
        meta["helix"][0]["foot"] = "99"
        blocks, _ = LP.block_rows()
        with self.assertRaisesRegex(LP.LevelsPageError, "no helix track from Switch 99"):
            LP.helix_rows(meta, blocks)


class TheInputsAreChecked(unittest.TestCase):
    def test_a_meta_file_without_the_helix_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(LEVELS, tmp, dirs_exist_ok=True)
            meta = json.loads((Path(tmp) / "levels_meta.json").read_text())
            del meta["helix"]
            (Path(tmp) / "levels_meta.json").write_text(json.dumps(meta))
            with self.assertRaisesRegex(LP.LevelsPageError, "no 'helix'"):
                LP.read_meta(Path(tmp))

    def test_a_missing_or_broken_meta_file_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(LP.LevelsPageError, "cannot read .*levels_meta.json"):
                LP.read_meta(Path(tmp))
            (Path(tmp) / "levels_meta.json").write_text("{")
            with self.assertRaisesRegex(LP.LevelsPageError, "is not JSON"):
                LP.read_meta(Path(tmp))
            (Path(tmp) / "levels_meta.json").write_text("[]")
            with self.assertRaisesRegex(LP.LevelsPageError, "is not an object"):
                LP.read_meta(Path(tmp))

    def test_a_level_without_its_counts_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(LEVELS, tmp, dirs_exist_ok=True)
            meta = json.loads((Path(tmp) / "levels_meta.json").read_text())
            del meta["levels"]["upper"]["ramp_m"]
            del meta["levels"]["main"]
            (Path(tmp) / "levels_meta.json").write_text(json.dumps(meta))
            with self.assertRaisesRegex(LP.LevelsPageError, "no main level"):
                LP.read_meta(Path(tmp))
            meta["levels"]["main"] = meta["levels"]["staging"]
            (Path(tmp) / "levels_meta.json").write_text(json.dumps(meta))
            with self.assertRaisesRegex(LP.LevelsPageError, "the upper level has no ramp_m"):
                LP.read_meta(Path(tmp))

    def test_a_missing_drawing_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(LEVELS, tmp, dirs_exist_ok=True)
            (Path(tmp) / "upper.svg").unlink()
            with self.assertRaisesRegex(LP.LevelsPageError, "cannot read .*upper.svg"):
                LP.render(Path(tmp))

    def test_a_timed_or_helix_block_without_a_plan_length_stops(self) -> None:
        blocks, measured = LP.block_rows()
        name = LP.loop_names()[0]
        fewer = {k: v for k, v in blocks.items() if k != name}
        with self.assertRaisesRegex(LP.LevelsPageError, f"no plan length for the timed block {name}"):
            LP.timed_rows(fewer, measured, [name])
        helix = {r.block for r in LP.railroad.read_helix_tracks(LP.HELIX_SOURCE).values()}
        with self.assertRaisesRegex(LP.LevelsPageError, "no plan length for the helix block"):
            LP.helix_rows(LP.read_meta(LEVELS), {k: v for k, v in blocks.items() if k not in helix})

    def test_the_artifact_copy_embeds_the_panel_picture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            png, site, art = Path(tmp) / "p.png", Path(tmp) / "site.html", Path(tmp) / "art.html"
            png.write_bytes(b"\x89PNG")
            LP.main(["--site", str(site), "--artifact", str(art), "--panel", str(png)])
            self.assertEqual(site.read_text(), PAGE.read_text())
            self.assertIn('src="data:image/png;base64,iVBORw=="', art.read_text())
            self.assertNotIn("@PANEL@", art.read_text())
            site.unlink()
            art.unlink()
            with self.assertRaises(SystemExit) as cm:
                LP.main(["--site", str(site), "--artifact", str(art), "--panel", str(Path(tmp) / "none.png")])
            self.assertIn("cannot read the panel picture", str(cm.exception))
            self.assertEqual(site.read_text(), PAGE.read_text())   # the site article is written all the same
            self.assertFalse(art.exists())

    def test_a_plan_version_that_is_not_one_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(LEVELS, tmp, dirs_exist_ok=True)
            meta = json.loads((Path(tmp) / "levels_meta.json").read_text())
            meta["plan"] = "x"
            (Path(tmp) / "levels_meta.json").write_text(json.dumps(meta))
            with self.assertRaisesRegex(LP.LevelsPageError, "not 'x'"):
                LP.render(Path(tmp))

    def test_a_staging_drawing_without_the_terminal_switches_stops(self) -> None:
        meta = LP.read_meta(LEVELS)
        real = LP.read_meta
        def without(levels):
            m = real(levels)
            m["levels"]["staging"]["labels"] = [s for s in m["levels"]["staging"]["labels"] if s != "13"]
            return m
        with mock.patch.object(LP, "read_meta", without):
            with self.assertRaisesRegex(LP.LevelsPageError, "no Switch 7, 9, 11 and 13"):
                LP.render(LEVELS)
        self.assertIn("13", meta["levels"]["staging"]["labels"])

    def test_a_plan_with_other_ramps_stops(self) -> None:
        real = LP.read_meta
        def one_ramp(levels):
            m = real(levels)
            m["ramps"] = m["ramps"][1:]
            return m
        with mock.patch.object(LP, "read_meta", one_ramp):
            with self.assertRaisesRegex(LP.LevelsPageError, "two helix tracks and one climb"):
                LP.render(LEVELS)


if __name__ == "__main__":
    unittest.main()
