"""hartlib.railroad: the fact files load once into typed objects, by layer, and every invariant between them holds."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import paths, railroad as R  # noqa: E402

REPO = R.Sources.under()
DATA_FILES = ("switches", "switch_legs", "name_map", "level_control_points", "local_switches", "lcos_nodes",
              "plan_overrides", "block_lengths", "staging_masts", "hands", "device_map", "level_masts")


class Copy(unittest.TestCase):
    """A copy of the fact files in a temporary data folder, which a test may edit."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.src = R.Sources.under(self.tmp / "data", tables_xml=REPO.tables)
        for name in DATA_FILES:
            dst = getattr(self.src, name)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(getattr(REPO, name), dst)

    def edit(self, name: str, old: str, new: str, count: int = 1) -> None:
        path = getattr(self.src, name)
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"{old!r} not in {path.name}")
        path.write_text(text.replace(old, new, count), encoding="utf-8")

    def append(self, name: str, line: str) -> None:
        with getattr(self.src, name).open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def problems(self, invariant: str, upto: str = "masts") -> list[str]:
        """The problems one invariant finds in the copy (the tables layer reads the checkout's tables.xml)."""
        rr = R.Railroad(self.src, upto=upto)
        inv = next(i for i in R.INVARIANTS if i.name == invariant)
        return inv.run(rr)

    def fails(self, reader, pattern: str) -> None:
        with self.assertRaisesRegex(R.FactsError, pattern):
            reader()


class RepoData(unittest.TestCase):
    def test_the_repo_facts_load_and_hold_but_for_the_known_problems(self) -> None:
        rr = R.Railroad()
        self.assertEqual(rr.switches[9].legs[0].closed, "Track EH-2")
        self.assertEqual(rr.switches[1].hardware, "M2T408")
        self.assertEqual(rr.main_upper_switches["225"].cp, "CP 225")
        self.assertEqual(rr.main_upper_switches["101"].cp, "")
        self.assertEqual(rr.device_map.sensors["BS Switch 101"], "IS:HART:C3:B:OS101")
        self.assertEqual(rr.device_map.turnouts["107"].jmri_name, "IT:HART:C3:107")
        self.assertEqual(rr.hands["223"].hand, "R")
        self.assertEqual(len(rr.level_masts), 44)   # the 2026-11-19 plan, APB intermediates and Mast 242L (240L before)
        fails, known = R.run_check(rr)
        self.assertEqual(fails, [])
        self.assertEqual(known, [])

    def test_every_known_message_names_a_registered_invariant(self) -> None:
        names = {i.name for i in R.INVARIANTS}
        self.assertEqual({m.split(":", 1)[0] for m in R.KNOWN} - names, set())

    def test_the_sources_are_the_files_the_builders_name(self) -> None:
        from hartlib import level_masts
        self.assertEqual(REPO.level_masts, level_masts.PATH)
        self.assertEqual(REPO.name_map, paths.PUBLIC_NAME_MAP)
        self.assertEqual(REPO.tables, paths.TABLES_XML)
        for name in DATA_FILES:
            self.assertTrue(getattr(REPO, name).is_file(), name)


class Layers(unittest.TestCase):
    """A Railroad built up to a layer refuses the layers the pipeline writes after it."""

    def test_a_later_layer_is_refused(self) -> None:
        rr = R.Railroad(upto="inputs")
        rr.plan_overrides                       # an input: allowed
        for attr, writer in (("hands", "build_hands.py"), ("device_map", "build_device_map.py"),
                             ("level_masts", "build_main_upper_masts.py"), ("tables", "build_layout_le.py")):
            with self.subTest(attr=attr), self.assertRaisesRegex(R.LayerError, writer):
                getattr(rr, attr)
        dm = R.Railroad(upto="device_map")
        self.assertTrue(dm.device_map.rows)
        with self.assertRaises(R.LayerError):
            dm.level_masts

    def test_check_runs_only_the_invariants_of_the_layers_read(self) -> None:
        ran = {p.invariant for p in R.Railroad(upto="inputs").check()}
        later = {i.name for i in R.INVARIANTS if R.LAYERS.index(i.layer) > 0}
        self.assertEqual(ran & later, set())
        fails, _ = R.run_check(R.Railroad(upto="inputs"))
        self.assertEqual(fails, [], "a KNOWN entry of a later layer is not stale when that layer is not read")

    def test_an_unknown_layer_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            R.Railroad(upto="schematic")

    def test_each_file_is_read_once(self) -> None:
        rr = R.Railroad(upto="device_map")
        self.assertIs(rr.device_map, rr.device_map)
        self.assertIs(rr.name_map, rr.name_map)


class Readers(Copy):
    """Each reader stops on its own file's shape, naming the file and line."""

    def test_columns_and_field_counts(self) -> None:
        self.edit("local_switches", "switch,level,area,notes", "switch,level,notes")
        self.fails(lambda: R.read_local_switches(self.src.local_switches), "no column area")
        self.edit("lcos_nodes", "2,North,42,", "2,North,42,x,y,")
        self.fails(lambda: R.read_lcos_nodes(self.src.lcos_nodes), r"lcos_nodes_main_upper.csv line 2: 4 fields")
        self.fails(lambda: R.read_rows(self.tmp / "missing.csv", ["a"]), "cannot read it")

    def test_extra_columns_are_allowed_and_optional_ones_optional(self) -> None:
        """A column a reader does not use may be added, and an optional one (switches.csv `hand`, a notes column)
        may be missing from the header or from the end of a short row."""
        text = self.src.switches.read_text(encoding="utf-8")
        lines = text.splitlines()
        self.src.switches.write_text("\n".join([lines[0] + ",note"] + [l + ",x" for l in lines[1:]]) + "\n",
                                     encoding="utf-8")
        self.assertEqual(R.Railroad(self.src).switches[9].hand, "L")
        self.src.switches.write_text("\n".join(l.rsplit(",", 1)[0] for l in lines) + "\n", encoding="utf-8")
        self.assertEqual(R.Railroad(self.src).switches[9].hand, "")
        self.src.switches.write_text(text + "1,99,TO999,no,99,no\n", encoding="utf-8")       # short: no hand
        self.fails(lambda: R.Railroad(self.src).switches, "Switch 99.*no rows in switch_legs.csv")
        self.src.switches.write_text(text + "1,99,TO999,no\n", encoding="utf-8")             # short: required
        self.fails(lambda: R.Railroad(self.src).switches, "switches.csv line 22: 7 fields")
        self.src.block_lengths.write_text("user_name,inches,extra\nTrack W-1,105,x\n", encoding="utf-8")
        self.assertEqual(R.read_block_lengths(self.src.block_lengths)["Track W-1"].inches, 105.0)

    def test_switches_read_only_their_own_name_map_rows(self) -> None:
        """A bad row elsewhere in the name map is the facts check's to report; it does not stop switch loading
        (cats_turnout_io.py and engine_terminal.py load switches)."""
        self.append("name_map", "light,Lamp 1,Lamp 1,,MTT100,MTT100,,")
        rr = R.Railroad(self.src)
        self.assertEqual(rr.switches[1].hardware, "M2T408")
        self.fails(lambda: rr.name_map, "layer is one of")
        self.append("name_map", "turnout,Switch 1,Switch 1,Brick,M2T999,999,,")
        self.fails(lambda: R.Railroad(self.src).switches, "both are the live turnout Switch 1")

    def test_a_tables_file_that_cannot_be_read(self) -> None:
        bad = self.tmp / "tables.xml"
        bad.write_text("<layout-config>", encoding="utf-8")
        self.fails(lambda: R.read_tables(bad), "tables.xml: cannot read it as a tables file")
        self.fails(lambda: R.read_tables(self.tmp / "none.xml"), "none.xml: cannot read it as a tables file")

    def test_a_noted_file_needs_its_note_line(self) -> None:
        noted = self.tmp / "noted.csv"
        noted.write_text("mast,facing,protects\nMast 2L,Track Main West,OS Switch 1\n", encoding="utf-8")
        self.fails(lambda: R.read_rows(noted, ("mast",), note=True), "noted.csv line 1: the note line")

    def test_a_staging_mast_needs_its_facing_block(self) -> None:
        self.edit("staging_masts", "Mast 2L,Brick,1,Track Main West,", "Mast 2L,Brick,1,,")
        self.fails(lambda: R.read_staging_masts(self.src.staging_masts), "has no facing block")

    def test_name_map(self) -> None:
        self.append("name_map", "turnout,Switch 1,Switch 1,Brick,M2T408,100,,")
        self.fails(lambda: R.read_name_map(self.src.name_map), r"lines 2 and \d+: both are turnout 'Switch 1'")

    def test_name_map_layer_and_dcc(self) -> None:
        self.append("name_map", "signal,X,X,,,,,")
        self.fails(lambda: R.read_name_map(self.src.name_map), "layer is one of")
        self.edit("name_map", "signal,X,X,,,,,", "turnout,X,X,,,1x,,")
        self.fails(lambda: R.read_name_map(self.src.name_map), "dcc is a number or blank")

    def test_switches_are_the_adr021_loader(self) -> None:
        self.append("switches", "2,9,TO999,no,99,no,")
        self.fails(lambda: R.Railroad(self.src).switches, r"lines 6 \(level 1\) and \d+ \(level 2\) both use Switch 9")
        self.edit("switches", "2,9,TO999,no,99,no,", "1,99,TO999,maybe,99,no,")
        self.fails(lambda: R.Railroad(self.src).switches, "Switch 99.*no rows in switch_legs.csv")

    def test_level_control_points(self) -> None:
        self.edit("level_control_points", 'cp_211,CP 211,3,211,', 'cp_211,CP 211,3,"211,107",')
        self.fails(lambda: R.read_level_control_points(self.src.level_control_points),
                   "switch 107 is in CP 107 and CP 211")
        self.edit("level_control_points", 'cp_211,CP 211,3,"211,107",', "cp_211,CP 211,4,211,")
        self.fails(lambda: R.read_level_control_points(self.src.level_control_points), "level is 2 or 3")
        self.edit("level_control_points", "cp_211,CP 211,4,211,", "cp_107,CP 211,3,211,")
        self.fails(lambda: R.read_level_control_points(self.src.level_control_points), "unique, 'cp_107' is not")

    def test_local_switches_and_nodes(self) -> None:
        self.append("local_switches", "101,2,Peninsula,again")
        self.fails(lambda: R.read_local_switches(self.src.local_switches), "both are switch 101")
        self.append("lcos_nodes", "3,West,42,again")
        self.fails(lambda: R.read_lcos_nodes(self.src.lcos_nodes), "both list node 42")

    def test_a_switch_in_a_control_point_and_local(self) -> None:
        self.append("local_switches", "107,2,West,also")
        self.fails(lambda: R.Railroad(self.src).main_upper_switches,
                   r"switch 107 is in a control point and in local_switches_main_upper.csv \(line \d+, CP 107\)")

    def test_plan_overrides(self) -> None:
        data = json.loads(self.src.plan_overrides.read_text(encoding="utf-8"))
        data["edits"].append({"op": "relabel", "map": {}})
        self.src.plan_overrides.write_text(json.dumps(data), encoding="utf-8")
        self.fails(lambda: R.read_plan_overrides(self.src.plan_overrides), "2 relabel edits")
        self.src.plan_overrides.write_text("{", encoding="utf-8")
        self.fails(lambda: R.read_plan_overrides(self.src.plan_overrides), "not a readable JSON file")
        self.src.plan_overrides.write_text('{"edits": [{"map": {}}]}', encoding="utf-8")
        self.fails(lambda: R.read_plan_overrides(self.src.plan_overrides), "objects with an `op`")

    def test_block_lengths_and_hands(self) -> None:
        self.edit("block_lengths", "Track W-1,Block 4-4,105,", "Track W-1,Block 4-4,long,")
        self.fails(lambda: R.read_block_lengths(self.src.block_lengths), "line 2: inches 'long' is not a number")
        self.edit("hands", "101A,L,", "101A,X,")
        self.fails(lambda: R.read_hands(self.src.hands), "hands.csv line 2")

    def test_device_map(self) -> None:
        dm = R.read_device_map(self.src.device_map)
        self.assertEqual(dm.blocks["Track 107-109"].trial, {"Track e19"})
        self.assertEqual(dm.heads_by_system["IH3332"].user_name, "Head 108LA Top")
        self.edit("device_map", "IS:HART:C3:B:OS101", "IS:OS101")
        self.fails(lambda: R.read_device_map(self.src.device_map), "BS Switch 101 has no virtual IS:HART:C3:B:")
        self.edit("device_map", "IS:OS101", "IS:HART:C3:B:OS101")
        self.edit("device_map", "2,,turnout,DCC Switch 103,", "2,,turnout,DCC Switch 101,")
        self.fails(lambda: R.read_device_map(self.src.device_map), r"lines 2 and 3: both are turnout DCC Switch 101")


class Invariants(Copy):
    """Each invariant finds what it is for in an edited copy, and nothing in the repo's files but KNOWN."""

    def test_the_copy_is_clean(self) -> None:
        for inv in R.INVARIANTS:
            if inv.layer != "tables":
                with self.subTest(invariant=inv.name):
                    self.assertEqual([p for p in self.problems(inv.name) if f"{inv.name}: {p}" not in R.KNOWN], [])

    def test_switch_numbers(self) -> None:
        self.edit("local_switches", "101,2,Peninsula,", "9,2,Peninsula,")
        self.edit("level_control_points", "cp_211,CP 211,", "cp_211,CP 212,")
        got = self.problems("switch-numbers")
        self.assertIn("Switch 9 is a staging switch (switches.csv) and a level 2 switch", got)
        self.assertTrue(any("CP 212 is named CP 211 by its lowest switch" in p for p in got), got)

    def test_lcos_nodes(self) -> None:
        self.edit("local_switches", "101,2,Peninsula,", "101,2,Attic,")
        self.edit("lcos_nodes", "2,North,42,", "2,North,4,")
        got = self.problems("lcos-nodes")
        self.assertIn("no node in lcos_nodes_main_upper.csv for level 2 Attic (switches 101)", got)
        self.assertTrue(any("node 4 is staging's (turnout Switch 1 (M2T408))" in p for p in got), got)

    def test_name_map(self) -> None:
        self.append("name_map", "turnout,Switch 999,Switch 998,,,,,")
        self.append("name_map", "turnout,Switch 997,Switch 997,,M2T408,100,,")
        got = self.problems("name-map")
        self.assertIn("public_name_map.csv: turnout 'Switch 999' is an alias of 'Switch 998', which has no live row "
                      "(current == proposed)", got)
        self.assertTrue(any("DCC 100 is Switch 1 and Switch 997" in p for p in got), got)
        self.assertTrue(any("turnouts Switch 1 and Switch 997 are both M2T408" in p for p in got), got)
        self.edit("name_map", "turnout,Switch 1,Switch 1,Brick,M2T408,100,", "turnout,Switch 1,Switch 1,Brick,,,")
        self.assertIn("Switch 1 (switches.csv): public_name_map.csv has no live turnout row with hardware and dcc",
                      self.problems("name-map"))

    def test_staging_blocks(self) -> None:
        self.edit("switch_legs", "1,OS Switch 1,OS Switch 3,Track Brick-Plane", "1,OS Switch 1,OS Switch 3,Track Nowhere")
        self.assertIn("Switch 1 (switch_legs.csv): thrown leg Track Nowhere is no live block of the name map",
                      self.problems("staging-blocks"))

    def test_plan_overrides(self) -> None:
        data = json.loads(self.src.plan_overrides.read_text(encoding="utf-8"))
        relabel = next(e for e in data["edits"] if e["op"] == "relabel")["map"]
        old = next(k for k, v in relabel.items() if v == "107")
        relabel[old] = "999"
        data["edits"].append({"op": "move", "switch": "T0"})
        self.src.plan_overrides.write_text(json.dumps(data), encoding="utf-8")
        got = self.problems("plan-overrides")
        self.assertIn(f"main_upper.plan_overrides.json: relabel {old!r} -> '999': 999 is no main or upper switch", got)
        self.assertIn("Switch 107 (CP 107): no plan switch is relabelled to it in main_upper.plan_overrides.json", got)
        self.assertIn("main_upper.plan_overrides.json: move edit names 'T0', which the relabel does not rename", got)

    def test_hands(self) -> None:
        self.append("hands", "9,L,test")
        got = self.problems("hands")
        self.assertTrue(any("9 is no label the plan's relabel gives" in p for p in got), got)
        self.assertTrue(any("9 is no main or upper switch" in p for p in got), got)

    def test_device_map(self) -> None:
        text = self.src.device_map.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        self.src.device_map.write_text("".join(l for l in lines if ",turnout,Switch 103," not in l),
                                       encoding="utf-8")
        self.edit("device_map", "2,CP 107,turnout,Switch 107,", "3,CP 107,turnout,Switch 107,")
        got = self.problems("device-map")
        self.assertIn("Switch 103 (local, level 2): no turnout row in device_map_main_upper.csv", got)
        self.assertTrue(any("Switch 107 is level 3 CP 107, the control points say level 2 CP 107" in p for p in got),
                        got)

    def test_device_map_nodes_dcc_and_names(self) -> None:
        self.edit("device_map", "2,,turnout,Switch 101,M2T3408,IT:HART:C3:101,34,120,",
                  "2,,turnout,Switch 101,M2T408,IT:HART:C3:101,99,100,")
        self.edit("device_map", "head,Head 108LA Top,IH3332,IH:HART:C3:108LA_Top,",
                  "head,Head 108LA Top,IH3332,IH:HART:C3:108LX_Top,")
        got = self.problems("device-map")
        self.assertTrue(any("turnout Switch 101 is on node 99, no level 2 node" in p for p in got), got)
        self.assertTrue(any("Switch 101 has DCC 100, staging's Switch 1" in p for p in got), got)
        self.assertTrue(any("Switch 101 plans M2T408, staging's Switch 1" in p for p in got), got)
        self.assertTrue(any("Switch 101 has no LCC alias" in p for p in got), got)
        self.assertTrue(any("head Head 108LA Top: jmri_name 'IH:HART:C3:108LX_Top'" in p for p in got), got)

    def test_name_clash(self) -> None:
        """The staging switches' DCC addresses are aliases "DCC <n>" (owner, 2026-11-17), not "Switch <n>": an alias
        named like a main level turnout would rename it in a rename pass."""
        self.assertEqual(self.problems("name-clash", upto="device_map"), [])
        self.edit("name_map", "turnout,DCC 107,Switch 25,", "turnout,Switch 107,Switch 25,")
        self.assertEqual(self.problems("name-clash", upto="device_map"),
                         ["public_name_map.csv: turnout Switch 107 is an alias of Switch 25 there and level 2 turnout "
                          "Switch 107 in device_map_main_upper.csv"])

    def test_level_masts(self) -> None:
        self.edit("level_masts", "Mast 110L,CP 107,109,Track 105-109,", "Mast 110L,CP 107,125,Track Nowhere,")
        got = self.problems("level-masts")
        self.assertIn("main_upper_masts.csv: Mast 110L faces Track Nowhere, which is no device map block", got)
        self.assertIn("main_upper_masts.csv: Mast 110L protects Switch 125, which is not in CP 107", got)
        lines = self.src.level_masts.read_text(encoding="utf-8").splitlines(keepends=True)
        self.src.level_masts.write_text("".join(l for l in lines if not l.startswith("Mast 108LA,")),
                                        encoding="utf-8")
        self.assertIn("main_upper_masts.csv: device map mast Mast 108LA has no row", self.problems("level-masts"))

    def test_tables(self) -> None:
        rr = R.Railroad(self.src)
        self.assertEqual(R.INVARIANTS[-1].run(rr), [])              # the checkout's tables.xml holds them all
        t = rr.tables
        t.turnouts.pop("Switch 1")
        t.turnouts["Switch 107"] = "IT107"
        t.sensors.pop("BS Switch 101")
        got = R.INVARIANTS[-1].run(rr)
        self.assertIn("Switch 1 (switches.csv): no turnout Switch 1 in tables.xml", got)
        self.assertIn("Switch 107: tables.xml has IT107, the device map says IT:HART:C3:107", got)
        self.assertIn("BS Switch 101: tables.xml has no such sensor, the device map says IS:HART:C3:B:OS101", got)


class Known(unittest.TestCase):
    def broken_map(self) -> Path:
        """A copy of the repo's name map with the Block 2-2 alias pointed at a name that has no live row."""
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        src = R.Sources.under().name_map.read_text(encoding="utf-8")
        old = "occupancy,Block 2-2,unused Block 2-2,"
        self.assertIn(old, src)
        out = d / "public_name_map.csv"
        out.write_text(src.replace(old, "occupancy,Block 2-2,BS unused,"), encoding="utf-8")
        return out

    def test_unknown_problems_fail_and_stale_known_entries_fail(self) -> None:
        rr = R.Railroad(sources=R.Sources.under().but(name_map=self.broken_map()), upto="device_map")
        problem = "name-map: public_name_map.csv: occupancy 'Block 2-2' is an alias of 'BS unused', which has no live row (current == proposed)"
        fails, _ = R.run_check(rr, {})
        self.assertIn(problem, fails)
        fails, _ = R.run_check(rr, {problem: "test"})
        self.assertNotIn(problem, fails)
        fails, _ = R.run_check(R.Railroad(upto="device_map"), {**R.KNOWN, "device-map: nothing like this": "test"})
        self.assertEqual(fails, ["KNOWN entry no longer happens; remove it from KNOWN: device-map: nothing like this"])

    def test_the_command(self) -> None:
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(R.main(["check", "--upto", "inputs"]), 0)
            self.assertEqual(R.main(["invariants"]), 0)
        self.assertIn("railroad facts: 5 invariants up to inputs, 0 failure(s)", out.getvalue())
        self.assertIn("name-clash (device_map):", out.getvalue())


class VirtualNames(unittest.TestCase):
    def row(self, layer, user, jmri):
        return R.DeviceRow(level=2, layer=layer, user_name=user, jmri_name=jmri)

    def test_the_level_devices_naming_rule(self) -> None:
        ok = [self.row("block", "Track 1-3", ""), self.row("occupancy", "BS 1-3", "IS:HART:C3:B:1-3"),
              self.row("turnout", "Switch 1", "IT:HART:C3:1"), self.row("turnout", "DCC Switch 1", "IT:HART:C3:1"),
              self.row("head", "Head 2L", "IH:HART:C3:2L")]
        self.assertEqual(R.check_virtual_names(ok), [])
        bad = R.check_virtual_names(ok + [self.row("block", "Track 3-5", ""),
                                          self.row("turnout", "Switch 3", "IT:HART:C3:1")])
        self.assertTrue(any("blocks and occupancy rows differ" in p for p in bad), bad)
        self.assertIn("turnout Switch 3: jmri_name 'IT:HART:C3:1', not IT:HART:C3:<switch number>", bad)
        self.assertIn("turnout rows: a virtual name is empty or given twice", bad)

    def test_a_block_or_occupancy_row_given_twice(self) -> None:
        """Two rows of one block (or of one occupancy sensor) are caught, not folded into one by a set."""
        ok = [self.row("block", "Track 1-3", ""), self.row("occupancy", "BS 1-3", "IS:HART:C3:B:1-3")]
        self.assertIn("block rows given twice: Track 1-3", R.check_virtual_names(ok + ok[:1]))
        self.assertIn("occupancy rows given twice: BS 1-3", R.check_virtual_names(ok + ok[1:]))


if __name__ == "__main__":
    unittest.main()
