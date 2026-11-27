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

from hartlib import block_lengths, devices as _devices, layer_files, paths, railroad as R, track_names  # noqa: E402
from master_edit import add, change, drop  # noqa: E402  the master is changed through hartlib.devices

REPO = R.Sources.under()
DATA_FILES = ("switches", "devices", "interlockings", "lcos_nodes",
              "plan_overrides", "block_lengths", "masts")


class Copy(unittest.TestCase):
    """A copy of the fact files in a temporary data folder, which a test may edit."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.src = R.Sources.under(self.tmp / "data", tables_xml=REPO.tables)
        self.src = self.src.but(devices=self.src.devices.with_name(_devices.ONE_FILE))     # a one-file copy
        for name in DATA_FILES:
            dst = getattr(self.src, name)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if name == "devices":       # the master as one file (no field file beside it), edited row by row
                _devices.one_file_copy(dst)
            else:
                shutil.copyfile(getattr(REPO, name), dst)
        shutil.copyfile(block_lengths.MEASURED, block_lengths.measured_path(self.src.block_lengths))
        prefs = layer_files.path("preferences", REPO.plan_overrides.parent)     # the helix tracks' labels
        shutil.copyfile(prefs, self.src.plan_overrides.parent / prefs.name)
        # the name store's plan graphs and owner rows (the one-file copy has no field file): the repo's, by opt-in
        track_names.repo_inputs(self.src.plan_overrides.parent)

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
        hit = [(r.level_cell, layer, user) for r in devices.load(self.src.devices)
               if r.layer == layer and r.user_name == user and r.level_cell in levels]
        self.assertEqual(len(hit), 1, f"{layer} {user}: {len(hit)} rows")
        return hit[0]

    def add_staging_row(self, **columns: str) -> None:
        """A staging (level 1) row of the master copy."""
        add(self.src.devices, **{"level": "1", **columns})

    def staging_row(self, **columns: str) -> dict[str, str]:
        """A row in read_staging_rows' form (railroad_facts.STAGING_COLUMNS), blank but for `columns`."""
        return {**{c: "" for c in R.STAGING_COLUMNS}, **columns}

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
        self.assertEqual(rr.device_map.occupancy["OS Switch 101"].jmri_name, "IS:HART:C3:B:OS101")
        self.assertEqual(rr.device_map.turnouts["107"].jmri_name, "IT:HART:C3:107")
        self.assertEqual(rr.hands["223"].hand, "R")
        # the 2026-11-19 plan, APB intermediates and Mast 242L (240L before), and 24 virtual destination masts (2026-11-20)
        self.assertEqual(len([r for r in rr.masts if r["level"] in (2, 3)]), 68)
        self.assertEqual(len(rr.masts), 98)                 # with staging's 30, one file
        fails, known = R.run_check(rr)
        self.assertEqual(fails, [])
        self.assertEqual(known, [])

    def test_every_known_message_names_a_registered_invariant(self) -> None:
        names = {i.name for i in R.INVARIANTS}
        self.assertEqual({m.split(":", 1)[0] for m in R.KNOWN} - names, set())

    def test_the_sources_are_the_files_the_builders_name(self) -> None:
        from hartlib import level_masts
        self.assertEqual(REPO.masts, level_masts.PATH)
        self.assertEqual(REPO.devices, _devices.MASTER)
        self.assertEqual(REPO.tables, paths.TABLES_XML)
        for name in DATA_FILES:
            self.assertTrue(getattr(REPO, name).is_file(), name)


class Layers(unittest.TestCase):
    """A Railroad built up to a layer refuses the layers the pipeline writes after it."""

    def test_a_later_layer_is_refused(self) -> None:
        rr = R.Railroad(upto="inputs")
        rr.plan_overrides                       # an input: allowed
        for attr, writer in (("hands", "build_hands.py"), ("device_map", "build_device_map.py"),
                             ("masts", "build_masts.py"), ("tables", "build_tables.py")):
            with self.subTest(attr=attr), self.assertRaisesRegex(R.LayerError, writer):
                getattr(rr, attr)
        dm = R.Railroad(upto="device_map")
        self.assertTrue(dm.device_map.rows)
        with self.assertRaises(R.LayerError):
            dm.masts

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
        self.assertIs(rr.staging_devices, rr.staging_devices)


class Readers(Copy):
    """Each reader stops on its own file's shape, naming the file and line."""

    def test_columns_and_field_counts(self) -> None:
        self.edit("switches", ",hand_source,area,", ",hand_source,")
        self.fails(lambda: R.read_local_switches(self.src.switches), "switches.csv: no column area")
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

    def test_extra_columns_are_allowed_and_every_switches_column_is_needed(self) -> None:
        """A column a reader does not use may be added; switches.csv needs every column of its own (SWITCH_COLUMNS),
        in the header and in each row."""
        text = self.src.switches.read_text(encoding="utf-8")
        lines = text.splitlines()
        self.src.switches.write_text("\n".join([lines[0] + ",note"] + [l + ",x" for l in lines[1:]]) + "\n",
                                     encoding="utf-8")
        self.assertEqual(R.Railroad(self.src).switches[9].hand, "L")
        self.src.switches.write_text("\n".join(l.rsplit(",", 1)[0] for l in lines) + "\n", encoding="utf-8")
        self.fails(lambda: R.read_switch_rows(self.src.switches), "switches.csv: no column notes")
        self.src.switches.write_text(text + "1,99,,OS Switch 99,Track A,Track B\n", encoding="utf-8")   # short
        self.fails(lambda: R.read_switch_rows(self.src.switches), rf"switches.csv line {len(lines) + 1}: 14 fields .*, not 6")
        self.src.block_lengths.write_text(",".join(block_lengths.PLAN_COLUMNS) + ",extra\n"
                                          "1,block:3B-end,105.2,,x\n", encoding="utf-8")
        self.assertEqual(block_lengths.read_plan(self.src.block_lengths)["block:3B-end"].plan_in, 105.2)

    def test_switches_read_only_their_own_rows(self) -> None:
        """A bad staging row elsewhere is the facts check's to report; it does not stop switch loading
        (cats_turnout_io.py loads switches)."""
        rr = R.Railroad(self.src)
        rows = rr.staging_rows + [(999, self.staging_row(layer="turnout", user_name="Lamp 1", dcc="1x"))]
        self.assertEqual(R.switch_turnouts(self.src.devices, rows, [1])[1]["system_name"], "M2T408")
        self.assertEqual(rr.switches[1].hardware, "M2T408")
        self.fails(lambda: R.read_staging_devices(self.src.devices, rows), "Lamp 1 \\(level 1, turnout\\): dcc is a number or blank")
        twice = rows + [(1000, self.staging_row(layer="turnout", user_name="Switch 1"))]
        self.fails(lambda: R.switch_turnouts(self.src.devices, twice, [1]), "two rows are both the turnout Switch 1")

    def test_a_switchs_hardware_and_dcc_are_its_turnout_rows_own_columns_its_cp_the_switch_lists(self) -> None:
        change(self.src.devices, ("1", "turnout", "Switch 1"), dcc="140")
        sw = R.Railroad(self.src).switches[1]
        self.assertEqual((sw.hardware, sw.dcc, sw.cp), ("M2T408", "140", "Brick"))      # stations.csv's desk area

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

    def test_a_mast_needs_its_facing_block(self) -> None:
        self.edit("masts", "1,Mast 2L,st:brick,1,Track Main West,", "1,Mast 2L,st:brick,1,,")
        self.fails(lambda: R.read_masts(self.src.masts), "masts.csv line 2: mast Mast 2L: a visible mast faces a block")

    def test_read_masts_gives_the_rows_of_the_levels_asked_for(self) -> None:
        staging = R.read_masts(self.src.masts, levels=(1,))
        self.assertEqual((len(staging), staging[0].level, staging[0].mast, staging[0].line), (30, 1, "Mast 2L", 2))
        self.assertEqual({m.level for m in R.read_masts(self.src.masts)}, {1, 2, 3})

    def test_staging_devices_are_level_1_rows_of_the_device_layers(self) -> None:
        sd = R.read_staging_devices(self.src.devices)
        self.assertEqual(len(sd.rows), 250)
        self.assertEqual(sd.by_name[("turnout", "Switch 1")].system_name, "M2T408")
        self.assertNotIn(("sensor", "SML Mode"), sd.by_name)        # a panel status lamp is no device layer's
        self.assertIn("Track Barn", sd.names("block"))

    def test_staging_devices_name_and_dcc(self) -> None:
        rows = R.read_staging_rows(self.src.devices)
        self.fails(lambda: R.read_staging_devices(self.src.devices, rows + [(999, self.staging_row(layer="turnout"))]),
                   r"\(level 1, turnout\): user_name is empty")
        change(self.src.devices, ("1", "turnout", "Switch 1"), dcc="1x")
        self.fails(lambda: R.read_staging_devices(self.src.devices), "dcc is a number or blank, not '1x'")

    def test_switches_are_the_adr021_loader(self) -> None:
        self.append("switches", "2,9,9,,,,,,,,,,,")
        self.fails(lambda: R.Railroad(self.src).switches, r"lines 7 \(level 1\) and \d+ \(level 2\) both use Switch 9")
        self.add_staging_row(layer="block", role="os", id="os:99", user_name="OS Switch 99", assignment="none",
                             description="Block OS Switch 99.")
        self.edit("switches", "2,9,9,,,,,,,,,,,",
                  "1,99,,os:99,block:9B-end,block:9C-end,,,,TO999,maybe,99,no,")
        self.fails(lambda: R.Railroad(self.src).switches, r"\(Switch 99\): expected yes or no, got 'maybe'")
        self.edit("switches", "TO999,maybe,99,no,", ",,,,")
        self.fails(lambda: R.Railroad(self.src).switches,
                   r"\(Switch 99\): a staging switch's first row gives le_ident, cats_inverted, ctc_is, ctc_signals")

    def test_switches_csv_rows_by_level(self) -> None:
        """Each row is held to its level's shape and names its file and line (read_switch_rows)."""
        text = self.src.switches.read_text(encoding="utf-8")
        cases = (
            # a staging row's OS block is its os_id; its name is the name store's (naming-layers step 5)
            ("1,9,,os:9,", "1,9,,os:11,", r"line 7 \(Switch 9\): a row keyed by its OS block gives the "
                                          r"device IDs of it \(os_id os:9, or os:9:<half>\)"),
            ("os:9,block:9B-end,block:9C-end,", "os:9,,block:9C-end,", "and of its legs \\(closed_id, thrown_id\\)"),
            ("os:9,block:9B-end,", "os:9,block:9X-end,", r"line 7 \(Switch 9\): closed_id block:9X-end is no level 1 "
                                                         r"device of the device master"),
            ("2,105,105,,,,", "2,105,105,,block:105B,,", "closed_id and thrown_id go with an os_id"),
            ("2,105,105,,,,", "2,105,105,os:105,,,", "a main or upper row is keyed by its half until its "
                                                      "switches are bound"),
            # a staging row with its IDs blanked is told it needs them, not a half-keyed row's rules (code review)
            ("os:9,block:9B-end,block:9C-end,", ",,,", r"line 7 \(Switch 9\): a staging row is keyed by its OS "
                                                      r"block and gives the device IDs of it \(os_id os:9"),
            ("1,9,,os:9,", "1,9,9,os:9,", "a row keyed by its OS block has no half"),
            ("block:9C-end,L,owner,", "block:9C-end,L,plan,", "hand_source plan is for rows keyed by their half"),
            ("block:9C-end,L,owner,", "block:9C-end,L,,", "a hand needs a hand_source"),
            ("block:9C-end,L,owner,", "block:9C-end,,owner,", "a hand needs a hand_source"),
            ("block:9C-end,L,owner,", "block:9C-end,L,someone,", "a hand needs a hand_source"),
            ("os:7:A-13C,,,,,", "os:7:A-13C,,,,TO117,",
             r"line 6 \(Switch 7\): le_ident hold a fact of the whole switch: give them on its first row \(line 5\)"),
            ("2,105,105,", "2,105,106,", r"\(Switch 105\): half is 105, 105A or 105B, not '106'"),
            ("2,105,105,,,,L,plan,West,,", "2,105,105,,,,L,plan,West,TO1,",
             "le_ident bind a row keyed by its OS block .* a row keyed by its half leaves them blank"),
            ("2,105,105,", "4,105,105,", "level is 1, 2 or 3"),
            ("2,101,101B,", "2,101,101A,", r"lines \d+ and \d+: both are 101A"),
        )
        for old, new, msg in cases:
            with self.subTest(new=new):
                self.assertIn(old, text)
                self.src.switches.write_text(text.replace(old, new, 1), encoding="utf-8")
                self.fails(lambda: R.read_switch_rows(self.src.switches), msg)
        more = (
            # a crossover's later staging row gives no hand: staging's hand is the switch's (Switch.hand)
            ("1,7,,os:7:A-5B,block:7B-33C,os:7:A-13C,,,", "1,7,,os:7:A-5B,block:7B-33C,os:7:A-13C,R,owner,",
             r"line 6 \(Switch 7\): hand, hand_source hold a fact of the whole switch"),
            # an owner row gives its hand; only a plan row waits for build_hands.py
            ("2,105,105,,,,L,plan,", "2,105,105,,,,,owner,", "an owner hand_source a hand"),
            # one row, half N, or both halves NA and NB
            ("2,105,105,", "2,105,105A,", r"\(Switch 105\): a switch keyed by its halves has one row, half 105, or "
                                          r"two, halves 105A and 105B; not 105A"),
            ("2,101,101B,", "2,101,101,", r"\(Switch 101\): .* not 101, 101A"),
        )
        for old, new, msg in more:
            with self.subTest(new=new):
                self.assertIn(old, text)
                self.src.switches.write_text(text.replace(old, new, 1), encoding="utf-8")
                self.fails(lambda: R.read_switch_rows(self.src.switches), msg)
        # a new plan row may leave its hand blank for build_hands.py; it is no hand until then
        self.src.switches.write_text(text.replace("2,105,105,,,,L,plan,", "2,105,105,,,,,plan,", 1), encoding="utf-8")
        self.assertNotIn("105", R.read_hands(self.src.switches))
        # a row's shape is its key's (naming-layers step 14), but only staging's switches are bound to the live
        # panels so far: a main row keyed by its OS block stops (code review: staging_switches and build_hands read
        # OS-keyed rows as staging's)
        self.src.switches.write_text(text.replace(
            "2,105,105,,,,L,plan,", "2,105,,os:105,block:105B,block:105C,L,owner,", 1),
            encoding="utf-8")
        self.fails(lambda: R.read_switch_rows(self.src.switches), "keyed by its half until its switches are bound")
        # a main or upper row has no OS block or legs
        self.src.switches.write_text(text, encoding="utf-8")
        self.assertEqual({(r.os_block, r.closed_leg, r.thrown_leg) for r in R.read_switch_rows(self.src.switches)
                          if not r.by_os}, {("", "", "")})
        self.src.switches.write_text(text + "1,9,,os:9:B,block:9B-end,block:9C-end,,,,,,,,\n",
                                     encoding="utf-8")
        self.fails(lambda: R.read_switch_rows(self.src.switches), r"Switch 9 is also on line 7; a switch's rows go together")

    def test_switches_csv_and_its_dictionary_have_the_readers_columns(self) -> None:
        """switches.csv's header is SWITCH_COLUMNS, in order, and switches.columns.csv describes each column once."""
        with REPO.switches.open(newline="", encoding="utf-8") as fh:
            self.assertEqual(tuple(next(csv.reader(fh))), R.SWITCH_COLUMNS)
        with (REPO.switches.parent / "switches.columns.csv").open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], ["column", "description", "type", "required", "key", "refs", "values"])  # check_data.py
        self.assertEqual(tuple(r[0] for r in rows[1:]), R.SWITCH_COLUMNS)
        self.assertTrue(all(len(r) == len(rows[0]) and r[1].strip() for r in rows[1:]), rows)

    def test_the_views_of_switches_csv(self) -> None:
        """Staging switches (level 1, legs in row order, the first row's whole-switch columns), local switches (main and
        upper switches whose first row gives an area) and hands (main and upper rows with a hand) are views of one file."""
        rr = R.Railroad(self.src)
        self.assertEqual(rr.switches[7].os_blocks, ("OS Switch 7", "OS Switch 7b"))
        self.assertEqual(rr.switches[35].os_blocks, ("OS Switch 35b", "OS Switch 35a"))
        self.assertEqual((rr.switches[7].le_ident, rr.switches[7].hand), ("TO117", "L"))
        self.assertEqual(set(rr.switches), {r.switch for r in rr.switch_rows if r.level == 1})
        local = {s.switch: s for s in rr.local_switches}
        self.assertEqual((local["101"].level, local["101"].area, local["101"].notes),
                         (2, "Peninsula", "Yard throat crossover"))
        self.assertNotIn("107", local)                                  # a control point switch: no area here
        self.assertEqual((rr.hands["101A"].hand, rr.hands["101A"].source), ("L", "plan"))
        self.assertNotIn("225", rr.hands)                               # the double crossover has a row, no hand
        self.assertFalse(any(label.isdigit() and int(label) < 100 for label in rr.hands))

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
        self.append("switches", "2,101,101A,,,,L,plan,Peninsula,,,,,again")
        self.fails(lambda: R.read_local_switches(self.src.switches),
                   r"\(Switch 101\): Switch 101 is also on line 25; a switch's rows go together")
        self.append("lcos_nodes", "3,West,42,again")
        self.fails(lambda: R.read_lcos_nodes(self.src.lcos_nodes), "both list node 42")

    def test_a_switch_in_a_control_point_and_local(self) -> None:
        self.edit("switches", "2,107,107,,,,L,plan,,,,,,", "2,107,107,,,,L,plan,West,,,,,also")
        self.fails(lambda: R.Railroad(self.src).main_upper_switches,
                   r"switch 107 is in a control point and in switches.csv \(line \d+, CP 107\)")

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

    def test_hands_read_strictly(self) -> None:
        self.edit("switches", "2,101,101A,,,,L,", "2,101,101A,,,,X,")
        self.fails(lambda: R.read_hands(self.src.switches), r"switches.csv line 25 \(Switch 101\): hand is L, R or blank")

    def test_device_map(self) -> None:
        dm = R.read_device_map(self.src.devices)
        self.assertEqual(dm.blocks["Track 107-109"].trial, {"Track 107A-109B"})
        self.assertEqual(dm.heads_by_system["IH3332"].user_name, "Head 108LA Top")
        self.assertEqual(dm.turnouts["101"].role, "turnout")
        occ = self.key("occupancy", "BS Switch 101")
        change(self.src.devices, occ, jmri_name="IS:OS101")
        self.fails(lambda: R.read_device_map(self.src.devices), "BS Switch 101 has no virtual IS:HART:C3:B:")
        change(self.src.devices, occ, jmri_name="IS:HART:C3:B:OS101")
        # a detector swapped in by its row (assignment field, ADR-028) is held to its wired M2S sensor, by the
        # column, not the level (naming-layers step 14)
        swap = self.key("occupancy", "BS Switch 107")
        system = R.read_device_map(self.src.devices).by_user("occupancy")["BS Switch 107"].system_name
        text = self.src.devices.read_text(encoding="utf-8")
        change(self.src.devices, swap, assignment="field", jmri_name=system, detector="wired", start="")
        row = R.read_device_map(self.src.devices).by_user("occupancy")["BS Switch 107"]
        self.assertEqual((row.swapped, row.jmri_name), (True, system))
        change(self.src.devices, swap, detector="planned")
        self.fails(lambda: R.read_device_map(self.src.devices), "BS Switch 107 is a field detector")
        self.src.devices.write_text(text, encoding="utf-8")
        # the master holds a (level, layer, name) once, as its own loader checks before the map is read
        change(self.src.devices, self.key("turnout", "DCC Switch 103"), user_name="DCC Switch 101")
        self.fails(lambda: R.read_device_map(self.src.devices), r"DCC Switch 101 \(level 2, turnout\): the same level, layer and user_name twice")

    def test_a_master_that_cannot_be_read(self) -> None:
        self.fails(lambda: R.read_device_map(self.tmp / "missing.csv"), "cannot read it")
        self.fails(lambda: R.read_staging_rows(self.tmp / "missing.csv"), "cannot read it")
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
        # switches.csv itself refuses a number on two levels (read_switch_rows); a control point can still list one
        self.edit("interlockings", "3,CP 217,217,", '3,CP 217,"217,9",')
        self.edit("interlockings", "3,CP 211,", "3,CP 212,")
        self.edit("interlockings", '1,Brick,"1,3,5"', '1,Brick,"1,3,5,99"')
        got = self.problems("switch-numbers")
        self.assertIn("Switch 9 is a switch of levels 1 (switches.csv) and 3 (interlockings.csv)", got)
        self.assertTrue(any("CP 212 is named CP 211 by its lowest switch" in p for p in got), got)
        self.assertTrue(any("level 1 interlocking Brick lists Switch 99, which is no level 1 switch" in p for p in got),
                        got)
        self.edit("interlockings", '2,CP 107,"107,', '2,CP 107,"201,107,')
        self.assertTrue(any("level 2 interlocking CP 107 lists Switch 201, which is no level 2 switch" in p
                            for p in self.problems("switch-numbers")), self.problems("switch-numbers"))

    def test_switches_csv_rows_match_the_main_and_upper_switches(self) -> None:
        """Every main and upper switch has rows in switches.csv, on its control point's level, and no row is for a
        number that is no main or upper switch."""
        self.edit("switches", "2,107,107,", "3,107,107,")
        self.edit("switches", "3,225,225,,,,,,,,,,,double crossover: no hand\n", "")
        self.append("switches", "3,299,299,,,,,,,,,,,")
        got = self.problems("switch-numbers")
        self.assertTrue(any("Switch 107 is level 3, its control point CP 107 level 2" in p for p in got), got)
        self.assertIn("Switch 225 (CP 225, level 3): no row in switches.csv", got)
        self.assertTrue(any("Switch 299 is in no main or upper control point and gives no area" in p for p in got), got)

    def test_lcos_nodes(self) -> None:
        self.edit("switches", "2,101,101A,,,,L,plan,Peninsula,", "2,101,101A,,,,L,plan,Attic,")
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

    def test_a_staging_rows_node_is_its_addresss(self) -> None:
        """The node of a packed address in a staging system name (a head inside a mast's too) is the row's node."""
        self.assertEqual(self.problems("lcos-nodes"), [])
        change(self.src.devices, ("1", "turnout", "Switch 1"), node="3")
        change(self.src.devices, ("1", "mast", "Mast 6LB"), node="12")
        got = self.problems("lcos-nodes")
        self.assertTrue(any("turnout Switch 1 is on node 3, but its address M2T408 is node 4's" in p for p in got), got)
        self.assertTrue(any("mast Mast 6LB is on node 12, but its address IH432 is node 4's" in p for p in got), got)

    def test_staging_devices(self) -> None:
        self.add_staging_row(layer="turnout", role="turnout", user_name="Switch 997", jmri_name="IT:HART:C3:997",
                             system_name="M2T408", dcc="100")
        got = self.problems("staging-devices")
        # the added row is hand-kept, so it comes first in the master
        self.assertTrue(any("DCC 100 is Switch 997 and Switch 1" in p for p in got), got)
        self.assertTrue(any("turnouts Switch 997 and Switch 1 are both M2T408" in p for p in got), got)
        self.assertEqual(len(got), 2, got)          # an LCC alias carries its turnout's DCC address: no clash
        drop(self.src.devices, ("1", "turnout", "Switch 997"))
        change(self.src.devices, ("1", "turnout", "Switch 1"), dcc="")
        self.assertIn("Switch 1 (switches.csv): devices.csv has no staging turnout row with a system_name and dcc",
                      self.problems("staging-devices"))

    def test_a_staging_mast_on_a_block_staging_has_not(self) -> None:
        self.edit("masts", "1,Mast 2L,st:brick,1,Track Main West,", "1,Mast 2L,st:brick,1,Track Nowhere,")
        self.assertIn("masts.csv: Mast 2L: block Track Nowhere is no level 1 block row of the device master",
                      self.problems("masts"))

    def test_staging_blocks(self) -> None:
        # a leg's ID is a device of the master (read_switch_rows), but here an occupancy, not a block
        self.edit("switches", "1,1,,os:1,os:3,block:1C-5A#1+1C-5A#2,", "1,1,,os:1,os:3,det:os:3,")
        self.assertIn("Switch 1 (switches.csv): thrown leg BS Switch 3 is no staging block row of the device master",
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

    def test_block_lengths_rows_are_device_ids(self) -> None:
        """naming-layers step 5: a block_lengths.csv row's (level, id) is a block of the device master, and a
        measured row names a row of it (ADR-039 lane L8)."""
        self.assertEqual([p for p in self.problems("staging-blocks") if "block_lengths" in p], [])
        self.assertEqual(R.Railroad(self.src).block_lengths["Track W-1"].id, "block:3B-end")
        self.edit("block_lengths", "1,block:3C-end,", "1,block:3Z-end,")
        got = self.problems("staging-blocks")
        self.assertIn("block_lengths.csv line 3: block:3Z-end is no level 1 block row of the device master", got)

    def test_hands(self) -> None:
        self.append("switches", "3,299,299,,,,L,owner,,,,,,test")
        got = self.problems("hands")
        self.assertTrue(any("299 is no label the plan's relabel gives" in p for p in got), got)
        self.assertTrue(any("299 is no main or upper switch" in p for p in got), got)

    def test_device_map(self) -> None:
        drop(self.src.devices, self.key("turnout", "Switch 103"))
        change(self.src.devices, self.key("turnout", "Switch 107"), level="3")
        got = self.problems("device-map")
        self.assertIn("Switch 103 (local, level 2): no turnout row in devices.csv", got)
        self.assertTrue(any("Switch 107 is level 3 local, the control points say level 2 CP 107" in p for p in got),
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
        self.assertTrue(any(re.search(r"Switch 101 \(level 2, turnout\): dcc '100' is Switch 1 \(level 1, turnout\)'s as well", p)
                            for p in got), got)
        self.assertTrue(any(re.search(r"Switch 101 \(level 2, turnout\): system_name 'M2T408' is Switch 1 \(level 1, turnout\)'s", p)
                            for p in got), got)
        self.assertTrue(any(re.search(r"Switch 103 \(level 2, turnout\): 0 LCC aliases carry its DCC address", p)
                            for p in got), got)

    def test_name_clash(self) -> None:
        """The staging switches' DCC addresses are aliases "DCC <n>" (owner, 2026-11-17), not "Switch <n>": an alias
        named like a main level turnout would rename it in a rename pass."""
        self.assertEqual(self.problems("name-clash", upto="device_map"), [])
        # a staging row named like a main turnout is the clash
        self.add_staging_row(layer="turnout", role="turnout", user_name="Switch 107", jmri_name="IT:HART:C1:107",
                             system_name="M2T1208", dcc="107")
        got = self.problems("name-clash", upto="device_map")
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0], "devices.csv: Switch 107 (level 1, turnout): staging turnout Switch 107 is "
                                 "level 2 turnout Switch 107 as well")

    def test_level_masts(self) -> None:
        self.edit("masts", "Mast 110L,cp:107,109,Track 105-109,", "Mast 110L,cp:107,125,Track Nowhere,")
        got = self.problems("masts")
        self.assertIn("masts.csv: Mast 110L faces Track Nowhere, which is no device map block", got)
        self.assertIn("masts.csv: Mast 110L protects Switch 125, which is not in CP 107", got)
        lines = self.src.masts.read_text(encoding="utf-8").splitlines(keepends=True)
        self.src.masts.write_text("".join(l for l in lines if not l.startswith("2,Mast 108LA,")), encoding="utf-8")
        self.assertIn("masts.csv: device map mast Mast 108LA has no row", self.problems("masts"))

    def test_tables(self) -> None:
        rr = R.Railroad(self.src)
        self.assertEqual(R.INVARIANTS[-1].run(rr), [])              # the checkout's tables.xml holds them all
        t = rr.tables
        t.turnouts.pop("Switch 1")
        t.turnouts["Switch 107"] = "IT107"          # devices.csv's rows: check_device_master.py's, every level
        got = R.INVARIANTS[-1].run(rr)
        self.assertEqual(got, ["Switch 1 (switches.csv): no turnout Switch 1 in tables.xml"])

    def test_tables_masts_of_every_level(self) -> None:
        rr = R.Railroad(self.src)
        t = rr.tables
        t.masts.pop("Mast 2L")
        t.masts["Mast 110L"] = "IF$x"
        got = R.INVARIANTS[-1].run(rr)
        self.assertTrue(any(p.startswith("masts.csv: Mast 2L: tables.xml has no such mast, the file says IF$")
                            for p in got), got)
        self.assertTrue(any(p.startswith("masts.csv: Mast 110L: tables.xml has IF$x, the file says IF$")
                            for p in got), got)

    def test_tables_staging_switches(self) -> None:
        rr = R.Railroad(self.src)
        rr.tables.turnouts.pop("Switch 3")
        rr.tables.blocks.discard("Track Brick-Plane")
        got = R.INVARIANTS[-1].run(rr)
        self.assertIn("Switch 3 (switches.csv): no turnout Switch 3 in tables.xml", got)
        self.assertIn("Switch 1 (switches.csv): no block Track Brick-Plane in tables.xml", got)


class Known(unittest.TestCase):
    def broken_rows(self) -> R.StagingDevices:
        """The repo's staging rows with one more turnout on Switch 1's DCC address."""
        path = R.Sources.under().devices
        rows = R.read_staging_rows(path) + [(999, {**{c: "" for c in R.STAGING_COLUMNS}, "layer": "turnout",
                                                   "role": "turnout", "user_name": "Switch 999", "dcc": "100"})]
        return R.read_staging_devices(path, rows)

    def test_unknown_problems_fail_and_stale_known_entries_fail(self) -> None:
        rr = R.Railroad(upto="device_map")
        rr.__dict__["staging_devices"] = self.broken_rows()
        problem = ("staging-devices: devices_generated.csv: Switch 1 and Switch 999 (level 1, turnout): DCC 100 is "
                   "Switch 1 and Switch 999")
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
    ROLES = {"block": "track", "occupancy": "track", "head": "head"}

    def row(self, layer, user, jmri, role=None):
        """A row as build_device_map makes it, with the role its writer gives it."""
        role = role or self.ROLES.get(layer) or ("lcc_alias" if user.startswith("DCC ") else "turnout")
        return R.DeviceRow.from_dict(dict(level="2", layer=layer, user_name=user, jmri_name=jmri, role=role))

    def test_a_row_has_the_role_it_is_given_and_never_one_from_its_name(self) -> None:
        self.assertEqual(R.DeviceRow(level=2, layer="block", user_name="OS Switch 7", role="track").role, "track")
        given = R.DeviceRow.from_dict(dict(level=2, layer="turnout", user_name="DCC Switch 1", role="lcc_alias"))
        self.assertEqual(given.role, "lcc_alias")
        with self.assertRaisesRegex(R.FactsError, "level 2 turnout 'DCC Switch 1' has role ''"):
            R.DeviceRow.from_dict(dict(level=2, layer="turnout", user_name="DCC Switch 1"), line=7)
        with self.assertRaisesRegex(R.FactsError, "has role 'siding', not one of"):
            R.DeviceRow(level=2, layer="block", user_name="Track 1-3", role="siding")
        with self.assertRaises(TypeError):          # role is a field with no default
            R.DeviceRow(level=2, layer="head", user_name="Head 2L")

    def test_a_blocks_occupancy_row_is_found_by_its_blocks_column(self) -> None:
        occ = self.row("occupancy", "BS Odd Name", "IS:HART:C3:B:1-3")
        dm = R.DeviceMap(rows=[self.row("block", "Track 1-3", ""), replace(occ, blocks="Track 1-3")])
        self.assertEqual(dm.occupancy["Track 1-3"].user_name, "BS Odd Name")
        self.assertEqual(R.DeviceMap(rows=[occ]).occupancy, {})            # an occupancy row serving no block
        twice = R.DeviceMap(rows=[replace(occ, blocks="Track 1-3", line=4),
                                  replace(occ, user_name="BS 1-3", blocks="Track 1-3", line=9)], path=Path("d.csv"))
        with self.assertRaisesRegex(R.FactsError, "d.csv: occupancy BS Odd Name and BS 1-3 both serve "
                                                  "block Track 1-3"):
            twice.occupancy  # noqa: B018

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

    def test_the_rule_reads_ids_not_names(self) -> None:
        """Naming-layers step 13: a turnout's switch number comes from its id, a block's detector is det:<its id>,
        and a block, detector or mast the owner names keeps its generated virtual names (held to their form only)."""
        ok = [replace(self.row("block", "Track Coal Spur", ""), id="block:1B-end"),
              replace(self.row("occupancy", "BS 1 Spur", "IS:HART:C3:B:1_Spur"), id="det:block:1B-end"),
              replace(self.row("turnout", "Switch Coal", "IT:HART:C3:1"), id="switch:1"),
              replace(self.row("turnout", "DCC Switch Coal", "IT:HART:C3:1", role="lcc_alias"), id="dcc:1"),
              replace(self.row("head", "Head Coal", "IH:HART:C3:2L"), id="mast:1:B:west:single")]
        owner = {(2, "block:1B-end"), (2, "switch:1"), (2, "mast:1:B:west")}
        self.assertEqual(R.check_virtual_names(ok, owner), [])
        bad = R.check_virtual_names(ok)             # the same names taken as generated
        self.assertTrue(any(p.startswith("occupancy BS 1 Spur: jmri_name") for p in bad), bad)
        self.assertTrue(any("Head Coal" in p for p in bad), bad)
        self.assertFalse(any(p.startswith("turnout") for p in bad), bad)       # the number is the id's
        moved = R.check_virtual_names([ok[0], replace(ok[1], id="det:block:3A-end")] + ok[2:], owner)
        self.assertTrue(any("blocks and occupancy rows differ" in p for p in moved), moved)
        self.assertIn("turnout Switch Coal: jmri_name 'IT:HART:C3:1', not IT:HART:C3:<switch number>",
                      R.check_virtual_names([replace(ok[2], id="switch:3")], owner))
        self.assertEqual(R.DeviceMap(rows=ok).turnouts, {"1": ok[2]})
        # paired row by row: a row with no id among rows with ids is named, not a reason to drop the ids
        mixed = R.check_virtual_names(ok + [self.row("block", "Track 3-5", ""),
                                            self.row("occupancy", "BS 3-5", "IS:HART:C3:B:3-5")], owner)
        self.assertEqual(mixed, ["rows with no id among rows with ids: block Track 3-5, occupancy BS 3-5"])
        # a swap (ADR-028): the owner's jmri_name on a turnout is a field device, held to no virtual rule
        swap = [replace(ok[2], jmri_name="M2T408")] + ok[3:]
        self.assertTrue(R.check_virtual_names(swap, owner))
        self.assertEqual(R.check_virtual_names(swap, owner, swapped={(2, "switch:1")}), [])
        # by the row's own column (naming-layers step 14): assignment field is a field device, its alias too
        field = [replace(ok[2], jmri_name="M2T408", assignment="field"),
                 replace(ok[3], jmri_name="MTT120", assignment="field")] + ok[4:]
        self.assertEqual(R.check_virtual_names(field, owner), [])

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
        self.assertEqual(R.read_helix_tracks(self.src.plan_overrides), rr.helix_tracks)
        self.assertEqual([h.block for h in rr.helix_tracks.values()], ["Track Helix Outer", "Track Helix Inner"])

    def test_a_helix_track_named_twice_stops(self) -> None:
        self.edit("plan_overrides", '"131B": "block:37B-helix"', '"131B": "block:39B-helix"')
        with self.assertRaisesRegex(R.FactsError, "named 'Helix Outer'"):
            R.read_helix_tracks(self.src.plan_overrides)

    def test_sources_but_swaps_one_file(self) -> None:
        other = self.src.but(switches=Path("x.csv"))
        self.assertEqual(other.switches, Path("x.csv"))
        self.assertEqual(other.devices, self.src.devices)

    def test_a_layer_beyond_upto_is_refused(self) -> None:
        rr = R.Railroad(self.src, upto="inputs")
        self.assertTrue(rr.has("inputs") and not rr.has("hands"))
        with self.assertRaises(R.LayerError):
            rr.hands
        with self.assertRaises(ValueError):
            R.Railroad(self.src, upto="nope")

    def test_the_staging_rows_are_read_once(self) -> None:
        """staging_devices and switches both start from one read of staging's rows of devices.csv."""
        reads = []
        real = R.read_staging_rows
        self.addCleanup(setattr, R, "read_staging_rows", real)
        R.read_staging_rows = lambda path: reads.append(path) or real(path)
        rr = R.Railroad(self.src, upto="inputs")
        self.assertTrue(rr.staging_devices)
        self.assertTrue(rr.switches)
        self.assertEqual(reads, [self.src.devices])
        self.assertTrue(R.switch_turnouts(self.src.devices, rr.staging_rows, [next(iter(rr.switches))]))
        self.assertEqual(len(reads), 1)


if __name__ == "__main__":
    unittest.main()
