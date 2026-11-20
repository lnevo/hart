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
import staging_device_map as sdm  # noqa: E402


def band(nodes, strands):
    return {"nodes": nodes, "strands": strands}


def sw(label, **legs):
    return dict(kind="switch", label=label, ins={}, outs={}, **legs)


def row(layer, user, system, jmri, notes=""):
    """A device map row (build_device_map.COLUMNS) of staging."""
    return dict(level="1", cp="", layer=layer, user_name=user, system_name=system, jmri_name=jmri, node="", dcc="",
                comment="", trial_name="", notes=notes)


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


class Pure(unittest.TestCase):
    def test_mast_kind_follows_the_row(self):
        self.assertEqual(sdm.mast_kind(dict(switch="1", protects="OS Switch 1")), "turnout")
        self.assertEqual(sdm.mast_kind(dict(switch="", protects="Track S-1 West")), "anchor")
        self.assertEqual(sdm.mast_kind(dict(switch="", protects="")), "end bumper")

    def test_track_placeholder_numbers_only_split_tracks(self):
        self.assertEqual(sdm.track_placeholder("e23", 1, 1), "Track e23")
        self.assertEqual(sdm.track_placeholder("e23", 2, 3), "Track e23 2/3")
        self.assertEqual(sdm.TRACK_RE.fullmatch("Track e9+e10").group(1), "e9+e10")
        self.assertEqual(sdm.TRACK_RE.fullmatch("Track e16.0 1/2").groups(), ("e16.0", "1", "2"))

    def test_crossover_halves_get_their_own_os_placeholder(self):
        b = band({"a": sw("7"), "b": sw("7"), "c": sw("9")},
                 {"x7": dict(src=("a", "C"), dst=("b", "C")), "e1": dict(src=("c", "A"), dst=("a", "A"))})
        turnouts, os_, strands = sdm.placeholders(b)
        self.assertEqual(turnouts, {"a": "Switch 7", "b": "Switch 7", "c": "Switch 9"})
        self.assertEqual(os_, {"a": "OS 7 at a", "b": "OS 7 at b", "c": "OS Switch 9"})
        self.assertEqual(strands, ["e1"])           # the strand inside the crossover carries no block

    def test_a_switch_label_that_is_no_number_stops(self):
        with self.assertRaisesRegex(sdm.StagingMapError, "no switch number"):
            sdm.placeholders(band({"a": sw("7x")}, {}))

    def test_a_block_with_no_occupancy_row_stops(self):
        rows = [row("block", "Track S-1", "IB1", "IB1"), row("block", "Track S-1 West", "IB2", "IB2"),
                row("occupancy", "BS S-1", "M2S206", "M2S206", notes="blocks Track S-1")]
        with self.assertRaisesRegex(sdm.StagingMapError, "Track S-1 West"):
            sdm.check_rows(rows)

    def test_a_shared_detector_serves_both_blocks(self):
        rows = [row("block", "Track S-1", "IB1", "IB1"), row("block", "Track S-1 West", "IB2", "IB2"),
                row("occupancy", "BS S-1", "M2S206", "M2S206", notes="blocks Track S-1; Track S-1 West")]
        sdm.check_rows(rows)

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
        self.assertEqual(sdm.check(self.band), [])
        self.assertEqual(len(set(self.names["turnouts"].values())), 20)
        self.assertEqual(len(self.names["masts"]), 37)
        self.assertEqual(self.names["idents"]["turnouts"]["TOL34511"], "TO1")         # switches.csv le_ident

    def _copy(self, edit):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        with sdm.DEVICE_MAP.open(newline="") as f:
            rows = list(csv.DictReader(f))
        edit(rows)
        out = tmp / "device_map_staging.csv"
        out.write_text(sdm.bdm.csv_text(rows), encoding="utf-8")
        return out, rows

    def _without(self, ph):
        def edit(rows):
            for r in rows:
                r["trial_name"] = ", ".join(p for p in sdm.split_names(r["trial_name"]) if p != ph)
        return self._copy(edit)[0]

    def test_a_missing_block_of_a_split_track_stops(self):
        with self.assertRaisesRegex(sdm.StagingMapError, "track e22: blocks .* are not 1/n to n/n"):
            sdm.load(self.band, device_map=self._without("Track e22 2/3"))

    def test_a_missing_turnout_placeholder_stops(self):
        with self.assertRaisesRegex(sdm.StagingMapError, "no turnout row has trial_name Switch 1"):
            sdm.load(self.band, device_map=self._without("Switch 1"))

    def test_a_device_not_in_tables_stops(self):
        from hartlib import railroad

        def edit(rows):
            next(r for r in rows if r["user_name"] == "Switch 1")["system_name"] = "M2T999"
        _out, rows = self._copy(edit)
        bad = sdm.check_tables(rows, railroad.Railroad())
        self.assertTrue(any("turnout Switch 1: tables.xml has 'M2T408', not M2T999" in b for b in bad), bad)

    def test_control_points_follow_the_overrides(self):
        self.assertEqual(sdm.check_control_points(), [])
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        bad = tmp / "cps.csv"
        bad.write_text(sdm.CPS.read_text(encoding="utf-8").replace('"1,3"', '"1"'), encoding="utf-8")
        self.assertTrue(sdm.check_control_points(bad))
        spaced = tmp / "spaced.csv"                     # spaces and an empty entry in a switches cell are no switch
        spaced.write_text(sdm.CPS.read_text(encoding="utf-8").replace('"1,3"', '" 1, 3,"'), encoding="utf-8")
        self.assertEqual(sdm.check_control_points(spaced), [])

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
        self.assertEqual(len(masts), 37)
        import json
        got = json.loads((sdm.pd.DATA / "staging.signals.json").read_text(encoding="utf-8"))
        self.assertEqual(got["signals"], sdm.signal_rows(masts))
        self.assertEqual(got["source"], sdm.SIGNALS_SOURCE)

    def test_the_command_is_a_check_only(self):
        import contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            sdm.main([])
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
        base = blb.paths.TABLES_XML          # the build starts from this checkout's tables.xml
        with contextlib.redirect_stdout(io.StringIO()):
            cls.data, cls.P, cls.names, _bands = blb.build(base, levels="staging", as_live=True, approved=None)
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

    def test_the_boundary_contract_follows_the_drawn_panel(self):
        self.B.check_boundaries(self.panel)                     # the committed file: every mast where it says
        text = self.B.BOUNDARIES.read_text(encoding="utf-8")
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        self.assertIn("anchor,AG31,east,Mast 8RA", text)          # the committed row the first case moves
        for old, new, why in (("anchor,AG31,east,Mast 8RA", "anchor,AG34,east,Mast 8RA", "Mast 8RA: recorded anchor AG34 east"),
                              ("turnout,TO1,C,Mast 14R", "turnout,TO1,B,Mast 14R", "Mast 14R: recorded turnout TO1 B")):
            with self.subTest(row=old):
                path = tmp / "b.csv"
                path.write_text(text.replace(old, new), encoding="utf-8")
                with self.assertRaisesRegex(self.B.BuildError, why):
                    self.B.check_boundaries(self.panel, path)

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
