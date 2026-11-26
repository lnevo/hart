"""Refusal and error paths of speedmatch/pom_guard_roster.py: roster parsing, address checks, consist state.

test_pom_guard.py covers the guard as a whole; these cases pin each refusal in the roster module
itself. In-process only: a fake roster in a temp folder and consist query logs as text.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_pom_guard import DEFAULT, N06, N2121, N2738, long_cvs, loco_xml, make_roster, qlog  # noqa: E402

_spec = importlib.util.spec_from_file_location("pom_guard_roster", HERE.parent / "speedmatch" / "pom_guard_roster.py")
r = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r)


class RosterCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def refused(self, fragment: str, fn, *a, **k) -> None:
        with self.assertRaises(r.GuardRefusal) as cm:
            fn(*a, **k)
        self.assertIn(fragment, str(cm.exception))

    def roster_dir(self, entries=DEFAULT, file_overrides=None) -> str:
        return make_roster(tempfile.mkdtemp(dir=self.dir), entries, file_overrides)

    def write_index(self, body: str) -> str:
        sub = tempfile.mkdtemp(dir=self.dir)
        os.makedirs(os.path.join(sub, "roster"))
        with open(os.path.join(sub, "roster.xml"), "w") as f:
            f.write("<roster-config><roster>%s</roster></roster-config>" % body)
        return sub


class AddressTest(RosterCase):
    def test_non_integer_address(self) -> None:
        self.refused("is not an integer", r.check_address, "3", False)
        self.refused("is not an integer", r.check_address, True, False)

    def test_short_lower_bound(self) -> None:
        self.refused("outside 1-127", r.check_address, -1, False)
        r.check_address(1, False)

    def test_train_node_refuses_a_bad_address(self) -> None:
        self.refused("broadcast", r.train_node, 0, True)


class LoadRosterTest(RosterCase):
    def test_full_entry_shape(self) -> None:
        roster = r.load_roster(self.roster_dir())
        e = roster["CSX 2738"]
        self.assertEqual((e["id"], e["address"], e["long"]), ("CSX 2738", 2738, True))
        self.assertTrue(e["file"].endswith(os.path.join("roster", "2738.xml")))
        self.assertEqual(e["cvs"][18], 2738 & 0xFF)

    def test_missing_index(self) -> None:
        self.refused("no roster index", r.load_roster, os.path.join(self.dir, "nowhere"))

    def test_duplicate_id(self) -> None:
        entries = [DEFAULT[0], ("CSX 2121", "other.xml", 2122, "yes", long_cvs(2122))]
        self.refused("appears twice", r.load_roster, self.roster_dir(entries))

    def test_missing_entry_file(self) -> None:
        d = self.roster_dir()
        os.remove(os.path.join(d, "roster", "2738.xml"))
        self.refused("roster file for 'CSX 2738' not found", r.load_roster, d)

    def test_empty_file_name(self) -> None:
        d = self.write_index(loco_xml("A 1", "", 5, "no", {}))
        self.refused("roster file for 'A 1' not found", r.load_roster, d)

    def test_entry_file_without_locomotive(self) -> None:
        d = self.roster_dir(file_overrides={"2738.xml": "<other/>"})
        self.refused("has no <locomotive>", r.load_roster, d)

    def test_entry_file_holds_another_id(self) -> None:
        body = loco_xml("CSX 9999", "2738.xml", 2738, "yes", long_cvs(2738))
        self.refused("holds id 'CSX 9999'", r.load_roster, self.roster_dir(file_overrides={"2738.xml": body}))

    def test_entry_file_address_disagrees(self) -> None:
        body = loco_xml("CSX 2738", "2738.xml", 2739, "yes", long_cvs(2739))
        self.refused("roster.xml says 2738L, 2738.xml says 2739L", r.load_roster,
                     self.roster_dir(file_overrides={"2738.xml": body}))

    def test_no_locoaddress(self) -> None:
        d = self.write_index('<locomotive id="A 1" fileName="a.xml" />')
        self.refused("has no <locoaddress>", r.load_roster, d)

    def test_no_dcclocoaddress(self) -> None:
        d = self.write_index('<locomotive id="A 1" fileName="a.xml"><locoaddress /></locomotive>')
        self.refused("has no <dcclocoaddress>", r.load_roster, d)

    def test_no_longaddress_flag(self) -> None:
        d = self.write_index('<locomotive id="A 1" fileName="a.xml"><locoaddress>'
                             '<dcclocoaddress number="5" /></locoaddress></locomotive>')
        self.refused("has no longaddress flag", r.load_roster, d)

    def test_address_not_a_number(self) -> None:
        d = self.write_index(loco_xml("A 1", "a.xml", "x5", "no", {}, attr_number="x5"))
        self.refused("address 'x5' is not a number", r.load_roster, d)

    def test_dcc_address_attribute_disagrees(self) -> None:
        d = self.write_index(loco_xml("A 1", "a.xml", 5, "no", {}, attr_number=6))
        self.refused("dccAddress 6 disagrees with dcclocoaddress 5", r.load_roster, d)

    def test_number_element_disagrees(self) -> None:
        body = loco_xml("A 1", "a.xml", 5, "no", {}).replace("<number>5</number>", "<number>7</number>")
        self.refused("<number> 7 disagrees with 5", r.load_roster, self.write_index(body))

    def test_unknown_protocol_is_not_checked(self) -> None:
        sub = self.roster_dir([("A 1", "a.xml", 5, "no", {1: 5})])
        roster = r.load_roster(sub)
        self.assertEqual(roster["A 1"]["address"], 5)

    def test_entry_cvs_skips_named_and_non_numeric_values(self) -> None:
        import xml.etree.ElementTree as ET
        root = ET.fromstring('<c><CVvalue name="3" value="26" /><CVvalue name="12.3" value="1" />'
                             '<CVvalue name="4" value="x" /><CVvalue name="5" /></c>')
        self.assertEqual(r._entry_cvs(root), {3: 26})


class TargetTest(RosterCase):
    def roster(self, entries=DEFAULT):
        return r.load_roster(self.roster_dir(entries))

    def test_short_cv1_must_match(self) -> None:
        roster = self.roster([("A 5", "a.xml", 5, "no", {1: 6})])
        self.refused("roster CV1 = 6 but the short address is 5", r.check_roster_target, roster, "A 5")

    def test_cv17_below_c0_is_refused(self) -> None:
        roster = self.roster([("A 1", "a.xml", 2738, "yes", long_cvs(2738, {17: 0x0A}))])
        self.refused("do not encode long address 2738", r.check_roster_target, roster, "A 1")

    def test_short_target_warns_on_another_entry_cv19(self) -> None:
        roster = self.roster([("A 5", "a.xml", 5, "no", {1: 5}), ("B 9", "b.xml", 9, "no", {1: 9, 19: 5})])
        e, warnings = r.check_roster_target(roster, "A 5")
        self.assertEqual(e["id"], "A 5")
        self.assertEqual(warnings, ["WARNING short address 5 is the roster CV19 of 'B 9' (may be a default)"])

    def test_clean_target_has_no_warnings(self) -> None:
        self.assertEqual(r.check_roster_target(self.roster(), "CSX 2738")[1], [])


class ConsistTest(RosterCase):
    def nodes(self):
        return r.query_nodes(r.load_roster(self.roster_dir()), "CSX 2738")

    def test_query_nodes_unknown_target(self) -> None:
        self.refused("is not in the roster", r.query_nodes, {}, "X")

    def test_query_nodes_refuses_an_entry_without_a_train_node(self) -> None:
        roster = {"A": {"address": 3, "long": False}, "B": {"address": 0, "long": False}}
        self.refused("roster entry 'B' has no train node to query: address 0", r.query_nodes, roster, "A")

    def test_parse_reads_counts_listeners_and_indices(self) -> None:
        st = r.parse_consist_log(qlog({N2738: [], N2121: [N06.lower()], N06: None}))
        self.assertTrue(st["complete"])
        self.assertEqual(st["nodes"][N2121], {"count": 1, "listeners": [N06], "indices": [0]})
        self.assertEqual(st["nodes"][N06]["count"], None)

    def test_parse_empty_and_none(self) -> None:
        self.assertEqual(r.parse_consist_log(None), {"complete": False, "errors": [], "nodes": {}})

    def test_parse_ignores_a_listener_before_any_header(self) -> None:
        st = r.parse_consist_log("  [0] flags 0x06 node 06.01.00.00.00.01\nEND\n")
        self.assertEqual(st["nodes"], {})

    def test_target_in_absent_ok(self) -> None:
        st = r.parse_consist_log(qlog({N2738: [], N2121: [], N06: []}))
        self.refused("cannot be in ABSENT_OK", r.check_no_consist, st, self.nodes(), ["CSX 2738"])

    def test_target_listed_as_a_listener(self) -> None:
        st = r.parse_consist_log(qlog({N2738: [], N2121: [], N06: [N2738]}))
        self.refused("is a listener of train node %s" % N06, r.check_no_consist, st, self.nodes())

    def test_clear_state_returns_no_notes(self) -> None:
        st = r.parse_consist_log(qlog({N2738: [], N2121: [], N06: []}))
        self.assertEqual(r.check_no_consist(st, self.nodes()), [])


if __name__ == "__main__":
    unittest.main()
