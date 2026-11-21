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
        cls.places = cdm.known_places(cls.rr.interlockings)
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

    def line(self, level, user):
        """The master line of the row (level, user_name)."""
        hit = [n for n, r in self.lines if (r["level"], r["user_name"]) == (level, user)]
        self.assertEqual(len(hit), 1, (level, user))
        return hit[0]

    @staticmethod
    def ends():
        """{block: control points of its end switches} from the drawing (SkipTest without the plugin)."""
        tsdm.Files.setUpClass()
        with cdm.pd.cache_on():
            return cdm.block_end_cps(cdm.master_lines(), cdm.railroad.Railroad().interlockings)


class RowRules(Master):
    def test_the_committed_rows_hold_on_every_level(self):
        self.assertEqual({r["level"] for _n, r in self.lines}, {"1", "2", "3"})
        self.assertEqual(cdm.row_problems(self.lines, self.cps, places=self.places), [])
        self.assertEqual(cdm.check_rows(self.lines, self.helix), [])

    def test_a_cp_is_one_of_its_levels(self):
        got = cdm.row_problems(self.edited({("2", "Switch 107"): dict(cp="CP 201"),
                                            ("1", "OS Switch 9"): dict(cp="CP 107")}), self.cps, ends_cps={},
                               places=self.places)
        self.assertProblem(r"\(level 2 turnout Switch 107\): cp 'CP 201' is no level 2 control point", got)
        self.assertProblem(r"\(level 1 block OS Switch 9\): cp 'CP 107' is no level 1 control point", got)

    def test_a_line_blocks_cp_lists_known_places(self):
        """A line block lists the stations or control points it joins (build_device_map.line_cp), of any level (a
        helix block joins two); each is a station of stations.csv or a control point of interlockings.csv."""
        got = cdm.row_problems(self.edited({("1", "Track Barn"): dict(cp="Barn;Nowhere")}), self.cps,
                               places=self.places)
        self.assertEqual(got, [f"devices_generated.csv line {self.line('1', 'Track Barn')} (level 1 block Track Barn): cp "
                               "names Nowhere, no station of stations.csv or control point of interlockings.csv"])
        self.assertEqual(cdm.row_problems(self.edited({("1", "Track Barn"): dict(cp="West Yard;CP 127")}),
                                          self.cps, places=self.places), [])

    def test_a_cp_of_another_level_is_one_of_its_blocks_end_switches(self):
        """A row's level is the band its track is drawn on: Track 127-221 is drawn on the upper band from main level
        CP 127, so it and its detector are in CP 127."""
        ends = self.ends()
        self.assertEqual(ends["Track 127-221"], {"CP 127", "CP 201"})
        self.assertFalse(hasattr(cdm, "KNOWN_CP"))
        self.assertEqual(cdm.row_problems(self.lines, self.cps, ends_cps=ends, places=self.places), [])
        # every line block lists its places now (owner, 2026-11-21), so none leans on its end switches
        self.assertEqual(cdm.row_problems(self.lines, self.cps, ends_cps={}, places=self.places), [])

    def test_a_line_blocks_places_are_the_rules_inputs(self):
        """Each place a line block lists is at one of its end switches or a station whose tracks name it (the rule's
        own inputs, build_device_map.line_cp): a hand edit naming another real place is caught, as a wrong level
        was before the list."""
        tsdm.Files.setUpClass()
        with cdm.pd.cache_on():
            line_places = cdm.line_block_places(cdm.block_end_switches(cdm.master_lines()))
        self.assertEqual(line_places["Track W-1"], {"Brick", "West Yard"})
        self.assertEqual(line_places["Track Helix Inner"], {"Princess", "CP 127"})
        self.assertEqual(cdm.row_problems(self.lines, self.cps, places=self.places, line_places=line_places), [])
        got = cdm.row_problems(self.edited({("1", "Track Barn"): dict(cp="CP 201"),
                                            ("3", "BS 127-221"): dict(cp="CP 201;CP 107")}),
                               self.cps, places=self.places, line_places=line_places)
        self.assertProblem(r"\(level 1 block Track Barn\): cp names CP 201, at no end switch of Track Barn and named "
                           r"by no station's tracks", got)
        self.assertProblem(r"\(level 3 occupancy BS 127-221\): cp names CP 107, at no end switch of Track 127-221",
                           got)
        self.assertEqual(len(got), 2, got)

    def test_a_k_of_n_key_reads_its_strands_ends(self):
        """block_end_cps reads a trial name by its piece (staging_device_map.piece_of), so the k-th of a strand's n
        blocks has the strand's end switches, as a whole strand's key does; a key that is no track key stops."""
        rows = [(2, dict(level="2", layer="block", user_name="Track A", trial_name="Track 127BB-221BA 1/2")),
                (3, dict(level="2", layer="block", user_name="Track B",
                         trial_name="Track 127BB-221BA 2/2, OS Switch 9"))]
        tsdm.Files.setUpClass()
        with cdm.pd.cache_on():
            got = cdm.block_end_cps(rows, cdm.railroad.Railroad().interlockings)
            self.assertEqual(got, {"Track A": {"CP 127", "CP 201"}, "Track B": {"CP 127", "CP 201"}})
            with self.assertRaisesRegex(cdm.DeviceMasterError, "block Track C: 'Track e73 1' is no track trial key"):
                cdm.block_end_cps([(2, dict(level="2", layer="block", user_name="Track C", trial_name="Track e73 1"))],
                                  cdm.railroad.Railroad().interlockings)

    def test_a_field_row_names_all_three(self):
        for col in ("user_name", "system_name", "jmri_name"):
            with self.subTest(col=col):
                got = cdm.row_problems(self.edited({("1", "Switch 1"): {col: ""}}), self.cps)
                self.assertProblem(r"a field device needs a user_name, a system_name and a jmri_name", got)

    def test_a_jmri_name_given_twice(self):
        got = cdm.check_rows(self.edited({("1", "Switch 3"): dict(jmri_name="M2T408"),
                                          ("3", "Head 202R Top"): dict(jmri_name="IH:HART:C3:202R_Bottom")}),
                             self.helix)
        self.assertProblem(r"level 1 turnout Switch 3\): jmri_name 'M2T408' is line \d+'s as well", got)
        self.assertProblem(r"level 3 head Head 202R Top\): jmri_name 'IH:HART:C3:202R_Bottom' is line \d+'s", got)

    def test_every_turnout_has_one_lcc_alias(self):
        for level, alias, turnout in (("2", "DCC Switch 101", "Switch 101"), ("1", "DCC Switch 1", "Switch 1")):
            with self.subTest(level=level):
                got = cdm.check_rows(self.edited(drop={(level, alias)}), self.helix)
                self.assertProblem(rf"level {level} turnout {turnout}\): 0 LCC aliases carry its DCC address", got)

    def test_a_detector_is_wired_exactly_when_it_is_a_field_device(self):
        got = cdm.row_problems(self.edited({("1", "BS Barn"): dict(detector="planned"),
                                            ("2", "BS Switch 101"): dict(detector="wired", system_name="M2S1")}),
                               self.cps)
        self.assertProblem(r"level 1 occupancy BS Barn\): assignment field with detector 'planned'", got)
        self.assertProblem(r"level 2 occupancy BS Switch 101\): assignment virtual with detector 'wired'", got)

    def test_a_row_kept_by_hand_is_a_field_device(self):
        got = cdm.row_problems(self.edited({("2", "Track 101-111"): dict(written_by="")}), self.cps)
        self.assertProblem(r"level 2 block Track 101-111\): kept by hand, so a field device, not assignment none",
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
        lines = self.edited({("2", "Track 101-111"): dict(user_name="Track K-1")})
        self.assertProblem(r"blocks named on more than one level: \['Track Helix Inner', 'Track Helix Outer', "
                           r"'Track K-1'\]", cdm.check_rows(lines, self.helix))
        self.assertProblem(r"blocks named on more than one level: .*exactly the helix blocks",
                           cdm.check_rows(self.lines, self.helix | {"Track X"}))

    def test_a_block_has_one_occupancy_row_on_any_level(self):
        got = cdm.check_rows(self.edited(drop={("3", "BS Helix Inner")}), self.helix)
        self.assertProblem(r"block Track Helix Inner has 0 occupancy rows naming it", got)
        got = cdm.check_rows(self.edited({("2", "BS 101-111"): dict(blocks="Track Barn")}), self.helix)
        self.assertProblem(r"block Track Barn has 2 occupancy rows naming it", got)
        self.assertProblem(r"block Track 101-111 has 0 occupancy rows", got)

    def test_names_given_twice(self):
        got = cdm.check_rows(self.edited({("3", "FB Switch 201 N"): dict(system_name="M2S470"),
                                          ("1", "Switch 3"): dict(user_name="Switch 1")}), self.helix)
        self.assertProblem(r"level 3 fb FB Switch 201 N\): system_name 'M2S470' is line \d+'s as well", got)
        self.assertProblem(r"level 1 turnout Switch 1\): user_name 'Switch 1' is line \d+'s as well", got)

    def test_a_dcc_address_or_device_on_two_levels(self):
        got = cdm.check_rows(self.edited({("2", "Switch 101"): dict(system_name="M2T408", dcc="100"),
                                          ("2", "DCC Switch 101"): dict(dcc="100", system_name="MTT100")}),
                             self.helix)
        one, alias = self.line("1", "Switch 1"), self.line("1", "DCC Switch 1")
        self.assertProblem(rf"level 2 turnout Switch 101\): system_name 'M2T408' is line {one}'s as well", got)
        self.assertProblem(rf"level 2 turnout Switch 101\): dcc '100' is line {one}'s as well", got)
        self.assertProblem(rf"level 2 turnout DCC Switch 101\): system_name 'MTT100' is line {alias}'s as well", got)
        # one device is one row whatever its layer: a head planned on a feedback sensor's name
        got = cdm.check_rows(self.edited({("3", "Head 202R Top"): dict(system_name="M2S470")}), self.helix)
        fb = self.line("1", "FB Switch 1 N")
        self.assertProblem(rf"level 3 head Head 202R Top\): system_name 'M2S470' is line {fb}'s as well", got)

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

    def problems(self, edit=None, drop=()):
        return cdm.check_tables([r for _n, r in self.edited(edit, drop)], self.rr)

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
                      self.problems({("2", "Track 101-111"): dict(user_name="Track Nowhere")}))

    def test_a_station_is_its_comment(self):
        self.assertIn("block Track Barn: stop is empty, but its comment in tables.xml marks a station",
                      self.problems({("1", "Track Barn"): dict(stop="")}))
        self.assertIn("block Track East Ext: stop is yes, but its comment in tables.xml does not mark a station",
                      self.problems({("1", "Track East Ext"): dict(stop="yes")}))
        self.assertIn("block Track 101-111: stop is yes, but its comment in tables.xml does not mark a station",
                      self.problems({("2", "Track 101-111"): dict(stop="yes")}))

    def test_the_rows_of_a_helix_block_agree_on_its_stop(self):
        """A helix block's rows (staging and main or upper) agree on its stop, with no list of known exceptions."""
        self.assertFalse(hasattr(cdm, "KNOWN_STOP"))
        got = self.problems({("3", "Track Helix Inner"): dict(stop="")})
        self.assertEqual(got, ["block Track Helix Inner: its rows disagree on stop (empty, yes)"])
        got = self.problems({("1", "Track Helix Outer"): dict(stop="")})
        self.assertEqual(got, ["block Track Helix Outer: its rows disagree on stop (empty, yes)"])

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

    def test_a_layer_no_device_map_holds_is_reported(self):
        rows = [r for _n, r in self.edited({("1", "Switch 1"): dict(layer="sensor")})]
        self.assertIn("sensor Switch 1: a device map holds no sensor rows", cdm.check_tables(rows, self.rr))

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
        self.assertIn("ok: devices_generated.csv, stations.csv, masts.csv hold their rules", out.getvalue())

    def test_without_the_drawing_the_rest_still_runs(self):
        self.assertEqual(cdm.check(None), [])

    def test_a_hand_kept_row_off_staging_has_no_drawing_reader(self):
        tsdm.Files.setUpClass()
        lines = [(n, dict(r, written_by="") if (r["level"], r["user_name"]) == ("2", "Track 101-111") else r)
                 for n, r in cdm.master_lines()]
        got = cdm.check_drawing(tsdm.Files.band, lines)
        self.assertEqual(len(got), 1, got)
        self.assertIn("level 2 block Track 101-111): kept by hand, but only staging's hand-kept rows", got[0])


class CheckParts(Master):
    """A broken staging row is reported once, and the tables part still runs."""

    def run_check(self, lines, load):
        from unittest import mock
        tsdm.Files.setUpClass()                 # the band (it loads the staging rows itself)
        with mock.patch.object(cdm, "master_lines", return_value=lines), \
                mock.patch.object(cdm.sdm, "load", side_effect=load) as loaded:
            return cdm.check(tsdm.Files.band), loaded

    def test_a_bad_staging_row_skips_the_drawing_and_not_the_tables(self):
        lines = self.edited({("1", "OS Switch 9"): dict(cp="Nowhere"), ("2", "Switch 107"): dict(jmri_name="IT107")})
        got, loaded = self.run_check(lines, cdm.sdm.StagingMapError("load ran"))
        self.assertFalse(loaded.called)
        self.assertEqual(len([p for p in got if "cp 'Nowhere'" in p]), 1, got)
        self.assertIn("turnout Switch 107: tables.xml has 'IT:HART:C3:107', not IT107", got)

    def test_a_drawing_error_leaves_the_tables_check_running(self):
        lines = self.edited({("2", "Switch 107"): dict(jmri_name="IT107")})
        got, _loaded = self.run_check(lines, cdm.sdm.StagingMapError("the drawing broke"))
        self.assertIn("the drawing broke", got)
        self.assertIn("turnout Switch 107: tables.xml has 'IT:HART:C3:107', not IT107", got)


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
                                ("OS Switch 9", dict(cp="Nowhere"), "cp 'Nowhere' is no level 1 control point"),
                                ("Track Barn", dict(cp="Nowhere"), "cp names Nowhere, no station"),
                                ("FB Switch 1 N", dict(trial_name="Track Nowhere"), "a fb row has a trial_name"),
                                ("Switch 3", dict(trial_name="Switch 1"), r"trial_name Switch 1 is line \d+'s as well")):
            with self.subTest(msg=msg), self.assertRaisesRegex(sdm.StagingMapError, msg):
                self._load(user, **cols)

    def test_the_interlockings_are_the_ones_given(self):
        import shutil
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        src = cdm.railroad.Sources.under().interlockings
        il = tmp / src.name
        il.write_text(src.read_text(encoding="utf-8") + "1,Nowhere,15,,\n", encoding="utf-8")

        def edit(rows):
            next(r for r in rows if r["level"] == "1" and r["user_name"] == "OS Switch 9")["cp"] = "Nowhere"
        dm = self._copy(edit)[0]
        with self.assertRaisesRegex(sdm.StagingMapError, "cp 'Nowhere' is no level 1 control point"):
            sdm.load(self.band, device_map=dm)
        sdm.load(self.band, device_map=dm, interlockings_path=il)


if __name__ == "__main__":
    unittest.main()
