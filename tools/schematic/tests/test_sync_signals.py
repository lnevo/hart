"""sync_signals.py: every level's masts and heads of a tables file follow masts.csv, and Signal Mast
Logic naming a mast that went or changed goes. Every test works on a small hand-written tables file and CSVs in a
temporary directory; only CommittedData reads the repo's files, as data checks under a guard that fails any write
into the repo (repo_read_only.py)."""
from __future__ import annotations

import contextlib
import csv
import functools
import io
import os
import sys
import tempfile
import unittest
import unittest.mock
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import sync_signals as sss  # noqa: E402
from hartlib import devices, level_masts, paths, railroad, tables  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402

HEAD_XML = "jmri.implementation.configurexml.VirtualSignalHeadXml"
SHSM_XML = "jmri.implementation.configurexml.SignalHeadSignalMastXml"
VSM_XML = "jmri.implementation.configurexml.VirtualSignalMastXml"


def head_xml(system, user, comment="internal"):
    note = f"<comment>{comment}</comment>" if comment else "<comment />"
    return (f'    <signalhead class="{HEAD_XML}">\n      <systemName>{system}</systemName>\n'
            f"      <userName>{user}</userName>\n      {note}\n    </signalhead>\n")


def mast_xml(system, user, comment, extra=""):
    return (f'    <signalmast class="{SHSM_XML}">\n      <systemName>{system}</systemName>\n'
            f"      <userName>{user}</userName>\n      <comment>{comment}</comment>\n"
            f'      <unlit allowed="no" />\n{extra}    </signalmast>\n')


def vsm_xml(system, user, comment):
    return (f'    <virtualsignalmast class="{VSM_XML}">\n      <systemName>{system}</systemName>\n'
            f"      <userName>{user}</userName>\n      <comment>{comment}</comment>\n"
            f'      <unlit allowed="yes" />\n    </virtualsignalmast>\n')


def logic_xml(source, *destinations):
    dests = "".join(f'      <destinationMast destination="{d}">\n'
                    f"        <destinationSignalMast>{d}</destinationSignalMast>\n"
                    f"        <enabled>yes</enabled>\n      </destinationMast>\n" for d in destinations)
    return (f'    <signalmastlogic source="{source}">\n      <sourceSignalMast>{source}</sourceSignalMast>\n'
            f"{dests}    </signalmastlogic>\n")


# The masts of the fixture, as the tables file holds them before a sync.
MAST_2R = mast_xml("IF$shsm:basic:one-searchlight(IH:HART:C1:2R)", "Mast 2R", "kept by hand &amp; never rewritten",
                   '      <disabledAspects>\n        <disabledAspect>Approach</disabledAspect>\n'
                   "      </disabledAspects>\n")
MAST_6LB = mast_xml("IF$shsm:basic:one-searchlight(IH432)", "Mast 6LB", "Plane | Switch 5")
MAST_4RA = mast_xml("IF$shsm:basic:one-low(IH:HART:C1:4RA)", "Mast 4RA", "Brick | Switch 3")       # changes type
MAST_9L = mast_xml("IF$shsm:basic:two-searchlight(IH:HART:C1:9L_Top)(IH:HART:C1:9L_Bottom)", "Mast 9L", "gone")
MAST_4LA = vsm_xml("IF$vsm:basic:one-low($1001)", "Mast 4LA", "Brick | virtual, kept")
MAST_5R = vsm_xml("IF$vsm:basic:one-low($1005)", "Mast 5R", "virtual, gone")
MAST_101L = mast_xml("IF$shsm:basic:two-searchlight(IH:HART:C3:101L_Top)(IH:HART:C3:101L_Bottom)", "Mast 101L",
                     "a main level mast")
HEAD_LAMP = head_xml("IH9990", "Turnout FB status", "a lamp, no staging head")
HEAD_2R = head_xml("IH:HART:C1:2R", "Head 2R")
HEAD_4RA = head_xml("IH:HART:C1:4RA", "Head 4RA", "hand comment on a head")
LEVEL_HEADS = head_xml("IH:HART:C3:101L_Top", "Head 101L Top") + head_xml("IH:HART:C3:101L_Bottom", "Head 101L Bottom")
LOGIC_KEPT = logic_xml("Mast 2R", "Mast 6LB")                 # names only unchanged masts
LOGIC_LEVEL = logic_xml("Mast 101L", "Mast 2R")
LOGIC_MIXED_BEFORE = logic_xml("Mast 6LB", "Mast 4RA", "Mast 2R")
LOGIC_MIXED_AFTER = logic_xml("Mast 6LB", "Mast 2R")          # its destination Mast 4RA went, the logic stays

TABLES = (
    "<?xml version='1.0' encoding='UTF-8'?>\n"
    "<layout-config>\n"
    '  <signalheads class="jmri.managers.configurexml.AbstractSignalHeadManagerXml">\n'
    + head_xml("IH432", "Head 6LB", "Node: 4 Signal: 0")
    + HEAD_LAMP
    + HEAD_2R
    + HEAD_4RA
    + head_xml("IH:HART:C1:9L_Top", "Head 9L Top")
    + head_xml("IH:HART:C1:9L_Bottom", "Head 9L Bottom")
    + head_xml("IH:HART:C1:30R", "Head 30R", "a staging head no mast uses")
    + LEVEL_HEADS
    + "  </signalheads>\n"
    '  <signalmasts class="jmri.managers.configurexml.DefaultSignalMastManagerXml">\n'
    + MAST_2R + MAST_4RA + MAST_6LB + MAST_9L + MAST_101L + MAST_4LA + MAST_5R
    + "  </signalmasts>\n"
    '  <signalmastlogics class="jmri.managers.configurexml.DefaultSignalMastLogicManagerXml">\n'
    "    <logicDelay>500</logicDelay>\n"
    + LOGIC_KEPT
    + logic_xml("Mast 4RA", "Mast 2R")                         # source changed
    + LOGIC_MIXED_BEFORE
    + logic_xml("Mast 9L", "Mast 2R")                          # source removed
    + LOGIC_LEVEL
    + logic_xml("IF$vsm:basic:one-low($1001)", "IF$vsm:basic:one-low($1005)")   # its one destination removed, by system name
    + "  </signalmastlogics>\n"
    "</layout-config>"
)


def mast_row(mast, system, cp="", switch="", heads="", level="1"):
    virtual = system.startswith("IF$vsm:")
    return dict(level=level, mast=mast, cp=cp, switch=switch, facing="Track X",
                protects="" if virtual else "OS Switch 1", dir="west", leg="", system_name=system,
                head_system_names=heads, device_system_name=system, **dict.fromkeys(level_masts.PLAN_FIELDS, ""))


# masts.csv of the fixture: 2R, 6LB, 4LA and the main level's 101L as the tables file has them, 4RA with another
# appearance on the same head, 10L and 12R new, and no 9L or 5R.
ROWS = [
    mast_row("Mast 2R", "IF$shsm:basic:one-searchlight(IH:HART:C1:2R)", "Brick", "1", "IH:HART:C1:2R=Head 2R"),
    mast_row("Mast 4RA", "IF$shsm:basic:one-searchlight(IH:HART:C1:4RA)", "Brick", "3", "IH:HART:C1:4RA=Head 4RA"),
    mast_row("Mast 6LB", "IF$shsm:basic:one-searchlight(IH432)", "Plane", "5", "IH432=Head 6LB"),
    mast_row("Mast 10L", "IF$shsm:basic:two-searchlight(IH:HART:C1:10L_Top)(IH:HART:C1:10L_Bottom)", "Barn", "",
             "IH:HART:C1:10L_Top=Head 10L Top;IH:HART:C1:10L_Bottom=Head 10L Bottom"),
    mast_row("Mast 4LA", "IF$vsm:basic:one-low($1001)", "Brick"),
    mast_row("Mast 12R", "IF$vsm:basic:one-low($1012)", "Barn"),
    mast_row("Mast 101L", "IF$shsm:basic:two-searchlight(IH:HART:C3:101L_Top)(IH:HART:C3:101L_Bottom)", "CP 101", "101",
             "IH:HART:C3:101L_Top=Head 101L Top;IH:HART:C3:101L_Bottom=Head 101L Bottom", level="2"),
]
COMMENTS = {"IH:HART:C1:10L_Top": "Barn | from the device map"}
NO_CHANGE = dict.fromkeys(("masts added", "masts removed", "heads added", "heads removed", "logics removed",
                           "destinations removed"), 0)


def device_row(layer, user, system, comment="", notes="", role=None):
    """A staging device-map row with the role its writer gives it: a head's is head, a mast's home unless given."""
    return dict(level="1", cp="", layer=layer, user_name=user, system_name=system, jmri_name=system, node="", dcc="",
                comment=comment, trial_name="", notes=notes, role=role or ("head" if layer == "head" else "home"),
                **dict.fromkeys(railroad.DEVICE_FACTS, ""))


def write_master(path: Path, rows) -> Path:
    """A devices.csv of just these staging device-map rows (hartlib.devices makes the master rows and holds them)."""
    mine = [devices.master_row(dict(r, id=f"test:{r['layer']}:{r['user_name']}"), "build_device_map.py")
            for r in rows]                    # a test id: check_rows wants one on every row with a level
    path.write_text(devices.master_text(devices.replace_rows([], "build_device_map.py", mine)), encoding="utf-8")
    return path


def write_csv(path: Path, columns, rows) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return path


def synced(text: str = TABLES, rows=None, comments=None):
    """(Tables after sync(), counts) for tables text and mast rows."""
    t = tables.loads(text.encode("utf-8"))
    counts = sss.sync(t.root, ROWS if rows is None else rows, COMMENTS if comments is None else comments)
    return t, counts


def text_of(t) -> str:
    return t.tobytes().decode("utf-8")


def users(root, beans) -> list[str]:
    return [tables.user_name(el) for el in beans(root)]


class Names(unittest.TestCase):
    def test_a_mast_is_a_mast_name_of_any_level(self):
        for name in ("Mast 2L", "Mast 4RA", "Mast 67", "Mast 8RC", "Mast 5", "Mast 101L", "Mast 120RC", "Mast A83"):
            self.assertTrue(sss.is_mast(name), name)
        for name in ("Mast A 5.7", "Mast 4r", "Head 2L", "Signal 2L", "", None, "Mast 2L "):
            self.assertFalse(sss.is_mast(name), name)
        self.assertTrue(sss.is_head("Head 101L Top") and sss.is_head("Head 67") and not sss.is_head("Turnout FB status"))


class Inputs(unittest.TestCase):
    """want_masts and head_comments read the files they are given (masts.csv, the master devices.csv)."""

    def test_want_masts_reads_the_rows_and_checks_the_columns(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_csv(Path(d) / "masts.csv", level_masts.FIELDS, ROWS)
            got = sss.want_masts(path)
            self.assertEqual([{c: r[c] for c in level_masts.FIELDS if c != "level"} for r in got],
                             [{c: r[c] for c in level_masts.FIELDS if c != "level"} for r in ROWS])
            self.assertEqual([r["level"] for r in got], [1, 1, 1, 1, 1, 1, 2])
            bad = write_csv(Path(d) / "bad.csv", ["mast", "system_name"], [dict(mast="Mast 2R", system_name="x")])
            with self.assertRaisesRegex(railroad.FactsError, "columns"):
                sss.want_masts(bad)
            with self.assertRaisesRegex(railroad.FactsError, "cannot read"):
                sss.want_masts(Path(d) / "missing.csv")

    def test_head_comments_join_comment_and_notes_of_head_rows_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_master(Path(d) / devices.ONE_FILE, [
                device_row("head", "Head 2R", "IH:HART:C1:2R", "Brick | Switch 1", "internal, not wired"),
                device_row("head", "Head 6LB", "IH432", "", "wired"),
                device_row("head", "Head 4RA", "IH:HART:C1:4RA", "Brick", ""),
                device_row("head", "Head 9L", "IH:HART:C1:9L"),
                device_row("mast", "Mast 2R", "IF$shsm:basic:one-searchlight(IH:HART:C1:2R)", "a mast", "no head"),
                dict(device_row("head", "Head 101L", "IH:HART:C3:101L", "CP 101", "virtual"), level="2")])
            self.assertEqual(sss.head_comments(path), {"IH:HART:C1:2R": "Brick | Switch 1 | internal, not wired",
                                                       "IH432": "wired", "IH:HART:C1:4RA": "Brick",
                                                       "IH:HART:C1:9L": "", "IH:HART:C3:101L": "CP 101 | virtual"})


class HeadCommentsErrors(unittest.TestCase):
    def test_a_master_that_cannot_be_read_stops_with_the_devices_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(devices.DevicesError, "cannot read it"):
                sss.head_comments(Path(d) / "missing.csv")
            bad = Path(d) / devices.ONE_FILE
            bad.write_text("layer,user_name\nhead,Head 2R\n", encoding="utf-8")
            with self.assertRaisesRegex(devices.DevicesError, "the header is not the master's columns"):
                sss.head_comments(bad)

    def test_a_master_with_no_head_rows_gives_no_comments(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sss.head_comments(write_master(Path(d) / devices.ONE_FILE, [])), {})


class Sync(unittest.TestCase):
    """sync() on the fixture: what stays, what is rewritten, what goes and what is added."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.counts = synced()
        cls.out = text_of(cls.t)

    def test_counts(self):
        self.assertEqual(self.counts, {"masts kept": 4, "masts added": 3, "masts removed": 3, "heads added": 2,
                                       "heads removed": 3, "logics removed": 3, "destinations removed": 2})

    def test_an_unchanged_mast_stays_byte_for_byte(self):
        # its hand comment and extra children carry over; system name, user name and class are all that is compared
        for block in (MAST_2R, MAST_6LB, MAST_4LA):
            self.assertIn(block, TABLES)
            self.assertIn(block, self.out)

    def test_another_levels_mast_in_the_file_and_a_head_of_no_mast_name_stay_byte_for_byte(self):
        for block in (MAST_101L, HEAD_LAMP, LEVEL_HEADS):
            self.assertIn(block, TABLES)
            self.assertIn(block, self.out)

    def test_a_changed_mast_is_rewritten_with_the_csv_name_and_a_new_comment(self):
        self.assertNotIn("IF$shsm:basic:one-low(IH:HART:C1:4RA)", self.out)
        self.assertIn(mast_xml("IF$shsm:basic:one-searchlight(IH:HART:C1:4RA)", "Mast 4RA", "Brick | Switch 3"),
                      self.out)
        self.assertEqual(users(self.t.root, tables.masts).count("Mast 4RA"), 1)

    def test_a_changed_mast_keeps_the_head_it_still_uses(self):
        self.assertIn(HEAD_4RA, self.out)

    def test_a_mast_not_in_the_csv_goes_with_its_heads(self):
        for gone in ("Mast 9L", "Head 9L", "IH:HART:C1:9L", "Mast 5R", "$1005"):
            self.assertIn(gone, TABLES)
            self.assertNotIn(gone, self.out)

    def test_a_staging_head_no_mast_uses_goes(self):
        self.assertNotIn("Head 30R", self.out)

    def test_new_masts_and_heads_are_added_as_jmri_writes_them(self):
        self.assertIn(mast_xml("IF$shsm:basic:two-searchlight(IH:HART:C1:10L_Top)(IH:HART:C1:10L_Bottom)", "Mast 10L",
                               "Barn"), self.out)
        self.assertIn(vsm_xml("IF$vsm:basic:one-low($1012)", "Mast 12R", "Barn"), self.out)
        # a new head takes the device map's comment and notes, or an empty comment
        self.assertIn(head_xml("IH:HART:C1:10L_Top", "Head 10L Top", "Barn | from the device map"), self.out)
        self.assertIn(head_xml("IH:HART:C1:10L_Bottom", "Head 10L Bottom", ""), self.out)

    def test_order_kept_elements_in_place_then_new_ones_in_csv_order_virtual_last(self):
        self.assertEqual(users(self.t.root, tables.masts),
                         ["Mast 2R", "Mast 6LB", "Mast 101L", "Mast 4LA", "Mast 4RA", "Mast 10L", "Mast 12R"])
        self.assertEqual(users(self.t.root, tables.signal_heads),
                         ["Head 6LB", "Turnout FB status", "Head 2R", "Head 4RA", "Head 101L Top", "Head 101L Bottom",
                          "Head 10L Top", "Head 10L Bottom"])

    def test_logic_naming_a_changed_or_removed_mast_goes_and_other_logic_stays(self):
        self.assertIn(LOGIC_KEPT, self.out)
        self.assertIn(LOGIC_LEVEL, self.out)
        self.assertIn("<logicDelay>500</logicDelay>", self.out)
        sources = [lg.get("source") for lg in self.t.root.iter("signalmastlogic")]
        # gone: the changed mast's own logic, the removed mast's, and the one left with no destination
        self.assertEqual(sources, ["Mast 2R", "Mast 6LB", "Mast 101L"])

    def test_a_logic_loses_only_the_destination_that_names_a_changed_mast(self):
        self.assertIn(LOGIC_MIXED_BEFORE, TABLES)
        self.assertIn(LOGIC_MIXED_AFTER, self.out)

    def test_the_result_is_well_formed_and_indented_like_the_rest(self):
        ET.fromstring(self.out.encode("utf-8"))
        self.assertTrue(self.out.startswith("<?xml version='1.0' encoding='UTF-8'?>\n<layout-config>\n"))
        self.assertTrue(self.out.endswith("  </signalmastlogics>\n</layout-config>"))
        for line in self.out.splitlines()[1:]:
            self.assertEqual((len(line) - len(line.lstrip(" "))) % 2, 0, line)
            self.assertFalse(line.endswith(" "), line)
            self.assertTrue(line.strip(), "an empty line")

    def test_a_second_sync_changes_nothing(self):
        again, counts = synced(self.out)
        self.assertEqual(counts, dict(NO_CHANGE, **{"masts kept": 7}))
        self.assertEqual(text_of(again), self.out)
        self.assertFalse(again.changed())


class SyncEdges(unittest.TestCase):
    def test_tables_that_already_follow_the_csv_are_left_byte_for_byte(self):
        rows = [ROWS[0], mast_row("Mast 4RA", "IF$shsm:basic:one-low(IH:HART:C1:4RA)", heads="IH:HART:C1:4RA=Head 4RA"),
                ROWS[2], mast_row("Mast 9L", "IF$shsm:basic:two-searchlight(IH:HART:C1:9L_Top)(IH:HART:C1:9L_Bottom)",
                                  heads="IH:HART:C1:9L_Top=Head 9L Top;IH:HART:C1:9L_Bottom=Head 9L Bottom"),
                ROWS[4], mast_row("Mast 5R", "IF$vsm:basic:one-low($1005)"),
                mast_row("Mast 30R", "IF$shsm:basic:one-low(IH:HART:C1:30R)", heads="IH:HART:C1:30R=Head 30R"),
                ROWS[-1]]                                       # the main level's 101L, in the same file
        text = TABLES.replace(MAST_5R, MAST_5R + mast_xml("IF$shsm:basic:one-low(IH:HART:C1:30R)", "Mast 30R", "added by hand"))
        t, counts = synced(text, rows)
        self.assertEqual(counts, dict(NO_CHANGE, **{"masts kept": 8}))
        self.assertFalse(t.changed())
        self.assertEqual(text_of(t), text)

    def test_a_mast_of_another_level_the_file_does_not_hold_goes_as_a_staging_one_does(self):
        _t, counts = synced(rows=ROWS[:-1])                     # 101L left out: one check for every level
        self.assertEqual((counts["masts removed"], counts["heads removed"]), (4, 5))

    def test_a_mast_whose_class_does_not_fit_its_system_name_is_replaced(self):
        # a virtual mast's row over a SignalHeadSignalMast element of the same names
        text = TABLES.replace(MAST_4LA, mast_xml("IF$vsm:basic:one-low($1001)", "Mast 4LA", "wrong class"))
        t, counts = synced(text)
        self.assertEqual((counts["masts kept"], counts["masts removed"], counts["masts added"]), (3, 4, 4))
        self.assertIn(vsm_xml("IF$vsm:basic:one-low($1001)", "Mast 4LA", "Brick"), text_of(t))

    def test_a_kept_mast_gets_a_head_the_tables_lack(self):
        t, counts = synced(TABLES.replace(HEAD_2R, ""))
        self.assertEqual((counts["masts kept"], counts["heads added"]), (4, 3))
        self.assertIn(MAST_2R, text_of(t))
        self.assertEqual(users(t.root, tables.signal_heads)[-3:], ["Head 2R", "Head 10L Top", "Head 10L Bottom"])

    def test_a_head_under_another_user_name_stops(self):
        text = TABLES.replace("<userName>Head 2R</userName>", "<userName>Head 2R Top</userName>")
        with self.assertRaises(sss.SyncError) as stop:
            synced(text)
        self.assertIn("head IH:HART:C1:2R is 'Head 2R Top' in tables.xml, 'Head 2R' in masts.csv",
                      str(stop.exception))

    def test_tables_without_a_heads_or_masts_section_stop(self):
        for text in ("<layout-config><signalheads /></layout-config>",
                     "<layout-config><signalmasts /></layout-config>"):
            with self.assertRaises(sss.SyncError) as stop:
                synced(text)
            self.assertIn("no signalheads or signalmasts section", str(stop.exception))

    def test_no_logic_section_is_fine(self):
        text = TABLES[:TABLES.index("  <signalmastlogics")] + "</layout-config>"
        _t, counts = synced(text)
        self.assertEqual((counts["logics removed"], counts["destinations removed"]), (0, 0))

    def test_a_logic_with_no_destination_of_its_own_stays(self):
        # only a logic that lost its last destination to this sync goes
        empty = logic_xml("Mast 2R")
        t, _counts = synced(TABLES.replace(LOGIC_KEPT, empty))
        self.assertIn(empty, text_of(t))

    def test_logic_is_matched_by_reference_not_by_comment(self):
        noted = LOGIC_KEPT.replace("<enabled>yes</enabled>", "<comment>Mast 4RA</comment>")
        t, _counts = synced(TABLES.replace(LOGIC_KEPT, noted))
        self.assertIn(noted, text_of(t))


class Cli(unittest.TestCase):
    """main(): --check reports and never writes; without it the file is written, unless JMRI runs."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        self.tables = d / "tables.xml"
        self.tables.write_bytes(TABLES.encode("utf-8"))
        masts = write_csv(d / "masts.csv", level_masts.FIELDS, ROWS)
        device_map = write_master(d / devices.ONE_FILE,
                                  [device_row("head", "Head 10L Top", "IH:HART:C1:10L_Top", "Barn", "from the device map")])
        for name, path in (("want_masts", masts), ("head_comments", device_map)):
            patch = unittest.mock.patch.object(sss, name, functools.partial(getattr(sss, name), path))
            patch.start()
            self.addCleanup(patch.stop)
        env = unittest.mock.patch.dict(os.environ, {"HART_GUARD_JMRI_RUNNING": "0"})
        env.start()
        self.addCleanup(env.stop)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sss.main([*args, "--tables", str(self.tables)])
        return code, out.getvalue(), err.getvalue()

    def test_check_reports_stale_and_writes_nothing(self):
        before = self.tables.read_bytes()
        stat = self.tables.stat()
        code, out, err = self.run_main("--check")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("differs from masts.csv", err)
        self.assertIn("'masts added': 3", err)
        self.assertIn("'logics removed': 3", err)
        self.assertNotIn("masts kept", err)
        self.assertIn("run tools/schematic/build_masts.py, then tools/schematic/build_tables.py", err)       # tables.xml is generated: sync_signals.py only checks
        self.assertEqual(self.tables.read_bytes(), before)
        self.assertEqual(self.tables.stat().st_mtime_ns, stat.st_mtime_ns)
        self.assertEqual(sorted(p.name for p in self.tables.parent.iterdir()),
                         [devices.ONE_FILE, "masts.csv", "tables.xml"])

    def test_sync_writes_then_check_reports_current_and_a_second_sync_is_the_same_file(self):
        code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.strip(), "4 masts kept, 3 masts added, 3 masts removed, 2 heads added, 3 heads removed, "
                                      "3 logics removed, 2 destinations removed")
        first = self.tables.read_bytes()
        self.assertEqual(first.decode("utf-8"), text_of(synced()[0]))
        code, out, err = self.run_main("--check")
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("ok: every level's signals in "), out)
        self.assertIn("follow masts.csv (7 masts)", out)
        self.assertEqual(self.tables.read_bytes(), first)
        code, out, _err = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "7 masts kept, 0 masts added, 0 masts removed, 0 heads added, 0 heads removed, "
                                      "0 logics removed, 0 destinations removed")
        self.assertEqual(self.tables.read_bytes(), first)

    def test_a_running_jmri_stops_the_write_but_not_the_check(self):
        before = self.tables.read_bytes()
        with unittest.mock.patch.dict(os.environ, {"HART_GUARD_JMRI_RUNNING": "1"}):
            code, _out, err = self.run_main()
            self.assertEqual(code, 2)
            self.assertIn("JMRI is running", err)
            self.assertEqual(self.tables.read_bytes(), before)
            self.assertEqual(self.run_main("--check")[0], 1)


class CommittedData(RepoReadOnly, unittest.TestCase):
    """Data checks, not rule tests: the repo's tables.xml follows the repo's masts.csv. They run --check and
    an in-memory sync under RepoReadOnly, so a write into the repo fails the test instead of changing a file."""

    def test_check_passes_on_the_committed_files_and_writes_nothing(self):
        before = paths.TABLES_XML.read_bytes()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sss.main(["--check"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("ok: every level's signals", out.getvalue())
        self.assertEqual(paths.TABLES_XML.read_bytes(), before)

    def test_every_committed_mast_is_kept_by_a_sync_in_memory(self):
        rows = sss.want_masts()
        counts = sss.sync(tables.read(paths.TABLES_XML), rows, sss.head_comments())
        self.assertEqual(counts, dict(NO_CHANGE, **{"masts kept": len(rows)}))


class MainStops(unittest.TestCase):
    def test_tables_without_sections_exit_1_naming_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_text("<layout-config><signalheads /></layout-config>", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sss.main(["--check", "--tables", str(path)]), 1)
        self.assertIn("no signalheads or signalmasts section", err.getvalue())


if __name__ == "__main__":
    unittest.main()
