"""hartlib.railroad: the fact files load once into typed objects, by layer, and every invariant between them holds."""
import csv
import json
import re
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import layer_files, paths, railroad as R  # noqa: E402
from master_edit import add, change, drop  # noqa: E402  the master is changed through hartlib.devices

REPO = R.Sources.under()
DATA_FILES = ("switches", "switch_legs", "devices", "interlockings", "local_switches", "lcos_nodes",
              "plan_overrides", "block_lengths", "staging_masts", "hands", "level_masts", "helix_tracks")


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

    def key(self, layer: str, user: str, levels: tuple[str, ...] = ("2", "3")) -> tuple[str, str, str]:
        """(level, layer, user_name) of the master row of a main or upper device (or of `levels`)."""
        from hartlib import devices
        hit = [(r["level"], layer, user) for r in devices.load(self.src.devices)
               if r["layer"] == layer and r["user_name"] == user and r["level"] in levels]
        self.assertEqual(len(hit), 1, f"{layer} {user}: {len(hit)} rows")
        return hit[0]

    def add_name_row(self, **columns: str) -> None:
        """A master row that has a place in the name map (its pnm_order, one past the last), level 1 unless given."""
        from hartlib import devices
        order = max(int(r["pnm_order"]) for r in devices.load(self.src.devices) if r["pnm_order"]) + 1
        add(self.src.devices, **{"level": "1", "pnm_order": str(order), **columns})

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
        # the 2026-11-19 plan, APB intermediates and Mast 242L (240L before), and 24 virtual destination masts (2026-11-20)
        self.assertEqual(len(rr.level_masts), 68)
        fails, known = R.run_check(rr)
        self.assertEqual(fails, [])
        self.assertEqual(known, [])

    def test_every_known_message_names_a_registered_invariant(self) -> None:
        names = {i.name for i in R.INVARIANTS}
        self.assertEqual({m.split(":", 1)[0] for m in R.KNOWN} - names, set())

    def test_the_sources_are_the_files_the_builders_name(self) -> None:
        from hartlib import level_masts
        self.assertEqual(REPO.level_masts, level_masts.PATH)
        self.assertEqual(REPO.devices, paths.DEVICES)
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
        self.fails(lambda: R.read_lcos_nodes(self.src.lcos_nodes), r"lcos_nodes.csv line 11: 4 fields")
        self.fails(lambda: R.read_rows(self.tmp / "missing.csv", ["a"]), "cannot read it")

    def test_the_device_maps_facts_are_columns(self) -> None:
        """An occupancy row's blocks and detector, and a mast's switch, facing and protected block, are columns of
        their own (DEVICE_FACTS): read and checked, never parsed out of the notes or comment."""
        dm = R.read_device_map(self.src.devices)
        occ = dm.by_user("occupancy")
        self.assertEqual((occ["BS Helix Inner"].served, occ["BS Helix Inner"].detector), (["Track Helix Inner"], "planned"))
        self.assertEqual(occ["BS 101 Spur 1"].detector, "none")
        mast = dm.by_user("mast")["Mast 132RA"]
        self.assertEqual((mast.switch, mast.facing, mast.protected), ("131", "Track Helix Outer", []))
        self.assertEqual(dm.by_user("mast")["Mast A83"].protected, ["Track 107 Loop 1"])
        for user, columns, msg in (("BS 101 Spur 1", dict(blocks="Track 101 Spur 2"), "not the one block"),
                                   ("BS 101 Spur 1", dict(detector="planned"), "needs system name"),
                                   ("BS 101 Spur 1", dict(detector="dark"), "is not one of"),
                                   ("BS Helix Inner", dict(detector="wired"), "calls it wired")):
            with self.subTest(msg=msg):
                text = self.src.devices.read_text(encoding="utf-8")
                change(self.src.devices, self.key("occupancy", user), **columns)
                self.fails(lambda: R.read_device_map(self.src.devices), msg)
                self.src.devices.write_text(text, encoding="utf-8")

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
        self.src.block_lengths.write_text("user_name,occupancy_sensor,plan_in,measured_in,source,note,extra\n"
                                          "Track W-1,Block 4-4,105.2,,plan,,x\n", encoding="utf-8")
        self.assertEqual(R.read_block_lengths(self.src.block_lengths)["Track W-1"].plan_in, 105.2)

    def test_switches_read_only_their_own_name_map_rows(self) -> None:
        """A bad row elsewhere in the name map is the facts check's to report; it does not stop switch loading
        (cats_turnout_io.py loads switches)."""
        self.add_name_row(layer="sensor", role="panel_status", written_by="panel_items.json", assignment="none",
                          user_name="Lamp 1")
        rr = R.Railroad(self.src)
        self.assertEqual(rr.switches[1].hardware, "M2T408")
        self.fails(lambda: rr.name_map, "layer is one of")
        self.add_name_row(layer="turnout", role="turnout", level="2", user_name="Switch 1",
                          jmri_name="IT:HART:C3:1", pnm_hardware="M2T999", pnm_dcc="999")
        self.fails(lambda: R.Railroad(self.src).switches, "both are the live turnout Switch 1")

    def test_a_tables_file_that_cannot_be_read(self) -> None:
        bad = self.tmp / "tables.xml"
        bad.write_text("<layout-config>", encoding="utf-8")
        self.fails(lambda: R.read_tables(bad), "tables.xml: cannot read it as a tables file")
        self.fails(lambda: R.read_tables(self.tmp / "none.xml"), "none.xml: cannot read it as a tables file")

    def test_a_user_name_given_to_two_beans_of_one_type(self) -> None:
        """Two turnouts, sensors, masts or blocks under one user name stop the read, naming the file, the type, the
        name and both system names; the same name on beans of different types is fine."""
        dup = self.tmp / "dup.xml"
        for kind, tag, box, system in (("turnout", "turnout", "turnouts", "MT1"),
                                       ("sensor", "sensor", "sensors", "MS1"),
                                       ("mast", "virtualsignalmast", "signalmasts", "MF1"),
                                       ("block", "block", "blocks", "IB1")):
            with self.subTest(kind):
                dup.write_text(
                    f"<layout-config><{box}>"
                    f"<{tag}><systemName>{system}</systemName><userName>Twin</userName><x/></{tag}>"
                    f"<{tag}><systemName>{system}9</systemName><userName>Twin</userName><x/></{tag}>"
                    f"</{box}></layout-config>", encoding="utf-8")
                self.fails(lambda: R.read_tables(dup),
                           f"dup.xml: two {kind}s have the user name 'Twin': {system} and {system}9$")
        dup.write_text("<layout-config><turnouts><turnout><systemName>MT1</systemName><userName>Twin</userName>"
                       "</turnout><turnout><systemName>MT2</systemName></turnout></turnouts>"
                       "<sensors><sensor><systemName>MS1</systemName><userName>Twin</userName></sensor></sensors>"
                       "</layout-config>", encoding="utf-8")
        t = R.read_tables(dup)
        self.assertEqual((t.turnouts, t.sensors), ({"Twin": "MT1"}, {"Twin": "MS1"}))
        # The repo's file reads as before: every named bean, once.
        live, root = R.read_tables(REPO.tables), R.tables.read(REPO.tables)
        for got, beans in ((live.turnouts, R.tables.turnouts(root)), (live.sensors, R.tables.sensors(root)),
                           (live.masts, R.tables.masts(root))):
            self.assertEqual(got, {R.tables.user_name(b): R.tables.system_name(b) for b in beans
                                   if R.tables.user_name(b)})
        self.assertEqual(live.blocks, {R.tables.user_name(b) or R.tables.system_name(b)
                                       for b in R.tables.blocks(root)})

    def test_a_bare_block_sharing_a_user_name_stops_the_read(self) -> None:
        """The block check covers every form JMRI writes: a block kept only as names, and one written both bare and
        in full (one bean, not twins)."""
        dup = self.tmp / "bare.xml"
        bare = "<block><systemName>IB{n}</systemName><userName>Twin</userName></block>"
        full = "<block><systemName>IB{n}</systemName><userName>Twin</userName><permissive>no</permissive></block>"
        for what, body in (("two bare", bare.format(n=1) + bare.format(n=2)),
                           ("bare then full", bare.format(n=1) + full.format(n=2)),
                           ("two sections", bare.format(n=1) + "</blocks><blocks>" + full.format(n=2))):
            with self.subTest(what):
                dup.write_text(f"<layout-config><blocks>{body}</blocks></layout-config>", encoding="utf-8")
                self.fails(lambda: R.read_tables(dup), "bare.xml: two blocks have the user name 'Twin': IB1 and IB2$")
        dup.write_text(f"<layout-config><blocks>{bare.format(n=1)}{full.format(n=1)}</blocks></layout-config>",
                       encoding="utf-8")
        self.assertEqual(R.read_tables(dup).blocks, {"Twin"})

    def test_empty_names_are_not_twins(self) -> None:
        """Beans without a user name never clash, and one without a system name neither clashes with a named bean
        nor hides two that do."""
        f = self.tmp / "empty.xml"

        def write(*beans: tuple[str, str]) -> None:
            f.write_text("<layout-config><turnouts>" + "".join(
                f"<turnout><systemName>{s}</systemName><userName>{u}</userName></turnout>" for s, u in beans)
                + "</turnouts></layout-config>", encoding="utf-8")
        write(("MT1", ""), ("MT2", " "), ("MT3", "Solo"))
        self.assertEqual(R.read_tables(f).turnouts, {"Solo": "MT3"})
        write(("", "Twin"), (" ", "Twin"))
        self.assertEqual(R.read_tables(f).turnouts, {"Twin": ""})
        for beans in ((("", "Twin"), ("MT1", "Twin")), (("MT1", "Twin"), ("", "Twin"))):
            write(*beans)
            self.assertEqual(R.read_tables(f).turnouts, {"Twin": "MT1"})
        write(("MT1", "Twin"), ("", "Twin"), ("MT2", "Twin"))
        self.fails(lambda: R.read_tables(f), "empty.xml: two turnouts have the user name 'Twin': MT1 and MT2$")
        write(("", "Twin"), ("MT1", "Twin"), ("MT2", "Twin"))
        self.fails(lambda: R.read_tables(f), "empty.xml: two turnouts have the user name 'Twin': MT1 and MT2$")

    def test_a_noted_file_needs_its_note_line(self) -> None:
        noted = self.tmp / "noted.csv"
        noted.write_text("mast,facing,protects\nMast 2L,Track Main West,OS Switch 1\n", encoding="utf-8")
        self.fails(lambda: R.read_rows(noted, ("mast",), note=True), "noted.csv line 1: the note line")

    def test_a_staging_mast_needs_its_facing_block(self) -> None:
        self.edit("staging_masts", "Mast 2L,Brick,1,Track Main West,", "Mast 2L,Brick,1,,")
        self.fails(lambda: R.read_staging_masts(self.src.staging_masts), "has no facing block")

    def test_name_map(self) -> None:
        self.add_name_row(layer="turnout", role="turnout", level="2", user_name="Switch 1",
                          jmri_name="IT:HART:C3:1", pnm_hardware="M2T408", pnm_dcc="100")
        self.fails(lambda: R.read_name_map(self.src.devices), r"lines \d+ and \d+: both are turnout 'Switch 1'")

    def test_name_map_layer_and_dcc(self) -> None:
        self.add_name_row(layer="sensor", role="panel_status", written_by="panel_items.json", assignment="none",
                          user_name="X")
        self.fails(lambda: R.read_name_map(self.src.devices), "layer is one of")
        drop(self.src.devices, ("1", "sensor", "X"))
        self.add_name_row(layer="turnout", role="turnout", level="2", user_name="X", jmri_name="IT:HART:C3:X",
                          pnm_dcc="1x")
        self.fails(lambda: R.read_name_map(self.src.devices), "dcc is a number or blank")

    def test_switches_are_the_adr021_loader(self) -> None:
        self.append("switches", "2,9,TO999,no,99,no,")
        self.fails(lambda: R.Railroad(self.src).switches, r"lines 6 \(level 1\) and \d+ \(level 2\) both use Switch 9")
        self.edit("switches", "2,9,TO999,no,99,no,", "1,99,TO999,maybe,99,no,")
        self.fails(lambda: R.Railroad(self.src).switches, "Switch 99.*no rows in switch_legs.csv")

    def test_interlockings(self) -> None:
        read = lambda: R.read_interlockings(self.src.interlockings)  # noqa: E731
        rr = R.Railroad(self.src, upto="inputs")
        self.assertEqual({i.level for i in rr.interlockings}, {1, 2, 3})
        self.assertEqual({i.level for i in rr.level_control_points}, {2, 3})
        self.assertEqual([i.name for i in R.read_interlockings(self.src.interlockings, (1,))],
                         ["Brick", "Barn", "East End", "Princess"])
        self.edit("interlockings", "3,CP 211,211,", '2,CP 211,"211,107",')
        self.fails(read, "switch 107 is in CP 107 and CP 211")
        self.edit("interlockings", '2,CP 211,"211,107",', "4,CP 211,211,")
        self.fails(read, "level is 1, 2 or 3")
        self.edit("interlockings", "4,CP 211,211,", "3,CP 201,211,")
        self.fails(read, "named, once per level; 'CP 201' is not")
        self.edit("interlockings", "3,CP 201,211,Peninsula", "3,CP 211,211,")
        self.fails(read, r"\(CP 211\): no area")
        self.edit("interlockings", "3,CP 211,211,", "3,CP 211,211,Peninsula")
        self.edit("interlockings", "1,Barn,7,,", "1,Barn,7,Barn,")
        self.fails(read, "a staging interlocking has no area")
        self.edit("interlockings", "1,Barn,7,Barn,", "1,Barn,x,,")
        self.fails(read, "switches is a list of switch numbers")

    def test_join_main_upper_refuses_a_staging_interlocking(self) -> None:
        rr = R.Railroad(self.src, upto="inputs")
        with self.assertRaisesRegex(R.FactsError, "Brick, Barn, East End, Princess are not main or upper"):
            R.join_main_upper(rr.interlockings, [])

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
        section = lambda data: self.src.plan_overrides.write_text(
            json.dumps({"_sections": True, "staging": {}, "main_upper": data}), encoding="utf-8")
        data = layer_files.read("plan_overrides", "main_upper", self.src.plan_overrides.parent)
        data["edits"].append({"op": "relabel", "map": {}})
        section(data)
        self.fails(lambda: R.read_plan_overrides(self.src.plan_overrides), r"plan_overrides.json\[main_upper\]: 2 relabel edits")
        self.src.plan_overrides.write_text("{", encoding="utf-8")
        self.fails(lambda: R.read_plan_overrides(self.src.plan_overrides), "not a readable layer section .*not JSON")
        section({"edits": [{"map": {}}]})
        self.fails(lambda: R.read_plan_overrides(self.src.plan_overrides), "objects with an `op`")
        self.src.plan_overrides.write_text('{"_sections": true, "staging": {}}', encoding="utf-8")
        self.fails(lambda: R.read_plan_overrides(self.src.plan_overrides), "no section 'main_upper'")
        self.fails(lambda: R.read_plan_overrides(self.src.plan_overrides.with_name("main_upper.plan_overrides.json")),
                   "the plan overrides are plan_overrides.json")

    def test_plan_overrides_are_named_by_the_sheet_read(self) -> None:
        relabel = {"edits": [{"op": "relabel", "map": {}}]}
        self.src.plan_overrides.write_text(
            json.dumps({"_sections": True, "staging": relabel, "main_upper": relabel}), encoding="utf-8")
        self.assertEqual(R.read_plan_overrides(self.src.plan_overrides).name, "plan_overrides.json[main_upper]")
        self.assertEqual(R.read_plan_overrides(self.src.plan_overrides, "staging").name, "plan_overrides.json[staging]")

    def test_block_lengths_and_hands(self) -> None:
        got = R.read_block_lengths(self.src.block_lengths)
        self.assertEqual(got["Track W-1"].source, "plan")
        self.assertIsNone(got["Track W-1"].measured_in)
        timed = got["Track Main West"]
        self.assertEqual(timed.source, "timed")
        # JMRI's block takes the plan length on every level; the measured one is for speed profiling only
        self.assertFalse(hasattr(timed, "jmri_in"))
        self.assertNotEqual(timed.plan_in, timed.measured_in)
        self.assertEqual(R.plan_cm({"Track Main West": timed})["Track Main West"], timed.plan_in * 2.54)
        text = self.src.block_lengths.read_text(encoding="utf-8")
        w1 = next(line for line in text.splitlines() if line.startswith("Track W-1,"))
        for bad, why in ((w1.replace(",plan,", ",assigned,"), "source 'assigned' is not one of"),
                         (w1.replace(",,plan,", ",99,plan,"), "a timed row gives its measured length, any other none"),
                         (w1.replace("Block 4-4,105.2,", "Block 4-4,long,"), "plan_in 'long' is not a number"),
                         (w1.replace("Block 4-4,105.2,", "Block 4-4,,"), "no plan_in"),
                         (w1.replace("Block 4-4,105.2,", "Block 4-4,-1,"), "plan_in -1 is below zero")):
            self.src.block_lengths.write_text(text.replace(w1, bad), encoding="utf-8")
            self.fails(lambda: R.read_block_lengths(self.src.block_lengths), f"line 2: .*{why}")
        mw = next(line for line in text.splitlines() if line.startswith("Track Main West,"))
        self.src.block_lengths.write_text(text.replace(mw, mw.replace(",timed,", ",plan,")), encoding="utf-8")
        self.fails(lambda: R.read_block_lengths(self.src.block_lengths), "source plan with measured_in")
        self.src.block_lengths.write_text(text, encoding="utf-8")
        self.edit("hands", "101A,L,", "101A,X,")
        self.fails(lambda: R.read_hands(self.src.hands), "hands.csv line 2")

    def test_device_map(self) -> None:
        dm = R.read_device_map(self.src.devices)
        self.assertEqual(dm.blocks["Track 107-109"].trial, {"Track 107A-109B"})
        self.assertEqual(dm.heads_by_system["IH3332"].user_name, "Head 108LA Top")
        self.assertEqual(dm.turnouts["101"].role, "turnout")
        occ = self.key("occupancy", "BS Switch 101")
        change(self.src.devices, occ, jmri_name="IS:OS101")
        self.fails(lambda: R.read_device_map(self.src.devices), "BS Switch 101 has no virtual IS:HART:C3:B:")
        change(self.src.devices, occ, jmri_name="IS:HART:C3:B:OS101")
        # the master holds a (level, layer, name) once, as its own loader checks before the map is read
        change(self.src.devices, self.key("turnout", "DCC Switch 103"), user_name="DCC Switch 101")
        self.fails(lambda: R.read_device_map(self.src.devices), r"the same level, layer and user_name as line")

    def test_a_master_that_cannot_be_read(self) -> None:
        self.fails(lambda: R.read_device_map(self.tmp / "missing.csv"), "cannot read it")
        self.fails(lambda: R.read_name_rows(self.tmp / "missing.csv"), "cannot read it")
        bad = self.tmp / "devices.csv"
        bad.write_text("level,layer\n2,mast\n", encoding="utf-8")
        self.fails(lambda: R.read_device_map(bad), "the header is not the master's columns")


class Invariants(Copy):
    """Each invariant finds what it is for in an edited copy, and nothing in the repo's files but KNOWN."""

    def test_the_copy_is_clean(self) -> None:
        for inv in R.INVARIANTS:
            if inv.layer != "tables":
                with self.subTest(invariant=inv.name):
                    self.assertEqual([p for p in self.problems(inv.name) if f"{inv.name}: {p}" not in R.KNOWN], [])

    def test_switch_numbers(self) -> None:
        self.edit("local_switches", "101,2,Peninsula,", "9,2,Peninsula,")
        self.edit("interlockings", "3,CP 211,", "3,CP 212,")
        self.edit("interlockings", '1,Brick,"1,3,5"', '1,Brick,"1,3,5,99"')
        got = self.problems("switch-numbers")
        self.assertIn("Switch 9 is a switch of levels 1 (switches.csv) and 2 (local_switches_main_upper.csv)", got)
        self.assertTrue(any("CP 212 is named CP 211 by its lowest switch" in p for p in got), got)
        self.assertTrue(any("level 1 interlocking Brick lists Switch 99, which is no level 1 switch" in p for p in got),
                        got)
        self.edit("interlockings", '2,CP 107,"107,', '2,CP 107,"201,107,')
        self.assertTrue(any("level 2 interlocking CP 107 lists Switch 201, which is no level 2 switch" in p
                            for p in self.problems("switch-numbers")), self.problems("switch-numbers"))

    def test_lcos_nodes(self) -> None:
        self.edit("local_switches", "101,2,Peninsula,", "101,2,Attic,")
        self.edit("lcos_nodes", "1,West,4,", "2,West,4,")           # a staging node given to the main level
        self.edit("lcos_nodes", "1,North,12,", "1,North,62,")        # and one that staging uses, left out
        got = self.problems("lcos-nodes")
        self.assertIn("no node in lcos_nodes.csv for level 2 Attic (switches 101)", got)
        self.assertTrue(any("node 4 is level 2, but it is staging's (turnout Switch 1 (M2T408))" in p for p in got),
                        got)
        self.assertTrue(any(p.startswith("staging node 12 (") and "is not in lcos_nodes.csv" in p for p in got), got)

    def test_the_committed_nodes_hold(self) -> None:
        """lcos_nodes.csv lists every level's nodes: staging's as built, main and upper's to hand out."""
        self.assertEqual(self.problems("lcos-nodes"), [])
        nodes = R.Railroad(self.src, upto="inputs").lcos_nodes
        self.assertEqual({n.node for n in nodes if n.level == 1}, {0, 1, 2, 3, 4, 5, 11, 12, 13})

    def test_name_map(self) -> None:
        self.add_name_row(layer="turnout", role="turnout", level="2", user_name="Switch 997",
                          jmri_name="IT:HART:C3:997", pnm_hardware="M2T408", pnm_dcc="100")
        got = self.problems("name-map")
        self.assertTrue(any("DCC 100 is Switch 1 and Switch 997" in p for p in got), got)
        self.assertTrue(any("turnouts Switch 1 and Switch 997 are both M2T408" in p for p in got), got)
        change(self.src.devices, ("1", "turnout", "Switch 1"), pnm_hardware="", pnm_dcc="")
        self.assertIn("Switch 1 (switches.csv): devices.csv has no live turnout row with hardware and dcc",
                      self.problems("name-map"))

    def test_name_map_aliases(self) -> None:
        """The master has no alias rows, but the invariant still holds a name map that has one (a NameMap from rows)."""
        rr = R.Railroad(self.src, upto="inputs")
        rows = rr.name_rows + [(999, dict(layer="turnout", current="Switch 999", proposed="Switch 998", cp="", hardware="",
                                          dcc="", comment="", notes=""))]
        rr.__dict__["name_map"] = R.read_name_map(self.src.devices, rows)
        inv = next(i for i in R.INVARIANTS if i.name == "name-map")
        self.assertIn("devices.csv: turnout 'Switch 999' is an alias of 'Switch 998', which has no live row "
                      "(current == proposed)", inv.run(rr))

    def test_staging_blocks(self) -> None:
        self.edit("switch_legs", "1,OS Switch 1,OS Switch 3,Track Brick-Plane", "1,OS Switch 1,OS Switch 3,Track Nowhere")
        self.assertIn("Switch 1 (switch_legs.csv): thrown leg Track Nowhere is no live block of the name map",
                      self.problems("staging-blocks"))

    def test_plan_overrides(self) -> None:
        data = layer_files.read("plan_overrides", "main_upper", self.src.plan_overrides.parent)
        relabel = next(e for e in data["edits"] if e["op"] == "relabel")["map"]
        old = next(k for k, v in relabel.items() if v == "107")
        relabel[old] = "999"
        data["edits"].append({"op": "move", "switch": "T0"})
        layer_files.write({("plan_overrides", "main_upper"): data}, self.src.plan_overrides.parent)
        got = self.problems("plan-overrides")
        self.assertIn(f"plan_overrides.json[main_upper]: relabel {old!r} -> '999': 999 is no main or upper switch", got)
        self.assertIn("Switch 107 (CP 107): no plan switch is relabelled to it in plan_overrides.json[main_upper]", got)
        self.assertIn("plan_overrides.json[main_upper]: move edit names 'T0', which the relabel does not rename", got)

    def test_hands(self) -> None:
        self.append("hands", "9,L,test")
        got = self.problems("hands")
        self.assertTrue(any("9 is no label the plan's relabel gives" in p for p in got), got)
        self.assertTrue(any("9 is no main or upper switch" in p for p in got), got)

    def test_device_map(self) -> None:
        drop(self.src.devices, self.key("turnout", "Switch 103"))
        change(self.src.devices, self.key("turnout", "Switch 107"), level="3")
        got = self.problems("device-map")
        self.assertIn("Switch 103 (local, level 2): no turnout row in devices.csv", got)
        self.assertTrue(any("Switch 107 is level 3 CP 107, the control points say level 2 CP 107" in p for p in got),
                        got)

    def test_device_map_nodes_dcc_and_names(self) -> None:
        """The DCC addresses, system names and LCC aliases of every level are check_device_master.py's
        (tools/audit/tests/test_check_device_master.py)."""
        change(self.src.devices, self.key("turnout", "Switch 101"), node="99")
        change(self.src.devices, self.key("head", "Head 108LA Top"), jmri_name="IH:HART:C3:108LX_Top")
        got = self.problems("device-map")
        self.assertTrue(any("turnout Switch 101 is on node 99, no level 2 node" in p for p in got), got)
        self.assertTrue(any("head Head 108LA Top: jmri_name 'IH:HART:C3:108LX_Top'" in p for p in got), got)

    def test_a_helix_block_is_never_on_a_staging_node(self) -> None:
        """A helix block may sit on either main or upper node, never on one of staging's (as built)."""
        change(self.src.devices, self.key("occupancy", "BS Helix Outer"), node="11")
        got = self.problems("device-map")
        self.assertTrue(any("occupancy BS Helix Outer is on node 11, no level 2 node" in p for p in got), got)

    def test_device_map_finds_clashes_and_missing_aliases_before_the_tables(self) -> None:
        """The rows of every level are held to each other at the device_map layer (railroad check --upto
        device_map), before tables.xml is built."""
        change(self.src.devices, self.key("turnout", "Switch 101"), system_name="M2T408", dcc="100")
        drop(self.src.devices, self.key("turnout", "DCC Switch 103"))
        got = self.problems("device-map", upto="device_map")
        self.assertTrue(any(re.search(r"level 2 turnout Switch 101\): dcc '100' is line \d+'s as well", p)
                            for p in got), got)
        self.assertTrue(any(re.search(r"level 2 turnout Switch 101\): system_name 'M2T408' is line \d+'s", p)
                            for p in got), got)
        self.assertTrue(any(re.search(r"level 2 turnout Switch 103\): 0 LCC aliases carry its DCC address", p)
                            for p in got), got)

    def test_name_clash(self) -> None:
        """The staging switches' DCC addresses are aliases "DCC <n>" (owner, 2026-11-17), not "Switch <n>": an alias
        named like a main level turnout would rename it in a rename pass."""
        self.assertEqual(self.problems("name-clash", upto="device_map"), [])
        # the name map holds no alias rows now: a staging row named like a main turnout is the clash that is left
        self.add_name_row(layer="turnout", role="turnout", user_name="Switch 107", jmri_name="IT:HART:C1:107",
                          pnm_hardware="M2T1208", pnm_dcc="107")
        self.assertEqual(self.problems("name-clash", upto="device_map"),
                         ["devices.csv: turnout Switch 107 is live there and level 2 turnout Switch 107 in devices.csv"])
        # an alias row (a NameMap built from rows) is the second kind
        rr = R.Railroad(self.src, upto="device_map")
        rows = rr.name_rows + [(999, dict(layer="turnout", current="Switch 101", proposed="Switch 25", cp="",
                                          hardware="", dcc="", comment="", notes=""))]
        rr.__dict__["name_map"] = R.read_name_map(self.src.devices, rows)
        inv = next(i for i in R.INVARIANTS if i.name == "name-clash")
        self.assertTrue(any("turnout Switch 101 is an alias of Switch 25 there" in p for p in inv.run(rr)))

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
        t.turnouts["Switch 107"] = "IT107"          # devices.csv's rows: check_device_master.py's, every level
        got = R.INVARIANTS[-1].run(rr)
        self.assertEqual(got, ["Switch 1 (switches.csv): no turnout Switch 1 in tables.xml"])

    def test_tables_masts_of_both_mast_files(self) -> None:
        rr = R.Railroad(self.src)
        t = rr.tables
        t.masts.pop("Mast 2L")
        t.masts["Mast 110L"] = "IF$x"
        got = R.INVARIANTS[-1].run(rr)
        self.assertTrue(any(p.startswith("staging_masts.csv: Mast 2L: tables.xml has no such mast, the file says IF$")
                            for p in got), got)
        self.assertTrue(any(p.startswith("main_upper_masts.csv: Mast 110L: tables.xml has IF$x, the file says IF$")
                            for p in got), got)

    def test_tables_staging_switch_legs(self) -> None:
        rr = R.Railroad(self.src)
        rr.tables.turnouts.pop("Switch 3")
        rr.tables.blocks.discard("Track Brick-Plane")
        got = R.INVARIANTS[-1].run(rr)
        self.assertIn("Switch 3 (switches.csv): no turnout Switch 3 in tables.xml", got)
        self.assertIn("Switch 1 (switch_legs.csv): no block Track Brick-Plane in tables.xml", got)


class Known(unittest.TestCase):
    def broken_map(self) -> R.NameMap:
        """The repo's name map with an alias row (the master has none) pointed at a name with no live row."""
        path = R.Sources.under().devices
        rows = R.read_name_rows(path) + [(999, dict(layer="occupancy", current="Block 2-2", proposed="BS unused", cp="",
                                                    hardware="M2S201", dcc="", comment="", notes="historical alias"))]
        return R.read_name_map(path, rows)

    def test_unknown_problems_fail_and_stale_known_entries_fail(self) -> None:
        rr = R.Railroad(upto="device_map")
        rr.__dict__["name_map"] = self.broken_map()
        problem = "name-map: devices.csv: occupancy 'Block 2-2' is an alias of 'BS unused', which has no live row (current == proposed)"
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
        """A row as build_device_map makes it: from_dict gives it its role (devices.role_of)."""
        return R.DeviceRow.from_dict(dict(level="2", layer=layer, user_name=user, jmri_name=jmri))

    def test_a_row_built_by_hand_is_never_roleless(self) -> None:
        self.assertEqual(R.DeviceRow(level=2, layer="turnout", user_name="DCC Switch 1").role, "lcc_alias")
        self.assertEqual(R.DeviceRow(level=2, layer="head", user_name="Head 2L").role, "head")
        self.assertEqual(R.DeviceRow(level=2, layer="mast", user_name="Mast 1L", jmri_name="IF$vsm:basic:x").role,
                         "hidden")
        self.assertEqual(R.DeviceRow(level=2, layer="turnout", user_name="Switch 1", role="turnout").role, "turnout")

    def test_from_dict_gives_the_role_a_reader_tests(self) -> None:
        self.assertEqual(self.row("turnout", "DCC Switch 1", "IT:HART:C3:1").role, "lcc_alias")
        self.assertEqual(self.row("turnout", "Switch 1", "IT:HART:C3:1").role, "turnout")
        self.assertEqual(self.row("block", "OS Switch 7", "").role, "os")
        given = R.DeviceRow.from_dict(dict(level=2, layer="turnout", user_name="Switch 1", role="turnout"))
        self.assertEqual(given.role, "turnout")
        with self.assertRaisesRegex(R.FactsError, "a device map has no sensor rows"):
            self.row("sensor", "Lamp", "")

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


class SmallHelpers(Copy):
    """Public helpers and loaders the module split moves, held to their behaviour."""

    def test_natural_orders_numbers_as_numbers(self) -> None:
        self.assertEqual(sorted(["Switch 101", "Switch 9"], key=R.natural), ["Switch 9", "Switch 101"])

    def test_switch_number_of_a_label(self) -> None:
        self.assertEqual([R.switch_number(x) for x in ("129A", "223*", "7", "", None)], ["129", "223", "7", "", ""])

    def test_device_list_splits_and_trims(self) -> None:
        self.assertEqual(R.device_list(" Track 1; Track 2 ;;"), ["Track 1", "Track 2"])
        self.assertEqual(R.device_list(""), [])

    def test_device_facts_flags_a_stray_and_a_missing_fact(self) -> None:
        base = {c: "" for c in R.DEVICE_COLUMNS}
        self.assertEqual(R.device_facts({**base, "layer": "turnout"}), [])
        self.assertIn("a turnout row has stop", R.device_facts({**base, "layer": "turnout", "stop": "yes"}))
        self.assertIn("a mast row names no facing block", R.device_facts({**base, "layer": "mast"}))
        mast = {**base, "layer": "mast", "facing": "Track 1", "dir": "east"}
        self.assertEqual(R.device_facts(mast), [])
        self.assertEqual(R.device_facts({**mast, "dir": "west"}), [])
        for bad in ("", "up", "West"):          # a mast's dir is east or west, never read from its name
            self.assertIn(f"dir {bad!r} is not one of east, west", R.device_facts({**mast, "dir": bad}))
        self.assertIn("a turnout row has dir", R.device_facts({**base, "layer": "turnout", "dir": "east"}))
        self.assertIn("an occupancy row names no blocks",
                      R.device_facts({**base, "layer": "occupancy", "detector": "none"}))

    def test_join_main_upper_stops_on_a_switch_in_both(self) -> None:
        rr = R.Railroad(self.src, upto="inputs")
        cps, local = rr.level_control_points, rr.local_switches
        joined = R.join_main_upper(cps, local)
        self.assertEqual(len(joined), sum(len(c.switches) for c in cps) + len(local))
        with self.assertRaises(R.FactsError):
            R.join_main_upper(cps, [replace(local[0], switch=cps[0].switches[0])])

    def test_switches_and_helix_tracks_load_from_the_checkout(self) -> None:
        rr = R.Railroad(self.src, upto="inputs")
        self.assertTrue(rr.switches)
        self.assertTrue(rr.helix_tracks)
        self.assertTrue(all(h.block.startswith("Track ") for h in rr.helix_tracks.values()))
        self.assertEqual(R.read_helix_tracks(self.src.helix_tracks), rr.helix_tracks)

    def test_a_helix_block_given_twice_stops(self) -> None:
        tracks = list(R.read_helix_tracks(self.src.helix_tracks).values())
        path = self.src.helix_tracks
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
            fields = rows[0].keys()
        rows[1]["block"] = tracks[0].block
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(fields))
            w.writeheader()
            w.writerows(rows)
        with self.assertRaises(R.FactsError):
            R.read_helix_tracks(path)

    def test_sources_but_swaps_one_file(self) -> None:
        other = self.src.but(hands=Path("x.csv"))
        self.assertEqual(other.hands, Path("x.csv"))
        self.assertEqual(other.switches, self.src.switches)

    def test_a_layer_beyond_upto_is_refused(self) -> None:
        rr = R.Railroad(self.src, upto="inputs")
        self.assertTrue(rr.has("inputs") and not rr.has("hands"))
        with self.assertRaises(R.LayerError):
            rr.hands
        with self.assertRaises(ValueError):
            R.Railroad(self.src, upto="nope")

    def test_the_name_rows_are_read_once(self) -> None:
        """name_map and switches both start from one read of the name map of devices.csv."""
        reads = []
        real = R.read_name_rows
        self.addCleanup(setattr, R, "read_name_rows", real)
        R.read_name_rows = lambda path: reads.append(path) or real(path)
        rr = R.Railroad(self.src, upto="inputs")
        self.assertTrue(rr.name_map)
        self.assertTrue(rr.switches)
        self.assertEqual(reads, [self.src.devices])
        self.assertTrue(R.switch_turnouts(self.src.devices, rr.name_rows, [next(iter(rr.switches))]))
        self.assertEqual(len(reads), 1)


if __name__ == "__main__":
    unittest.main()
