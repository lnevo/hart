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
from master_edit import fixture_id  # noqa: E402

REAL = D.Files.here()
# A second writer for the writer rules' fixtures: build_masts.py held the staging masts until naming-layers step 12,
# and now build_device_map.py writes every mast, so these tests add one of their own to devices.WRITERS
OTHER = "test_writer.py"
_WRITERS = None


def setUpModule():
    """devices.WRITERS with OTHER last, for this module's tests (and the modules that import it, which call it)."""
    global _WRITERS
    if _WRITERS is None:
        _WRITERS = D.WRITERS
        D.WRITERS = (*D.WRITERS, OTHER)


def tearDownModule():
    global _WRITERS
    if _WRITERS is not None:
        D.WRITERS, _WRITERS = _WRITERS, None


def blank(**cells) -> dict:
    """A master row of `cells`, the rest empty; a row with a level gets a test id from its layer and name unless
    `cells` gives one (check_rows wants one on every row with a level)."""
    row = {c: "" for c in D.COLUMNS}
    row.update(cells)
    if row["level"] and "id" not in cells:
        row["id"] = fixture_id(row)
    return row


def turnout(user="Switch 1", **cells) -> dict:
    return blank(**{**dict(level="1", layer="turnout", role="turnout", user_name=user, assignment="field",
                           system_name="M2T408", jmri_name="M2T408", dcc="100",
                           wiring="Node: 4 Turnout: 0 | OU: 1 Ports: 1,2", description="Turnout."), **cells})


def mast(user="Mast 2L", **cells) -> dict:
    return blank(**{**dict(level="1", layer="mast", role="home", user_name=user, assignment="virtual",
                           system_name="IF$vsm:basic:one-low($1)", jmri_name="IF$vsm:basic:one-low($1)",
                           written_by=OTHER, description="Mast."), **cells})


def old_form(rows, levels=("1",)) -> list[dict]:
    """The device-map rows of `levels` (device_map_rows) each with its role and id, as a writer gives them to
    outputs_after."""
    return [dict(D.device_map_row(r), role=r["role"], id=r["id"]) for r in rows
            if r["level"] in levels and r["role"] not in D.OUT_OF_MAPS]


def problems(rows) -> str:
    with unittest.TestCase().assertRaises(D.DevicesError) as cm:
        D.check_rows(rows)
    return str(cm.exception)


class TheCommittedMaster(unittest.TestCase):
    def test_it_loads_and_every_row_has_a_description_and_a_known_writer(self):
        rows = D.load()
        self.assertGreater(len(rows), 700)
        self.assertTrue(all(r.description.strip() for r in rows))
        self.assertLessEqual({r.written_by for r in rows}, {""} | set(D.WRITERS))

    def test_the_three_generated_files_are_what_it_generates(self):
        self.assertEqual(D.stale(), [])

    def test_the_dictionary_describes_every_column_and_only_those(self):
        self.assertEqual(list(D.read_dictionary(REAL.dictionary)), list(D.COLUMNS))

    def test_levels_are_one_structure_and_hold_spares_and_status_beans(self):
        rows = D.load()
        self.assertEqual({r.level_cell for r in rows if not D.is_unplaced(r)}, {"1", "2", "3"})
        self.assertEqual({r.user_name for r in rows if r.role == "spare"}, {"unused Block 2-2", "unused Block 3-8"})
        self.assertEqual({r.user_name for r in rows if r.role == "panel_status"},
                         {"Bridge HBLOOP", "SML Mode", "Track Power", "Turnout FB status"})

    def test_the_command_checks_the_checkout(self):
        self.assertEqual(D.main(["check"]), 0)


class TheMasterAgainstTables(unittest.TestCase):
    """The guards the old public name map had against tables.xml, now on the master."""

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
        cls.names = {layer: {r.user_name for r in cls.rows if r.layer == layer} for layer in D.LAYERS}

    def test_every_live_user_name_on_a_turnout_block_mast_or_head_has_a_row(self):
        missing = [f"{layer} {user} ({system})"
                   for layer, beans in (("turnout", [b for b in self.turnouts if b[0].startswith("M2T")]),
                                        ("block", self.blocks), ("mast", self.masts),
                                        ("head", [b for b in self.heads if b[0].startswith("IH")]))
                   for system, user in beans if user and user not in self.names[layer]]
        self.assertEqual(missing, [])

    def test_every_field_device_system_name_is_in_tables_xml(self):
        missing = [f"{r.user_name} {r.system_name}" for r in self.rows
                   if r.assignment == "field" and r.system_name.startswith(("M2T", "M2S", "IH", "MTT"))
                   and r.system_name not in self.system_names]
        self.assertEqual(missing, [])

    def test_field_rows_for_wired_hardware_carry_a_comment(self):
        bare = [f"{r.layer} {r.user_name}" for r in self.rows
                if r.assignment == "field" and r.system_name.startswith(("M2T", "M2S", "IH", "MTT"))
                and not (r.wiring or r.jmri_comment) and not D.is_unplaced(r)]   # kept as the Store had it
        self.assertEqual(bare, [])

    def test_mtt_100_to_119_are_lcc_aliases_named_dcc_switch(self):
        by_system = {r.system_name: r for r in self.rows if r.system_name.startswith("MTT")}
        wrong = [name for name in (f"MTT{n}" for n in range(100, 120))
                 if name not in by_system or by_system[name].role != "lcc_alias"
                 or not by_system[name].user_name.startswith("DCC Switch ")]
        self.assertEqual(wrong, [])

    def test_mast_comments_name_the_protected_switch(self):
        masts = {r.user_name: r for r in self.rows if r.layer == "mast" and r.level == 1}
        self.assertEqual(masts["Mast 2L"].jmri_comment, "Brick | Switch 1")
        self.assertEqual(masts["Mast 67"].jmri_comment, "Princess")


class TheDictionary(unittest.TestCase):
    def read(self, text: str):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "devices.columns.csv"
            p.write_text(text, encoding="utf-8")
            return D.read_dictionary(p)

    def full(self) -> str:
        return "column,file,description\n" + "".join(f"{c},{D.column_file(c)},text\n" for c in D.COLUMNS)

    def test_a_complete_dictionary_reads(self):
        self.assertEqual(set(self.read(self.full())), set(D.COLUMNS))

    def test_a_column_with_no_description_fails(self):
        text = self.full().replace("cp,field,text\n", "cp,field,\n")
        with self.assertRaisesRegex(D.DevicesError, "cp has no description"):
            self.read(text)

    def test_a_master_column_missing_from_the_dictionary_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "dir is a master column with no description"):
            self.read(self.full().replace("dir,generated,text\n", ""))

    def test_a_described_column_the_master_lacks_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "colour is described but is no master column"):
            self.read(self.full() + "colour,generated,text\n")

    def test_a_column_described_twice_or_a_bad_header_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "cp is described twice"):
            self.read(self.full() + "cp,field,again\n")
        with self.assertRaisesRegex(D.DevicesError, "header is column,file,description"):
            self.read("name,text\n")

    def test_a_column_in_the_wrong_file_fails(self):
        """The file column says which file may hold a column: the key and FIELD_COLUMNS the field file, the rest the
        generated file alone."""
        self.assertEqual({c for c in D.COLUMNS if D.column_file(c) == "field"},
                         set(D.KEY) | set(D.FIELD_HELD) | set(D.FIELD_COLUMNS))
        with self.assertRaisesRegex(D.DevicesError, "wiring is in file 'generated', not 'field'"):
            self.read(self.full().replace("wiring,generated,", "wiring,field,"))

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
        self.assertIn("Switch 1 (level 1, turnout): the same level, layer and user_name twice",
                      problems([turnout(), turnout()]))
        D.check_rows([turnout(), turnout() | {"level": "2", "system_name": "M2T9", "jmri_name": "M2T9"}])

    def test_a_virtual_turnout_and_its_lcc_alias_may_share_a_jmri_name(self):
        virtual = turnout("Switch 101", assignment="virtual", jmri_name="IT:HART:C3:101", level="2")
        alias = virtual | {"user_name": "DCC Switch 101", "role": "lcc_alias", "system_name": "MTT120",
                           "id": "dcc:101"}
        D.check_rows([virtual, alias])
        self.assertIn("jmri_name 'IT:HART:C3:101' is Switch 101 (level 2, turnout)'s",
                      problems([virtual, virtual | {"user_name": "Switch 103"}]))

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

    def test_only_a_line_block_lists_places_in_cp(self):
        self.assertIn("cp 'Brick;Plane' is a list, but a turnout sits in one control point",
                      problems([turnout(cp="Brick;Plane")]))
        D.check_rows([blank(level="1", layer="block", role="track", user_name="Track X", assignment="none",
                            cp="Brick;Plane", description="x")])
        self.assertEqual(D.cp_list({"cp": "Brick;Plane"}), ["Brick", "Plane"])
        self.assertEqual(D.cp_list({"cp": ""}), [])

    def test_a_row_has_one_comment(self):
        self.assertIn("wiring and jmri_comment are both set", problems([turnout(jmri_comment="x")]))

    def test_the_name_map_copy_is_gone(self):
        """The six pnm_ columns (the name map's copy, R9e) are no master columns: their facts are in cp, system_name,
        dcc, wiring, jmri_comment and notes."""
        self.assertFalse([c for c in D.COLUMNS if c.startswith("pnm_")])
        self.assertFalse(hasattr(D, "name_map_lines"))

    def test_rows_out_of_order_fail(self):
        self.assertIn("out of order", problems([mast(), turnout()]))
        hand_after_writer = [mast(), mast("Mast 4L", system_name="IF$vsm:basic:one-low($2)",
                                           jmri_name="IF$vsm:basic:one-low($2)") | {"written_by": ""}]
        self.assertIn("out of order", problems(hand_after_writer))


def block(user="OS Switch 9", **cells) -> dict:
    return blank(**{**dict(level="1", layer="block", role="os", user_name=user, assignment="field",
                           system_name="IB:AUTO:0040", jmri_name="IB:AUTO:0040", layout_block="ILB40",
                           written_by="build_device_map.py", description="Block."), **cells})


def part(user="Track 9-11", part_of="OS Switch 9", **cells) -> dict:
    return blank(**{**dict(level="1", layer="block", role="part", user_name=user, assignment="none",
                           part_of=part_of, written_by="build_device_map.py", description="Part."), **cells})


class TheParts(unittest.TestCase):
    """A block row with part_of is a piece of track inside another block: it makes no JMRI block,
    layout block or occupancy row of its own, and the block it names exists and is no part itself."""

    def test_a_part_of_an_existing_block_passes(self):
        D.check_rows([block(), part()])

    def test_role_part_and_part_of_go_together(self):
        self.assertIn("role part and part_of go together", problems([block(), part(role="track")]))
        self.assertIn("role part and part_of go together", problems([block(), part(part_of="")]))

    def test_only_a_block_row_is_a_part(self):
        self.assertIn("part_of is for a block row", problems([block(), part(layer="occupancy")]))

    def test_a_part_has_no_detector_of_its_own_on_every_level(self):
        """One rule for every level: a part is a JMRI block whose occupancy sensor is its block's,
        so it has no detector, wiring, node or DCC address of its own, and no field assignment."""
        for level in ("1", "2"):
            home = block(level=level) if level == "1" else block(level="2", assignment="none", system_name="",
                                                                    jmri_name="", layout_block="")
            for col, value in (("assignment", "field"), ("node", "4"), ("detector", "wired"),
                               ("wiring", "Node: 4 Block: 2"), ("dcc", "100")):
                with self.subTest(level=level, col=col):
                    self.assertIn("a part has no detector of its own",
                                  problems([home, part(level=level, **{col: value})]))

    def test_a_part_may_be_a_jmri_block_of_its_own_on_every_level(self):
        # main and upper's links and staging's 16 pieces: a JMRI block and layout block whose
        # sensor is its block's
        main = block(level="2", assignment="none", system_name="", jmri_name="", layout_block="")
        D.check_rows([main, part(level="2", system_name="IB9", jmri_name="IB9", layout_block="ILB9",
                                 assignment="virtual")])
        D.check_rows([block(), part(jmri_name="IB:AUTO:0099", layout_block="ILB99", assignment="virtual")])

    def test_a_parts_description_is_the_same_on_every_level(self):
        for level in ("1", "2"):
            self.assertEqual(D.describe(part(level=level)),
                             "Piece Track 9-11 of block OS Switch 9: a JMRI block of its own on OS Switch 9's "
                             "occupancy sensor.")
        self.assertFalse(hasattr(D, "STAGING_LEVELS"))
    def test_the_block_it_names_is_on_the_parts_own_level(self):
        other = block(level="2", assignment="none", system_name="", jmri_name="", layout_block="")
        self.assertIn("part_of 'OS Switch 9' is no block row", problems([part(), other]))
        # a level 2 part that has a level 1 block's name is no part of a chain on level 1
        other11 = other | {"user_name": "OS Switch 11", "id": "os:11"}
        D.check_rows([block(), part(), other11, part(level="2", user_name="OS Switch 9", part_of="OS Switch 11")])

    def test_the_block_it_names_must_exist(self):
        self.assertIn("part_of 'OS Switch 11' is no block row", problems([block(), part(part_of="OS Switch 11")]))

    def test_a_part_of_a_part_is_refused_so_no_chain_or_cycle(self):
        chain = [block(), part(), part("Track 7-9", part_of="Track 9-11")]
        self.assertIn("part_of 'Track 9-11' is itself a part", problems(chain))
        cycle = [part("Track 1-3", part_of="Track 3-5"), part("Track 3-5", part_of="Track 1-3")]
        self.assertIn("itself a part", problems(cycle))

    def test_a_start_is_one_its_layer_takes_on_a_row_with_a_bean(self):
        """start (naming-layers step 9): inactive on a detector, closed or thrown on a turnout, on a row with a bean of
        its own (a jmri_name, not an LCC alias); empty anywhere else."""
        D.check_rows([turnout(start="thrown"), mast(bean_comment="any words")])
        self.assertIn("start 'inactive' is not one a turnout row takes (closed, thrown)",
                      problems([turnout(start="inactive")]))
        self.assertIn("start 'closed' is not one a mast row takes (none)", problems([mast(start="closed")]))
        self.assertIn("start is set, but the row makes no bean of its own",
                      problems([turnout(role="lcc_alias", start="closed")]))
        self.assertIn("start is set, but the row makes no bean of its own",
                      problems([turnout(assignment="none", system_name="", jmri_name="", start="closed")]))

    def test_the_device_maps_leave_parts_out(self):
        self.assertIn("part", D.OUT_OF_MAPS)
        self.assertIn("a JMRI block of its own", D.describe(part()))


BEAN = ('{"beans":[{"section":["turnouts","jmri.jmrix.openlcb.configurexml.OlcbTurnoutManagerXml"],'
        '"element":{"tag":"turnout","attrs":{"feedback":"MONITORING"},"children":[{"tag":"systemName","attrs":{},'
        '"text":"MTT999"},{"tag":"userName","column":"user_name"}]}}]}')


def unplaced(user="Test 999", **cells) -> dict:
    return blank(**{**dict(level="", layer="turnout", user_name=user, assignment="field", system_name="MTT999",
                           jmri_name="MTT999", jmri_bean=BEAN, description="Added in PanelPro."), **cells})


class TheUnplacedDevices(unittest.TestCase):
    """A device added in PanelPro and not on the layout yet has no level, cp or role, and carries its Store beans in
    jmri_bean; it comes after every level's rows."""

    def test_a_level_less_row_with_its_bean_passes(self) -> None:
        D.check_rows([turnout(), unplaced()])

    def test_no_level_needs_a_bean(self) -> None:
        self.assertIn("or empty for a device kept by its jmri_bean", problems([unplaced(jmri_bean="")]))

    def test_a_row_with_a_level_has_no_bean(self) -> None:
        self.assertIn("jmri_bean is for a level-less device", problems([turnout(jmri_bean=BEAN)]))

    def test_a_level_less_row_has_no_cp_role_or_writer_yet(self) -> None:
        got = problems([unplaced(cp="Brick", role="turnout", written_by="build_device_map.py")])
        self.assertIn("has no cp, role, written_by", got)

    def test_its_bean_is_its_own(self) -> None:
        self.assertIn("holds no bean named 'MTT998'", problems([unplaced(system_name="MTT998", jmri_name="MTT998")]))
        self.assertIn("not JSON", problems([unplaced(jmri_bean="{")]))

    def test_it_comes_after_every_level(self) -> None:
        self.assertIn("out of order", problems([unplaced(), turnout()]))


class TheWritersRules(unittest.TestCase):
    def test_a_writer_replaces_only_its_own_rows_and_the_result_is_in_order(self):
        held = [turnout(), mast("Mast 2L"), mast("Mast 4L", system_name="IF$vsm:basic:one-low($2)",
                                                  jmri_name="IF$vsm:basic:one-low($2)")]
        new = [mast("Mast 6L", system_name="IF$vsm:basic:one-low($3)", jmri_name="IF$vsm:basic:one-low($3)")]
        got = D.replace_rows(held, OTHER, new)     # virtual masts: the rule's, no field facts
        self.assertEqual([r["user_name"] for r in got], ["Switch 1", "Mast 6L"])

    def test_a_writer_not_in_the_one_list_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, "writer 'other.py' is not one of"):
            D.replace_rows([], "other.py", [])

    def test_a_row_naming_another_writer_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, "held by someone else"):
            D.replace_rows([], "build_device_map.py", [mast()])

    def test_a_writer_will_not_take_the_key_of_a_row_someone_else_holds(self):
        held = [unplaced()]                                   # a Store's device: the field file's
        clash = unplaced() | {"written_by": "build_device_map.py"}
        with self.assertRaisesRegex(D.DevicesError, r"would rewrite row\(s\) it does not hold: 'Test 999'.*held by "
                                                    r"devices_field.csv"):
            D.replace_rows(held, "build_device_map.py", [clash])
        other = mast() | {"written_by": "build_device_map.py", "level": "2"}
        with self.assertRaisesRegex(D.DevicesError, "held by build_device_map.py"):
            D.replace_rows([other], OTHER, [mast() | {"level": "2"}])

    def test_a_result_that_breaks_a_check_is_refused(self):
        with self.assertRaisesRegex(D.DevicesError, "description is empty"):
            D.replace_rows([], OTHER, [mast() | {"description": ""}])


class TheRowForms(unittest.TestCase):
    OLD = dict(level="1", cp="Brick", layer="turnout", user_name="Switch 1", system_name="M2T408",
               jmri_name="M2T408", node="4", dcc="100", comment="Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2",
               trial_name="Switch 1", notes="", blocks="", detector="", stop="", switch="", facing="", protects="",
               dir="", role="turnout")

    def test_a_field_turnouts_dcc_group_is_split_out_and_put_back(self):
        r = D.master_row(dict(self.OLD, id="switch:1"), "")
        self.assertEqual((r["wiring"], r["dcc"], r["jmri_comment"]), ("Node: 4 Turnout: 0 | OU: 1 Ports: 1,2", "100", ""))
        self.assertEqual(dict(D.device_map_row(r), role=r["role"]), self.OLD)

    def test_text_that_is_not_wiring_is_a_jmri_comment(self):
        old = dict(self.OLD, layer="mast", user_name="Mast 2L", comment="Brick | Switch 1", dcc="",
                   system_name="IF$vsm:basic:one-low($1)", jmri_name="IF$vsm:basic:one-low($1)", role="hidden")
        r = D.master_row(old, OTHER)
        self.assertEqual((r["wiring"], r["jmri_comment"], r["role"], r["assignment"]),
                         ("", "Brick | Switch 1", "hidden", "virtual"))
        self.assertEqual(dict(D.device_map_row(r), role=r["role"]), old)

    def test_a_comment_that_cannot_be_split_back_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "does not survive the split"):
            D.master_row(dict(self.OLD, id="switch:1", comment="Node: 4 Turnout: 0 | OU: 1 Ports: 1,2"), "")  # no DCC group

    def test_a_dcc_text_that_is_not_a_second_group_fails(self):
        with self.assertRaises(ValueError):
            D.master_row(dict(self.OLD, comment="Node: 4 DCC: 100"), "")

    def test_a_row_missing_columns_fails(self):
        with self.assertRaisesRegex(D.DevicesError, "misses columns"):
            D.master_row({"layer": "turnout", "user_name": "x"}, "")

    def test_the_role_is_the_writers_never_the_names(self):
        """A writer states each row's role (hand-off row 8): master_row keeps it whatever the name says, and stops on
        a row with none, one not in ROLES, or a layer a device map does not hold."""
        odd = dict(self.OLD, layer="block", user_name="OS Switch 7", system_name="", jmri_name="", node="", dcc="",
                   comment="", role="track")          # an OS-shaped name: the role given wins
        self.assertEqual(D.master_row(odd, "build_device_map.py")["role"], "track")
        for role in (None, "", "siding"):
            with self.subTest(role=role), self.assertRaisesRegex(D.DevicesError, "gives it role"):
                row = {k: v for k, v in self.OLD.items() if k != "role"} if role is None else dict(self.OLD, role=role)
                D.master_row(row, "build_device_map.py")
        with self.assertRaisesRegex(D.DevicesError, "has no sensor rows"):
            D.master_row(dict(self.OLD, layer="sensor", user_name="SML Mode"), OTHER)
        self.assertFalse(hasattr(D, "role_of") or hasattr(D, "block_role"))

    def test_assignments_come_from_the_jmri_name(self):
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


def hand_keep(files, layer="turnout", user="Switch 1"):
    """Make one row of the copied master hand-kept again (no written_by; every committed row has a
    writer), moved ahead of the writers' rows of its level as a hand-kept row stands, and return it."""
    rows = [r.cells() for r in D.load(files)]
    i = next(i for i, r in enumerate(rows) if r["layer"] == layer and r["user_name"] == user)
    row = dict(rows.pop(i), written_by="")
    at = next(i for i, r in enumerate(rows) if r["level"] == row["level"])
    rows.insert(at, row)
    files.master.write_text(D.master_text(rows), encoding="utf-8")
    return row


class TheWriters(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.files = D.Files(self.tmp / "devices.csv", self.tmp / "devices.columns.csv")
        D.one_file_copy(self.files.master)              # a copy that holds every cell, edited row by row
        shutil.copyfile(REAL.dictionary, self.files.dictionary)

    def test_the_master_and_its_dictionary_check_clean(self):
        self.assertEqual(D.stale(self.files), [])

    def test_a_device_not_on_the_layout_yet_passes_the_check(self):
        """A Store's level-less row (split_store --apply) has no role: it is on no device map, so the check leaves it
        out rather than stopping on its empty role."""
        self.files.master.write_text(D.master_text([r.cells() for r in D.load(self.files)] + [unplaced()]), "utf-8")
        self.assertTrue(any(D.is_unplaced(r) for r in D.load(self.files)))
        self.assertEqual(D.stale(self.files), [])

    def test_a_row_the_old_form_readers_cannot_convert_fails_the_check(self):
        rows = [r.cells() for r in D.load(self.files)]
        row = next(r for r in rows if r["role"] == "turnout" and r["assignment"] == "field" and r["wiring"] and r["dcc"])
        row["wiring"] = row["wiring"] + " | DCC: 1"                  # a DCC group of its own beside the dcc column
        self.files.master.write_text(D.master_text(rows), encoding="utf-8")
        got = D.stale(self.files)
        self.assertEqual(len(got), 1)
        self.assertIn(row["user_name"], got[0])

    def test_the_device_maps_leave_out_spare_and_status_rows_and_split_levels(self):
        staging = D.device_map_rows([r.cells() for r in D.load(self.files)], ("1",))
        both = D.device_map_rows([r.cells() for r in D.load(self.files)], ("2", "3"))
        self.assertEqual({r["level"] for r in staging}, {"1"})
        self.assertEqual({r["level"] for r in both}, {"2", "3"})
        names = {r["user_name"] for r in staging}
        self.assertFalse(names & {"unused Block 2-2", "SML Mode", "Turnout FB status"})

    WRITER = "build_device_map.py"          # every level's rows, masts and heads too (naming-layers step 12)

    def mine(self, files):
        return [r.cells() for r in D.load(files) if r.written_by == self.WRITER]

    def test_a_writer_that_gives_its_rows_back_unchanged_changes_no_file(self):
        out = D.outputs_after_rows(self.WRITER, self.mine(self.files), self.files)
        for path, text in out.items():
            self.assertEqual(path.read_text(encoding="utf-8"), text, path.name)

    def test_a_writer_that_drops_a_row_changes_only_its_own_rows_of_the_master(self):
        mine = self.mine(self.files)
        drop = next(r for r in mine if r["role"] == "hidden")           # a virtual mast: no field cells
        gone = (drop["level"], drop["layer"], drop["user_name"])
        out = D.outputs_after_rows(self.WRITER, [r for r in mine if r is not drop], self.files,
                                   warn=lambda line: None)
        before = {(r.level_cell, r.layer, r.user_name) for r in D.load(self.files)}
        after = {(r["level"], r["layer"], r["user_name"]) for r in csv.DictReader(io.StringIO(out[self.files.master]))}
        self.assertEqual(len(before - after), 1)
        self.assertEqual(before - after, {gone})
        self.assertEqual(after - before, set())                       # no row is added
        held = [r.cells() for r in D.load(self.files) if r.written_by != self.WRITER]
        kept = [r for r in csv.DictReader(io.StringIO(out[self.files.master])) if r["written_by"] != self.WRITER]
        self.assertEqual(kept, held)                                  # every other writer's and hand-kept row is as it was

    def test_a_writer_that_renames_a_device_the_field_file_names_is_refused(self):
        """A rename keeps the key (the id), and the field row names the mast (Mast 6LB): a writer that gives
        another name would override the owner's, so the write stops and says to drop the field row's user name."""
        pair = D.pair_copy(self.tmp / "pair")
        mine = self.mine(pair)
        first = next(r for r in mine if r["user_name"] == "Mast 6LB")            # the wired mast
        renamed = [dict(r, user_name=r["user_name"] + " X") if r is first else r for r in mine]
        with self.assertRaisesRegex(D.DevicesError, r"build_device_map.py names id 'mast:\S+' \(level 1, mast\) "
                                                    r"'Mast 6LB X', but devices_field.csv names it 'Mast 6LB'"):
            D.outputs_after_rows(self.WRITER, renamed, pair, warn=lambda line: None)

    def test_a_writer_that_would_drop_an_id_the_field_file_holds_is_refused(self):
        """Decision 3: a gone ID with owner's cells (Mast 6LB's node, in devices_field.csv) stops the write, which
        lists it, its cells and the new IDs of its level and layer."""
        pair = D.pair_copy(self.tmp / "pair")
        mine = self.mine(pair)
        first = next(r for r in mine if r["user_name"] == "Mast 6LB")
        moved = [dict(r, id="mast:99:A:west") if r is first else r for r in mine]
        with self.assertRaisesRegex(D.DevicesError, rf"id '{first['id']}' \(Mast 6LB \(level 1, mast\)\) is gone "
                                                    r"from the plan, and its field row holds user_name 'Mast 6LB', "
                                                    r"node '4': move them to the device's new id \(new on level 1, "
                                                    r"mast: mast:99:A:west\), or remove the row"):
            D.outputs_after_rows(self.WRITER, moved, pair, warn=lambda line: None)

    def test_a_rule_mast_and_a_panel_status_bean_may_go_without_saying_so(self):
        """Rows the rule makes (a virtual staging mast) or panel_items.json writes carry no field facts, so their
        writers drop them freely (build_device_map.py and panel_items.py pass no drops)."""
        mine = [r for r in self.mine(self.files) if r["user_name"] != "Mast 4LA"]
        out = D.outputs_after_rows(self.WRITER, mine, self.files, warn=lambda line: None)
        self.assertNotIn(",Mast 4LA,", out[self.files.master])
        status = [r.cells() for r in D.load(self.files) if r.written_by == "panel_items.json"]
        out = D.outputs_after_rows("panel_items.json", [r for r in status if r["user_name"] != "SML Mode"], self.files)
        self.assertNotIn(",SML Mode,", out[self.files.master])

    def test_the_guarded_rows_are_the_field_files(self):
        """The rows a writer may not drop are the ones devices_field.csv names: staging's field devices (less its
        spares, which wiring.csv makes), the wired mast and head, and the masts whose names the owner keeps (staging's
        6L and 8R pairs, whose letters the plan's order would swap: naming-layers step 12), which hold a name only."""
        keys = D.field_index()
        self.assertTrue(keys)
        self.assertEqual({k[0] for k in keys}, {"1"})
        rows = {D.key_of(r): r for r in D.load()}
        named = {k for k, f in keys.items() if f["layer"] == "mast"
                 and not any(f[c] for c in D.FIELD_COLUMNS if c != "user_name")}
        self.assertEqual({rows[k].assignment for k in set(keys) - named}, {"field"})
        self.assertEqual(sorted(rows[k].user_name for k in named), ["Mast 6LA", "Mast 8RA", "Mast 8RB"])

    def test_a_writer_may_drop_a_main_or_upper_row_without_saying_so(self):
        """A writer may drop a row the field file holds no cells for (here a main level spur): the row is the
        rule's alone."""
        held = [r for r in D.load(self.files) if r.written_by == "build_device_map.py" and r.level == 2
                and r.role == "spur"]
        gone = (held[0].level_cell, held[0].layer, held[0].user_name)
        rest = [r.cells() for r in D.load(self.files) if r.written_by == "build_device_map.py"
                and (r.level_cell, r.layer, r.user_name) != gone]
        out = D.outputs_after_rows("build_device_map.py", rest, self.files)
        after = {(r["level"], r["layer"], r["user_name"]) for r in csv.DictReader(io.StringIO(out[self.files.master]))}
        self.assertNotIn(gone, after)

    def test_a_writer_that_gives_a_row_a_hand_kept_row_has_is_refused(self):
        hand = hand_keep(self.files)
        stray = dict(D.device_map_row(hand), role=hand["role"], id=hand["id"])
        with self.assertRaisesRegex(D.DevicesError, "would rewrite row"):
            D.outputs_after(OTHER, [stray], self.files)

    def test_a_row_the_writer_gave_that_is_not_a_device_map_layer_is_refused(self):
        row = dict(TheRowForms.OLD, layer="sensor", user_name="SML Mode")
        with self.assertRaisesRegex(D.DevicesError, "has no sensor rows"):
            D.outputs_after(OTHER, [row], self.files)


class TheNits(unittest.TestCase):
    def test_field_rows_with_no_system_name_do_not_clash_with_each_other(self):
        fb = lambda user: blank(level="1", layer="fb", role="fb", user_name=user, assignment="field", description="x")
        text = problems([fb("a"), fb("b")])
        self.assertNotIn("is line", text)
        self.assertIn("a field device needs", text)

    def test_one_data_folder_moves_every_file(self):
        f = D.Files.under(Path("/x/data"))
        self.assertEqual({p.parent for p in (f.master, f.dictionary)}, {Path("/x/data")})

    def test_a_row_with_a_wrong_column_set_is_a_devices_error(self):
        with self.assertRaisesRegex(D.DevicesError, "misses columns"):
            D.master_row({"layer": "turnout", "user_name": "x", "comment": "", "extra": ""}, "")

    def test_a_stale_master_points_at_its_writer(self):
        f = D.Files.here()
        self.assertEqual(D.stale_message(f.master, f, "tools/schematic/x.py"),
                         "devices_generated.csv is stale: run python3 tools/schematic/x.py")


class TheReaders(unittest.TestCase):
    """The one way a reader gets device-map rows and a row's comment: from the master (device_map_lines,
    comment_of)."""

    def test_the_lines_give_the_old_forms(self):
        rows = list(D.load())
        for levels in (("1",), ("2", "3")):
            with self.subTest(levels=levels):
                got = D.device_map_lines(levels)
                self.assertTrue(got)
                self.assertTrue(all(set(r) == set(D.DEVICE_COLUMNS) | {"role"} for _n, r in got))
                self.assertEqual({r["level"] for _n, r in got}, set(levels))
                self.assertTrue(all(0 < n <= len(rows) + 1 for n, _r in got))

    def test_a_rows_comment_is_its_jmri_comment_else_its_wiring_with_a_field_turnouts_dcc(self):
        self.assertEqual(D.comment_of(turnout()), "Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2")
        alias = turnout("DCC Switch 1", role="lcc_alias", system_name="MTT100", jmri_name="MTT100")
        self.assertEqual(D.comment_of(alias), "Node: 4 Turnout: 0 | OU: 1 Ports: 1,2")     # an alias has no DCC group
        self.assertEqual(D.comment_of(mast(jmri_comment="Brick | Switch 1")), "Brick | Switch 1")
        self.assertEqual(D.comment_of(turnout(assignment="virtual")), "Node: 4 Turnout: 0 | OU: 1 Ports: 1,2")

    def test_a_line_is_the_masters_own(self):
        rows = list(D.load())
        for n, r in D.device_map_lines(("2", "3")):
            self.assertEqual((rows[n - 2].level_cell, rows[n - 2].user_name), (r["level"], r["user_name"]))
            self.assertEqual(rows[n - 2].role, r["role"])

    def test_no_panel_status_row_is_in_a_device_map(self):
        roles = {r["role"] for _n, r in D.device_map_lines(("1", "2", "3"))}
        self.assertFalse(roles & set(D.OUT_OF_MAPS))
        self.assertIn("lcc_alias", roles)

    def test_a_master_that_cannot_be_read_stops_with_its_path(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "devices.csv"
            for call in (lambda: D.device_map_lines(("1",), missing), lambda: D.load(missing)):
                with self.assertRaisesRegex(D.DevicesError, "cannot read it"):
                    call()
            missing.write_text("level,layer\n1,mast\n", encoding="utf-8")
            with self.assertRaisesRegex(D.DevicesError, "the header is not the master's columns"):
                D.load(missing)

    def test_the_path_or_the_files_name_the_same_master(self):
        self.assertEqual(D.device_map_lines(("1",), REAL.master), D.device_map_lines(("1",), REAL))


class TheKindFromTheRow(unittest.TestCase):
    """A reader takes a device's kind from its row's layer and role (row_role, is_os, index), never from its name
    (hand-off row 8)."""

    def test_the_role_is_the_rows(self):
        self.assertEqual(D.row_role(turnout()), "turnout")
        self.assertTrue(D.is_os(blank(layer="block", role="xover_corner", user_name="Track Odd")))
        self.assertFalse(D.is_os(blank(layer="block", role="track", user_name="OS Switch 9")))

    def test_a_row_with_no_role_stops_naming_where(self):
        for row in (blank(layer="block", user_name="OS Switch 9"), {"layer": "block", "user_name": "OS Switch 9"}):
            with self.assertRaisesRegex(D.DevicesError, r"devices.csv line 7: block 'OS Switch 9' has no role"):
                D.is_os(row, "devices.csv line 7")

    def test_the_index_finds_a_device_by_layer_and_name(self):
        ix = D.index()
        self.assertIs(ix, D.index())                # built once per file state
        self.assertEqual(ix.role("block", "OS Switch 225b"), "xover_corner")
        self.assertTrue(ix.is_os("OS Switch 101"))
        self.assertFalse(ix.is_os("Track Helix Inner"))        # a row on staging and one on the upper level
        self.assertEqual(len(ix.rows("block", "Track Helix Inner")), 2)
        self.assertIn("Switch 101", ix.names("turnout", roles=("turnout",)))
        self.assertNotIn("DCC Switch 101", ix.names("turnout", roles=("turnout",)))
        self.assertEqual(set(ix.names("occupancy", levels=("2",))),
                         {r.user_name for r in D.load() if r.layer == "occupancy" and r.level == 2})
        with self.assertRaisesRegex(D.DevicesError, "devices_generated.csv: no block row 'Track Nowhere'"):
            ix.role("block", "Track Nowhere")

    def test_a_device_not_on_the_layout_yet_is_left_out_of_a_role_query(self):
        """A level-less row (added in PanelPro, no role yet) is no layout element: a role query skips it, never stops
        on it; has, is_unplaced and where still see it."""
        from hartlib import jmri_bean, tables_sections
        import xml.etree.ElementTree as ET
        el = ET.fromstring("<sensor inverted=\"false\"><systemName>M2S9999</systemName>"
                           "<userName>BS Store Added</userName></sensor>")
        row = unplaced("BS Store Added", layer="occupancy", system_name="M2S9999", jmri_name="M2S9999")
        row["jmri_bean"] = jmri_bean.bean_json([(tables_sections.MQTT_SENSORS, el)], row)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "devices.csv"
            path.write_text(D.master_text([r.cells() for r in D.load()] + [row]), encoding="utf-8")
            ix = D.index(path)
            detectors = ix.names("occupancy", roles=set(D.ROLES) - {"spare"})
            self.assertNotIn("BS Store Added", detectors)
            self.assertIn("BS Switch 101", detectors)
            self.assertIn("BS Store Added", ix.names("occupancy"))         # no role asked: every row
            self.assertTrue(ix.has("occupancy", "BS Store Added"))
            self.assertTrue(ix.is_unplaced("occupancy", "BS Store Added"))
            self.assertFalse(ix.is_unplaced("occupancy", "BS Switch 101"))
            self.assertEqual(ix.where(row), "devices.csv: BS Store Added (no level, occupancy)")
            self.assertEqual(ix.where(dict(row, user_name="BS Nowhere")), "devices.csv")
            with self.assertRaisesRegex(D.DevicesError, "has no role"):
                ix.role("occupancy", "BS Store Added")

    def test_rows_that_disagree_on_a_role_stop_naming_their_lines(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "devices.csv"
            rows = list(csv.reader(io.StringIO(D.master_text(r.cells() for r in D.load()), newline="")))
            col = rows[0].index
            helix = [i for i, r in enumerate(rows) if r[col("layer")] == "block" and r[col("user_name")] ==
                     "Track Helix Inner"]
            rows[helix[1]][col("role")] = "track"
            buf = io.StringIO()
            csv.writer(buf, lineterminator="\n").writerows(rows)
            path.write_text(buf.getvalue(), encoding="utf-8")
            ix = D.index(path)
            with self.assertRaisesRegex(D.DevicesError, r"Track Helix Inner \(level 1, block\); devices.csv: Track "
                                                        r"Helix Inner \(level 3, block\): block "
                                                        r"'Track Helix Inner' has roles helix, track"):
                ix.role("block", "Track Helix Inner")


class TheStagingFacts(unittest.TestCase):
    """What the pnm_ columns held that the master's own columns lacked, now in them."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {(r.level_cell, r.layer, r.user_name): r.cells() for r in D.load()}

    def test_a_line_blocks_cp_lists_the_places_it_joins(self):
        """The stations (or control points) of the switches at a line block's two ends,
        plus a station whose tracks name it, in stations.csv's order; its sensor has its block's."""
        cp = lambda layer, name, level="1": self.rows[(level, layer, name)]["cp"]  # noqa: E731
        self.assertEqual(cp("block", "Track Main East"), "Barn;East End")
        self.assertEqual(cp("block", "Track Main West"), "Brick;East End")
        self.assertEqual(cp("block", "Track East Ext"), "Plane;Barn")
        self.assertEqual(cp("block", "Track W-1"), "Brick;West Yard")             # West Yard lists W-1 too
        self.assertEqual(cp("occupancy", "BS EH-1"), "Barn;Engine House")         # was empty
        # one block across the levels: each row lists its own level's place first
        self.assertEqual(cp("block", "Track Helix Inner"), "Princess;CP 127")
        self.assertEqual(cp("block", "Track Helix Outer"), "Princess;CP 127")
        self.assertEqual(cp("block", "Track Helix Inner", "3"), "CP 127;Princess")
        self.assertEqual(cp("occupancy", "BS Helix Inner", "3"), "CP 127;Princess")
        self.assertEqual(cp("block", "Track Helix Outer", "2"), "CP 127;Princess")
        self.assertEqual(cp("block", "Track 127-221", "3"), "CP 201;CP 127")       # upper's CP first
        self.assertEqual(cp("block", "Track 119-123", "2"), "CP 107;CP 123")

    def test_every_sensor_has_its_blocks_cp_and_only_a_line_block_a_list(self):
        blocks = {(r["level"], r["user_name"]): r["cp"] for r in self.rows.values() if r["layer"] == "block"}
        for r in self.rows.values():
            if r["layer"] == "occupancy" and r["role"] != "spare":
                self.assertEqual(r["cp"], blocks[(r["level"], r["blocks"])], r["user_name"])
            if D.LIST in r["cp"]:
                self.assertIn(r["role"], D.LINE_ROLES, r["user_name"])

    def test_the_old_name_maps_notes_kept_their_facts(self):
        """The internal heads' note and the alias's turnout and address, which the pnm_notes held."""
        rows = [r for k, r in self.rows.items() if k[0] == "1"]
        internal = [r for r in rows if r["layer"] == "head" and r["assignment"] == "virtual"]
        self.assertEqual({r["notes"] for r in internal}, {"internal, not wired"})
        turnouts = {r["user_name"]: r["system_name"] for r in rows if r["role"] == "turnout"}
        aliases = [r for r in rows if r["role"] == "lcc_alias"]
        self.assertEqual(len(aliases), 20)
        for r in aliases:
            sw = r["user_name"].removeprefix("DCC ")
            self.assertEqual(r["notes"], f"LCC alias of {sw} ({turnouts[sw]})")

    def test_head_6lb_says_it_is_one_high_head(self):
        self.assertEqual(self.rows[("1", "head", "Head 6LB")]["notes"], "one high head (owner 2026-11-19); IH433 dropped")


class TheLoaderIsStrictAndCurrent(unittest.TestCase):
    """The master is one validated file: a bad row anywhere stops the load and says where; a changed file is read again."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = D.one_file_copy(self.tmp / "devices.csv")

    def test_a_bad_row_names_the_file_the_line_and_the_row(self):
        rows = [r.cells() for r in D.load(self.path)]
        rows[4]["description"] = ""
        self.path.write_text(D.master_text(rows), encoding="utf-8")
        with self.assertRaises(D.DevicesError) as cm:
            D.load(self.path)
        self.assertIn(f"devices.csv: {rows[4]['user_name']} (level {rows[4]['level']}, {rows[4]['layer']}): "
                      "description is empty", str(cm.exception))

    def test_a_same_size_write_in_the_same_tick_is_read_again(self):
        import os
        before = os.stat(self.path)
        rows = [r.cells() for r in D.load(self.path)]
        old = rows[0]["description"]
        rows[0]["description"] = old[:-1] + ("!" if old[-1] != "!" else "?")        # one character, the same length
        self.path.write_text(D.master_text(rows), encoding="utf-8")
        os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))        # the same mtime too
        after = os.stat(self.path)
        self.assertEqual((after.st_size, after.st_mtime_ns), (before.st_size, before.st_mtime_ns))
        self.assertEqual(D.load(self.path)[0].description, rows[0]["description"])

    def test_a_line_break_in_a_field_is_refused_naming_the_row(self):
        rows = [r.cells() for r in D.load(self.path)]
        rows[2]["notes"] = "two\nlines"
        self.path.write_text(D.master_text(rows), encoding="utf-8")
        with self.assertRaisesRegex(D.DevicesError, rf"{rows[2]['user_name']} \(level 1, turnout\): notes hold a line break"):
            D.load(self.path)


class TheMasterFile(unittest.TestCase):
    def read(self, text: str):
        with tempfile.TemporaryDirectory() as d:
            files = D.Files.here().but(master=Path(d) / "devices.csv", field=None)
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
        self.assertEqual(set(D.WRITERS) - {OTHER}, {"build_device_map.py", "panel_items.json"})


if __name__ == "__main__":
    unittest.main()
