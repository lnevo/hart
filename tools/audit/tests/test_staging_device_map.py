"""staging_device_map.py: staging's facts in the device map's form (hand-kept), their rules, and what reads them."""
from __future__ import annotations

import csv
import io
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
import check_device_master as cdm  # noqa: E402
import staging_device_map as sdm  # noqa: E402


def band(nodes, strands):
    return {"nodes": nodes, "strands": strands}


def sw(label, **legs):
    return dict(kind="switch", label=label, ins={}, outs={}, **legs)


def row(layer, user, system, jmri, notes="", level="1", **facts):
    """A device map row (build_device_map.COLUMNS, and its role) of staging, kept by hand, a field device."""
    return dict(level=level, cp="", layer=layer, user_name=user, system_name=system, jmri_name=jmri, node="", dcc="",
                comment="", trial_name="", notes=notes, role=sdm.devices.role_of(layer, user, system, jmri),
                assignment="field", written_by="", **{c: facts.get(c, "") for c in sdm.railroad.DEVICE_FACTS})


def numbered(rows):
    """(line, row) as check_device_master reads the master."""
    return list(enumerate(rows, 2))


class SwitchFacts(unittest.TestCase):
    """The staging switches come from hartlib.railroad (le_common.staging_switches); a file it cannot read stops with
    StagingMapError, as every other staging map problem does."""

    def test_closed_legs_are_switch_legs_csv(self):
        with (ROOT / "jmri/layouts/hart/data/switch_legs.csv").open(newline="", encoding="utf-8") as fh:
            want = {r["os_block"]: r["closed_leg"] for r in csv.DictReader(fh)}
        self.assertEqual(sdm.closed_legs(), want)

    def test_a_facts_error_is_a_staging_map_error(self):
        def bad():
            raise sdm.lc.BuildError("staging switches: switches.csv line 3: hand is L, R or blank, got 'X'")
        with unittest.mock.patch.object(sdm.lc, "staging_switches", bad), \
                self.assertRaisesRegex(sdm.StagingMapError, "switches.csv line 3"):
            sdm.closed_legs()


class ShortTracks(unittest.TestCase):
    """A short track between two switches with no block of its own takes the OS block whose gap it sits inside, from
    short_tracks_staging.csv keyed by its two switches (owner, 2026-11-20)."""

    @staticmethod
    def band(*strands):
        nodes = {"N35": dict(kind="switch", label="35"), "N37": dict(kind="switch", label="37"),
                 "N39": dict(kind="switch", label="39"), "E": dict(kind="end", label="")}
        return {"nodes": nodes, "strands": {sid: {"src": (a, "B"), "dst": (b, "A")} for sid, a, b in strands}}

    NAMES = {"blocks": {}, "os": {"N35": "OS Switch 35a", "N37": "OS Switch 37", "N39": "OS Switch 39"}}

    def read(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "short.csv"
            p.write_text("switch_a,switch_b,block,notes\n" + text, encoding="utf-8")
            return sdm.read_short_tracks(p)

    def test_the_committed_file(self):
        self.assertEqual(sdm.read_short_tracks(), {("35", "37"): ("OS Switch 35a", 2)})

    def test_bad_rows_stop(self):
        for text, msg in (("37,35,OS Switch 35a,\n35,37,OS Switch 37,\n", "given a block twice"),
                          ("35,35,OS Switch 35a,\n", "two switch numbers"),
                          ("35,37,Track 35-37,\n", "an OS block")):
            with self.subTest(msg=msg), self.assertRaisesRegex(sdm.StagingMapError, msg):
                self.read(text)

    def test_the_track_takes_its_row_keyed_by_its_switches(self):
        b = self.band(("s", "N37", "N35"))
        got, bad = sdm.short_track_blocks(b, self.NAMES, ["s"], self.read("35,37,OS Switch 35a,\n"))
        self.assertEqual((got, bad), ({"s": ["OS Switch 35a"]}, []))

    def test_no_row_another_switchs_block_or_a_stale_row_stops(self):
        b = self.band(("s", "N35", "N37"))
        cases = (("", "has no block: give it"),
                 ("35,37,OS Switch 39,\n", "the OS block of neither of its switches"),
                 ("35,37,OS Switch 35a,\n37,39,OS Switch 37,\n", "line 3: Switch 37 to Switch 39: the staging "
                                                                  "drawing has no such track"))
        for text, msg in cases:
            with self.subTest(msg=msg):
                _got, bad = sdm.short_track_blocks(b, self.NAMES, ["s"], self.read(text))
                self.assertTrue(any(msg in p for p in bad), bad)

    def test_a_row_for_a_track_with_its_own_block_stops(self):
        b = self.band(("s", "N35", "N37"))
        names = dict(self.NAMES, blocks={"s": ["Track X"]})
        _got, bad = sdm.short_track_blocks(b, names, ["s"], self.read("35,37,OS Switch 35a,\n"))
        self.assertEqual(bad, ["short_tracks_staging.csv line 2: Switch 35 to Switch 37: the device map gives it a "
                               "block of its own"])

    def test_two_tracks_between_the_same_switches_are_ambiguous(self):
        b = self.band(("s", "N35", "N37"), ("t", "N37", "N35"))
        _got, bad = sdm.short_track_blocks(b, self.NAMES, ["s", "t"], self.read("35,37,OS Switch 35a,\n"))
        self.assertTrue(bad and all("2 tracks join those switches" in p for p in bad[:2]), bad)

    def test_a_track_to_an_end_with_no_block_stops(self):
        _got, bad = sdm.short_track_blocks(self.band(("s", "N35", "E")), self.NAMES, ["s"], {})
        self.assertEqual(bad, ["track s: no block in the device map, and it does not run between two switches"])


class Pure(unittest.TestCase):
    def test_mast_kind_follows_the_row(self):
        self.assertEqual(sdm.mast_kind(dict(switch="1", protects="OS Switch 1")), "turnout")
        self.assertEqual(sdm.mast_kind(dict(switch="", protects="Track S-1 West")), "anchor")
        self.assertEqual(sdm.mast_kind(dict(switch="", protects="")), "end bumper")

    def test_track_placeholder_numbers_only_split_tracks(self):
        self.assertEqual(sdm.track_placeholder("17C-29C", 1, 1), "Track 17C-29C")
        self.assertEqual(sdm.track_placeholder("17C-29C", 2, 3), "Track 17C-29C 2/3")
        self.assertEqual(sdm.TRACK_RE.fullmatch("Track 1C-5A #2").groups(), ("1C-5A #2", None, None))
        self.assertEqual(sdm.TRACK_RE.fullmatch("Track 37C-39C #2 1/2").groups(), ("37C-39C #2", "1", "2"))

    def test_crossover_halves_get_their_own_os_placeholder(self):
        b = band({"a": sw("7"), "b": sw("7"), "c": sw("9"), "d": sw("11")},
                 {"x7": dict(src=("a", "C"), dst=("b", "C")), "e1": dict(src=("c", "A"), dst=("a", "A")),
                  "e2": dict(src=("b", "A"), dst=("d", "A"))})
        turnouts, os_, strands = sdm.placeholders(b)
        self.assertEqual(turnouts, {"a": "Switch 7", "b": "Switch 7", "c": "Switch 9", "d": "Switch 11"})
        self.assertEqual(os_, {"a": "OS 7 A-9A", "b": "OS 7 A-11A", "c": "OS Switch 9", "d": "OS Switch 11"})
        self.assertEqual({k: v[0] for k, v in strands.items()}, {"e1": "7A-9A", "e2": "7A-11A"})   # x7: none

    def test_track_references_survive_a_new_export(self):
        """The drawing's edge and node ids change with every export; the references are by switch and leg, so the
        same track gets the same reference under other ids, and a run's pieces and blocks count from its lower
        switch whichever way the export draws them."""
        def drawn(ids, flip):
            n1, n3, t, e1, e2, e3 = ids
            a, b = ((n3, "A"), (t, "A")) if flip else ((t, "A"), (n3, "A"))
            nodes = {n1: sw("1"), n3: sw("3"), t: dict(kind="turnback", label=""), "E": dict(kind="end", label="")}
            return band(nodes, {e1: dict(src=(n1, "B"), dst=(t, "A")), e2: dict(src=a, dst=b),
                                e3: dict(src=(n3, "B"), dst=("E", "A"))})
        one = sdm.piece_refs(drawn(("N1", "N3", "T", "e1", "e2", "e3"), False))
        two = sdm.piece_refs(drawn(("Q7", "Q8", "Q9", "k5", "k6", "k7"), True))
        self.assertEqual(sorted(r for r, _a in one.values()), ["1B-3A #1", "1B-3A #2", "3B-end"])
        self.assertEqual(sorted(r for r, _a in two.values()), ["1B-3A #1", "1B-3A #2", "3B-end"])
        self.assertEqual(one["e2"][0], two["k6"][0])
        self.assertNotEqual(one["e2"][1], two["k6"][1])     # drawn the other way: its blocks are read reversed

    def test_two_runs_with_the_same_ends_stop(self):
        b = band({"a": sw("1"), "b": sw("3")}, {"e1": dict(src=("a", "B"), dst=("b", "A")),
                                                "e2": dict(src=("b", "A"), dst=("a", "B"))})
        with self.assertRaisesRegex(sdm.StagingMapError, "both run 1B-3A"):
            sdm.piece_refs(b)

    def test_a_switch_label_that_is_no_number_stops(self):
        with self.assertRaisesRegex(sdm.StagingMapError, "no switch number"):
            sdm.placeholders(band({"a": sw("7x")}, {}))

    def test_a_block_with_no_occupancy_row_stops(self):
        rows = [row("block", "Track S-1", "IB1", "IB1"), row("block", "Track S-1 West", "IB2", "IB2"),
                row("occupancy", "BS S-1", "M2S206", "M2S206", blocks="Track S-1", detector="wired")]
        self.assertEqual(cdm.check_rows(numbered(rows), set()),
                         ["devices.csv line 3: block Track S-1 West has 0 occupancy rows naming it (none), not one"])

    def test_a_shared_detector_serves_both_blocks(self):
        rows = [row("block", "Track S-1", "IB1", "IB1"), row("block", "Track S-1 West", "IB2", "IB2"),
                row("occupancy", "BS S-1", "M2S206", "M2S206", notes="blocks Track S-1; Track S-1 West",
                    blocks="Track S-1;Track S-1 West", detector="wired")]
        self.assertEqual(cdm.check_rows(numbered(rows), set()), [])

    def test_the_blocks_column_is_read_and_never_the_notes(self):
        r = row("occupancy", "BS S-1", "M2S206", "M2S206", notes="blocks Track X", blocks="Track S-1;Track S-1 West",
                detector="wired")
        self.assertEqual(sdm.occupancy_blocks(r), ["Track S-1", "Track S-1 West"])
        self.assertEqual(sdm.occupancy_blocks(dict(r, blocks="")), [])

    def test_fact_columns_are_checked(self):
        facts = sdm.railroad.device_facts
        self.assertEqual(facts(row("occupancy", "BS S-1", "M2S206", "M2S206", blocks="Track S-1", detector="wired")),
                         [])
        for r, msg in ((row("occupancy", "BS S-1", "M2S206", "M2S206", detector="wired"), "names no blocks"),
                       (row("occupancy", "BS S-1", "M2S206", "M2S206", blocks="Track S-1", detector="yes"),
                        "is not one of"),
                       (row("occupancy", "BS S-1", "", "IS:X", blocks="Track S-1", detector="planned"),
                        "needs system name"),
                       (row("occupancy", "BS S-1", "M2S1", "IS:X", blocks="Track S-1", detector="none"),
                        "has no system name"),
                       (row("block", "Track S-1", "IB1", "IB1", stop="y"), "is not yes or empty"),
                       (row("block", "Track S-1", "IB1", "IB1", blocks="Track S-1"), "a block row has blocks"),
                       (row("mast", "Mast 2L", "IF$x", "IF$x", switch="1"), "names no facing block"),
                       (row("mast", "Mast 2L", "IF$x", "IF$x", switch="1A", facing="Track A"), "not a switch number"),
                       (row("turnout", "Switch 1", "MT1", "MT1", facing="Track A"), "a turnout row has facing")):
            with self.subTest(msg=msg):
                self.assertTrue(any(msg in p for p in facts(r)), facts(r))

    def test_a_staging_station_is_its_stop_token(self):
        self.assertTrue(cdm.stop_token("Track K-1; occupancy Block 1-1 / M2S100; stop"))
        self.assertTrue(cdm.stop_token("stop"))
        self.assertFalse(cdm.stop_token("Hidden throat; not a station"))
        self.assertFalse(cdm.stop_token(None))

    def test_signal_rows_in_the_plugins_order(self):
        m = dict(signal="10LA", toward="9", run=["9", ""], names=["EH-2"], edge_cm=61.0, cm_from_toward=61.0,
                 dir="west", signal_kind="virtual", heads=1, schematic_edge="n5", schematic_toward_node="NEW:9")
        got = sdm.signal_rows([m, dict(m, signal="2L"), dict(m, signal="10L")])
        self.assertEqual([r["mast"] for r in got], ["2L", "10L", "10LA"])
        self.assertEqual(got[0]["_edge"], "n5")
        self.assertEqual(got[0]["source"], "le_panel")


class Files(unittest.TestCase):
    """The committed files hold their rules, and each kind of break stops naming the place."""

    @classmethod
    def setUpClass(cls):
        import build_layout_le as blb
        try:
            cls.band, _opts, _core = sdm.staging_band()
        except (blb.BuildError, SystemExit) as exc:
            raise unittest.SkipTest(f"schematic-maps plugin not available: {exc}")
        cls.names = sdm.load(cls.band)

    def test_the_committed_files_hold_their_rules(self):
        self.assertEqual(cdm.check(self.band), [])
        self.assertEqual(len(set(self.names["turnouts"].values())), 20)
        self.assertEqual(len(self.names["masts"]), 30)
        self.assertEqual(self.names["idents"]["turnouts"]["TOL34511"], "TO1")         # switches.csv le_ident

    def _copy(self, edit):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        rows = [dict(r) for r in sdm.devices.load(sdm.DEVICE_MAP)]        # the master's rows, whole
        edit(rows)
        out = tmp / "devices.csv"
        out.write_text(sdm.devices.master_text(rows), encoding="utf-8")
        return out, sdm.read_device_rows(out)

    def _without(self, ph):
        def edit(rows):
            for r in rows:
                r["trial_name"] = ", ".join(p for p in sdm.split_names(r["trial_name"]) if p != ph)
        return self._copy(edit)[0]

    def test_a_missing_block_of_a_split_track_stops(self):
        with self.assertRaisesRegex(sdm.StagingMapError, "track 5C-7B: blocks .* are not 1/n to n/n"):
            sdm.load(self.band, device_map=self._without("Track 5C-7B 1/2"))

    def test_a_missing_turnout_placeholder_stops(self):
        with self.assertRaisesRegex(sdm.StagingMapError, "no turnout row has trial_name Switch 1"):
            sdm.load(self.band, device_map=self._without("Switch 1"))

    def test_a_device_not_in_tables_stops(self):
        from hartlib import railroad

        def edit(rows):
            hit = next(r for r in rows if r["user_name"] == "Switch 1")
            hit["system_name"] = hit["jmri_name"] = "M2T999"       # a field device: the two are one
        out, _rows = self._copy(edit)
        bad = cdm.check_tables([r for _n, r in cdm.master_lines(out)], railroad.Railroad())
        self.assertTrue(any("turnout Switch 1: tables.xml has 'M2T408', not M2T999" in b for b in bad), bad)

    def test_a_mast_on_a_switch_with_no_turnout_row_stops(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        bad = tmp / "masts.csv"
        bad.write_text(sdm.MASTS.read_text(encoding="utf-8").replace("Mast 2L,Brick,1,", "Mast 2L,Brick,99,"),
                       encoding="utf-8")
        with self.assertRaisesRegex(sdm.StagingMapError, "Mast 2L is on switch '99', which no turnout row"):
            sdm.load(self.band, masts_path=bad)

    def test_the_run_walk_counts_a_block_through_a_turnback_once(self):
        runs = sdm.run_blocks(self.band, self.names)
        for _start, seq, _end in runs:
            self.assertFalse([b for a, b in zip(seq, seq[1:]) if a == b], seq)
        self.assertIn(["Track Brick-Plane"], [seq for _s, seq, _e in runs])
        chains = sdm.staging_chains(self.band, self.names)
        self.assertEqual(len(chains), len(runs))
        # the track from Switch 35 to Switch 37 is all OS Switch 35a: its gap is at Switch 37's points
        self.assertTrue(any({e[0] for e in c["ends"]} == {"TOR36", "TO113"} and
                            c["blocks"] == ["OS Switch 35a"] for c in chains))

    def test_the_signal_plan_reads_back(self):
        masts = sdm.load_signal_masts()
        self.assertEqual(len(masts), 30)
        got = sdm.layer_files.read("signals", "staging", sdm.pd.DATA)
        self.assertEqual(got["signals"], sdm.signal_rows(masts))
        self.assertEqual(got["source"], sdm.SIGNALS_SOURCE)

    def test_the_command_is_a_check_only(self):
        import contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            cdm.main([])
        self.assertIn("--check is the only mode", err.getvalue())


class DeviceMapBuild(unittest.TestCase):
    """build_layout_le.py draws staging from these files."""

    @classmethod
    def setUpClass(cls):
        import contextlib
        import build_layout_le as blb
        cls.B = blb
        try:
            blb.plugin()
        except blb.BuildError as exc:
            raise unittest.SkipTest(f"plugin not available: {exc}")
        with contextlib.redirect_stdout(io.StringIO()):     # on the generator's base (ADR-029)
            cls.data, cls.P, cls.names, _bands = blb.build(levels="staging", as_live=True, approved=None)
        from hartlib import tables
        cls.tables = tables
        cls.panel = tables.layout_editor(tables.loads(cls.data).root, blb.TEMPLATE_PANEL)

    def test_every_staging_mast_is_placed_once_with_no_entry_exit_sensor(self):
        placed = [m["mast"] for m in self.B.slots_module().Index(self.panel).masts()]
        self.assertEqual(sorted(placed), sorted(sdm.mast_facts()))
        self.assertFalse([el for el in self.panel.iter() if any(k.endswith("boundsensor") for k in el.attrib)])

    def test_the_status_cluster_is_on_the_panel_by_name(self):
        sensors = {el.get("sensor") for el in self.panel.findall("sensoricon")}
        self.assertEqual(sensors, {"Bridge HBLOOP", "SML Mode", "Track Power"})
        self.assertEqual([el.get("signalhead") for el in self.panel.findall("signalheadicon")], ["IH9990"])
        self.assertTrue(self.tables.generated_panel(self.panel))

    def test_a_staging_mast_on_an_unknown_switch_is_a_build_error(self):
        import le_checks
        from unittest import mock
        with mock.patch.object(sdm, "mast_facts", side_effect=sdm.StagingMapError("x is on switch 99")):
            with self.assertRaisesRegex(self.B.BuildError, "staging device map: x is on switch 99"):
                le_checks.check_device_masts(self.P, [], self.B.plugin()[1])

    def test_the_panel_attributes_are_the_items_files(self):
        import panel_items
        attrs, _opts = panel_items.panel_attributes(panel_items.load(self.B.PANEL_ITEMS))
        for k, v in attrs.items():
            if k != "scrollable":                       # the build sets it when the panel outgrows its window
                self.assertEqual(self.panel.get(k), v, k)


if __name__ == "__main__":
    unittest.main()
