"""staging_device_map.py: staging's facts in the device map's form, their rules, and what reads them."""
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
from hartlib import devices  # noqa: E402


def band(nodes, strands):
    return {"nodes": nodes, "strands": strands}


def sw(label, **legs):
    return dict(kind="switch", label=label, ins={}, outs={}, **legs)


def row(layer, user, system, jmri, notes="", level="1", role="track", **facts):
    """A device map row (build_device_map.COLUMNS, and its role: a track block's or its sensor's unless given) of
    staging, kept by hand, a field device."""
    return dict(level=level, cp="", layer=layer, user_name=user, system_name=system, jmri_name=jmri, node="", dcc="",
                comment="", trial_name="", notes=notes, role=role,
                assignment="field", written_by="", **{c: facts.get(c, "") for c in sdm.railroad.DEVICE_FACTS})


def numbered(rows):
    """(line, row) as check_device_master reads the master."""
    return list(enumerate(rows, 2))


class SwitchFacts(unittest.TestCase):
    """The staging switches come from hartlib.railroad (le_common.staging_switches); a file it cannot read stops with
    StagingMapError, as every other staging map problem does."""

    def test_closed_legs_are_the_staging_rows_of_switches_csv(self):
        # the file gives IDs; their names are the name store's
        names = devices.user_names()
        with (ROOT / "jmri/layouts/hart/data/switches.csv").open(newline="", encoding="utf-8") as fh:
            want = {names[("1", r["os_id"])]: names[("1", r["closed_id"])] for r in csv.DictReader(fh)
                    if r["level"] == "1"}
        self.assertEqual(sdm.closed_legs(), want)

    def test_a_facts_error_is_a_staging_map_error(self):
        def bad():
            raise sdm.lc.BuildError("staging switches: switches.csv line 3: hand is L, R or blank, got 'X'")
        with unittest.mock.patch.object(sdm.lc, "staging_switches", bad), \
                self.assertRaisesRegex(sdm.StagingMapError, "switches.csv line 3"):
            sdm.closed_legs()


def keys_of(rows):
    """A drawing_keys.Keys of {trial key: (layer, user name)}, each row its own device."""
    from hartlib import drawing_keys
    ids = {ph: ("1", f"id{n}") for n, ph in enumerate(rows)}
    return drawing_keys.Keys(ids, {ids[ph]: dict(layer=layer, user_name=user, jmri_name=f"J{user}")
                                   for ph, (layer, user) in rows.items()})


class LoadSteps(unittest.TestCase):
    """load()'s steps: the block rows' track keys by piece, and each strand's blocks from its first end."""

    def test_track_runs_group_block_rows_by_piece(self):
        keys = keys_of({"Track 5C-7B 2/2": ("block", "B2"), "Track 5C-7B 1/2": ("block", "B1"),
                        "Track 1C-end": ("block", "S1"), "Switch 5": ("turnout", "T5"), "OS Switch 5": ("block", "OS5")})
        self.assertEqual(sdm.track_runs(keys), {"5C-7B": {2: (2, "Track 5C-7B 2/2"), 1: (2, "Track 5C-7B 1/2")},
                                                "1C-end": {1: (1, "Track 1C-end")}})

    def test_a_strand_takes_its_blocks_from_its_first_end_and_marks_them_used(self):
        keys = keys_of({"Track 5C-7B 1/2": ("block", "B1"), "Track 5C-7B 2/2": ("block", "B2")})
        bad: list[str] = []
        trials = sdm._Trials(keys, bad)
        got = sdm.strand_blocks({"s1": ("5C-7B", False), "s2": ("5C-7B", True)}, sdm.track_runs(keys), trials)
        self.assertEqual(got, {"s1": ["B1", "B2"], "s2": ["B2", "B1"]})
        self.assertEqual((bad, trials.used), ([], {"Track 5C-7B 1/2", "Track 5C-7B 2/2"}))

    def test_a_strand_with_no_rows_or_a_broken_run_is_a_problem(self):
        keys = keys_of({"Track 5C-7B 1/2": ("block", "B1")})
        bad: list[str] = []
        got = sdm.strand_blocks({"s1": ("5C-7B", False), "s2": ("9C-end", False)}, sdm.track_runs(keys),
                                sdm._Trials(keys, bad))
        self.assertEqual(got, {})
        self.assertEqual(len(bad), 2)
        self.assertIn("track 5C-7B: blocks ['Track 5C-7B 1/2'] are not 1/n to n/n", bad)
        self.assertTrue(bad[1].startswith("track 9C-end (s2) is on no block row"))

    def test_a_trial_key_of_another_layer_is_a_problem(self):
        bad: list[str] = []
        trials = sdm._Trials(keys_of({"Switch 5": ("turnout", "T5")}), bad)
        self.assertEqual(trials.name("Switch 5", "turnout"), "JT5")
        self.assertEqual(trials.name("Switch 5", "block"), "")
        self.assertEqual(bad, ["no block row has trial_name Switch 5"])


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

    def test_main_and_upper_keys_are_the_same_grammar(self):
        """Main and upper use the same keys: a lettered crossover half's label and leg ("121AB"),
        a double crossover's leg ("225D"), ordered by switch number, half letter and leg; a run that ends at a
        connector takes the switch and leg beyond it on the other band (band_refs)."""
        dx = dict(kind="dx", label="225", ins={}, outs={})
        b = band({"a": sw("121A"), "b": sw("125B"), "c": sw("229"), "d": dx, "L": dict(kind="end", sub="link")},
                 {"e1": dict(src=("a", "B"), dst=("b", "C")), "e2": dict(src=("c", "A"), dst=("d", "D")),
                  "e3": dict(src=("L", "E"), dst=("a", "C"))})
        far = band({"f": sw("127B"), "M": dict(kind="end", sub="link")}, {"e9": dict(src=("M", "E"), dst=("f", "A"))})
        bands = [("Main level", b, {}), ("Upper level", far, {})]
        joined = {(0, "L"): (1, "M"), (1, "M"): (0, "L")}
        got = {k: v[0] for k, v in sdm.band_refs(bands, joined, 0).items()}
        self.assertEqual(got, {"e1": "121AB-125BC", "e2": "225D-229A", "e3": "121AC-127BA"})
        self.assertEqual({k: v[0] for k, v in sdm.band_refs(bands, joined, 1).items()}, {"e9": "121AC-127BA"})
        with self.assertRaisesRegex(sdm.StagingMapError, "connector L: a run ends at it"):
            sdm.piece_refs(b)
        with self.assertRaisesRegex(sdm.StagingMapError, "connector L is joined to no other band"):
            sdm.band_refs(bands, {}, 0)

    def test_a_strands_keys_count_from_its_pieces_first_end(self):
        """strand_placeholders: the one k/n rule the writer and every reader key a strand by; piece_of reads it back."""
        self.assertEqual(sdm.strand_placeholders(("5C-7B", False)), ["Track 5C-7B"])
        self.assertEqual(sdm.strand_placeholders(("5C-7B", False), 2), ["Track 5C-7B 1/2", "Track 5C-7B 2/2"])
        self.assertEqual(sdm.strand_placeholders(("5C-7B", True), 2), ["Track 5C-7B 2/2", "Track 5C-7B 1/2"])
        with self.assertRaisesRegex(ValueError, "at least one block"):
            sdm.strand_placeholders(("5C-7B", False), 0)
        self.assertEqual(sdm.piece_of("Track 37C-39C #2 1/2"), ("37C-39C #2", 1, 2))
        self.assertEqual(sdm.piece_of("Track 107B-107C #1"), ("107B-107C #1", 1, 1))
        with self.assertRaisesRegex(sdm.StagingMapError, "'OS Switch 9' is no track trial key"):
            sdm.piece_of("OS Switch 9")

    def test_the_os_layer_gives_each_part_to_its_block(self):
        """A part is a JMRI block of its own (load's blocks); the masts read it inside its OS block (os_layer), as
        main and upper's mast process reads block_layer.Layer.bands."""
        names = {"os": {"a": "OS Switch 1"}, "blocks": {"e1": ["Track 1-3 at 1", "Track 1-3 at 3"],
                                                        "e2": ["Track W-1"]}}
        parts = {"Track 1-3 at 1": "OS Switch 1", "Track 1-3 at 3": "OS Switch 3"}
        got = sdm.os_layer(names, parts)
        self.assertEqual(got["blocks"], {"e1": ["OS Switch 1", "OS Switch 3"], "e2": ["Track W-1"]})
        self.assertEqual(names["blocks"]["e1"], ["Track 1-3 at 1", "Track 1-3 at 3"])      # a copy
        with self.assertRaisesRegex(sdm.StagingMapError, "part of another part"):
            sdm.os_layer(names, {"Track 1-3 at 1": "Track 1-3 at 3", "Track 1-3 at 3": "OS Switch 3"})

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
                         ["devices_generated.csv: Track S-1 West (level 1, block): block Track S-1 West has 0 occupancy "
                          "rows naming it (none), not one"])

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

    def test_the_helix_tracks_are_found_by_the_name_stores_names_not_the_drawings(self):
        """check_helix finds each helix track by the name store's name of its strand (staging_names, by the strand's
        ID): the drawn names are not read (naming-layers step 3b)."""
        import copy
        stored = sdm.staging_names(self.band, sdm.pd.DATA)
        self.assertEqual({stored[s] for s in stored if stored[s].startswith("Helix")}, {"Helix Outer", "Helix Inner"})
        drawn = copy.deepcopy(self.band)
        for s in drawn["strands"].values():
            s["name"] = ""
        self.assertEqual(sdm.check_helix(drawn, self.names, sdm.staging_names(drawn, sdm.pd.DATA)), [])
        self.assertEqual(len(sdm.check_helix(self.band, self.names, {})), 2)      # no stored name: not found

    def test_the_names_come_from_the_folder_given(self):
        """staging_names reads the store of the schematic folder it is given, not publish_draft.DATA."""
        with tempfile.TemporaryDirectory() as root:
            data = Path(root) / "schematic"
            shutil.copytree(sdm.pd.DATA, data, symlinks=True)
            field = Path(root) / devices.FIELD_FILE
            text = devices.field_path(sdm.pd.DATA.parent).read_text(encoding="utf-8")
            self.assertIn(",Track S-1,", text)
            field.write_text(text.replace(",Track S-1,", ",Track S-9,", 1), encoding="utf-8")
            got = sdm.staging_names(self.band, data)
        self.assertIn("S-9", got.values())
        self.assertNotIn("S-1", got.values())
        self.assertIn("S-1", sdm.staging_names(self.band, sdm.pd.DATA).values())

    def _copy(self, edit):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        rows = [r.cells() for r in sdm.devices.load(sdm.DEVICE_MAP)]        # the master's rows, whole
        edit(rows)
        out = tmp / devices.ONE_FILE
        out.write_text(sdm.devices.master_text(rows), encoding="utf-8")
        return out, sdm.read_device_rows(out)

    def _without(self, ph):
        def edit(rows):
            for r in rows:
                r["trial_name"] = ", ".join(p for p in sdm.split_names(r["trial_name"]) if p != ph)
        return self._copy(edit)[0]

    def test_a_missing_block_of_a_split_track_stops(self):
        # a row left with no key stops the one reader (hartlib.drawing_keys); a k/n key moved off its row stops load
        with self.assertRaisesRegex(sdm.StagingMapError, r"Track 1-3 at 1 \(level 1, block\) has no trial_name"):
            sdm.load(self.band, sdm.LoadOptions(device_map=self._without("Track 1B-3A 1/2")))

        def edit(rows):
            hit = next(r for r in rows if r["user_name"] == "Track 1-3 at 1" and r["layer"] == "block")
            hit["trial_name"] = "Track 1B-3A 3/3"
        with self.assertRaisesRegex(sdm.StagingMapError, "track 1B-3A: blocks .* are not 1/n to n/n"):
            sdm.load(self.band, sdm.LoadOptions(device_map=self._copy(edit)[0]))

    def test_a_part_is_a_block_of_its_own_inside_the_block_it_names(self):
        """A part row (part_of) carries its pieces' trial names; load() draws them as the part's own JMRI block, and
        os_layer gives them to the block it names, as the masts read them."""
        sid = next(s for s, (piece, _rev) in sdm.piece_refs(self.band).items() if piece == "35B-37A")
        self.assertEqual(self.names["blocks"][sid], ["Track 35-37"])
        both = next(s for s, (p, _r) in sdm.piece_refs(self.band).items() if p == "1B-3A")
        self.assertEqual(self.names["blocks"][both], ["Track 1-3 at 3", "Track 1-3 at 1"])
        parts = sdm.staging_parts()
        self.assertEqual(len(parts), 14)          # the halves of 35-39 stay inside their OS blocks (inside yes)
        layer = sdm.os_layer(self.names, parts)
        self.assertEqual((layer["blocks"][sid], layer["blocks"][both]),
                         (["OS Switch 35a"], ["OS Switch 3", "OS Switch 1"]))

    def test_a_piece_on_no_row_stops(self):
        def edit(rows):         # the part row of 35B-37A gone
            rows[:] = [r for r in rows if not (r["user_name"] == "Track 35-37" and r["layer"] == "block")]
        with self.assertRaisesRegex(sdm.StagingMapError, r"track 35B-37A \(e\d+\) is on no block row"):
            sdm.load(self.band, sdm.LoadOptions(device_map=self._copy(edit)[0]))

    def test_a_piece_on_two_rows_stops(self):
        def edit(rows):
            hit = next(r for r in rows if r["user_name"] == "OS Switch 37" and r["layer"] == "block")
            hit["trial_name"] += ", Track 35B-37A"
        with self.assertRaisesRegex(sdm.StagingMapError,
                                    r"trial_name Track 35B-37A is given to OS Switch 37 \(level 1, block\) and "
                                    r"Track 35-37 \(level 1, block\)"):
            sdm.load(self.band, sdm.LoadOptions(device_map=self._copy(edit)[0]))

    def test_a_missing_turnout_placeholder_stops(self):
        with self.assertRaisesRegex(sdm.StagingMapError, r"Switch 1 \(level 1, turnout\) has no trial_name"):
            sdm.load(self.band, sdm.LoadOptions(device_map=self._without("Switch 1")))

        def edit(rows):         # Switch 1's key on its LCC alias, which holds no piece
            for r in rows:
                if r["level"] == "1" and r["layer"] == "turnout" and r["user_name"] == "Switch 1":
                    r["trial_name"] = "Switch 999"
        with self.assertRaisesRegex(sdm.StagingMapError, "no turnout row has trial_name Switch 1"):
            sdm.load(self.band, sdm.LoadOptions(device_map=self._copy(edit)[0]))

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
        bad.write_text(sdm.MASTS.read_text(encoding="utf-8").replace("Mast 2L,st:brick,1,", "Mast 2L,st:brick,99,"),
                       encoding="utf-8")
        with self.assertRaisesRegex(sdm.StagingMapError, "Mast 2L is on switch '99', which no turnout row"):
            sdm.load(self.band, sdm.LoadOptions(masts_path=bad))

    def test_the_run_walk_counts_a_block_through_a_turnback_once(self):
        runs = sdm.run_blocks(self.band, self.names)
        for _start, seq, _end in runs:
            self.assertFalse([b for a, b in zip(seq, seq[1:]) if a == b], seq)
        self.assertIn(["Track Brick-Plane"], [seq for _s, seq, _e in runs])
        chains = sdm.staging_chains(self.band, self.names)
        self.assertEqual(len(chains), len(runs))
        # the track from Switch 35 to Switch 37 is the part Track 35-37 (inside OS Switch 35a): its gap is at
        # Switch 37's points
        self.assertTrue(any({e[0] for e in c["ends"]} == {"TOR36", "TO113"} and
                            c["blocks"] == ["Track 35-37"] for c in chains))

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
            cls.data, cls.P, cls.names, _bands = blb.build(levels="staging", as_live=True)
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
                le_checks.mast_turnouts([])

    def test_the_panel_attributes_are_the_items_files(self):
        import panel_items
        attrs, _opts = panel_items.panel_attributes(panel_items.load(self.B.PANEL_ITEMS))
        for k, v in attrs.items():
            if k != "scrollable":                       # the build sets it when the panel outgrows its window
                self.assertEqual(self.panel.get(k), v, k)


if __name__ == "__main__":
    unittest.main()
