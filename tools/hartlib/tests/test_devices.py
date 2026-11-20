"""hartlib.devices: the device master, its dictionary, the checks, the writers' rules and the generated files."""
from __future__ import annotations

import csv
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import devices as D  # noqa: E402

REAL = D.Files.here()


def blank(**cells) -> dict:
    row = {c: "" for c in D.COLUMNS}
    row.update(cells)
    return row


def turnout(user="Switch 1", **cells) -> dict:
    return blank(**{**dict(level="1", layer="turnout", role="turnout", user_name=user, assignment="field",
                           system_name="M2T408", jmri_name="M2T408", dcc="100",
                           wiring="Node: 4 Turnout: 0 | OU: 1 Ports: 1,2", description="Turnout."), **cells})


def mast(user="Mast 2L", **cells) -> dict:
    return blank(**{**dict(level="1", layer="mast", role="home", user_name=user, assignment="virtual",
                           system_name="IF$vsm:basic:one-low($1)", jmri_name="IF$vsm:basic:one-low($1)",
                           written_by="build_staging_masts.py", description="Mast."), **cells})


def problems(rows) -> str:
    with unittest.TestCase().assertRaises(D.DevicesError) as cm:
        D.check_rows(rows)
    return str(cm.exception)


class TheCommittedMaster(unittest.TestCase):
    def test_it_loads_and_every_row_has_a_description_and_a_known_writer(self):
        rows = D.load()
        self.assertGreater(len(rows), 700)
        self.assertTrue(all(r["description"].strip() for r in rows))
        self.assertLessEqual({r["written_by"] for r in rows}, {""} | set(D.WRITERS))

    def test_the_three_generated_files_are_what_it_generates(self):
        self.assertEqual(D.stale(), [])

    def test_the_dictionary_describes_every_column_and_only_those(self):
        self.assertEqual(list(D.read_dictionary(REAL.dictionary)), list(D.COLUMNS))

    def test_levels_are_one_structure_and_hold_spares_and_status_beans(self):
        rows = D.load()
        self.assertEqual({r["level"] for r in rows}, {"1", "2", "3"})
        self.assertEqual({r["user_name"] for r in rows if r["role"] == "spare"}, {"unused Block 2-2", "unused Block 3-8"})
        self.assertEqual({r["user_name"] for r in rows if r["role"] == "panel_status"},
                         {"Bridge HBLOOP", "SML Mode", "Track Power", "Turnout FB status"})

    def test_the_command_checks_the_checkout(self):
        self.assertEqual(D.main(["check"]), 0)


class TheMasterAgainstTables(unittest.TestCase):
    """The guards public_name_map.csv had against tables.xml, now on the master."""

    @classmethod
    def setUpClass(cls):
        import xml.etree.ElementTree as ET
        from hartlib import paths
        root = ET.parse(paths.REPO_TABLES_XML).getroot()
        cls.rows = D.load()
        cls.system_names = {e.text.strip() for e in root.iter("systemName") if e.text}

        def beans(tag):
            return [((e.findtext("systemName") or "").strip(), (e.findtext("userName") or "").strip())
                    for e in root.iter(tag)]
        cls.turnouts, cls.blocks, cls.heads = beans("turnout"), beans("block"), beans("signalhead")
        cls.masts = beans("signalmast") + beans("virtualsignalmast")
        cls.names = {layer: {r["user_name"] for r in cls.rows if r["layer"] == layer} for layer in D.LAYERS}

    def test_every_live_user_name_on_a_turnout_block_mast_or_head_has_a_row(self):
        missing = [f"{layer} {user} ({system})"
                   for layer, beans in (("turnout", [b for b in self.turnouts if b[0].startswith("M2T")]),
                                        ("block", self.blocks), ("mast", self.masts),
                                        ("head", [b for b in self.heads if b[0].startswith("IH")]))
                   for system, user in beans if user and user not in self.names[layer]]
        self.assertEqual(missing, [])

    def test_every_field_device_system_name_is_in_tables_xml(self):
        missing = [f"{r['user_name']} {r['system_name']}" for r in self.rows
                   if r["assignment"] == "field" and r["system_name"].startswith(("M2T", "M2S", "IH", "MTT"))
                   and r["system_name"] not in self.system_names]
        self.assertEqual(missing, [])

    def test_field_rows_for_wired_hardware_carry_a_comment(self):
        bare = [f"{r['layer']} {r['user_name']}" for r in self.rows
                if r["assignment"] == "field" and r["system_name"].startswith(("M2T", "M2S", "IH", "MTT"))
                and not (r["wiring"] or r["jmri_comment"])]
        self.assertEqual(bare, [])

    def test_mtt_100_to_119_are_lcc_aliases_named_dcc_switch(self):
        by_system = {r["system_name"]: r for r in self.rows if r["system_name"].startswith("MTT")}
        wrong = [name for name in (f"MTT{n}" for n in range(100, 120))
                 if name not in by_system or by_system[name]["role"] != "lcc_alias"
                 or not by_system[name]["user_name"].startswith("DCC Switch ")]
        self.assertEqual(wrong, [])

    def test_mast_comments_name_the_protected_switch(self):
        masts = {r["user_name"]: r for r in self.rows if r["layer"] == "mast" and r["level"] == "1"}
        self.assertEqual(masts["Mast 2L"]["jmri_comment"], "Brick | Switch 1")
        self.assertEqual(masts["Mast 67"]["jmri_comment"], "Princess")


class TheDictionary(unittest.TestCase):
    def read(self, text: str):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "devices.columns.csv"
            p.write_text(text, encoding="utf-8")
            return D.read_dictionary(p)

    def full(self) -> str:
        return "column,description\n" + "".join(f"{c},text\n" for c in D.COLUMNS)

    def test_a_complete_dictionary_reads(self):
        self.assertEqual(set(self.read(self.full())), set(D.COLUMNS))

    def test_a_column_with_no_description_fails(self):
        text = self.full().replace("cp,text\n", "cp,\n")
        with self.assertRaisesRegex(D.DevicesError, "cp has no description"):
            self.read(text)

    def test_a_master_column_missing_from_the_dictionary_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "dir is a master column with no description"):
            self.read(self.full().replace("dir,text\n", ""))

    def test_a_described_column_the_master_lacks_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "colour is described but is no master column"):
            self.read(self.full() + "colour,text\n")

    def test_a_column_described_twice_or_a_bad_header_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "cp is described twice"):
            self.read(self.full() + "cp,again\n")
        with self.assertRaisesRegex(D.DevicesError, "header is column,description"):
            self.read("name,text\n")

    def test_a_missing_file_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "cannot read it"):
            D.read_dictionary(Path("/nonexistent/devices.columns.csv"))


class TheChecks(unittest.TestCase):
    def test_valid_rows_pass(self):
        D.check_rows([turnout(), mast()])

    def test_a_value_outside_its_allowed_set_fails(self):
        for col, bad in (("level", "4"), ("layer", "relay"), ("role", "gizmo"), ("assignment", "alias"),
                         ("written_by", "by_hand.py")):
            with self.subTest(col):
                row = turnout()
                row[col] = bad
                self.assertIn(col if col != "level" else "level", problems([row]))

    def test_an_empty_description_or_name_fails(self):
        self.assertIn("description is empty", problems([turnout(**{}) | {"description": " "}]))
        self.assertIn("user_name is empty", problems([turnout("")]))

    def test_the_same_level_layer_and_name_twice_fails_but_another_level_may_share_a_name(self):
        self.assertIn("the same level, layer and user_name as line 2", problems([turnout(), turnout()]))
        D.check_rows([turnout(), turnout() | {"level": "2", "system_name": "M2T9", "jmri_name": "M2T9"}])

    def test_a_virtual_turnout_and_its_lcc_alias_may_share_a_jmri_name(self):
        virtual = turnout("Switch 101", assignment="virtual", jmri_name="IT:HART:C3:101", level="2")
        alias = virtual | {"user_name": "DCC Switch 101", "role": "lcc_alias", "system_name": "MTT120"}
        D.check_rows([virtual, alias])
        self.assertIn("jmri_name 'IT:HART:C3:101' is line 2's", problems([virtual, virtual | {"user_name": "Switch 103"}]))

    def test_field_rows_have_system_name_equal_to_jmri_name(self):
        row = turnout(jmri_name="M2T409")
        row["role"] = "fb"
        self.assertIn("field, but system_name 'M2T408' is not jmri_name 'M2T409'", problems([row]))

    def test_a_field_turnout_the_tables_bind_by_its_user_name_is_the_one_exception(self):
        D.check_rows([turnout(jmri_name="Switch 1")])

    def test_field_needs_names_and_none_has_no_jmri_name(self):
        self.assertIn("a field device needs", problems([turnout(system_name="")]))
        self.assertIn("assignment none, but jmri_name", problems([turnout(assignment="none")]))
        self.assertIn("a virtual device needs a jmri_name", problems([turnout(assignment="virtual", jmri_name="")]))

    def test_spare_goes_with_role_spare_and_has_its_detector_name(self):
        row = blank(level="1", layer="occupancy", role="turnout", user_name="unused", assignment="spare",
                    system_name="M2S201", jmri_name="M2S201", description="x")
        self.assertIn("assignment spare and role spare go together", problems([row]))
        row = row | {"role": "spare", "jmri_name": ""}
        self.assertIn("a spare detector has its M2S name", problems([row]))

    def test_panel_status_goes_with_the_panel_items_writer(self):
        row = blank(level="1", layer="sensor", role="panel_status", user_name="SML Mode", assignment="virtual",
                    system_name="IS:SML_MODE", jmri_name="IS:SML_MODE", description="x")
        self.assertIn("role panel_status and written_by panel_items.json go together", problems([row]))
        D.check_rows([row | {"written_by": "panel_items.json"}])

    def test_a_row_has_one_comment(self):
        self.assertIn("wiring and jmri_comment are both set", problems([turnout(jmri_comment="x")]))

    def test_pnm_columns_need_a_pnm_order_that_is_a_number_of_its_own(self):
        self.assertIn("pnm_ columns are set but pnm_order is empty", problems([turnout(pnm_cp="Brick")]))
        self.assertIn("pnm_order 'x'", problems([turnout(pnm_order="x")]))
        self.assertIn("pnm_order '1'", problems([turnout(pnm_order="1"), turnout("Switch 3", pnm_order="1",
                                                                                 system_name="M2T9", jmri_name="M2T9")]))

    def test_rows_out_of_order_fail(self):
        self.assertIn("out of order", problems([mast(), turnout()]))
        hand_after_writer = [mast(), mast("Mast 4L", system_name="IF$vsm:basic:one-low($2)",
                                           jmri_name="IF$vsm:basic:one-low($2)") | {"written_by": ""}]
        self.assertIn("out of order", problems(hand_after_writer))


class TheWritersRules(unittest.TestCase):
    def test_a_writer_replaces_only_its_own_rows_and_the_result_is_in_order(self):
        held = [turnout(), mast("Mast 2L"), mast("Mast 4L", system_name="IF$vsm:basic:one-low($2)",
                                                  jmri_name="IF$vsm:basic:one-low($2)")]
        new = [mast("Mast 6L", system_name="IF$vsm:basic:one-low($3)", jmri_name="IF$vsm:basic:one-low($3)")]
        got = D.replace_rows(held, "build_staging_masts.py", new)
        self.assertEqual([r["user_name"] for r in got], ["Switch 1", "Mast 6L"])

    def test_a_writer_not_in_the_one_list_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, "writer 'other.py' is not one of"):
            D.replace_rows([], "other.py", [])

    def test_a_row_naming_another_writer_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, "held by someone else"):
            D.replace_rows([], "build_device_map.py", [mast()])

    def test_a_writer_will_not_take_the_key_of_a_row_someone_else_holds(self):
        held = [turnout()]                                    # hand-kept
        clash = turnout() | {"written_by": "build_device_map.py"}
        with self.assertRaisesRegex(D.DevicesError, r"would rewrite row\(s\) it does not hold: 'Switch 1'.*held by hand"):
            D.replace_rows(held, "build_device_map.py", [clash])
        other = mast() | {"written_by": "build_device_map.py", "level": "2"}
        with self.assertRaisesRegex(D.DevicesError, "held by build_device_map.py"):
            D.replace_rows([other], "build_staging_masts.py", [mast() | {"level": "2"}])

    def test_a_result_that_breaks_a_check_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, "description is empty"):
            D.replace_rows([], "build_staging_masts.py", [mast() | {"description": ""}])


class TheRowForms(unittest.TestCase):
    OLD = dict(level="1", cp="Brick", layer="turnout", user_name="Switch 1", system_name="M2T408",
               jmri_name="M2T408", node="4", dcc="100", comment="Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2",
               trial_name="Switch 1", notes="", blocks="", detector="", stop="", switch="", facing="", protects="",
               dir="")

    def test_a_field_turnouts_dcc_group_is_split_out_and_put_back(self):
        r = D.master_row(self.OLD, "")
        self.assertEqual((r["wiring"], r["dcc"], r["jmri_comment"]), ("Node: 4 Turnout: 0 | OU: 1 Ports: 1,2", "100", ""))
        self.assertEqual(D.device_map_row(r), self.OLD)

    def test_text_that_is_not_wiring_is_a_jmri_comment(self):
        old = dict(self.OLD, layer="mast", user_name="Mast 2L", comment="Brick | Switch 1", dcc="",
                   system_name="IF$vsm:basic:one-low($1)", jmri_name="IF$vsm:basic:one-low($1)")
        r = D.master_row(old, "build_staging_masts.py")
        self.assertEqual((r["wiring"], r["jmri_comment"], r["role"], r["assignment"]),
                         ("", "Brick | Switch 1", "hidden", "virtual"))
        self.assertEqual(D.device_map_row(r), old)

    def test_a_comment_that_cannot_be_split_back_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "does not survive the split"):
            D.master_row(dict(self.OLD, comment="Node: 4 Turnout: 0 | OU: 1 Ports: 1,2"), "")    # no DCC group, field

    def test_a_dcc_text_that_is_not_a_second_group_fails(self):
        with self.assertRaises(ValueError):
            D.master_row(dict(self.OLD, comment="Node: 4 DCC: 100"), "")

    def test_a_row_missing_columns_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "misses columns"):
            D.master_row({"layer": "turnout", "user_name": "x"}, "")

    def test_roles_and_assignments_come_from_the_names(self):
        self.assertEqual([D.block_role(n) for n in ("OS Switch 7", "OS Switch 225b", "Track 101 Spur 1",
                                                    "Track Helix Inner", "BS 107 Loop 2", "Track Barn", "BS Switch 9")],
                         ["os", "xover_corner", "spur", "helix", "loop_half", "track", "os"])
        self.assertEqual(D.role_of("turnout", "DCC Switch 1", "MTT100", "MTT100"), "lcc_alias")
        self.assertEqual(D.role_of("mast", "Mast 67", "", "IF$shsm:basic:one-searchlight(IH:HART:C1:67)"), "intermediate")
        self.assertEqual(D.role_of("mast", "Mast A83", "", "IF$shsm:x(IH:HART:C3:A83)"), "intermediate")
        self.assertEqual(D.role_of("mast", "Mast 108LA", "", "IF$shsm:x(IH:HART:C3:108LA)"), "home")
        with self.assertRaisesRegex(D.DevicesError, "has no sensor rows"):
            D.role_of("sensor", "SML Mode", "IS:SML_MODE", "IS:SML_MODE")
        self.assertEqual([D.assignment_of(n) for n in ("", "IT:HART:C3:101", "IH:HART:C1:2R", "IF$vsm:basic:one-low($1)",
                                                      "IF$shsm:basic:one-searchlight(IH:HART:C1:2R)",
                                                      "IF$shsm:basic:one-searchlight(IH432)", "IH432", "M2T408")],
                         ["none", "virtual", "virtual", "virtual", "virtual", "field", "field", "field"])

    def test_every_role_a_device_map_row_can_have_has_a_description(self):
        for role in D.ROLES:
            if role in ("panel_status",):
                continue
            with self.subTest(role):
                self.assertTrue(D.describe(blank(user_name="X 1", role=role, assignment="field")).endswith("."))
        with self.assertRaisesRegex(D.DevicesError, "no description rule for role 'panel_status'"):
            D.describe(blank(user_name="X", role="panel_status"))


class TheGeneratedFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.files = D.Files(self.tmp / "devices.csv", self.tmp / "devices.columns.csv", self.tmp / "staging.csv",
                             self.tmp / "main_upper.csv", self.tmp / "public_name_map.csv")
        for name in ("master", "dictionary", "staging", "main_upper", "name_map"):
            shutil.copyfile(getattr(REAL, name), getattr(self.files, name))

    def test_a_tampered_generated_file_is_named(self):
        self.files.staging.write_text(self.files.staging.read_text(encoding="utf-8") + "extra\n", encoding="utf-8")
        got = D.stale(self.files)
        self.assertEqual(len(got), 1)
        self.assertIn("staging.csv is not what devices.csv generates", got[0])

    def test_the_name_map_is_the_rows_with_a_pnm_order_in_that_order_and_has_no_alias_rows(self):
        rows = list(csv.DictReader(io.StringIO(D.name_map_text(D.load(self.files)))))
        self.assertTrue(rows)
        self.assertTrue(all(r["current"] == r["proposed"] for r in rows))
        self.assertEqual(len(rows), sum(1 for r in D.load(self.files) if r["pnm_order"]))

    def test_the_device_maps_leave_out_spare_and_status_rows_and_split_levels(self):
        staging = list(csv.DictReader(io.StringIO(D.device_map_text(D.load(self.files), ("1",)))))
        both = list(csv.DictReader(io.StringIO(D.device_map_text(D.load(self.files), ("2", "3")))))
        self.assertEqual({r["level"] for r in staging}, {"1"})
        self.assertEqual({r["level"] for r in both}, {"2", "3"})
        names = {r["user_name"] for r in staging}
        self.assertFalse(names & {"unused Block 2-2", "SML Mode", "Turnout FB status"})

    def test_a_writer_that_gives_its_rows_back_unchanged_changes_no_file(self):
        mine = D.device_map_rows([r for r in D.load(self.files) if r["written_by"] == "build_staging_masts.py"], ("1",))
        out = D.outputs_after("build_staging_masts.py", mine, self.files)
        for path, text in out.items():
            self.assertEqual(path.read_text(encoding="utf-8"), text, path.name)

    def test_a_writer_that_drops_a_row_changes_the_master_and_the_maps_but_no_other_writers_rows(self):
        mine = D.device_map_rows([r for r in D.load(self.files) if r["written_by"] == "build_staging_masts.py"], ("1",))
        out = D.outputs_after("build_staging_masts.py", mine[1:], self.files)
        before = {(r["level"], r["layer"], r["user_name"]) for r in D.load(self.files)}
        after = {(r["level"], r["layer"], r["user_name"]) for r in csv.DictReader(io.StringIO(out[self.files.master]))}
        self.assertEqual(len(before - after), 1)
        self.assertEqual(out[self.files.main_upper], self.files.main_upper.read_text(encoding="utf-8"))

    def test_a_writer_that_gives_a_row_a_hand_kept_row_has_is_refused(self):
        hand = next(r for r in D.load(self.files) if not r["written_by"] and r["layer"] == "turnout")
        stray = D.device_map_row(hand)
        with self.assertRaisesRegex(D.DevicesError, "would rewrite row"):
            D.outputs_after("build_staging_masts.py", [stray], self.files)

    def test_a_row_the_writer_gave_that_is_not_a_device_map_layer_is_refused(self):
        row = dict(TheRowForms.OLD, layer="sensor", user_name="SML Mode")
        with self.assertRaisesRegex(D.DevicesError, "has no sensor rows"):
            D.outputs_after("build_staging_masts.py", [row], self.files)


class TheNits(unittest.TestCase):
    def test_pnm_order_is_compared_as_a_number(self):
        a = turnout(pnm_order="1")
        b = turnout("Switch 3", pnm_order="01", system_name="M2T9", jmri_name="M2T9")
        self.assertIn("pnm_order '01'", problems([a, b]))

    def test_field_rows_with_no_system_name_do_not_clash_with_each_other(self):
        fb = lambda user: blank(level="1", layer="fb", role="fb", user_name=user, assignment="field", description="x")
        text = problems([fb("a"), fb("b")])
        self.assertNotIn("is line", text)
        self.assertIn("a field device needs", text)

    def test_one_data_folder_moves_every_file(self):
        f = D.Files.under(Path("/x/data"))
        self.assertEqual({p.parent for p in (f.master, f.dictionary, f.name_map)}, {Path("/x/data")})
        self.assertEqual({f.staging.parent, f.main_upper.parent}, {Path("/x/data/schematic")})

    def test_a_row_with_a_wrong_column_set_is_a_devices_error(self):
        with self.assertRaisesRegex(D.DevicesError, "misses columns"):
            D.master_row({"layer": "turnout", "user_name": "x", "comment": "", "extra": ""}, "")

    def test_a_stale_generated_file_points_at_regenerate(self):
        f = D.Files.here()
        self.assertIn("hartlib.devices regenerate", D.stale_message(f.staging, f, "tools/schematic/x.py"))
        self.assertNotIn("regenerate", D.stale_message(f.master, f, "tools/schematic/x.py"))


class TheReaders(unittest.TestCase):
    """The one way a reader gets the old files' rows: from the master (device_map_lines, name_map_lines)."""

    def test_the_lines_give_what_the_generated_files_hold(self):
        rows = list(D.load())
        for levels, path in ((("1",), REAL.staging), (("2", "3"), REAL.main_upper)):
            with self.subTest(levels=levels), path.open(newline="", encoding="utf-8") as fh:
                want = list(csv.DictReader(fh))
            got = [{c: r[c] for c in D.DEVICE_COLUMNS} for _n, r in D.device_map_lines(levels)]
            self.assertEqual(got, want)
        with REAL.name_map.open(newline="", encoding="utf-8") as fh:
            old = list(csv.DictReader(fh))
        self.assertEqual([r for _n, r in D.name_map_lines()], old)
        self.assertTrue(all(0 < n <= len(rows) + 1 for n, _r in D.name_map_lines()))

    def test_a_line_is_the_masters_own(self):
        rows = list(D.load())
        for n, r in D.device_map_lines(("2", "3")):
            self.assertEqual((rows[n - 2]["level"], rows[n - 2]["user_name"]), (r["level"], r["user_name"]))
            self.assertEqual(rows[n - 2]["role"], r["role"])

    def test_no_panel_status_row_is_in_a_device_map(self):
        roles = {r["role"] for _n, r in D.device_map_lines(("1", "2", "3"))}
        self.assertFalse(roles & set(D.OUT_OF_MAPS))
        self.assertIn("lcc_alias", roles)

    def test_a_master_that_cannot_be_read_stops_with_its_path(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "devices.csv"
            for call in (lambda: D.device_map_lines(("1",), missing), lambda: D.name_map_lines(missing)):
                with self.assertRaisesRegex(D.DevicesError, "cannot read it"):
                    call()
            missing.write_text("level,layer\n1,mast\n", encoding="utf-8")
            with self.assertRaisesRegex(D.DevicesError, "the header is not the master's columns"):
                D.name_map_lines(missing)

    def test_the_path_or_the_files_name_the_same_master(self):
        self.assertEqual(D.device_map_lines(("1",), REAL.master), D.device_map_lines(("1",), REAL))


class ThePnmComments(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        (self.tmp / "schematic").mkdir()
        self.files = D.Files.under(self.tmp)
        for name in ("master", "dictionary", "staging", "main_upper", "name_map"):
            shutil.copyfile(getattr(REAL, name), getattr(self.files, name))

    def test_a_row_a_builder_writes_takes_the_comment_and_keeps_its_owner(self):
        """pnm_comment is no builder's output, so a builder's row may change it, and written_by stays."""
        head = next(r for r in D.load(self.files) if r["layer"] == "head" and r["pnm_order"] and r["written_by"])
        update = D.set_pnm_comments("head", {head["user_name"]: "a new comment"}, self.files)
        self.assertEqual(update.changed, 1)
        changed = {(r["level"], r["layer"], r["user_name"]): r for r in csv.DictReader(io.StringIO(update.texts[self.files.master]))}
        row = changed[(head["level"], head["layer"], head["user_name"])]
        self.assertEqual((row["pnm_comment"], row["written_by"]), ("a new comment", head["written_by"]))
        self.assertEqual({k: v for k, v in row.items() if k != "pnm_comment"},
                         {k: v for k, v in head.items() if k != "pnm_comment"})
        self.assertIn("a new comment", update.texts[self.files.name_map])

    def test_the_comment_survives_the_builders_next_run(self):
        """The builder's rewrite carries the pnm_ columns of the row it replaces (outputs_after_rows)."""
        head = next(r for r in D.load(self.files) if r["layer"] == "head" and r["pnm_order"] and r["written_by"])
        update = D.set_pnm_comments("head", {head["user_name"]: "a new comment"}, self.files)
        D.write_all(self.files, update.texts)
        mine = [dict(r) for r in D.load(self.files) if r["written_by"] == head["written_by"]]
        for r in mine:                                   # what the builder gives: its columns, none of the pnm_ ones
            r.update({c: "" for c in r if c.startswith("pnm_")})
        out = D.outputs_after_rows(head["written_by"], mine, self.files)
        row = next(r for r in csv.DictReader(io.StringIO(out[self.files.master]))
                   if r["user_name"] == head["user_name"] and r["layer"] == "head")
        self.assertEqual(row["pnm_comment"], "a new comment")

    def test_a_comment_for_a_name_that_is_no_row_changes_nothing(self):
        update = D.set_pnm_comments("head", {"Head Nowhere": "x"}, self.files)
        self.assertEqual((update.changed, update.texts), (0, {}))

    def test_no_change_gives_no_texts(self):
        head = next(r for r in D.load(self.files) if r["layer"] == "head" and r["pnm_order"])
        update = D.set_pnm_comments("head", {head["user_name"]: head["pnm_comment"] or head["user_name"]}, self.files) \
            if head["pnm_comment"] else D.set_pnm_comments("head", {}, self.files)
        self.assertEqual((update.changed, update.texts), (0, {}))

    def test_a_hand_kept_row_changes_and_the_name_map_follows(self):
        rows = [dict(r) for r in D.load(self.files)]
        hand = next(r for r in rows if r["layer"] == "turnout" and r["pnm_order"] and not r["written_by"])
        update = D.set_pnm_comments("turnout", {hand["user_name"]: "Node: 99"}, self.files)
        self.assertEqual(update.changed, 1)
        self.assertIn("Node: 99", update.texts[self.files.name_map])
        self.assertNotIn("Node: 99", update.texts[self.files.staging])


class TheMasterFile(unittest.TestCase):
    def read(self, text: str):
        with tempfile.TemporaryDirectory() as d:
            files = D.Files.here().but(master=Path(d) / "devices.csv")
            files.master.write_text(text, encoding="utf-8")
            return D.load(files)

    def test_a_wrong_header_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "header is not the master's columns"):
            self.read("level,cp\n1,x\n")

    def test_a_short_row_fails_with_its_line(self):
        with self.assertRaisesRegex(D.DevicesError, "line 2: 2 fields"):
            self.read(",".join(D.COLUMNS) + "\n1,x\n")

    def test_a_missing_master_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "cannot read it"):
            D.load(D.Files.here().but(master=Path("/nonexistent/devices.csv")))

    def test_the_writers_are_one_tuple_of_distinct_names(self):
        self.assertEqual(len(set(D.WRITERS)), len(D.WRITERS))
        self.assertEqual(set(D.WRITERS), {"build_staging_masts.py", "build_device_map.py", "build_main_upper_masts.py",
                                          "panel_items.json"})


if __name__ == "__main__":
    unittest.main()
