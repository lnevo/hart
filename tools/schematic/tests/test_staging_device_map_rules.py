"""staging_device_map.py's key grammar and load()'s drawn names, and staging_mast_rows.py's checks of masts.csv's
staging rows, over small fakes. None needs the schematic plugin; the band-level tests are in
tools/audit/tests/test_staging_device_map.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import staging_device_map as sdm  # noqa: E402
import staging_mast_rows as smr  # noqa: E402
import staging_records  # noqa: E402
from hartlib import drawing_keys  # noqa: E402


def keys(rows: dict[str, dict[str, str]]) -> drawing_keys.Keys:
    """Drawing keys over {trial key: row}, each row its own device."""
    return drawing_keys.Keys(ids={ph: ("1", f"id:{ph}") for ph in rows},
                             rows={("1", f"id:{ph}"): r for ph, r in rows.items()})


def block(name: str) -> dict[str, str]:
    return {"layer": "block", "user_name": name, "jmri_name": name}


class KeyGrammar(unittest.TestCase):

    def test_piece_of_reads_a_track_key(self):
        self.assertEqual(sdm.piece_of("Track 37C-39C #2 1/2"), ("37C-39C #2", 1, 2))
        self.assertEqual(sdm.piece_of("Track 5C-7B"), ("5C-7B", 1, 1))
        with self.assertRaisesRegex(sdm.StagingMapError, "'OS Switch 5' is no track trial key"):
            sdm.piece_of("OS Switch 5")

    def test_a_strand_run_against_its_piece_counts_from_the_piece_end(self):
        self.assertEqual(sdm.strand_placeholders(("5C-7B", True), 2), ["Track 5C-7B 2/2", "Track 5C-7B 1/2"])
        self.assertEqual(sdm.strand_placeholders(("5C-7B", False)), ["Track 5C-7B"])
        self.assertEqual(len(sdm.strand_ids(("5C-7B", True), 2)), 2)
        for f in (sdm.strand_placeholders, sdm.strand_ids):
            with self.subTest(f=f.__name__), self.assertRaises(ValueError):
                f(("5C-7B", False), 0)

    def test_split_names_drops_empty_items(self):
        self.assertEqual(sdm.split_names(" A, ,B ,"), ["A", "B"])
        self.assertEqual(sdm.split_names(""), [])


class DrawnNames(unittest.TestCase):
    """load()'s step that binds the drawing's placeholders to the rows of their trial keys."""

    def test_each_placeholder_takes_its_rows_name(self):
        k = keys({"Switch 5": {"layer": "turnout", "user_name": "Switch 5", "jmri_name": "M2T400"},
                  "OS Switch 5": block("OS Switch 5"), "Track 5B-end 1/2": block("Track A"),
                  "Track 5B-end 2/2": block("Track B")})
        got = sdm._drawn_names(k, {"n1": "Switch 5"}, {"n1": "OS Switch 5"}, {"s1": ("5B-end", True)}, "master")
        self.assertEqual(got, {"turnouts": {"n1": "M2T400"}, "os": {"n1": "OS Switch 5"},
                               "blocks": {"s1": ["Track B", "Track A"]}})

    def test_a_missing_row_a_broken_run_and_an_unused_key_stop_together(self):
        k = keys({"Track 1B-3A 2/2": block("Track B"), "Track 9B-end": block("Track X"),
                  "OS Switch 7": block("OS Switch 7")})
        with self.assertRaises(sdm.StagingMapError) as caught:
            sdm._drawn_names(k, {}, {"n1": "OS Switch 5"}, {"s1": ("1B-3A", False)}, "master")
        text = str(caught.exception)
        self.assertTrue(text.startswith("master: no block row has trial_name OS Switch 5; "), text)
        self.assertIn("track 1B-3A: blocks ['Track 1B-3A 2/2'] are not 1/n to n/n", text)
        self.assertIn("trial names for track 9B-end, which the staging drawing does not have", text)
        self.assertIn("trial names the staging drawing does not have: ['OS Switch 7', 'Track 1B-3A 2/2']", text)

    def test_load_takes_one_options_record(self):
        with self.assertRaises(TypeError):
            sdm.load({}, sdm.DEVICE_MAP, sdm.MASTS)     # type: ignore[call-arg]
        with self.assertRaisesRegex(TypeError, r"options must be a LoadOptions, not \w*Path"):
            sdm.load({}, sdm.DEVICE_MAP)                # type: ignore[arg-type]
        self.assertEqual(sdm.DEFAULT_LOAD, sdm.LoadOptions(sdm.DEVICE_MAP, sdm.MASTS, sdm.STATIONS,
                                                           sdm.INTERLOCKINGS, None, True, True, True))

    def test_os_layer_gives_a_parts_pieces_to_its_block(self):
        names = staging_records.StagingNames(turnouts={}, os={}, blocks={"s1": ["P", "T"]})
        self.assertEqual(sdm.os_layer(names, {"P": "OS Switch 5"})["blocks"], {"s1": ["OS Switch 5", "T"]})
        with self.assertRaisesRegex(sdm.StagingMapError, r"parts \['P'\] are part of another part"):
            sdm.os_layer(names, {"P": "Q", "Q": "OS Switch 5"})


def mast_row(**cells: str) -> dict[str, str]:
    row = dict(mast="5RA", switch="5", protects="OS Switch 5", facing="Track A", cp="Brick", leg="",
               system_name="SM:5RA", device_system_name="SM:5RA", head_system_names="")
    return dict(row, **cells)


class MastRows(unittest.TestCase):

    def test_the_slot_kind_follows_the_row(self):
        self.assertEqual(smr.mast_kind(mast_row()), "turnout")
        self.assertEqual(smr.mast_kind(mast_row(switch="")), "anchor")
        self.assertEqual(smr.mast_kind(mast_row(switch="", protects="")), "end bumper")

    def test_a_row_that_matches_its_device_row_has_no_problem(self):
        r = mast_row(system_name="IF$vsm:5RA", device_system_name="IF$vsm:5RA", cp="")
        heads = smr.level_masts.mast_heads(r["system_name"])
        self.assertEqual(heads, [])
        self.assertEqual(smr._mast_problems(r, {"system_name": "IF$vsm:5RA"}, {"Brick"}, {}), [])

    def test_each_rule_a_row_breaks_is_named(self):
        r = mast_row(system_name="IF$vsm:5RA", device_system_name="other", cp="Nowhere", facing="", leg="sideways")
        got = smr._mast_problems(r, {"system_name": "IF$vsm:5RA"}, {"Brick"}, {})
        self.assertEqual(got, [" system name 'IF$vsm:5RA', the device map's 'IF$vsm:5RA'",
                               " needs a facing block, and its cp (if any) a staging control point",
                               " leg 'sideways'"])

    def test_a_visible_mast_needs_a_control_point(self):
        r = mast_row(cp="", system_name="IF$vsm:x", device_system_name="IF$vsm:x")
        self.assertEqual(smr._mast_problems(dict(r, system_name="SM:5RA", device_system_name="SM:5RA"),
                                            {"system_name": "SM:5RA"}, set(), {})[0],
                         " is a visible mast in no control point")

    def test_the_plugins_mast_carries_its_leg_and_an_end_bumpers_join(self):
        got = smr._staging_mast(mast_row(leg="normal", system_name="IF$vsm:5RA"), (12, 40))
        self.assertEqual((got["kind"], got["hidden"], got["icon"], got["leg"]), ("turnout", True, [12, 40], "normal"))
        self.assertNotIn("or_join", got)
        bumper = smr._staging_mast(mast_row(switch="", protects=""), (12, 17))
        self.assertTrue(bumper["or_join"])
        self.assertEqual(bumper["protects"], [])

    def test_signals_are_in_number_then_name_order(self):
        masts = [staging_records.SignalMast(mast=m, kind="anchor", facing="", protects=[], signal=m, toward="",
                                            run=[], names=[], edge_cm=0.0, cm_from_toward=0.0, dir="", signal_kind="",
                                            heads=1, schematic_edge="", schematic_toward_node="")
                 for m in ("B", "10A", "9B", "9A")]
        self.assertEqual([r["mast"] for r in smr.signal_rows(masts)], ["9A", "9B", "10A", "B"])


class TheSplit(unittest.TestCase):

    def test_staging_device_map_re_exports_the_mast_readers_and_the_error(self):
        for name in ("DEVICE_MAP", "LEVEL", "LIST", "MASTS", "load_masts", "load_signal_masts", "mast_facts",
                     "mast_kind", "read_device_rows", "signal_rows", "staging_masts"):
            with self.subTest(name=name):
                self.assertIs(getattr(sdm, name), getattr(smr, name))
        self.assertIs(sdm.StagingMapError, staging_records.StagingMapError)
        self.assertEqual(sdm.LEVEL, 1)


if __name__ == "__main__":
    unittest.main()
