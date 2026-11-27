"""build_cats_panel.check_desk_faults: the plugin's desk faults printed with their count, and a desk with one stops."""
import contextlib
import io
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_cats_panel as b  # noqa: E402


def fake_cats(found):
    """A stand-in for the plugin's cats module whose faults() returns `found` and records what it was asked."""
    asked = []

    def faults(P, fit):
        asked.append((P, fit))
        return list(found)
    return SimpleNamespace(faults=faults, asked=asked)


class DeskFaults(unittest.TestCase):

    def run_check(self, found):
        cats = fake_cats(found)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                b.check_desk_faults(cats, "panel", (62, 30))
            except b.CatsPanelError as exc:
                return out.getvalue(), str(exc), cats.asked
        return out.getvalue(), None, cats.asked

    def test_no_fault_prints_the_count_and_goes_on(self):
        out, code, asked = self.run_check([])
        self.assertEqual(out, "CATS desk faults: 0\n")
        self.assertIsNone(code)
        self.assertEqual(asked, [("panel", (62, 30))])       # the window's fit is passed on

    def test_a_fault_is_listed_and_stops(self):
        fault = "Main level: blocks A, B land in one cell, (17, 15) edge LEFT, where both reach one edge"
        out, code, _asked = self.run_check([fault])
        self.assertEqual(out, f"CATS desk faults: 1\n  {fault}\n")
        self.assertEqual(code, "error: the desk has 1 fault(s), listed above")


class Apart(unittest.TestCase):
    def test_a_desk_block_takes_its_bindings_name_else_its_panel_name(self):
        self.assertEqual(b.block_names({"e1": {"name": "Track 1-3"}, "Track 5-7": {}}), {"Track 1-3", "Track 5-7"})

    def test_staging_and_main_upper_blocks_must_not_share_a_panel_name(self):
        with self.assertRaisesRegex(b.CatsPanelError, "share panel names e1"):
            b.check_apart({"e1": {}}, {"e1": {}, "e2": {}})

    def test_staging_and_main_upper_blocks_must_not_become_one_block(self):
        b.check_apart({"e1": {"name": "Track 1-3"}}, {"e2": {"name": "Track 5-7"}})
        with self.assertRaisesRegex(b.CatsPanelError, "would both be Track 1-3"):
            b.check_apart({"e1": {"name": "Track 1-3"}}, {"Track 1-3": {}})

    def test_shared_binding_keys_stop(self):
        b.check_keys_apart("mast", {"2L": 1}, {"202L": 1})
        with self.assertRaisesRegex(b.CatsPanelError, "staging and main/upper share mast keys 2L"):
            b.check_keys_apart("mast", {"2L": 1}, {"2L": 1})


OPTIONS = b.DeskOptions(scale=2, helix_blocks="one", band_gap=None, title_gap=None, window=(1900, 1000), fit=(90, 40))


class DeskSteps(unittest.TestCase):
    """generate()'s steps over a stand-in for the plugin's cats module."""

    def cats(self, found=(), log=()):
        calls = []
        panel = SimpleNamespace(log=list(log))

        def make(bands, **kw):
            calls.append(("panel", kw))
            return panel

        def check_fit(P, cols, rows):
            calls.append(("check_fit", (cols, rows)))

        return SimpleNamespace(panel=make, faults=lambda P, fit: list(found), check_fit=check_fit,
                               shown=lambda P: (80, 30), GRID_PX=20, summary=lambda P: "3 blocks",
                               SchematicError=ValueError, calls=calls, made=panel)

    def test_the_panel_is_built_in_the_fit_columns_and_held_to_the_window(self):
        cats = self.cats()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIs(b.desk_panel(cats, [], OPTIONS, {"switches": {}}), cats.made)
        (_, kw), fit = cats.calls
        self.assertEqual((kw["max_cols"], kw["scale"], kw["helix_blocks"], kw["bindings"]),
                         (90, 2, "one", {"switches": {}}))
        self.assertEqual(fit, ("check_fit", (90, 40)))

    def test_a_desk_fault_stops_before_the_fit_backstop(self):
        cats = self.cats(found=["two blocks in cell 3,4"])
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(b.CatsPanelError, "1 fault"):
            b.desk_panel(cats, [], OPTIONS, {})
        self.assertEqual([name for name, _ in cats.calls], ["panel"])

    def test_the_report_gives_the_size_and_the_log(self):
        cats = self.cats(log=["mast 2L: its gap moved 1 cell(s)"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            b.report(cats, cats.made, [("Staging", {}, {}), ("Main", {}, {})], OPTIONS)
        self.assertEqual(out.getvalue().splitlines(),
                         ["Staging, Main: 3 blocks; shows 80 x 30 cells (1600 x 600 pixels at the 20 pixel grid), "
                          "fit 90 x 40 in a 1900 x 1000 window", "mast 2L: its gap moved 1 cell(s)"])

    def test_a_label_with_no_room_stops_after_the_report(self):
        cats = self.cats(log=["no room for label Track 1-3"])
        with contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(b.CatsPanelError, "labels clash.*\n  no room for label Track 1-3"):
            b.report(cats, cats.made, [], OPTIONS)

    def test_a_host_screen_that_does_not_read_is_a_named_error(self):
        bad = b.pd.host_screen.HostScreenError("host_screen: no width")
        with unittest.mock.patch.object(b.pd, "solved_sheet", side_effect=bad), \
                self.assertRaisesRegex(b.CatsPanelError, "error: host_screen: no width") as stop:
            b.solved(SimpleNamespace(), SimpleNamespace(device=None))
        self.assertIs(stop.exception.__cause__, bad)

    def stopped_in_bindings(self, cats):
        """generate()'s steps up to bindings() replaced by stand-ins, and bindings() stopping as the plugin does."""
        stop = cats.SchematicError("switch 7 has no leg C")
        steps = dict(plugin_modules=unittest.mock.DEFAULT, load_facts=unittest.mock.DEFAULT,
                     level_signals=unittest.mock.DEFAULT, bound_index=unittest.mock.DEFAULT)
        return stop, unittest.mock.patch.multiple(
            b, **steps, solved=unittest.mock.Mock(return_value=b.Solved([], {})),
            desk_options=unittest.mock.Mock(return_value=OPTIONS), bindings=unittest.mock.Mock(side_effect=stop))

    def test_a_plugin_stop_in_the_bindings_is_a_named_error_and_writes_nothing(self):
        cats = self.cats()
        stop, patched = self.stopped_in_bindings(cats)
        with tempfile.TemporaryDirectory() as tmp, patched as steps:
            steps["plugin_modules"].return_value = (cats, SimpleNamespace())
            out, bound = Path(tmp) / "ctc.xml", Path(tmp) / "bindings.json"
            with self.assertRaisesRegex(b.CatsPanelError, "^error: switch 7 has no leg C$") as named:
                b.generate(Path("plugin"), out, bound)
            self.assertIs(named.exception.__cause__, stop)
            self.assertEqual(list(Path(tmp).iterdir()), [])
        self.assertEqual(cats.calls, [])        # the desk's panel was never asked for

    def test_main_turns_a_bindings_stop_into_exit_1_with_its_message(self):
        cats = self.cats()
        _stop, patched = self.stopped_in_bindings(cats)
        err = io.StringIO()
        with patched as steps, unittest.mock.patch.object(b.pd, "plugin", return_value=Path("plugin")), \
                unittest.mock.patch.object(b, "compare") as compare, contextlib.redirect_stderr(err):
            steps["plugin_modules"].return_value = (cats, SimpleNamespace())
            self.assertEqual(b.main(["--check"]), 1)
        self.assertEqual(err.getvalue(), "error: switch 7 has no leg C\n")
        compare.assert_not_called()

    def test_only_the_desks_given_a_path_are_written(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(b, "dress", side_effect=lambda cats, xml, header, plate, desk, fit, plates:
                                           f"{desk} {xml} {fit}\n"), \
                unittest.mock.patch.object(b, "desk_plates", return_value=[]):
            ctc = Path(tmp) / "ctc.xml"
            cats = SimpleNamespace(to_xml=lambda P, desk, header, window: f"xml {desk} {window}")
            b.write_desks(cats, object(), OPTIONS, ([], []), {"CTC": ctc, "ABS": None})
            self.assertEqual(ctc.read_text(encoding="utf-8"), "CTC xml CTC (1900, 1000) (90, 40)\n")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["ctc.xml"])


if __name__ == "__main__":
    unittest.main()
