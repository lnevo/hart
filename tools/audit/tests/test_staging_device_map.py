"""staging_device_map.py: staging's facts in the main and upper levels' shape, and the reader the trial builds from."""
from __future__ import annotations

import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
import staging_device_map as sdm  # noqa: E402


def band(nodes, strands):
    return {"nodes": nodes, "strands": strands}


def sw(label, **legs):
    return dict(kind="switch", label=label, ins={}, outs={}, **legs)


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
        rows = [sdm.row("block", "Track S-1", "IB1", "IB1"), sdm.row("block", "Track S-1 West", "IB2", "IB2"),
                sdm.row("occupancy", "BS S-1", "M2S206", "M2S206", notes="blocks Track S-1")]
        with self.assertRaisesRegex(sdm.StagingMapError, "Track S-1 West"):
            sdm.check_rows(rows)

    def test_a_shared_detector_serves_both_blocks(self):
        rows = [sdm.row("block", "Track S-1", "IB1", "IB1"), sdm.row("block", "Track S-1 West", "IB2", "IB2"),
                sdm.row("occupancy", "BS S-1", "M2S206", "M2S206", notes="blocks Track S-1; Track S-1 West")]
        sdm.check_rows(rows)


class AgainstTheFrozenBinding(unittest.TestCase):
    """The committed files give the staging band the same binding the build reads off the frozen panel today."""

    @classmethod
    def setUpClass(cls):
        import build_layout_le as blb
        try:
            cls.band, _opts, core = sdm.staging_band()
        except (blb.BuildError, SystemExit) as exc:
            raise unittest.SkipTest(f"schematic-maps plugin not available: {exc}")
        import le_inputs
        cls.frozen = blb.staging_names(cls.band, le_inputs.load(), core.tidy)
        cls.names = sdm.load(cls.band)

    def test_turnouts_os_blocks_and_normal_legs_match(self):
        for key in ("turnouts", "os", "blocks", "normal"):
            self.assertEqual(self.names[key], self.frozen[key], key)

    def test_turnout_idents_are_switches_csv_le_idents(self):
        self.assertEqual(self.names["idents"]["turnouts"], self.frozen["idents"]["turnouts"])

    def test_every_frozen_mast_is_read_with_its_blocks_and_kind(self):
        import le_inputs
        want = {m["mast"]: (m["facing"], m["protects"], m["kind"], m["hidden"], list(m["icon"]))
                for m in le_inputs.load().masts}
        got = {m["mast"]: (m["facing"], m["protects"], m["kind"], m["hidden"], m["icon"]) for m in self.names["masts"]}
        self.assertEqual(got, want)

    def _copy_without(self, ph):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        with sdm.DEVICE_MAP.open(newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["trial_name"] = ", ".join(p for p in sdm.split_names(r["trial_name"]) if p != ph)
        out = tmp / "device_map_staging.csv"
        with out.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=sdm.bdm.COLUMNS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        return out

    def test_a_missing_block_of_a_split_track_stops(self):
        with self.assertRaisesRegex(sdm.StagingMapError, "track e23: blocks .* are not 1/n to n/n"):
            sdm.load(self.band, device_map=self._copy_without("Track e23 2/3"))

    def test_a_missing_turnout_placeholder_stops(self):
        with self.assertRaisesRegex(sdm.StagingMapError, "no turnout row has trial_name Switch 1"):
            sdm.load(self.band, device_map=self._copy_without("Switch 1"))

    def test_the_tracks_are_the_frozen_tracks(self):
        # staging_chains (build_cats_panel.py, build_signals.py) holds every frozen track's blocks, in order, between
        # the same two turnouts (or a turnout and a bumper); the legs are the band's, not Layout Editor letters
        import le_inputs
        key = lambda c: (frozenset(e[0] for e in c["ends"]), tuple(c["blocks"]))       # noqa: E731
        flip = lambda c: (frozenset(e[0] for e in c["ends"]), tuple(c["blocks"][::-1]))  # noqa: E731
        ends = lambda c: [("END" if e[0] == "END" else e[0]) for e in c["ends"]]        # noqa: E731
        frozen = [dict(c, ends=[(e, "") for e in ends(c)]) for c in le_inputs.load().chains]
        mine = sdm.staging_chains(self.band, self.names)
        self.assertEqual(len(mine), len(frozen))
        got = {key(c) for c in mine}
        for c in frozen:
            self.assertTrue(key(c) in got or flip(c) in got, c)

    def test_the_signal_plan_reads_back_as_frozen(self):
        import le_inputs
        self.assertEqual(le_inputs.signal_rows(sdm.load_signal_masts()), le_inputs.signal_rows(le_inputs.load().masts))


class DeviceMapPath(unittest.TestCase):
    """build_layout_le.py's device-map staging path (--staging devicemap)."""

    @classmethod
    def setUpClass(cls):
        import build_layout_le as blb
        cls.B = blb
        try:
            blb.plugin()
            base = blb.template_tables()
        except blb.BuildError as exc:
            raise unittest.SkipTest(f"plugin or hand-drawn tables not available: {exc}")
        cls.data, cls.P, cls.names, _bands = blb.build(base, levels="staging", as_live=True, approved=None,
                                                         staging_source="devicemap")
        from hartlib import tables
        cls.tables = tables
        cls.root = tables.loads(cls.data).root
        cls.panel = tables.layout_editor(cls.root, blb.TEMPLATE_PANEL)

    def test_its_trial_files_sit_beside_the_frozen_ones(self):
        B = self.B
        self.assertEqual(B.default_out("all", True, "devicemap").name, "tables_cutover_devicemap.xml")
        self.assertEqual(B.default_out("staging", True, "devicemap").name, "tables_cutover_devicemap_staging.xml")
        self.assertEqual(B.staging_out(B.default_out("all", True, "devicemap")),
                         B.default_out("staging", True, "devicemap"))
        self.assertEqual(B.default_out("all", True), B.CUTOVER)          # the frozen path keeps its names

    def test_a_bad_source_or_frozen_inputs_stop(self):
        with self.assertRaisesRegex(self.B.BuildError, "staging_source must be one of"):
            self.B.build(levels="staging", staging_source="hand")
        with self.assertRaisesRegex(self.B.BuildError, "reads no frozen inputs"):
            self.B.build(levels="staging", staging_source="devicemap", inputs=object())

    def test_approving_the_device_map_panel_waits_for_the_switch_over(self):
        # approved_staging.sha256 guards the frozen candidate until devicemap is the default (staged/README.md)
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.B.main(["--approve-staging", "--staging", "devicemap"]), 1)
        self.assertIn("guards the frozen path until the switch-over", out.getvalue())

    def test_the_run_walk_counts_a_block_through_a_turnback_once(self):
        band, _opts, _core = sdm.staging_band()
        names = sdm.load(band)
        for _start, seq, _end in sdm.run_blocks(band, names):
            self.assertFalse([b for a, b in zip(seq, seq[1:]) if a == b], seq)
        self.assertIn(["Track Brick-Plane"], [seq for _s, seq, _e in sdm.run_blocks(band, names)])

    def test_every_staging_mast_is_placed_once_with_no_entry_exit_sensor(self):
        placed = [m["mast"] for m in self.B.slots_module().Index(self.panel).masts()]
        self.assertEqual(sorted(placed), sorted(sdm.mast_facts()))
        self.assertFalse([el for el in self.panel.iter() if any(k.endswith("boundsensor") for k in el.attrib)])

    def test_the_status_cluster_is_on_the_panel_by_name(self):
        sensors = {el.get("sensor") for el in self.panel.findall("sensoricon")}
        self.assertEqual(sensors, {"Bridge HBLOOP", "SML Mode", "Track Power"})
        self.assertEqual([el.get("signalhead") for el in self.panel.findall("signalheadicon")], ["IH9990"])
        self.assertTrue(self.tables.generated_panel(self.panel))

    def test_the_panel_attributes_are_the_items_files(self):
        import panel_items
        attrs, _opts = panel_items.panel_attributes(panel_items.load(self.B.PANEL_ITEMS))
        for k, v in attrs.items():
            if k != "scrollable":                       # the build sets it when the panel outgrows its window
                self.assertEqual(self.panel.get(k), v, k)


if __name__ == "__main__":
    unittest.main()
