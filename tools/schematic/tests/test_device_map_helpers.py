"""The device map's small readers and staging helpers that had no test of their own: helix_pins, read_places,
loop_placeholder, helix_ends, line_cp, part_row, piece_trials, alias_note, new_spare, wire_block, staging_field and
taken_bean_names. They pin the behaviour the split of build_device_map.py into device_map_inputs.py,
device_map_schematic.py and device_map_staging.py keeps; none needs the schematic plugin."""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(ROOT / "tools/hartlib/src")]
import build_device_map as bdm  # noqa: E402
import device_map_inputs as inputs  # noqa: E402
import device_map_schematic as schematic  # noqa: E402
import device_map_staging as staging  # noqa: E402
from hartlib import devices, railroad, wiring  # noqa: E402

WIRING_HEAD = ",".join(wiring.COLUMNS) + "\n"
STATIONS_HEAD = "level,station,switches,tracks,desk_code,desk_plate,notes\n"
INTERLOCKINGS_HEAD = "level,interlocking,switches,area,notes\n"


class TempFiles(unittest.TestCase):
    def file(self, name: str, text: str) -> Path:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = Path(d.name) / name
        p.write_text(text, encoding="utf-8")
        return p


class Readers(TempFiles):
    def test_helix_pins_are_the_main_and_upper_helix_detectors_by_staging_block_id(self):
        """naming-layers step 5: {staging helix block id: pin}, the main or upper helix track's switch label (131A of
        det:block:131AA-helix) found in the helix map, so a renamed helix track keeps its detector."""
        p = self.file("wiring.csv", WIRING_HEAD
                      + "2,detector,det:block:131AA-helix,,,,,,41,2,,,planned,\n"
                        "2,detector,,,107,109,,,42,1,,,planned,\n"
                        "2,detector,det:os:107,,,,,,42,2,,,planned,\n"
                        "1,detector,det:block:7A-13C,,,,,,13,1,,,wired,\n")
        self.assertEqual(bdm.helix_pins(p), {"block:39B-helix": (41, 1)})
        self.assertEqual(bdm.helix_pins(p, {"131A": "block:37B-helix"}), {"block:37B-helix": (41, 1)})
        with self.assertRaisesRegex(bdm.MapError, r"line 2: det:block:131AA-helix is on helix switch 131A, which the "
                                                  r"helix map \(131B\) does not have"):
            bdm.helix_pins(p, {"131B": "block:37B-helix"})

    def test_helix_pins_of_the_committed_file(self):
        self.assertEqual(bdm.helix_pins(), {"block:39B-helix": (41, 1), "block:37B-helix": (41, 0)})

    def test_a_bad_wiring_file_is_a_map_error(self):
        p = self.file("wiring.csv", WIRING_HEAD + "2,detector,det:block:131AA-helix,,,,,,41,9,,,planned,\n")
        with self.assertRaisesRegex(bdm.MapError, "index is 1 to 8"):
            bdm.helix_pins(p)

    def places(self, stations: str, interlockings: str):
        """read_places of these rows: stations.csv in a schematic folder of a copy whose field and generated files
        are the repo's (the name store names the tracks cell's block IDs from them)."""
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root = Path(d.name)
        (root / "schematic").mkdir()
        for name in (devices.FIELD_FILE, devices.GENERATED_FILE):
            (root / name).write_bytes((devices.field_path().parent / name).read_bytes())
        path = root / "schematic" / "stations.csv"
        path.write_text(STATIONS_HEAD + stations, encoding="utf-8")
        return bdm.read_places(path, self.file("interlockings.csv", INTERLOCKINGS_HEAD + interlockings))

    def test_read_places(self):
        got = self.places('1,West Yard,"3,5",block:3B-end;block:3C-end,WY,,\n2,Princess,131,none,PR,,\n',
                          '1,Brick,"1,3",,\n2,CP 127,"127,129",West,\n')
        self.assertEqual(got.of, {"3": ("West Yard",), "5": ("West Yard",), "131": ("Princess",), "1": ("Brick",),
                                  "127": ("CP 127",), "129": ("CP 127",)})
        self.assertEqual(got.order, {"West Yard": 0, "Princess": 1, "Brick": 2, "CP 127": 3})
        self.assertEqual(got.level, {"West Yard": 1, "Princess": 2, "Brick": 1, "CP 127": 2})
        self.assertEqual(got.tracks, {"Track W-1": ["West Yard"], "Track W-2": ["West Yard"]})

    def test_a_place_on_two_levels_stops(self):
        with self.assertRaisesRegex(bdm.MapError, "Brick is a station or control point of levels 1 and 2"):
            self.places("1,Brick,3,none,BK,,\n", "2,Brick,127,West,\n")

    def test_an_unreadable_places_file_is_a_map_error(self):
        with self.assertRaisesRegex(bdm.MapError, "stations.csv"):
            self.places("1,,3,none,BK,,\n", "")

    def test_loop_placeholder(self):
        self.assertEqual(bdm.loop_placeholder("Track 107 Loop", 2), "Track 107 Loop 2")
        self.assertEqual(bdm.loop_placeholder("Track 107-109", None), "Track 107-109")

    def test_staging_nodes_are_lcos_nodes_level_1(self):
        want = {n.node for n in railroad.read_lcos_nodes(railroad.Sources.under().lcos_nodes) if n.level == 1}
        self.assertEqual(bdm.staging_nodes(), want)
        self.assertTrue(want)


class Places(unittest.TestCase):
    PLACES = bdm.Places(of={"57": ("Princess",), "131": ("CP 127",), "3": ("West Yard",)},
                        order={"West Yard": 0, "Princess": 1, "CP 127": 2},
                        level={"West Yard": 1, "Princess": 2, "CP 127": 2},
                        tracks={"Track Helix Outer": ["West Yard"]})

    def test_helix_ends_are_both_levels_switches(self):
        helix = {"x": {"block": "Track Helix Outer", "staging_switch": "57", "level_switch": "131A"}}
        self.assertEqual(bdm.helix_ends(helix), {"Track Helix Outer": {"57", "131"}})

    def test_line_cp_puts_the_rows_own_level_first(self):
        track = {"ends": [("sw", "131"), ("helix", "x")]}
        ends = {"Track Helix Outer": {"57", "131"}}
        self.assertEqual(bdm.line_cp("Track Helix Outer", 2, track, self.PLACES, ends), "Princess;CP 127;West Yard")
        self.assertEqual(bdm.line_cp("Track Helix Outer", "1", track, self.PLACES, ends), "West Yard;Princess;CP 127")
        self.assertEqual(bdm.line_cp("Track Helix Outer", 2, track, self.PLACES), "CP 127;West Yard")

    def test_a_block_in_no_place_has_no_cp(self):
        self.assertEqual(bdm.line_cp("Track 9-11", 1, {"ends": [("sw", "9"), ("sw", "11")]}, self.PLACES), "")


class StagingHelpers(unittest.TestCase):
    def test_part_row(self):
        part = {"track": {"cm": 30, "ends": [("sw", "5"), ("sw", "3")]}, "part_of": "OS Switch 3", "why": "a link"}
        row = bdm.part_row("1", "Track 3-5", part, "Track 3B")
        self.assertEqual(set(row), set(devices.COLUMNS))
        self.assertEqual((row["level"], row["layer"], row["role"], row["assignment"], row["part_of"], row["trial_name"],
                          row["written_by"]),
                         ("1", "block", "part", "none", "OS Switch 3", "Track 3B", "build_device_map.py"))
        self.assertEqual(row["notes"], "a piece of the 30 cm track from Switch 3 to Switch 5, part of OS Switch 3 "
                                       "(a link)")
        self.assertTrue(row["description"])

    def test_piece_trials_keys_each_strand_and_skips_one_inside_a_crossover(self):
        got = bdm.piece_trials({0: {"s1": ["Track A", "Track B"], "s2": ["OS Switch 9"]}}, {0: {"s1": ("3B-5A", True)}},
                               {0: {"OS Switch 9"}})
        self.assertEqual(got, {"Track A": ["Track 3B-5A 2/2"], "Track B": ["Track 3B-5A 1/2"]})

    def test_piece_trials_stops_on_a_strand_with_no_key(self):
        with self.assertRaisesRegex(bdm.MapError, "strand s1 of band 0 has blocks"):
            bdm.piece_trials({0: {"s1": ["Track A"]}}, {0: {}}, {0: set()})

    def test_alias_note(self):
        self.assertEqual(bdm.alias_note("Switch 1", "M2T408"), "LCC alias of Switch 1 (M2T408)")
        with self.assertRaisesRegex(bdm.MapError, "LCC alias DCC Switch 1: Switch 1 has no turnout row"):
            bdm.alias_note("Switch 1", "")

    def test_new_spare_is_named_by_its_input(self):
        row = bdm.new_spare(bdm.StagingPin(3, "", 13, 0))
        self.assertEqual((row["level"], row["layer"], row["role"], row["user_name"], row["assignment"], row["node"],
                          row["system_name"], row["jmri_name"], row["wiring"]),
                         ("1", "occupancy", "spare", "unused Block 13-1", "spare", "13", "M2S1300", "M2S1300",
                          "Node: 13 Block: 1"))
        self.assertEqual(row["detector"], "none")  # owner, 2026-11-25: a spare detector is none

    def test_wire_block_fills_the_occupancy_mark(self):
        row = {"user_name": "Track Barn", "jmri_comment": f"Barn track; {devices.OCCUPANCY_MARK}"}
        got = bdm.wire_block(row, 13, 1)
        self.assertEqual((got["node"], got["jmri_comment"]), ("13", "Barn track; occupancy Block 13-2 / M2S1301"))

    def test_wire_block_stops_on_a_comment_with_no_mark(self):
        with self.assertRaisesRegex(bdm.MapError, "Track Barn: its jmri_comment 'Barn track' has no"):
            bdm.wire_block({"user_name": "Track Barn", "jmri_comment": "Barn track"}, 13, 1)

    def test_staging_field_is_full_rows_of_staging_block_and_occupancy(self):
        got = bdm.staging_field()
        self.assertTrue(got)
        self.assertEqual({layer for layer, _n in got}, {"block", "occupancy"})
        self.assertTrue(all(set(r) == set(devices.COLUMNS) and r["level"] == "1" for r in got.values()))

    def test_taken_bean_names_leave_out_the_staging_blocks_the_builder_numbers(self):
        """Naming-layers step 7: the builder numbers staging's parts and any block with no field row, so its own
        level 1 block rows' names are its memory, not taken; a field row's (no writer) and other levels' are."""
        def row(level, role, *names, writer="build_device_map.py"):
            return dict(level=level, layer="block", role=role, system_name=names[0], jmri_name=names[1],
                        layout_block=names[2], written_by=writer)
        got = bdm.taken_bean_names([row("1", "part", "", "IB:AUTO:0060", "ILB60"),
                                    row("1", "track", "", "IB:AUTO:0062", "ILB62"),
                                    row("2", "part", "", "IB:AUTO:0061", "ILB61"),
                                    row("1", "track", "IB:AUTO:0010", "", "ILB10", writer="")])
        self.assertFalse({"IB:AUTO:0060", "ILB60", "IB:AUTO:0062", "ILB62"} & got)
        self.assertLessEqual({"IB:AUTO:0061", "ILB61", "IB:AUTO:0010", "ILB10"}, got)


class StagingRowSteps(unittest.TestCase):
    """staging_rows' steps over a fake block layer: what each takes out of the field rows and the problems it
    finds."""

    def blocks(self, *, blocks=(), ids=None, parts=None, tracks=None, helix=(), prior=None) -> staging.StagingBlocks:
        lay = SimpleNamespace(parts=parts or {}, tracks=tracks or {})
        return staging.StagingBlocks(lay, 0, {}, dict(ids or {}), set(blocks), {}, set(helix), dict(prior or {}), [])

    @staticmethod
    def field(**cells: str) -> dict:
        return dict({c: "" for c in devices.COLUMNS}, **cells)

    def test_unnamed_blocks_are_those_the_owner_gives_no_bean_names(self):
        s = self.blocks(blocks=("A", "B", "C", "D"), ids={"A": "block:a", "B": "block:b", "C": "block:c"},
                        prior={("block", "block:b"): self.field(jmri_name="IB:AUTO:0001", layout_block="ILB1"),
                               ("block", "block:c"): self.field(user_name="Track C", jmri_name="IB:AUTO:0002")})
        self.assertEqual(staging._unnamed_blocks(s), ["A"])
        self.assertEqual(len(s.bad), 1)
        self.assertIn("staging block Track C (id block:c): it gives jmri_name but not layout_block", s.bad[0])

    def test_a_pin_on_a_helix_block_or_an_undrawn_block_is_a_problem(self):
        s = self.blocks(blocks=("H", "T"), ids={"H": "block:h", "T": "block:t"}, helix=("H",))
        staging._check_pins(s, [inputs.StagingPin(2, "H", 13, 0, "block:h"), inputs.StagingPin(3, "X", 13, 1, "block:x"),
                                inputs.StagingPin(4, "T", 13, 2, "block:t"), inputs.StagingPin(5, "", 13, 3)])
        self.assertEqual(len(s.bad), 2)
        self.assertIn("line 2: H is a helix block", s.bad[0])
        self.assertIn("line 3: staging has no block X (block:x)", s.bad[1])

    def test_block_role_by_id_then_by_track_ends(self):
        lay = SimpleNamespace(tracks={"Track T": ({"ends": []}, None)})
        self.assertEqual(staging._block_role(lay, "OS Switch 5", "os:5"), "os")
        self.assertEqual(staging._block_role(lay, "OS Switch 5", "os:5:A-B"), "xover_corner")
        with unittest.mock.patch.object(staging, "line_role", side_effect=bdm.MapError("no role")):
            self.assertEqual(staging._block_role(lay, "Track T", "block:t"), "track")
        with unittest.mock.patch.object(staging, "line_role", return_value="siding"):
            self.assertEqual(staging._block_role(lay, "Track T", "block:t"), "siding")

    def test_drop_takes_field_rows_by_id_or_by_name(self):
        prior = {("block", "block:a"): self.field(user_name="Owner A"), ("block", "block:b"): self.field(user_name="B"),
                 ("occupancy", "det:block:a"): self.field(user_name="B")}
        self.assertEqual(staging._drop(prior, "block", "A", "block:a"), ["A"])
        self.assertEqual(staging._drop(prior, "block", "B"), ["B"])
        self.assertEqual(list(prior), [("occupancy", "det:block:a")])
        self.assertEqual(staging._drop(prior, "block", "Z"), [])

    def test_spares_are_unblocked_pins_and_pins_on_a_part(self):
        spare_pin, part_pin = inputs.StagingPin(2, "", 13, 0), inputs.StagingPin(3, "P", 13, 1, "block:p")
        s = self.blocks(ids={"P": "block:p"}, parts={"P": {}},
                        prior={("occupancy", "x"): self.field(user_name="unused Block 13-1")})
        got = staging._spare_rows(s, [spare_pin, part_pin, inputs.StagingPin(4, "T", 13, 2, "block:t")])
        self.assertEqual([r["user_name"] for r in got], ["unused Block 13-1", "unused Block 13-2"])
        self.assertEqual(s.prior, {})
        self.assertEqual(len(s.bad), 1)
        self.assertIn("occupancy unused Block 13-1 is a spare input", s.bad[0])


class TheSplit(TempFiles):
    """The readers live in device_map_inputs.py, which never loads the builder; build_device_map re-exports them."""
    READERS = ("CPS", "NODES", "OS_BLOCK", "PINS", "STATIONS", "UID", "WIRING", "Places", "StagingPin",
               "frozen_wires", "helix_pins", "loop_placeholder", "read_places", "read_staging_pins", "staging_nodes",
               "wiring_rows")

    def test_the_builder_re_exports_the_readers(self):
        for name in self.READERS:
            with self.subTest(name=name):
                self.assertIs(getattr(bdm, name), getattr(inputs, name))
        self.assertIs(bdm.SOURCES, inputs.SOURCES)

    STAGING = ("BEAN_NAME", "FIELD_LAYERS", "PART_BLOCK_FIRST", "STAGING_SHEET", "WIRED_LAYERS", "alias_note",
               "field_row", "helix_ends", "level_trials", "line_cp", "new_spare", "part_bean_names", "part_row",
               "piece_trials", "staging_cps", "staging_field", "staging_layer", "staging_part_names", "staging_rows",
               "staging_switches", "staging_trials", "staging_wired_rows", "taken_bean_names", "wire_block",
               "wire_occupancy")

    def test_the_builder_re_exports_the_staging_layer(self):
        for name in self.STAGING:
            with self.subTest(name=name):
                self.assertIs(getattr(bdm, name), getattr(staging, name))

    SCHEMATIC = ("block_overrides", "check_helix_ends", "corner_blocks_of", "dx_corners",
                 "helix_tracks", "home_and_posts", "labels_by_level", "line_role", "loop_halves", "main_upper_layer",
                 "named_tracks", "overrides_keys", "read_pins", "split_edges", "split_tracks", "xover_corners")

    def test_the_builder_re_exports_the_node_allocator(self):
        import device_map_nodes as nodes
        for name in ("CAP", "MAX_OU", "STAGING_LEVEL", "NoBoardRoom", "Nodes"):
            with self.subTest(name=name):
                self.assertIs(getattr(bdm, name), getattr(nodes, name))

    def test_the_builder_re_exports_the_row_stages(self):
        import device_map_level_masts as level_masts
        import device_map_master as master
        import device_map_plant as plant
        for module, names in ((plant, ("NOT_WIRED", "NO_DETECTOR", "block_sensor", "occupancy_user", "assign_ports")),
                              (level_masts, ("HEAD_NOT_WIRED", "head_name", "virtual_memory")),
                              (master, ("WRITER", "block_beans", "check_virtual", "startup_thrown"))):
            for name in names:
                with self.subTest(name=name):
                    self.assertIs(getattr(bdm, name), getattr(module, name))

    def test_the_build_records_are_device_map_records(self):
        import device_map_records as rec
        for name in ("Corners", "DeviceMapRow", "Drawing", "MapBuild", "MapInputs", "MapOutput", "MastKind", "Runs"):
            with self.subTest(name=name):
                self.assertIs(getattr(bdm, name), getattr(rec, name))

    def test_map_inputs_come_from_the_railroad(self):
        rr = SimpleNamespace(plan_overrides=SimpleNamespace(data={"edits": []}), level_control_points=["cp"],
                             lcos_nodes=["node"], local_switches=["local"])
        self.assertEqual(bdm.MapInputs.of(rr), bdm.MapInputs({"edits": []}, ["cp"], ["node"], ["local"]))
        self.assertEqual(bdm.MapInputs({}, [], []).local, ())

    def test_build_returns_its_named_parts(self):
        """build() returns MapOutput; a caller unpacks it as (control points, rows, parts) or reads it by name."""
        self.assertEqual(bdm.MapOutput._fields, ("control_points", "rows", "parts"))
        self.assertEqual(bdm.Drawing._fields, ("bands", "joined", "runs", "corners"))

    def test_the_builder_re_exports_the_schematic_helpers(self):
        for name in self.SCHEMATIC:
            with self.subTest(name=name):
                self.assertIs(getattr(bdm, name), getattr(schematic, name))
        self.assertIs(staging.builder, schematic.builder)

    def test_no_module_loads_the_builder_at_import(self):
        for mod in ("device_map_inputs", "device_map_staging", "device_map_schematic", "device_map_nodes"):
            with self.subTest(mod=mod):
                code = f"import sys; import {mod}; sys.exit('build_device_map' in sys.modules)"
                got = subprocess.run([sys.executable, "-c", code], cwd=HERE.parent, capture_output=True, text=True)
                self.assertEqual(got.returncode, 0, got.stderr)

    def test_the_staging_layer_reads_the_builders_paths_when_called(self):
        """builder() is the builder as it is then: a patched OUT reaches staging_field, as it did in one module."""
        self.assertIs(staging.builder(), bdm)
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(bdm, "OUT", Path(d) / devices.MASTER_FILE):
            with self.assertRaises(railroad.FactsError):     # no field file there: read from the patched folder
                staging.staging_field()
        with unittest.mock.patch.object(bdm, "OVERRIDES", Path("/nonexistent/plan_overrides.json")):
            self.assertEqual(schematic.block_overrides(), Path("/nonexistent") / "block_overrides.csv")

    def test_a_patched_reader_path_reaches_the_builders_readers(self):
        """The readers' default paths are device_map_inputs' (its docstring): patched there, the builder reads it."""
        p = self.file("wiring.csv", WIRING_HEAD + "2,detector,det:block:131AA-helix,,,,,,41,3,,,planned,\n")
        with unittest.mock.patch.object(inputs, "WIRING", p):
            self.assertEqual(bdm.helix_pins(), {"block:39B-helix": (41, 2)})

    def test_run_as_a_script_the_builder_is_the_running_module(self):
        """python3 build_device_map.py: builder() gets the running module, not a second copy loaded by name."""
        code = ("import runpy, sys\n"
                "sys.argv = ['build_device_map.py', '--check']\n"
                "try:\n"
                "    runpy.run_path('build_device_map.py', run_name='__main__')\n"
                "except SystemExit:\n"
                "    pass\n"
                "import device_map_schematic\n"
                "print(device_map_schematic.builder().__name__)\n")
        got = subprocess.run([sys.executable, "-c", code], cwd=HERE.parent, capture_output=True, text=True)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(got.stdout.strip().splitlines()[-1], "__main__")

    def test_read_pins_needs_its_tracks(self):
        """The reader takes the tracks it resolves against; the builder's read_pins gives the solved schematic's."""
        with self.assertRaises(TypeError):
            inputs.read_pins(None)          # pylint: disable=no-value-for-parameter
        p = self.file("wiring.csv", WIRING_HEAD + "2,detector,det:os:123,,,,,,42,1,,,planned,\n")
        self.assertEqual(inputs.read_pins(p, [], set()), {"OS Switch 123": (42, 0)})
        self.assertEqual(bdm.read_pins(p, found=[], split=set()), {"OS Switch 123": (42, 0)})


class TheRun(TempFiles):
    """main()'s steps after the build: what --check reports and what a write prints and returns."""

    def setUp(self):
        self.tmp = self.file("seed.txt", "").parent

    def wanted(self, held=()):
        path = self.tmp / "out.csv"
        return path, bdm.Wanted({path: "new\n"}, Counter({"turnout": 2, "fb": 4}), list(held))

    def run_step(self, step, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = step(*args)
        return status, out.getvalue(), err.getvalue()

    def test_a_write_writes_the_stale_outputs_and_prints_the_counts(self):
        path, want = self.wanted()
        status, out, err = self.run_step(bdm._write, want, [path])
        self.assertEqual((status, path.read_text(encoding="utf-8"), err), (0, "new\n", ""))
        self.assertEqual(out.splitlines(), [f"wrote {path}", "2 turnout, 4 fb"])

    def test_a_write_with_staging_masts_held_writes_and_exits_2(self):
        path, want = self.wanted(held=["Track 9-11 has no plan length"])
        status, out, err = self.run_step(bdm._write, want, [path])
        self.assertEqual((status, path.read_text(encoding="utf-8")), (2, "new\n"))
        self.assertNotIn("turnout", out)
        self.assertIn("rows written, staging's masts kept as they were: Track 9-11 has no plan length", err)

    def test_a_check_is_1_on_a_stale_output_or_held_masts(self):
        self.assertEqual(self.run_step(bdm._report_stale, [], []), (0, "", ""))
        status, out, err = self.run_step(bdm._report_stale, [bdm.GENERATED], [])
        self.assertEqual((status, out), (1, ""))
        self.assertIn(bdm.GENERATED.name, err)
        status, _out, err = self.run_step(bdm._report_stale, [], ["no plan length"])
        self.assertEqual((status, err), (1, "build_device_map.py: staging's masts not placed again: no plan length\n"))

    def test_a_fact_that_stops_the_build_is_named_and_exits_2(self):
        self.assertEqual(self.run_step(bdm._stopped, bdm.MapError("switch 9 is in no control point")),
                         (2, "", "build_device_map.py: switch 9 is in no control point\n"))

    def test_a_bad_input_file_exits_2_before_the_drawing_is_solved(self):
        gone = railroad.Sources.under().but(interlockings=self.tmp / "gone.csv")
        with unittest.mock.patch.object(bdm, "sources", return_value=gone), \
                unittest.mock.patch.object(bdm, "solve", side_effect=AssertionError("solved")):
            status, _out, err = self.run_step(bdm.main, ["--check"])
        self.assertEqual(status, 2)
        self.assertIn("gone.csv", err)

    def test_held_wiring_reads_the_given_pins_and_frozen_wires(self):
        held = bdm._held([], {}, [], found=[], split_names=set(), track_ids={})
        self.assertEqual((held.os_pin_level, held.cps, held.devices, held.blocks), ({}, frozenset(), set(), set()))
        self.assertIsInstance(held.nodes, bdm.Nodes)

    def test_a_pin_on_a_node_the_node_list_lacks_stops(self):
        with self.assertRaisesRegex(bdm.MapError, "Track 1-3 is pinned to node 4, which lcos_nodes.csv does not list"):
            bdm._held([], {"Track 1-3": (4, 0)}, [], found=[], split_names=set(), track_ids={})


class RowMakers(unittest.TestCase):
    """device_map_rows: one maker of a switch's rows and one way the owner's values go over a generated row."""

    def test_a_switch_gives_its_turnout_alias_and_feedback(self):
        import device_map_rows as rm
        got = rm.switch_device_rows(
            1, "Brick", "7", ["7", "7"], rm.Wired("M2T1308", 13, "Node: 13 Turnout: 0"),
            {"N": rm.Wired("M2S1367", 13, "Node: 13 Sensor: 0"), "R": rm.Wired("M2S1368", 13, "Node: 13 Sensor: 1")},
            "117", jmri="M2T1308", alias_notes="LCC alias")
        self.assertEqual([(r["id"], r["user_name"], r["jmri_name"], r["role"]) for r in got],
                         [("switch:7", "Switch 7", "M2T1308", "turnout"),
                          ("dcc:7", "DCC Switch 7", "MTT117", "lcc_alias"),
                          ("fb:7:N", "FB Switch 7 N", "M2S1367", "fb"), ("fb:7:R", "FB Switch 7 R", "M2S1368", "fb")])
        self.assertEqual(got[0]["trial_name"], "Switch 7")                  # the two halves' labels, once
        bare = rm.switch_device_rows(1, "", "9", ["9"], rm.Wired("M2T1310", 13, ""),
                                     {"N": rm.Wired("M2S1", 13, ""), "R": rm.Wired("M2S2", 13, "")}, "", jmri="",
                                     alias_notes="", alias=False)
        self.assertEqual([r["id"] for r in bare], ["switch:9", "fb:9:N", "fb:9:R"])
        self.assertEqual(bare[1]["jmri_name"], "")                          # DIRECT feedback: no sensor of its own

    def test_a_switchs_rows_take_the_shape_of_its_turnouts_assignment(self):
        """Naming-layers step 14: a field turnout's alias is a turnout of its own and its feedback sensors; a virtual
        one's alias names its bean and its feedback has none, on any level."""
        import device_map_rows as rm
        self.assertEqual(rm.switch_shape("M2T3308", "123"), ("MTT123", True))
        self.assertEqual(rm.switch_shape("IT:HART:C3:107", "123"), ("IT:HART:C3:107", False))
        main = rm.switch_device_rows(
            2, "CP 107", "107", ["107"], rm.Wired("M2T3308", 33, "Node: 33 Turnout: 0"),
            {"N": rm.Wired("M2S3367", 33, ""), "R": rm.Wired("M2S3368", 33, "")}, 123, jmri="M2T3308",
            alias_notes="")
        self.assertEqual([r["jmri_name"] for r in main], ["M2T3308", "MTT123", "M2S3367", "M2S3368"])

    def test_a_swap_is_one_cell_the_jmri_name(self):
        """Code review of step 14: an owner's row giving only a jmri_name sets the assignment its name gives (a swap
        is one cell, ADR-028), so the alias and feedback follow; an owner's assignment wins; an internal name stays
        virtual."""
        import device_map_rows as rm
        gen = dict.fromkeys(rm.devices.COLUMNS, "")
        gen.update(level="2", layer="turnout", role="turnout", id="switch:107", user_name="Switch 107",
                   system_name="M2T3308", jmri_name="IT:HART:C3:107", assignment="virtual", dcc="123")
        field = dict.fromkeys(rm.devices.COLUMNS, "")
        self.assertEqual(rm.owner_over(gen, dict(field, jmri_name="M2T3308"))["assignment"], "field")
        self.assertEqual(rm.owner_over(gen, dict(field, jmri_name="IT:HART:C3:107"))["assignment"], "virtual")
        self.assertEqual(rm.owner_over(gen, dict(field, jmri_name="M2T3308", assignment="none"))["assignment"], "none")
        alias = dict(gen, role="lcc_alias", id="dcc:107", user_name="DCC Switch 107", system_name="MTT123")
        got = rm.follow_swaps([rm.owner_over(gen, dict(field, jmri_name="M2T3308")), alias], {})
        self.assertEqual((got[1]["jmri_name"], got[1]["assignment"]), ("MTT123", "field"))

    def test_a_mast_follows_its_swapped_heads_in_one_pass(self):
        """mast_on_heads: the mast's name is rebuilt from its heads by ID and place, in one pass, so heads whose names
        trade places (top to the bottom's old name) still land each in its own slot; a mast with no field head, or
        the owner's own mast row, is kept."""
        import device_map_rows as rm

        def row(layer, ident, jmri, assignment):
            r = dict.fromkeys(rm.devices.COLUMNS, "")
            r.update(level="2", layer=layer, role="head" if layer == "head" else "home", id=ident,
                     user_name=ident, jmri_name=jmri, assignment=assignment)
            return r
        mast = row("mast", "mast:107:B:west", "IF$shsm:basic:two-searchlight(IH3332)(IH3333)", "field")
        top = row("head", "mast:107:B:west:top", "IH3333", "field")         # A->B
        bottom = row("head", "mast:107:B:west:bottom", "IH3334", "field")   # B->C
        heads = {(r["level"], r["id"]): r for r in (top, bottom)}
        self.assertEqual(rm.mast_on_heads(mast, heads)["jmri_name"], "IF$shsm:basic:two-searchlight(IH3333)(IH3334)")
        virtual = row("mast", "mast:107:B:west", "IF$shsm:basic:two-searchlight(IH:HART:C3:108LA_Top)"
                      "(IH:HART:C3:108LA_Bottom)", "virtual")
        unswapped = {k: dict(v, jmri_name=f"IH:HART:C3:108LA_{k[1].rsplit(':', 1)[1].title()}", assignment="virtual")
                     for k, v in heads.items()}
        self.assertIs(rm.mast_on_heads(virtual, unswapped), virtual)
        got = rm.follow_swaps([virtual, top, bottom], {})
        self.assertEqual((got[0]["jmri_name"], got[0]["assignment"]),
                         ("IF$shsm:basic:two-searchlight(IH3333)(IH3334)", "field"))
        own = dict.fromkeys(rm.devices.COLUMNS, "") | {"jmri_name": virtual["jmri_name"]}
        self.assertEqual(rm.follow_swaps([virtual, top, bottom], {("2", "mast:107:B:west"): own})[0], virtual)

    def test_a_swap_by_one_row_brings_the_alias_and_feedback(self):
        """follow_swaps: the owner's row makes Switch 107 a field turnout; its alias and feedback rows follow, a
        detector swapped the same way is wired, and a row the owner gives its own jmri_name keeps it."""
        import device_map_rows as rm

        def row(layer, role, ident, system, jmri, assignment, **more):
            r = dict.fromkeys(rm.devices.COLUMNS, "")
            r.update(level="2", layer=layer, role=role, id=ident, user_name=ident, system_name=system,
                     jmri_name=jmri, assignment=assignment, dcc="123" if layer == "turnout" else "", **more)
            return r
        rows = [row("turnout", "turnout", "switch:107", "M2T3308", "M2T3308", "field"),
                row("turnout", "lcc_alias", "dcc:107", "MTT123", "IT:HART:C3:107", "virtual"),
                row("fb", "fb", "fb:107:N", "M2S3367", "", "none"),
                row("fb", "fb", "fb:107:R", "M2S3368", "", "none"),
                row("occupancy", "track", "det:block:107B-107C#1", "M2S3305", "M2S3305", "field", detector="planned"),
                row("turnout", "turnout", "switch:109", "M2T3309", "IT:HART:C3:109", "virtual"),
                row("fb", "fb", "fb:109:N", "M2S3369", "", "none")]
        got = {r["id"]: r for r in rm.follow_swaps(rows, {("2", "fb:107:R"): {"jmri_name": "M2S9999"}})}
        self.assertEqual((got["dcc:107"]["jmri_name"], got["dcc:107"]["assignment"]), ("MTT123", "field"))
        self.assertEqual((got["fb:107:N"]["jmri_name"], got["fb:107:N"]["assignment"]), ("M2S3367", "field"))
        self.assertEqual(got["fb:107:R"]["jmri_name"], "")                  # the owner's own row: left to it
        self.assertEqual(got["det:block:107B-107C#1"]["detector"], "wired")
        self.assertEqual(got["fb:109:N"]["jmri_name"], "")                  # a virtual turnout's: as generated

    def test_the_owners_values_go_over_the_generated_ones(self):
        import device_map_rows as rm
        gen = dict.fromkeys(devices.COLUMNS, "")
        gen.update(level="2", layer="block", role="spur", id="block:103BB-end", user_name="Track 103 Spur",
                   assignment="none", notes="111.0 cm", written_by="build_device_map.py")
        gen["description"] = devices.describe(gen)
        self.assertEqual(rm.owner_over(gen, None), gen)
        field = dict.fromkeys(devices.COLUMNS, "")
        field.update(level="2", layer="block", id="block:103BB-end", user_name="Track Coal Spur")
        got = rm.owner_over(gen, field)
        self.assertEqual({c for c in got if got[c] != gen[c]}, {"user_name", "description"})   # empty: no override
        self.assertIn("Track Coal Spur", got["description"])

    def test_a_templated_owner_comment_keeps_the_filled_generated_one(self):
        """Code review of step 7: a field jmri_comment with {occupancy} is the builder's to fill: when the generated
        cell already follows it, it stands (as devices.merge takes it); else the field text goes over it, for the
        caller to fill."""
        import device_map_rows as rm
        gen = dict.fromkeys(devices.COLUMNS, "")
        gen.update(level="2", layer="block", role="track", id="block:x", user_name="Track X",
                   jmri_comment="Lead; occupancy Block 13-1 / M2S1300")
        field = dict.fromkeys(devices.COLUMNS, "")
        field.update(level="2", layer="block", id="block:x", jmri_comment=f"Lead; {devices.OCCUPANCY_MARK}")
        self.assertEqual(rm.owner_over(gen, field)["jmri_comment"], "Lead; occupancy Block 13-1 / M2S1300")
        self.assertEqual(rm.owner_over(dict(gen, jmri_comment="Track X"), field)["jmri_comment"],
                         f"Lead; {devices.OCCUPANCY_MARK}")


if __name__ == "__main__":
    unittest.main()
