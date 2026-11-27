"""hartlib's shared types: the Level parser, the error hierarchy, the JMRI process check, the end-order key, the
relabel map and the store split's item keys."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import (block_numbering, coordinator, devices, drawing_keys, errors, files,  # noqa: E402
                     hand_lists, layer_files, levels, parked, railroad, railroad_facts, store_split, tables,
                     tables_build, track_names, wiring)


class Levels(unittest.TestCase):
    def test_parses_text_and_numbers(self) -> None:
        self.assertEqual(levels.parse_level("2", "x"), 2)
        self.assertEqual(levels.parse_level(3, "x"), 3)
        self.assertEqual(levels.parse_level(" 1 ", "x"), 1)

    def test_one_message_for_each_range(self) -> None:
        with self.assertRaisesRegex(errors.FactsError,
                                    r"^f line 4: level is 1, 2 or 3 \(staging, main, upper\), not 4$"):
            levels.parse_level("4", "f line 4")
        with self.assertRaisesRegex(errors.FactsError, r"^w: level is 2 or 3 \(main, upper\), not 1$"):
            levels.parse_level("1", "w", levels.MAIN_UPPER)
        with self.assertRaisesRegex(errors.FactsError, r"^w: level is 1 \(staging\), not 2$"):
            levels.parse_level("2", "w", (levels.STAGING,))
        with self.assertRaisesRegex(errors.FactsError, r"^w: level is a whole number, not 'two'$"):
            levels.parse_level("two", "w")

    def test_the_fact_readers_use_it(self) -> None:
        self.assertIs(railroad_facts.LEVEL_NUMBERS, levels.MAIN_UPPER)
        with self.assertRaisesRegex(errors.FactsError, r"level is 2 or 3 \(main, upper\), not 1"):
            railroad_facts._level("1", "w")
        self.assertEqual(levels.level_text(2), "2")
        self.assertEqual(devices.LEVELS, ("1", "2", "3"))


class Errors(unittest.TestCase):
    def test_every_module_error_is_a_hartlib_error_and_keeps_its_base(self) -> None:
        for cls, base in ((railroad.FactsError, ValueError), (devices.DevicesError, ValueError),
                          (tables_build.TablesBuildError, ValueError), (store_split.SplitError, ValueError),
                          (track_names.TrackNameError, ValueError), (layer_files.LayerFileError, ValueError),
                          (hand_lists.HandListError, ValueError), (parked.ParkError, ValueError),
                          (block_numbering.NumberingError, ValueError), (coordinator.CoordinatorError, ValueError),
                          (drawing_keys.DrawingKeyError, ValueError), (files.GitError, RuntimeError),
                          (railroad_facts.LayerError, RuntimeError), (tables.JmriCheckError, RuntimeError)):
            with self.subTest(cls=cls.__name__):
                self.assertTrue(issubclass(cls, errors.HartlibError))
                self.assertTrue(issubclass(cls, base))
        self.assertIs(railroad.FactsError, errors.FactsError)
        self.assertIs(devices.DevicesError, errors.FactsError)

    def test_a_wrapped_error_keeps_its_cause(self) -> None:
        with self.assertRaises(railroad.FactsError) as got:
            railroad_facts._int("x", "w", "node")
        self.assertIsInstance(got.exception.__cause__, ValueError)


class JmriProcess(unittest.TestCase):
    def state(self, rc: int | None = None, exc: Exception | None = None) -> tables.JmriState:
        done: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess([], rc if rc is not None else 0)
        env = {k: v for k, v in os.environ.items() if k != "HART_GUARD_JMRI_RUNNING"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(tables.subprocess, "run", side_effect=exc, return_value=done):
            return tables.jmri_state()

    def test_pgrep_answers(self) -> None:
        self.assertIs(self.state(0), tables.JmriState.RUNNING)
        self.assertIs(self.state(1), tables.JmriState.STOPPED)
        self.assertIs(self.state(2), tables.JmriState.UNKNOWN)
        self.assertIs(self.state(exc=FileNotFoundError("pgrep")), tables.JmriState.UNKNOWN)
        self.assertIs(self.state(exc=subprocess.TimeoutExpired("pgrep", 5)), tables.JmriState.UNKNOWN)

    def test_forced(self) -> None:
        with mock.patch.dict(os.environ, {"HART_GUARD_JMRI_RUNNING": "1"}):
            self.assertIs(tables.jmri_state(), tables.JmriState.RUNNING)
            self.assertTrue(tables.jmri_running())
        with mock.patch.dict(os.environ, {"HART_GUARD_JMRI_RUNNING": "0"}):
            self.assertFalse(tables.jmri_running())

    def test_running_refuses_to_guess(self) -> None:
        with mock.patch.object(tables, "jmri_state", return_value=tables.JmriState.UNKNOWN), \
                self.assertRaisesRegex(tables.JmriCheckError, "cannot tell"):
            tables.jmri_running()
        with mock.patch.object(tables, "jmri_state", return_value=tables.JmriState.STOPPED):
            self.assertFalse(tables.jmri_running())


class EndOrder(unittest.TestCase):
    def test_switch_legs_by_number_half_and_leg_then_other_ends(self) -> None:
        self.assertEqual(sorted(["helix", "105B", "103BA", "end", "9C", "103AB"], key=track_names.end_order),
                         ["9C", "103AB", "103BA", "105B", "end", "helix"])
        self.assertEqual(track_names.end_order("103AB"), (0, 103, "A", "B"))
        self.assertEqual(track_names.end_order("end"), (1, 0, "", "end"))
        self.assertEqual(track_names.run_of("39C", "37C"), "37C-39C")


class Relabel(unittest.TestCase):
    def test_later_edits_win_and_other_edits_are_skipped(self) -> None:
        section = {"edits": [{"op": "relabel", "map": {"a": "1", "b": "2"}}, {"op": "end", "ends": []},
                             {"op": "relabel", "map": {"a": "3"}}]}
        self.assertEqual(track_names.relabel_map(section), {"a": "3", "b": "2"})
        self.assertEqual(track_names.relabel_map({}), {})


class ItemKeys(unittest.TestCase):
    def test_labels(self) -> None:
        sk = ("turnouts", "jmri.Class")
        ss = store_split
        self.assertEqual(ss.label(ss.PanelKey("panel", "P")), "panel 'P'")
        self.assertEqual(ss.label(ss.SectionKey("section", "x", "a.b.C")), "section <x> (C)")
        self.assertEqual(ss.label(ss.AttrsKey("attrs", sk)), "<turnouts> settings")
        self.assertEqual(ss.label(ss.LogicKey("logic", "M1")), "Signal Mast Logic from 'M1'")
        self.assertEqual(ss.label(ss.BeanKey("bean", sk, "turnout", "block-names", "IT1")),
                         "turnout IT1 (names-only pass)")
        self.assertEqual(ss.label(ss.SettingKey("setting", sk, "opt", 0)), "<turnouts> <opt>")
        self.assertEqual(ss.label(ss.SettingKey("setting", sk, "opt", 2)), "<turnouts> <opt> #3")
        self.assertEqual(ss.label(ss.SettingKey("setting", sk, "opt", ss.ById(ss.BY_ID, "k"))), "<turnouts> <opt> 'k'")
        got = ss.label(ss.SettingKey("setting", sk, "opt", ss.ByContent(ss.BY_CONTENT, "<a>hi</a>", 1)))
        self.assertRegex(got, r"^<turnouts> <opt> \(hi; [0-9a-f]{6}\) copy 2$")
        # a key compares and hashes as the plain tuple of its parts
        self.assertEqual(ss.BeanKey("bean", sk, "t", "", "n"), ("bean", sk, "t", "", "n"))
        self.assertEqual(hash(ss.BeanKey("bean", sk, "t", "", "n")), hash(("bean", sk, "t", "", "n")))

    def test_sort_group_is_public(self) -> None:
        self.assertTrue(callable(tables_build.sort_group))


class WiringKinds(unittest.TestCase):
    def test_lcos_kinds_are_named(self) -> None:
        self.assertEqual(wiring.LCOS["head"].board, "OU")
        self.assertEqual(wiring.LCOS["turnout"].ports, 2)
        self.assertEqual(set(wiring.KINDS), set(wiring.LCOS))


if __name__ == "__main__":
    unittest.main()
