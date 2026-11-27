"""hartlib.railroad_facts on small fixtures: the strict CSV reader, switches.csv and its staging and main/upper views,
interlockings, stations, OS labels, LCOS nodes, plan overrides, block lengths, the device map's rows and helpers and
the main/upper join. test_railroad.py holds the same readers to the committed data through hartlib.railroad;
test_station_groups.py covers the desk areas."""
from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import devices, railroad_facts as rf  # noqa: E402
from master_edit import name_store  # noqa: E402  a fixture's name store


class Tmp(unittest.TestCase):
    """A temporary folder for a test's fact files."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, name: str, text: str) -> Path:
        p = self.tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def write_rows(self, name: str, columns, rows: list[dict], *, dropped=()) -> Path:
        """`dropped`: columns the rows give that the header leaves out on purpose."""
        p = self.tmp / name
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(columns), lineterminator="\n")
            w.writeheader()
            for r in rows:
                unknown = set(r) - set(columns) - set(dropped)
                assert not unknown, f"{name}: no such column {sorted(unknown)}"
                w.writerow({c: r.get(c, "") for c in columns})
        return p

    def master(self) -> Path:
        """A two-file device master holding one staging turnout, Switch 9, with the owner's cells."""
        key = dict(level="1", layer="turnout", user_name="Switch 9", id="switch:9")
        blank = {c: "" for c in devices.COLUMNS}
        (self.tmp / devices.GENERATED_FILE).write_text(devices.master_text(
            [blank | key | dict(written_by="build_device_map.py", description="Switch 9's turnout.")]), encoding="utf-8")
        (self.tmp / devices.FIELD_FILE).write_text(devices.master_text(
            [blank | key | dict(role="turnout", assignment="field", system_name="M2T9", jmri_name="M2T9")]),
            encoding="utf-8")
        return devices.master_path(self.tmp)

    def fails(self, reader, pattern: str) -> None:
        with self.assertRaisesRegex(rf.FactsError, pattern):
            reader()


# ---------------------------------------------------------------- read_rows and small helpers

class ReadRows(Tmp):
    def test_required_and_optional_columns_only_values_stripped(self) -> None:
        p = self.write("a.csv", "a,b,c\n 1 ,2, 3\n")
        self.assertEqual(rf.read_rows(p, ("a",), optional=("c", "z", "a")), [(2, {"a": "1", "c": "3", "z": ""})])

    def test_an_optional_column_at_the_end_of_a_short_row_is_empty(self) -> None:
        p = self.write("a.csv", "a,b,c\n1,2\n")
        self.assertEqual(rf.read_rows(p, ("a",), optional=("c",)), [(2, {"a": "1", "c": ""})])

    def test_a_short_row_without_a_required_field_stops(self) -> None:
        p = self.write("a.csv", "a,b,c\n1,2\n")
        self.fails(lambda: rf.read_rows(p, ("a", "c")), r"^a.csv line 2: 3 fields \(a,b,c\), not 2$")

    def test_a_long_row_stops(self) -> None:
        p = self.write("a.csv", "a,b,c\n1,2,3,4\n")
        self.fails(lambda: rf.read_rows(p, ("a",)), r"^a.csv line 2: 3 fields \(a,b,c\), not 4$")

    def test_a_missing_column_stops_naming_the_header(self) -> None:
        p = self.write("a.csv", "a,b\n1,2\n")
        self.fails(lambda: rf.read_rows(p, ("a", "c", "d")), r"^a.csv: no column c, d \(the header is a,b\)$")

    def test_a_note_line_counts_in_the_line_numbers(self) -> None:
        p = self.write("a.csv", "# from somewhere\na\n1\n2\n")
        self.assertEqual([n for n, _ in rf.read_rows(p, ("a",), note=True)], [3, 4])
        self.fails(lambda: rf.read_rows(self.write("b.csv", "a\n1\n"), ("a",), note=True), "b.csv line 1: the note line")

    def test_a_file_that_cannot_be_read(self) -> None:
        self.fails(lambda: rf.read_rows(self.tmp / "none.csv", ("a",)), r"none.csv: cannot read it")


class SmallHelpers(Tmp):
    def test_natural(self) -> None:
        self.assertEqual(sorted(["Switch 101", "Switch 9", "Switch 10b", "Switch 10a"], key=rf.natural),
                         ["Switch 9", "Switch 10a", "Switch 10b", "Switch 101"])

    def test_switch_number(self) -> None:
        for label, want in (("129A", "129"), ("129B", "129"), ("223*", "223"), ("101B*", "101"), ("107", "107"),
                            ("", ""), (None, "")):
            with self.subTest(label):
                self.assertEqual(rf.switch_number(label), want)

    def test_device_list(self) -> None:
        self.assertEqual(rf.device_list(" Track A ;; Track B;"), ["Track A", "Track B"])
        self.assertEqual(rf.device_list(""), [])
        self.assertEqual(rf.device_list(None), [])

    def test_track_labels(self) -> None:
        self.assertEqual(rf.track_labels({}), {})
        self.assertEqual(rf.track_labels({rf.TRACK_LABELS: {"Helix Outer": "Outer"}}), {"Helix Outer": "Outer"})
        for bad in ({"Helix Outer": ""}, {" ": "Outer"}, {"Helix Outer": 3}, ["Helix Outer"]):
            with self.subTest(bad):
                with self.assertRaisesRegex(rf.FactsError, "track_labels: .* is not an object of plan name to label"):
                    rf.track_labels({rf.TRACK_LABELS: bad})

    def test_sources_under_a_data_folder_and_but(self) -> None:
        data = Path("/x/data")
        s = rf.Sources.under(data, tables_xml=Path("/x/tables.xml"))
        self.assertEqual((s.switches, s.interlockings, s.lcos_nodes, s.stations, s.block_lengths, s.tables),
                         (data / "switches.csv", data / "schematic/interlockings.csv", data / "schematic/lcos_nodes.csv",
                          data / "schematic/stations.csv", data / "block_lengths.csv", Path("/x/tables.xml")))
        self.assertEqual(s.plan_overrides.name, "plan_overrides.json")
        self.assertEqual(s.devices, devices.master_path(data))
        swapped = s.but(switches=Path("/y.csv"))
        self.assertEqual((swapped.switches, swapped.stations), (Path("/y.csv"), s.stations))

    def test_master_at_names_the_file_holding_the_row(self) -> None:
        master = self.master()
        self.assertEqual(rf.master_at(master, "Switch 9", 1, "turnout"), "devices_field.csv: Switch 9 (level 1, turnout)")
        self.assertEqual(rf.master_at(master, "No Such Row", "1", "turnout"),
                         "devices_generated.csv: No Such Row (level 1, turnout)")


# ---------------------------------------------------------------- switches.csv

def sw(**cells) -> dict:
    return {c: "" for c in rf.SWITCH_COLUMNS} | {k: str(v) for k, v in cells.items()}


# The fixture's name store: the staging blocks its rows give by ID (a one-file master beside the fixture, SwitchFiles)
NAMES = {"os:1": "OS Switch 1", "block:1B-end": "Track A", "block:1C-end": "Track B", "os:7:A-13C": "OS Switch 7",
         "block:5C-7B": "Track Scale", "os:7:A-5B": "OS Switch 7b", "block:c": "Track C", "block:d": "Track D"}


def write_names(path: Path, names: dict[str, str] = NAMES) -> Path:
    """A one-file device master at `path` holding a level 1 block of each {id: user name} in `names`."""
    return name_store(path, names)


def switch_rows() -> list[dict]:
    """Staging Switch 1 (one OS block) and the Switch 7 crossover (two), main 101 (halves A and B) and the local
    switch 107, and upper 201. The rows sit on lines 2 to 8."""
    return [
        sw(level=1, switch=1, os_id="os:1",
           closed_id="block:1B-end", thrown_id="block:1C-end", hand="L", hand_source="owner", le_ident="TOL1",
           cats_inverted="no", ctc_is=1, ctc_signals="yes"),
        sw(level=1, switch=7,
           os_id="os:7:A-13C", closed_id="block:5C-7B", thrown_id="os:7:A-5B", hand="L", hand_source="owner",
           le_ident="TO117", cats_inverted="yes", ctc_is=7, ctc_signals="no"),
        sw(level=1, switch=7, os_id="os:7:A-5B",
           closed_id="block:c", thrown_id="block:d"),
        sw(level=2, switch=101, half="101A", hand="R", hand_source="plan"),
        sw(level=2, switch=101, half="101B", hand_source="plan"),
        sw(level=2, switch=107, half="107", hand="L", hand_source="owner", area="Yard", notes="a yard switch"),
        sw(level=3, switch=201, half="201"),
    ]


def staging_rows() -> list[tuple[int, dict[str, str]]]:
    """Staging rows of the master in read_staging_rows' form: Switch 1's turnout, and a block that is no turnout."""
    blank = {c: "" for c in rf.STAGING_COLUMNS}
    return [(2, blank | dict(layer="turnout", user_name="Switch 1", system_name="M2T1", dcc="100", cp="Brick")),
            (3, blank | dict(layer="block", user_name="Switch 7", system_name="IB7"))]


class SwitchFiles(Tmp):
    """switches.csv fixtures, each with its name store beside it (a one-file devices.csv of NAMES, which
    read_switch_rows finds there); no tests of its own, so a subclass runs only its own."""

    def path(self, rows=None) -> Path:
        write_names(self.tmp / devices.ONE_FILE)
        return self.write_rows("switches.csv", rf.SWITCH_COLUMNS, switch_rows() if rows is None else rows)

    def changed(self, line: int, **cells) -> Path:
        """The fixture with the row on `line` changed."""
        rows = switch_rows()
        rows[line - 2] |= {k: str(v) for k, v in cells.items()}
        return self.path(rows)


class SwitchRows(SwitchFiles):
    def test_the_rows_in_file_order(self) -> None:
        rows = rf.read_switch_rows(self.path())
        self.assertEqual([(r.line, r.level, r.switch, r.key) for r in rows],
                         [(2, 1, 1, "OS Switch 1"), (3, 1, 7, "OS Switch 7"), (4, 1, 7, "OS Switch 7b"),
                          (5, 2, 101, "101A"), (6, 2, 101, "101B"), (7, 2, 107, "107"), (8, 3, 201, "201")])
        self.assertEqual([r.by_os for r in rows], [True] * 3 + [False] * 4)
        self.assertEqual((rows[0].os_id, rows[0].closed_id, rows[0].thrown_id), ("os:1", "block:1B-end", "block:1C-end"))

    def test_switch_groups_by_level(self) -> None:
        rows = rf.read_switch_rows(self.path())
        self.assertEqual({n: [r.line for r in rs] for n, rs in rf.switch_groups(rows, (1,)).items()}, {1: [2], 7: [3, 4]})
        self.assertEqual(list(rf.switch_groups(rows, rf.LEVEL_NUMBERS)), [101, 107, 201])
        self.assertEqual(rf.switch_groups(rows, ()), {})

    def test_local_switches_are_main_and_upper_first_rows_with_an_area(self) -> None:
        want = [rf.LocalSwitch(7, "107", 2, "Yard", "a yard switch")]
        self.assertEqual(rf.local_switches(rf.read_switch_rows(self.path())), want)
        self.assertEqual(rf.read_local_switches(self.path()), want)

    def test_hands_are_the_half_keyed_rows_that_give_one(self) -> None:
        want = {"101A": rf.Hand(5, "101A", "R", "plan"), "107": rf.Hand(7, "107", "L", "owner")}
        self.assertEqual(rf.hands(rf.read_switch_rows(self.path())), want)
        self.assertEqual(rf.read_hands(self.path()), want)

    def test_a_bad_row_stops_naming_the_file_and_line(self) -> None:
        cases = (
            ((8, dict(switch="x")), r"switches.csv line 8: switch is a whole number, not 'x'"),
            ((8, dict(level=4)), r"line 8 \(Switch 201\): level is 1, 2 or 3"),
            ((8, dict(level=2, switch=101, half=101)), r"line 8 \(Switch 101\): Switch 101 is also on line 5; a switch's rows "
                                                     r"go together"),
            ((8, dict(level=1, switch=101, half="", os_id="os:101", closed_id="a", thrown_id="b")),
             r"switches.csv lines 5 \(level 2\) and 8 \(level 1\) both use Switch 101"),
            ((6, dict(half="101A")), r"switches.csv lines 5 and 6: both are 101A"),
            ((8, dict(half="201C")), r"line 8 \(Switch 201\): half is 201, 201A or 201B, not '201C'"),
            ((8, dict(le_ident="TO1")), r"line 8 \(Switch 201\): le_ident bind"),
            ((8, dict(os_id="os:201")), r"line 8 \(Switch 201\): a staging row is keyed by its OS block.*not os_id 'os:201'"),
            ((8, dict(closed_id="block:x")), r"line 8 \(Switch 201\): closed_id and thrown_id go with an os_id"),
            ((8, dict(hand="X", hand_source="owner")), r"line 8 \(Switch 201\): hand is L, R or blank, got 'X'"),
            ((8, dict(hand="L")), r"line 8 \(Switch 201\): a hand needs a hand_source.*got hand 'L', hand_source ''$"),
            ((8, dict(hand_source="owner")), r"line 8 \(Switch 201\): a hand needs a hand_source.*got hand '', hand_source 'owner'$"),
            ((8, dict(hand="L", hand_source="guess")), r"line 8 \(Switch 201\): a hand needs a hand_source.*got hand 'L', hand_source 'guess'$"),
            ((6, dict(area="Yard")), r"line 6 \(Switch 101\): area hold.*first row \(line 5\) only$"),
            ((4, dict(hand="L", hand_source="owner")), r"line 4 \(Switch 7\): hand, hand_source hold.*first row \(line 3\) only$"),
            ((2, dict(half="1")), r"line 2 \(Switch 1\): a row keyed by its OS block has no half"),
            ((2, dict(hand_source="plan")), r"line 2 \(Switch 1\): hand_source plan is for rows keyed by their half"),
            ((2, dict(os_id="os:2")), r"line 2 \(Switch 1\): a row keyed by its OS block gives the device IDs"),
            ((2, dict(thrown_id="")), r"line 2 \(Switch 1\): a row keyed by its OS block gives the device IDs"),
            ((2, dict(closed_id="block:x")), r"line 2 \(Switch 1\): closed_id block:x is no level 1 device of the "
                                             r"device master"),
            ((4, dict(os_id="os:7:A-9")), r"line 4 \(Switch 7\): os_id os:7:A-9 is no level 1 device"),
            ((2, dict(os_id="")), r"line 2 \(Switch 1\): a staging row is keyed by its OS block"),
        )
        for (line, cells), pattern in cases:
            with self.subTest(cells):
                self.fails(lambda: rf.read_switch_rows(self.changed(line, **cells)), pattern)

    def test_a_half_keyed_switch_has_one_row_or_both_halves(self) -> None:
        rows = switch_rows()
        del rows[4]                                     # 101A alone
        self.fails(lambda: rf.read_switch_rows(self.path(rows)),
                   r"line 5 \(Switch 101\): a switch keyed by its halves has one row, half 101, or two, halves 101A "
                   r"and 101B; not 101A")

    def test_a_missing_column_stops(self) -> None:
        p = self.write_rows("switches.csv", rf.SWITCH_COLUMNS[:-1], switch_rows(),
                           dropped=rf.SWITCH_COLUMNS[-1:])
        self.fails(lambda: rf.read_switch_rows(p), r"switches.csv: no column notes")

    def test_the_labels_are_the_name_stores_names_of_the_ids(self) -> None:
        rows = rf.read_switch_rows(self.path())
        self.assertEqual([(r.os_block, r.closed_leg, r.thrown_leg) for r in rows[:3]],
                         [("OS Switch 1", "Track A", "Track B"), ("OS Switch 7", "Track Scale", "OS Switch 7b"),
                          ("OS Switch 7b", "Track C", "Track D")])
        self.assertEqual({(r.os_block, r.closed_leg, r.thrown_leg) for r in rows[3:]}, {("", "", "")})

    def test_a_rename_in_the_name_store_relabels_the_row(self) -> None:
        """A rename by ID in the device master alone reaches SwitchRow, with switches.csv as it was."""
        path = self.path()
        before = path.read_bytes()
        write_names(self.tmp / devices.ONE_FILE, NAMES | {"os:1": "OS Brick", "block:1B-end": "Track Brick Lead"})
        row = rf.read_switch_rows(path)[0]
        self.assertEqual((row.os_block, row.closed_leg, row.thrown_leg, row.key),
                         ("OS Brick", "Track Brick Lead", "Track B", "OS Brick"))
        self.assertEqual(path.read_bytes(), before)

    def test_a_callers_names_win(self) -> None:
        names = {("1", i): n.upper() for i, n in NAMES.items()}
        self.assertEqual(rf.read_switch_rows(self.path(), names)[0].closed_leg, "TRACK A")

    def test_a_name_column_stops(self) -> None:
        """The file holds IDs only: a label column back in the header stops the read, whatever its cells hold."""
        for label in rf.LABEL_COLUMNS:
            with self.subTest(label):
                p = self.write_rows("switches.csv", rf.SWITCH_COLUMNS + (label,), switch_rows())
                self.fails(lambda: rf.read_switch_rows(p), rf"switches.csv: {label} are no columns")


class StagingSwitches(SwitchFiles):
    def test_a_switch_of_the_os_keyed_rows_with_its_turnout_row(self) -> None:
        got = rf.read_switches(self.path(), self.tmp / "devices.csv", staging_rows())
        self.assertEqual(list(got), [1, 7])
        self.assertEqual(got[1], rf.Switch(number=1, level=1, le_ident="TOL1", cats_inverted=False, ctc_is=1,
                                           ctc_signals=True, legs=(rf.Leg("OS Switch 1", "Track A", "Track B", "os:1"),),
                                           hand="L", hardware="M2T1", dcc="100", cp="Brick"))
        s7 = got[7]
        self.assertEqual((s7.os_blocks, s7.hand, s7.cats_inverted, s7.ctc_signals), (("OS Switch 7", "OS Switch 7b"), "L",
                                                                                     True, False))
        self.assertEqual((s7.hardware, s7.dcc, s7.cp), ("", "", ""))      # the master's "Switch 7" is no turnout row
        self.assertEqual((s7.turnout, s7.uss_slot, got[1].uss_slot), ("Switch 7", 3, 0))

    def test_staging_switches_takes_rows_read_already(self) -> None:
        got = rf.staging_switches(rf.read_switch_rows(self.path()), self.path(), self.tmp / "devices.csv", staging_rows())
        self.assertEqual(list(got), [1, 7])
        self.assertEqual((got[1].hardware, got[1].dcc, got[1].uss_slot, got[7].turnout, got[7].uss_slot),
                         ("M2T1", "100", 0, "Switch 7", 3))

    def test_a_bad_first_row_stops(self) -> None:
        cases = (
            ((2, dict(le_ident="", ctc_signals="")), r"line 2 \(Switch 1\): a staging switch's first row gives "
                                                      r"le_ident, ctc_signals$"),
            ((3, dict(ctc_is=1)), r"switches.csv lines 2 \(Switch 1\) and 3 \(Switch 7\) both use USS lever IS1$"),
            ((2, dict(cats_inverted="maybe")), r"line 2 \(Switch 1\): expected yes or no, got 'maybe'"),
            ((2, dict(ctc_is="x")), r"line 2 \(Switch 1\): ctc_is is a whole number, not 'x'"),
        )
        for (line, cells), pattern in cases:
            with self.subTest(cells):
                self.fails(lambda: rf.read_switches(self.changed(line, **cells), self.tmp / "d.csv", staging_rows()),
                           pattern)

    def test_switch_turnouts_looks_at_the_numbers_asked_for(self) -> None:
        rows = staging_rows()
        self.assertEqual(rf.switch_turnouts(self.tmp / "d.csv", rows, [1, 7]), {1: rows[0][1]})
        self.assertEqual(rf.switch_turnouts(self.tmp / "d.csv", rows, []), {})
        twice = rows + [(4, rows[0][1] | {"system_name": "M2T2"})]
        self.fails(lambda: rf.switch_turnouts(self.master(), twice, [1]),
                   r"Switch 1 \(level 1, turnout\): two rows are both the turnout Switch 1")


class StagingDevicesRead(Tmp):
    """read_staging_devices on rows given; a fixture master names a row in a message."""

    def rows(self, **cells):
        return [(2, {c: "" for c in rf.STAGING_COLUMNS} | dict(layer="turnout", user_name="Switch 1", dcc="100")),
                (3, {c: "" for c in rf.STAGING_COLUMNS} | dict(layer="block", user_name="OS Switch 1") | cells)]

    def test_the_rows_by_layer_and_name(self) -> None:
        got = rf.read_staging_devices(self.master(), self.rows())
        self.assertEqual([(r.line, r.layer, r.user_name, r.dcc) for r in got.rows],
                         [(2, "turnout", "Switch 1", "100"), (3, "block", "OS Switch 1", "")])
        self.assertEqual(got.by_name[("block", "OS Switch 1")].line, 3)
        self.assertEqual((got.names("turnout"), got.names("mast")), ({"Switch 1"}, set()))

    def test_an_empty_name_or_a_dcc_that_is_no_number_stops(self) -> None:
        with self.assertRaisesRegex(rf.FactsError, "user_name is empty"):
            rf.read_staging_devices(self.master(), self.rows(user_name=""))
        with self.assertRaisesRegex(rf.FactsError, r"dcc is a number or blank, not 'x1'"):
            rf.read_staging_devices(self.master(), self.rows(dcc="x1"))


# ---------------------------------------------------------------- interlockings, stations, OS labels, nodes

class Interlockings(Tmp):
    ROWS = [dict(level=1, interlocking="Brick", switches="1,3"),
            dict(level=2, interlocking="CP 101", switches="101, 103", area="North"),
            dict(level=3, interlocking="CP 201", switches="201", area="South", notes="a note")]

    def path(self, *extra: dict) -> Path:
        return self.write_rows("interlockings.csv", ("level", "interlocking", "switches", "area", "notes"),
                               self.ROWS + list(extra))

    def test_every_level_or_the_levels_asked_for(self) -> None:
        got = rf.read_interlockings(self.path())
        self.assertEqual(got[1], rf.Interlocking(3, 2, "CP 101", ("101", "103"), "North", ""))
        self.assertEqual([i.name for i in got], ["Brick", "CP 101", "CP 201"])
        self.assertEqual([i.name for i in rf.read_interlockings(self.path(), levels=(2,))], ["CP 101"])
        # the same name on another level is fine
        self.assertEqual(len(rf.read_interlockings(self.path(dict(level=1, interlocking="CP 101", switches="5")))), 4)

    def test_a_bad_row_stops_whatever_levels_are_asked_for(self) -> None:
        cases = (
            (dict(level=4, interlocking="X", switches="5", area="A"), r"line 5: level is 1, 2 or 3"),
            (dict(level=2, interlocking="X", switches=""), r"line 5 \(X\): switches is a list of switch numbers"),
            (dict(level=2, interlocking="X", switches="105,1a", area="A"), r"switches is a list of switch numbers, not '105,1a'"),
            (dict(level=2, interlocking="CP 101", switches="105", area="A"), r"line 5: an interlocking is named, once per level"),
            (dict(level=2, interlocking="", switches="105", area="A"), r"line 5: an interlocking is named"),
            (dict(level=2, interlocking="CP 103", switches="103", area="A"), r"line 5: switch 103 is in CP 101 and CP 103"),
            (dict(level=1, interlocking="Plane", switches="5", area="A"), r"line 5 \(Plane\): a staging interlocking has no area"),
            (dict(level=3, interlocking="CP 203", switches="203"), r"line 5 \(CP 203\): no area"),
        )
        for row, pattern in cases:
            with self.subTest(row):
                self.fails(lambda: rf.read_interlockings(self.path(row), levels=(1,)), pattern)


class Stations(Tmp):
    COLUMNS = rf.STATION_COLUMNS + rf.STATION_OPTIONAL
    ROWS = [dict(level=1, station="Brick", switches="1;3", desk_code="BK", desk_plate="yes"),
            dict(level=1, station="West Yard", switches="3", tracks="block:3B-end; block:3C-end", desk_code="BK"),
            dict(level=1, station="Plane", switches="5, 7", tracks="none", desk_code="PL", notes="n")]

    def path(self, *extra: dict, columns=COLUMNS) -> Path:
        return self.write_rows("stations.csv", columns, self.ROWS + list(extra),
                               dropped=set(self.COLUMNS) - set(columns))

    def test_stations_and_their_tracks_cells(self) -> None:
        brick, west, plane = rf.read_stations(self.path())
        self.assertEqual((brick.line, brick.level, brick.name, brick.switches, brick.desk_code, brick.desk_plate),
                         (2, 1, "Brick", ("1", "3"), "BK", True))
        self.assertEqual((brick.track_ids, west.track_ids, plane.track_ids),
                         (None, ("block:3B-end", "block:3C-end"), ()))
        self.assertEqual((plane.switches, plane.notes, west.desk_plate), (("5", "7"), "n", False))

    def test_no_desk_plate_column_puts_no_plate(self) -> None:
        p = self.path(columns=rf.STATION_COLUMNS)
        self.assertEqual([s.desk_plate for s in rf.read_stations(p)], [False] * 3)

    def test_a_bad_row_stops(self) -> None:
        ok = dict(level=1, switches="9", desk_code="BN")
        cases = (
            (ok | dict(station=""), r"line 5: the station has no name"),
            (ok | dict(station="Plane"), r"line 5: station 'Plane' is also on line 4"),
            (ok | dict(station="X", level=0), r"line 5 \(X\): level is 1, 2 or 3"),
            (ok | dict(station="X", switches=" ; "), r"line 5 \(X\): no switches"),
            (ok | dict(station="X", switches="9,9b"), r"switches is a list of switch numbers, not '9,9b'"),
            (ok | dict(station="X", switches="9;9"), r"lists switch 9 twice"),
            (ok | dict(station="X", desk_code=""), r"no desk code"),
            (ok | dict(station="X", desk_code="BN EH"), r"two desk codes in 'BN EH'"),
            (ok | dict(station="X", desk_code="Bn"), r"desk code 'Bn' is not capital letters"),
            (ok | dict(station="X", desk_plate="no"), r"desk_plate is yes or empty, not 'no'"),
            (ok | dict(station="X", tracks="block:a;"), r"has an empty entry"),
            (ok | dict(station="X", tracks="Track W-1"), r"not 'Track W-1'"),
            (ok | dict(station="X", tracks="block:a;block:a"), r"tracks lists a block twice"),
        )
        for row, pattern in cases:
            with self.subTest(row):
                self.fails(lambda: rf.read_stations(self.path(row)), pattern)


def os_row(switch: int, os_block: str, os_id: str, line: int = 4) -> rf.SwitchRow:
    return rf.SwitchRow(line=line, level=1, switch=switch, half="", os_block=os_block, closed_leg="", thrown_leg="",
                        hand="", hand_source="", area="", le_ident="", cats_inverted="", ctc_is="", ctc_signals="",
                        notes="", os_id=os_id)


class OsLabel(unittest.TestCase):
    WHERE = Path("switches.csv")

    def test_a_switchs_one_os_block(self) -> None:
        self.assertEqual(rf.os_label(os_row(19, "OS Switch 19", "os:19"), self.WHERE), "19")
        self.assertEqual(rf.os_label(os_row(19, "Track Coal", "os:19"), self.WHERE), "19")         # renamed
        self.assertEqual(rf.os_label(os_row(19, "OS Switch 3", "os:19"), self.WHERE), "19")        # another number
        with self.assertRaisesRegex(rf.FactsError, r"switches.csv line 4 \(Switch 19\): os:19:B is named "
                                                   r"'Track Coal', which gives no label"):
            rf.os_label(os_row(19, "Track Coal", "os:19:B"), self.WHERE)

    def test_a_crossover_half_by_its_letter(self) -> None:
        letters = {("1", "os:7:A-13C"): "a", ("1", "os:7:A-5B"): "b", ("1", "os:23:A-1C"): "a"}
        self.assertEqual(rf.os_label(os_row(7, "OS Switch 7", "os:7:A-13C"), self.WHERE, letters), "7")
        self.assertEqual(rf.os_label(os_row(7, "OS Switch 7b", "os:7:A-5B"), self.WHERE, letters), "7b")
        self.assertEqual(rf.os_label(os_row(23, "OS Switch 23a", "os:23:A-1C"), self.WHERE, letters), "23a")
        # the letter is the ID's, never the name's
        self.assertEqual(rf.os_label(os_row(7, "OS Switch 7", "os:7:A-5B"), self.WHERE, letters), "7b")
        calls = []
        self.assertEqual(rf.os_label(os_row(7, "OS Switch 7b", "os:7:A-5B"), self.WHERE,
                                     lambda: calls.append(1) or letters), "7b")
        self.assertEqual(calls, [1])

    def test_a_half_with_no_letter_stops(self) -> None:
        for letters in (None, {}):
            with self.assertRaisesRegex(rf.FactsError, r"line 4 \(Switch 7\): os:7:A-5B \(OS Switch 7b\) is a "
                                                       "crossover half with no crossover_half row"):
                rf.os_label(os_row(7, "OS Switch 7b", "os:7:A-5B"), self.WHERE, letters)

    def test_half_text(self) -> None:
        self.assertEqual(rf.half_text(7, "OS Switch 7", "a"), "7")
        self.assertEqual(rf.half_text(7, "OS Switch 7", "b"), "7b")
        self.assertEqual(rf.half_text(7, "Track Scale", "a"), "7a")


class LcosNodes(Tmp):
    def path(self, *extra: dict) -> Path:
        rows = [dict(level=1, area="Brick", node=4, source="v86"), dict(level=2, area="North", node=10)]
        return self.write_rows("lcos_nodes.csv", ("level", "area", "node", "source"), rows + list(extra))

    def test_the_nodes(self) -> None:
        self.assertEqual(rf.read_lcos_nodes(self.path()),
                         [rf.LcosNode(2, 1, "Brick", 4, "v86"), rf.LcosNode(3, 2, "North", 10, "")])

    def test_a_bad_row_stops(self) -> None:
        cases = ((dict(level=3, area="South", node=4), r"lcos_nodes.csv lines 2 and 4: both list node 4"),
                 (dict(level=3, area="", node=11), r"lcos_nodes.csv line 4: no area$"),
                 (dict(level=4, area="South", node=11), r"line 4: level is 1, 2 or 3"),
                 (dict(level=3, area="South", node="x"), r"line 4: node is a whole number, not 'x'"))
        for row, pattern in cases:
            with self.subTest(row):
                self.fails(lambda: rf.read_lcos_nodes(self.path(row)), pattern)


# ---------------------------------------------------------------- plan overrides and block lengths

class PlanOverrides(Tmp):
    def path(self, main_upper: dict) -> Path:
        return self.write("plan_overrides.json", json.dumps({"_sections": True, "staging": {}, "main_upper": main_upper}))

    def test_the_section_and_its_relabel_map(self) -> None:
        edits = [{"op": "relabel", "map": {"T7": "107"}}, {"op": "end", "ends": []}]
        got = rf.read_plan_overrides(self.path({"edits": edits, "other": 1}))
        self.assertEqual((got.relabel, got.edits, got.data["other"], got.sheet, got.name),
                         ({"T7": "107"}, tuple(edits), 1, "main_upper", "plan_overrides.json[main_upper]"))

    def test_edits_need_one_relabel_with_a_map(self) -> None:
        cases = (({"edits": {}}, "`edits` is a list of objects with an `op`"),
                 ({"edits": [{"op": 3}]}, "`edits` is a list of objects with an `op`"),
                 ({"edits": [{"op": "end"}]}, r"0 relabel edits; it needs exactly one, with a `map`"),
                 ({"edits": [{"op": "relabel", "map": []}]}, r"1 relabel edits; it needs exactly one, with a `map`"))
        for section, pattern in cases:
            with self.subTest(section):
                self.fails(lambda: rf.read_plan_overrides(self.path(section)), pattern)


# ---------------------------------------------------------------- the device map's rows

def device(**cells) -> dict:
    return {c: "" for c in rf.DEVICE_COLUMNS} | cells


class DeviceFacts(unittest.TestCase):
    def test_good_rows_have_no_problems(self) -> None:
        for r in (device(layer="occupancy", blocks="Track 1-3", detector="planned", system_name="M2S1"),
                  device(layer="occupancy", blocks="Track 1-3", detector="none"),
                  device(layer="block", stop="yes"), device(layer="block"),
                  device(layer="mast", facing="Track 1-3", switch="7", dir="east", protects="Track 3-5"),
                  device(layer="head"), device(layer="turnout")):
            with self.subTest(r["layer"]):
                self.assertEqual(rf.device_facts(r), [])

    def test_each_problem_is_named(self) -> None:
        cases = (
            (device(layer="block", facing="Track 1-3", detector="none"), ["a block row has detector, facing"]),
            (device(layer="occupancy", detector="none"), ["an occupancy row names no blocks"]),
            (device(layer="occupancy", blocks="T", detector="maybe"),
             ["detector 'maybe' is not one of wired, planned, not_wired, none"]),
            (device(layer="occupancy", blocks="T", detector="wired"), ["a wired detector needs system name (it has '')"]),
            (device(layer="occupancy", blocks="T", detector="not_wired", system_name="M2S1"),
             ["a not_wired detector has no system name (it has 'M2S1')"]),
            (device(layer="block", stop="no"), ["stop 'no' is not yes or empty"]),
            (device(layer="mast", switch="7a", dir="north"),
             ["a mast row names no facing block", "switch '7a' is not a switch number",
              "dir 'north' is not one of east, west"]),
        )
        for r, want in cases:
            with self.subTest(want):
                self.assertEqual(rf.device_facts(r), want)


def drow(layer: str, user: str, role: str, **cells) -> rf.DeviceRow:
    return rf.DeviceRow(level=2, layer=layer, user_name=user, role=role, **cells)


class DeviceRows(unittest.TestCase):
    def test_a_rows_lists_and_assignment(self) -> None:
        r = drow("mast", "Mast 2L", "home", protects="Track A; Track B", blocks="Track C;", trial_name="Track 1-3, ,Track 3-5")
        self.assertEqual((r.protected, r.served, r.trial), (["Track A", "Track B"], ["Track C"],
                                                            frozenset({"Track 1-3", "Track 3-5"})))
        self.assertFalse(r.swapped)
        self.assertTrue(replace(r, assignment="field").swapped)
        self.assertFalse(replace(r, assignment="virtual").swapped)

    def test_from_dict_reads_the_level_as_a_number_and_the_rest_as_text(self) -> None:
        r = rf.DeviceRow.from_dict({"level": "3", "layer": "turnout", "user_name": "Switch 201", "role": "turnout",
                                    "dcc": 201, "line": 99}, line=7)
        self.assertEqual((r.level, r.dcc, r.line), (3, "201", 7))

    def test_a_row_is_a_mapping_of_the_masters_columns_as_text(self) -> None:
        r = drow("mast", "Mast 2L", "home", comment="built", line=5, written_by="build_masts.py")
        self.assertEqual(list(r), list(devices.COLUMNS))
        self.assertEqual(len(r), len(devices.COLUMNS))
        self.assertEqual((r["level"], r["layer"], r["written_by"], r.get("dir")), ("2", "mast", "build_masts.py", ""))
        for not_a_column in ("comment", "line", "swapped"):
            with self.subTest(not_a_column), self.assertRaises(KeyError):
                r[not_a_column]
        self.assertEqual(dict(r) | {"dir": "east"}, r | {"dir": "east"})
        self.assertEqual(r, dict(r))                    # equal to the same columns as a dict
        self.assertNotEqual(r, dict(r) | {"dir": "east"})
        self.assertNotEqual(r, replace(r, line=6))      # two rows also hold line and comment to each other
        self.assertEqual(hash(r), hash(replace(r)))

    def test_cells_are_the_row_as_the_master_holds_it(self) -> None:
        r = drow("mast", "Mast 2L", "home", comment="built", line=5, written_by="build_masts.py", dir="east")
        cells = r.cells()
        self.assertEqual(list(cells), list(devices.COLUMNS))     # every column, in file order
        self.assertEqual((cells["level"], cells["layer"], cells["dir"], cells["notes"]), ("2", "mast", "east", ""))
        self.assertNotIn("comment", cells)                       # built text and the place are no columns
        self.assertNotIn("line", cells)
        self.assertTrue(all(isinstance(v, str) for v in cells.values()))
        self.assertEqual(r.level_cell, "2")
        cells["dir"] = "west"                                   # a new dict: the row stays as it was
        self.assertEqual((r.dir, r.cells()["dir"]), ("east", "east"))
        self.assertIsNot(r.cells(), r.cells())

    def test_cells_read_back_to_the_same_row(self) -> None:
        cells = dict.fromkeys(devices.COLUMNS, "") | dict(level="3", layer="block", role="track", id="block:7",
                                                         user_name="Track 7", blocks="Track 7")
        r = rf.MasterRow.from_master(cells, 9, "here")
        self.assertEqual(r.cells(), cells)
        self.assertEqual(rf.MasterRow.from_master(r.cells(), 9, "here"), r)
        store = cells | dict(level="", role="", id="", assignment="field", jmri_name="IS9", system_name="IS9")
        kept = rf.MasterRow.from_master(store, 5, "here")       # a Store's level-less row: level ""
        self.assertEqual((kept.level_cell, kept.cells()), ("", store))

    def test_from_master_reads_a_master_rows_text(self) -> None:
        cells = dict.fromkeys(devices.COLUMNS, "") | dict(level="1", layer="block", role="os", id="os:1",
                                                         user_name="OS Switch 1")
        r = rf.MasterRow.from_master(cells, 4, "here")
        self.assertIsInstance(r, rf.DeviceRow)
        self.assertEqual((r.level, r.line, r.id, dict(r)), (1, 4, "os:1", cells))
        store = cells | dict(level="", role="", id="", assignment="field", jmri_name="IS9", system_name="IS9")
        kept = rf.MasterRow.from_master(store, 5, "here")       # a Store's level-less row: no level, no role
        self.assertNotIsInstance(kept, rf.DeviceRow)
        self.assertEqual((kept.level, kept["level"], kept.role), (None, "", ""))
        with self.assertRaisesRegex(rf.FactsError, "here: level is 1, 2 or 3"):
            rf.MasterRow.from_master(cells | {"level": "4"}, 6, "here")
        with self.assertRaisesRegex(rf.FactsError, "here: a device master row has no jmri_bean"):
            rf.MasterRow.from_master({k: v for k, v in cells.items() if k != "jmri_bean"}, 7, "here")
        with self.assertRaisesRegex(rf.FactsError, "has role ''"):
            rf.MasterRow.from_master(cells | {"role": ""}, 8, "here")

    def test_the_merged_view_is_device_rows(self) -> None:
        rows = devices.load()
        self.assertTrue(rows and all(isinstance(r, rf.DeviceRow) for r in rows))
        self.assertEqual([r.line for r in rows[:3]], [2, 3, 4])
        self.assertEqual(devices.index().lines[0], (2, rows[0]))

    def test_the_maps_views(self) -> None:
        t5 = drow("turnout", "Switch 5", "turnout")
        alias = drow("turnout", "DCC Switch 5", "lcc_alias")
        coal = drow("turnout", "Switch Coal", "turnout", id="switch:9")
        head = drow("head", "Head 2L", "head", system_name="IH402")
        dm = rf.DeviceMap(rows=[t5, alias, coal, head])
        self.assertEqual(dm.turnouts, {"5": t5, "9": coal})
        self.assertEqual(dm.heads_by_system, {"IH402": head})
        self.assertEqual((dm.of("turnout"), dm.of("mast")), ([t5, alias, coal], []))
        self.assertEqual(dm.by_user("head"), {"Head 2L": head})

    def test_turnout_switch_reads_the_id_else_the_name(self) -> None:
        for cells, want in ((dict(id="switch:12"), "12"), (dict(id="dcc:12"), "12"), (dict(id="block:12"), None),
                            (dict(id="switch:12", user_name="Switch 4"), "12"),
                            (dict(user_name="Switch 4"), "4"), (dict(user_name="DCC Switch 4"), "4"),
                            (dict(user_name="Coal"), None), (dict(user_name="Switch 4a"), None)):
            with self.subTest(cells):
                cells = dict(cells)
                r = drow("turnout", cells.pop("user_name", "Switch Coal"), "turnout", **cells)
                self.assertEqual(rf.turnout_switch(r), want)


class VirtualNames(unittest.TestCase):
    """check_virtual_names' head, mast and key rules (test_railroad.py holds the block, occupancy and turnout ones)."""

    def test_heads_by_their_user_names(self) -> None:
        self.assertEqual(rf.check_virtual_names([drow("head", "Head 108R Top", "head", jmri_name="IH:HART:C3:108R_Top")]),
                         [])
        self.assertEqual(rf.check_virtual_names([drow("head", "Head 2L", "head", jmri_name="IH:HART:C3:2R")]),
                         ["head Head 2L: jmri_name 'IH:HART:C3:2R', not IH:HART:C3:2L"])
        bad = rf.check_virtual_names([drow("head", "Signal 2L", "head", jmri_name="IH:HART:C3:2L")])
        self.assertEqual(len(bad), 1)
        self.assertIn("head 'Signal 2L' is not named Head", bad[0])

    def test_an_owner_named_head_is_held_to_the_form_only(self) -> None:
        owner = {(2, "mast:1:B:west")}
        head = drow("head", "Head Coal", "head", jmri_name="IH:HART:C3:2L", id="mast:1:B:west:single")
        self.assertEqual(rf.check_virtual_names([head], owner), [])
        self.assertEqual(rf.check_virtual_names([replace(head, jmri_name="IH77")], owner),
                         ["head Head Coal: jmri_name 'IH77' is no virtual head name"])
        self.assertEqual(rf.check_virtual_names([replace(head, jmri_name="IH77")], owner, swapped={(2, "mast:1:B:west")}),
                         [])

    def test_a_mast_with_no_virtual_name(self) -> None:
        self.assertEqual(rf.check_virtual_names([drow("mast", "Mast 2L", "home")]),
                         ["mast rows: a virtual name is empty or given twice"])

    def test_a_block_that_gives_no_sensor_key(self) -> None:
        rows = [drow("block", "Track 1/3", "track"), drow("occupancy", "BS 1/3", "track", jmri_name="IS:HART:C3:B:1/3")]
        bad = rf.check_virtual_names(rows)
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0].startswith("block Track 1/3: block 'Track 1/3' gives no clean sensor key"), bad)


class JoinMainUpper(unittest.TestCase):
    def test_control_points_and_local_switches(self) -> None:
        cps = [rf.Interlocking(2, 2, "CP 101", ("101", "103"), "North")]
        local = [rf.LocalSwitch(7, "107", 2, "Yard", "a spur")]
        got = rf.join_main_upper(cps, local)
        self.assertEqual(got, {"101": rf.MainUpperSwitch("101", 2, "North", "CP 101"),
                               "103": rf.MainUpperSwitch("103", 2, "North", "CP 101"),
                               "107": rf.MainUpperSwitch("107", 2, "Yard", notes="a spur")})
        with self.assertRaisesRegex(rf.FactsError, r"switch 103 is in a control point and in mine.csv \(line 9, CP 101\)"):
            rf.join_main_upper(cps, [rf.LocalSwitch(9, "103", 2, "Yard")], "mine.csv")


if __name__ == "__main__":
    unittest.main()
