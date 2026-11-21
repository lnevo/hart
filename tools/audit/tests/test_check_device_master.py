"""check_device_master.py: one set of rules for every level of devices.csv, and every row against tables.xml."""
from __future__ import annotations

import contextlib
import io
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
import check_device_master as cdm  # noqa: E402
import staging_device_map as sdm  # noqa: E402
import test_staging_device_map as tsdm  # noqa: E402  the staging band and an edited copy of the master


class Master(unittest.TestCase):
    """The committed master's rows, every level, and a way to break a copy of them."""

    @classmethod
    def setUpClass(cls):
        cls.rr = cdm.railroad.Railroad()
        cls.lines = cdm.master_lines()
        cls.cps = cdm.control_points(cls.rr.interlockings)
        cls.helix = {h.block for h in cls.rr.helix_tracks.values()}

    def edited(self, edit=None, drop=()):
        """(line, row) of the master with `edit` ({(level, user_name): columns}) applied and `drop` rows left out."""
        out = []
        for n, r in self.lines:
            key = (r["level"], r["user_name"])
            if key in drop:
                continue
            out.append((n, dict(r, **(edit or {}).get(key, {}))))
        return out

    def assertProblem(self, pattern, got):
        self.assertTrue(any(re.search(pattern, p) for p in got), got)


class RowRules(Master):
    def test_the_committed_rows_hold_on_every_level(self):
        self.assertEqual({r["level"] for _n, r in self.lines}, {"1", "2", "3"})
        self.assertEqual(cdm.row_problems(self.lines, self.cps), [])
        self.assertEqual(cdm.check_rows(self.lines, self.helix), [])

    def test_a_cp_is_one_of_its_levels(self):
        got = cdm.row_problems(self.edited({("2", "Track 101-103"): dict(cp="CP 201"),
                                            ("1", "Track Barn"): dict(cp="CP 107")}), self.cps)
        self.assertProblem(r"\(level 2 block Track 101-103\): cp 'CP 201' is no level 2 control point", got)
        self.assertProblem(r"\(level 1 block Track Barn\): cp 'CP 107' is no level 1 control point", got)

    def test_a_known_cp_exception_that_no_row_uses_fails(self):
        got = cdm.row_problems(self.lines, self.cps, known_cp={**cdm.KNOWN_CP, ("2", "CP 201"): "test"})
        self.assertEqual(got, ["KNOWN_CP entry no longer happens; remove it: level 2 CP 201"])
        self.assertTrue(cdm.row_problems(self.lines, self.cps, known_cp={}))      # the CP 127 rows are reported

    def test_a_detector_is_wired_exactly_when_it_is_a_field_device(self):
        got = cdm.row_problems(self.edited({("1", "BS Barn"): dict(detector="planned"),
                                            ("2", "BS Switch 101"): dict(detector="wired", system_name="M2S1")}),
                               self.cps)
        self.assertProblem(r"level 1 occupancy BS Barn\): assignment field with detector 'planned'", got)
        self.assertProblem(r"level 2 occupancy BS Switch 101\): assignment virtual with detector 'wired'", got)

    def test_a_row_kept_by_hand_is_a_field_device(self):
        got = cdm.row_problems(self.edited({("2", "Track 101-103"): dict(written_by="")}), self.cps)
        self.assertProblem(r"level 2 block Track 101-103\): kept by hand, so a field device, not assignment none",
                           got)

    def test_trial_names(self):
        got = cdm.row_problems(self.edited({("1", "FB Switch 1 N"): dict(trial_name="Track Nowhere"),
                                            ("3", "Switch 203"): dict(trial_name="Switch 201")}), self.cps)
        self.assertProblem(r"level 1 fb FB Switch 1 N\): a fb row has a trial_name", got)
        self.assertProblem(r"level 3 turnout Switch 203\): trial_name Switch 201 is line \d+'s as well", got)

    def test_a_fact_column_out_of_place(self):
        got = cdm.row_problems(self.edited({("3", "Switch 203"): dict(facing="Track X")}), self.cps)
        self.assertProblem(r"level 3 turnout Switch 203\): a turnout row has facing", got)

    def test_only_the_helix_blocks_are_on_two_levels(self):
        lines = self.edited({("2", "Track 101-103"): dict(user_name="Track K-1")})
        self.assertProblem(r"blocks named on more than one level: \['Track Helix Inner', 'Track Helix Outer', "
                           r"'Track K-1'\]", cdm.check_rows(lines, self.helix))
        self.assertProblem(r"blocks named on more than one level: .*exactly the helix blocks",
                           cdm.check_rows(self.lines, self.helix | {"Track X"}))

    def test_a_block_has_one_occupancy_row_on_any_level(self):
        got = cdm.check_rows(self.edited(drop={("3", "BS Helix Inner")}), self.helix)
        self.assertProblem(r"block Track Helix Inner has 0 occupancy rows naming it", got)
        got = cdm.check_rows(self.edited({("2", "BS 101-103"): dict(blocks="Track Barn")}), self.helix)
        self.assertProblem(r"block Track Barn has 2 occupancy rows naming it", got)
        self.assertProblem(r"block Track 101-103 has 0 occupancy rows", got)

    def test_names_given_twice(self):
        got = cdm.check_rows(self.edited({("3", "FB Switch 201 N"): dict(system_name="M2S470"),
                                          ("1", "Switch 3"): dict(user_name="Switch 1")}), self.helix)
        self.assertProblem(r"level 3 fb FB Switch 201 N\): system_name 'M2S470' is line \d+'s as well", got)
        self.assertProblem(r"level 1 turnout Switch 1\): user_name 'Switch 1' is line \d+'s as well", got)

    def test_a_dcc_address_or_device_on_two_levels(self):
        got = cdm.check_rows(self.edited({("2", "Switch 101"): dict(system_name="M2T408", dcc="100"),
                                          ("2", "DCC Switch 101"): dict(dcc="100", system_name="MTT100")}),
                             self.helix)
        self.assertProblem(r"level 2 turnout Switch 101\): system_name 'M2T408' is line 22's as well", got)
        self.assertProblem(r"level 2 turnout Switch 101\): dcc '100' is line 22's as well", got)
        self.assertProblem(r"level 2 turnout DCC Switch 101\): system_name 'MTT100' is line 2's as well", got)
        # one device is one row whatever its layer: a head planned on a feedback sensor's name
        got = cdm.check_rows(self.edited({("3", "Head 202R Top"): dict(system_name="M2S470")}), self.helix)
        self.assertProblem(r"level 3 head Head 202R Top\): system_name 'M2S470' is line 42's as well", got)

    def test_an_lcc_alias_on_every_level(self):
        got = cdm.check_rows(self.edited({("2", "DCC Switch 101"): dict(jmri_name="IT:HART:C3:103"),
                                          ("1", "DCC Switch 1"): dict(jmri_name="M2T408")}), self.helix)
        self.assertProblem(r"level 2 turnout DCC Switch 101\): the LCC alias of Switch 101 \(DCC 120\) is user, "
                           r"system and jmri name DCC Switch 101, MTT120, IT:HART:C3:101 \(on its turnout\)", got)
        self.assertProblem(r"level 1 turnout DCC Switch 1\): the LCC alias of Switch 1 \(DCC 100\) is .*MTT100, "
                           r"MTT100 \(a field device\)", got)
        got = cdm.check_rows(self.edited({("3", "DCC Switch 201"): dict(dcc="999")}), self.helix)
        self.assertProblem(r"DCC Switch 201\): no level 3 turnout has its DCC address 999", got)


class TablesCheck(Master):
    """check_tables holds each row of every level to its bean in tables.xml, and names the row and what differs."""

    def problems(self, edit=None, drop=(), known_stop=None):
        return cdm.check_tables([r for _n, r in self.edited(edit, drop)], self.rr, known_stop)

    def test_the_committed_rows_hold(self):
        self.assertEqual(self.problems(), [])

    def test_a_head_of_another_name(self):
        self.assertIn("head IH:HART:C1:24L: tables.xml names it 'Head 24L', not 'Head 24X'",
                      self.problems({("1", "Head 24L"): dict(user_name="Head 24X")}))
        self.assertIn("head IH:HART:C3:108LA_Top: tables.xml names it 'Head 108LA Top', not 'Head 108LA Up'",
                      self.problems({("2", "Head 108LA Top"): dict(user_name="Head 108LA Up")}))

    def test_a_block_of_another_system_name_or_none(self):
        self.assertIn("block Track Barn: tables.xml has IB15, not IB99",
                      self.problems({("1", "Track Barn"): dict(system_name="IB99")}))
        self.assertIn("block Track Nowhere: tables.xml has none, not a block of that name",
                      self.problems({("2", "Track 101-103"): dict(user_name="Track Nowhere")}))

    def test_a_station_is_its_comment(self):
        self.assertIn("block Track Barn: stop is empty, but its comment in tables.xml marks a station",
                      self.problems({("1", "Track Barn"): dict(stop="")}))
        self.assertIn("block Track East Ext: stop is yes, but its comment in tables.xml does not mark a station",
                      self.problems({("1", "Track East Ext"): dict(stop="yes")}))
        self.assertIn("block Track 101-103: stop is yes, but its comment in tables.xml does not mark a station",
                      self.problems({("2", "Track 101-103"): dict(stop="yes")}))

    def test_the_rows_of_a_helix_block_agree_on_its_stop_but_the_known_ones(self):
        got = self.problems(known_stop={})
        self.assertIn("block Track Helix Inner: its rows disagree on stop (empty, yes)", got)
        self.assertIn("block Track Helix Outer: its rows disagree on stop (empty, yes)", got)
        got = self.problems({("3", "Track Helix Inner"): dict(stop="yes")})
        self.assertEqual(got, ["KNOWN_STOP entry no longer happens; remove it: Track Helix Inner"])

    def test_a_block_whose_detector_is_another(self):
        got = self.problems({("1", "BS Barn"): dict(user_name="BS Elsewhere", system_name="M2S9999",
                                                    jmri_name="M2S9999")})
        self.assertProblem(r"^block Track Barn: its detector in tables.xml is '.+', the device map's BS Elsewhere$",
                           got)

    def test_a_helix_blocks_detector_is_its_main_or_upper_occupancy_row(self):
        got = self.problems({("3", "BS Helix Inner"): dict(user_name="BS Other", jmri_name="IS:X")})
        self.assertProblem(r"^block Track Helix Inner: its detector in tables.xml is '.+', the device map's "
                           r"BS Other$", got)

    def test_a_turnout_bound_by_another_turnouts_name(self):
        self.assertIn("turnout Switch 1: jmri_name M2T409 is not that turnout in tables.xml",
                      self.problems({("1", "Switch 1"): dict(jmri_name="M2T409")}))

    def test_a_turnout_or_sensor_of_another_virtual_name(self):
        self.assertIn("turnout Switch 107: tables.xml has 'IT:HART:C3:107', not IT107",
                      self.problems({("2", "Switch 107"): dict(jmri_name="IT107")}))
        self.assertIn("occupancy BS Switch 201: tables.xml has 'IS:HART:C3:B:OS201', not IS:X",
                      self.problems({("3", "BS Switch 201"): dict(jmri_name="IS:X")}))

    def test_a_feedback_sensor_with_no_fb_row(self):
        self.assertProblem(r"^turnout Switch 1: feedback .*have no fb rows$",
                           self.problems(drop={("1", "FB Switch 1 N")}))

    def test_a_row_with_no_jmri_name_is_not_looked_for(self):
        self.assertEqual(self.problems({("2", "FB Switch 101 N"): dict(user_name="FB Nowhere")}), [])

    def test_a_mast_of_another_system_name_or_without_its_head_rows(self):
        self.assertProblem(r"^mast Mast 24L: tables.xml has 'IF\$shsm.*', not IF\$x$",
                           self.problems({("1", "Mast 24L"): dict(system_name="IF$x", jmri_name="IF$x")}))
        self.assertIn("mast Mast 24L: heads ['IH:HART:C1:24L'] have no head rows",
                      self.problems(drop={("1", "Head 24L")}))
        self.assertIn("mast Mast 108LA: planned heads ['IH3332'] are no head row's system name",
                      self.problems({("2", "Head 108LA Top"): dict(system_name="IH3399")}))


class Command(unittest.TestCase):
    def test_the_check_command_names_its_files(self):
        tsdm.Files.setUpClass()                  # SkipTest without the plugin
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cdm.main(["--check"]), 0)
        self.assertIn("ok: devices.csv, control_points_staging.csv, staging_masts.csv, staging_signals.csv hold their "
                      "rules", out.getvalue())

    def test_without_the_drawing_the_rest_still_runs(self):
        self.assertEqual(cdm.check(None), [])

    def test_a_hand_kept_row_off_staging_has_no_drawing_reader(self):
        tsdm.Files.setUpClass()
        lines = [(n, dict(r, written_by="") if (r["level"], r["user_name"]) == ("2", "Track 101-103") else r)
                 for n, r in cdm.master_lines()]
        got = cdm.check_drawing(tsdm.Files.band, lines)
        self.assertEqual(len(got), 1, got)
        self.assertIn("level 2 block Track 101-103): kept by hand, but only staging's hand-kept rows", got[0])


class StagingLoad(unittest.TestCase):
    """staging_device_map.load holds its rows to the same rules, naming the line."""

    _copy = tsdm.Files._copy

    @classmethod
    def setUpClass(cls):
        tsdm.Files.setUpClass()
        cls.band = tsdm.Files.band

    def _load(self, user, **cols):
        def edit(rows):
            hit = next(r for r in rows if r["level"] == "1" and r["user_name"] == user)
            hit.update(cols)
        return sdm.load(self.band, device_map=self._copy(edit)[0])

    def test_the_rules_stop_the_load(self):
        for user, cols, msg in (("BS Barn", dict(detector="planned"), "assignment field with detector 'planned'"),
                                ("Track Barn", dict(cp="Nowhere"), "cp 'Nowhere' is no level 1 control point"),
                                ("FB Switch 1 N", dict(trial_name="Track Nowhere"), "a fb row has a trial_name"),
                                ("Switch 3", dict(trial_name="Switch 1"), r"trial_name Switch 1 is line \d+'s as well")):
            with self.subTest(msg=msg), self.assertRaisesRegex(sdm.StagingMapError, msg):
                self._load(user, **cols)


if __name__ == "__main__":
    unittest.main()
