"""hartlib.wiring: wiring.csv, the physical wiring source, read and checked; addresses and wiring texts follow."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import wiring as W  # noqa: E402
from hartlib.railroad_facts import FactsError  # noqa: E402

HEAD = ",".join(W.COLUMNS) + "\n"
GOOD = (HEAD + "1,turnout,Switch 1,,,,,4,0,OU1,\"1,2\",wired,\n"
        "1,fb,FB Switch 1 N,,,,,4,3,IN1,1,wired,\n"
        "1,head,Head 6LB,,,,,4,0,OU2,\"1,2,3\",wired,\n"
        "1,detector,Track Barn,,,,,13,1,,,wired,\n"
        "1,detector,,,,,,2,2,,,wired,spare\n"
        "3,detector,,227,241,,2,41,4,,,planned,\n")


class Read(unittest.TestCase):
    def read(self, text):
        d = Path(tempfile.mkdtemp())
        p = d / "wiring.csv"
        p.write_text(text, encoding="utf-8")
        return W.read(p)

    def test_addresses_and_wiring_texts(self):
        got = [(w.kind, w.address, w.wiring_text) for w in self.read(GOOD)]
        self.assertEqual(got, [("turnout", "M2T408", "Node: 4 Turnout: 0 | OU: 1 Ports: 1,2"),
                               ("fb", "M2S470", "Node: 4 Sensor: 3 | IN: 1 Ports: 1"),
                               ("head", "IH432", "Node: 4 Signal: 0 | OU: 2 Ports: 1,2,3"),
                               ("detector", "M2S1300", "Node: 13 Block: 1"),
                               ("detector", "M2S201", "Node: 2 Block: 2"),
                               ("detector", "M2S4103", "Node: 41 Block: 4")])
        self.assertEqual(self.read(GOOD)[3].input, "Block 13-1")
        local = self.read(GOOD + "1,button,Switch 1 BTN,,,,,4,,IN2,1,wired,\n1,relay,Relay 1,,,,,2,,OU2,8,wired,\n")
        self.assertEqual([(w.kind, w.index, w.wiring_text) for w in local[-2:]],
                         [("button", None, "Node: 4 | IN: 2 Ports: 1"), ("relay", None, "Node: 2 | OU: 2 Ports: 8")])
        with self.assertRaisesRegex(ValueError, "no JMRI address"):
            local[-1].address

    def test_the_committed_file(self):
        rows = W.read()
        count = lambda lv, kind: sum(w.level == lv and w.kind == kind for w in rows)  # noqa: E731
        self.assertEqual((count(1, "turnout"), count(1, "fb"), count(1, "head"), count(1, "detector")),
                         (20, 40, 1, 45))
        self.assertTrue(all(w.status == "wired" for w in rows if w.level == 1 and w.kind not in ("calibration", "button")))
        self.assertEqual([w.device for w in rows if w.kind == "button" and w.status == "planned"],
                         ["Switch 7 BTN", "Switch 11 BTN", "Switch 9 BTN"])           # C13-IN2-1 to 3, not connected
        self.assertEqual([w.node for w in rows if w.kind == "calibration" and w.status == "planned"], [13])  # reserved

    def test_bad_rows_stop(self):
        for extra, msg in (("4,turnout,Switch 2,,,,,4,1,OU1,\"3,4\",wired,", "level is 1, 2 or 3"),
                           ("1,motor,Switch 2,,,,,4,1,OU1,\"3,4\",wired,", "kind is one of"),
                           ("1,turnout,Switch 2,,,,,4,1,OU1,\"3,4\",built,", "status is wired or planned"),
                           ("1,turnout,Switch 2,,,,,four,1,OU1,\"3,4\",wired,", "are numbers"),
                           ("1,turnout,Switch 2,,,,,4,8,OU1,\"3,4\",wired,", "a turnout's index is 0 to 7"),
                           ("1,detector,Track X,,,,,4,0,,,wired,", "a detector's index is 1 to 8"),
                           ("1,turnout,Switch 2,,,,,4,1,IN1,\"3,4\",wired,", "lands on an OU board"),
                           ("1,turnout,Switch 2,,,,,4,1,OU1,3,wired,", "takes 2 port"),
                           ("1,fb,FB Switch 2 N,,,,,4,4,IN1,9,wired,", "takes 1 port"),
                           ("1,turnout,,,,,,4,1,OU1,\"3,4\",wired,", "needs its device name"),
                           ("1,turnout,Switch 2,101,,,,4,1,OU1,\"3,4\",wired,", "named by device alone"),
                           ("1,detector,Track X,,,,,4,1,OU1,1,wired,", "no board or ports"),
                           ("3,detector,Track X,227,241,,1,41,5,,,planned,", "not both"),
                           ("1,detector,,13,15,,,3,1,,,wired,", "a staging detector is named by its block alone"),
                           ("1,button,Switch 1 BTN,,,,,4,0,IN2,1,wired,", "a button has no JMRI device, so no index"),
                           ("1,button,Switch 1 BTN,,,,,4,,OU2,1,wired,", "lands on an IN board"),
                           ("1,relay,Relay 2,,,,,4,,OU1,2,wired,", "node 4 OU1-2 is line 2's"),
                           ("1,turnout,Switch 1,,,,,4,1,OU1,\"3,4\",wired,", "turnout Switch 1 is line 2's"),
                           ("1,turnout,Switch 2,,,,,4,0,OU1,\"3,4\",wired,", "node 4 Turnout 0 is line 2's"),
                           ("1,turnout,Switch 2,,,,,4,1,OU1,\"2,3\",wired,", "node 4 OU1-2 is line 2's"),
                           ("1,detector,Track Y,,,,,13,1,,,wired,", "node 13 Block 1 is line 5's"),
                           ("1,turnout,Switch 2,,,,,4,1,OU1,\"3,4\",wired,,extra", "more fields")):
            with self.subTest(msg=msg), self.assertRaisesRegex(FactsError, msg):
                self.read(GOOD + extra + "\n")
        with self.assertRaisesRegex(FactsError, "columns"):
            self.read("level,kind\n1,turnout\n")



class Digicon(unittest.TestCase):
    """digicon_rows: the wired heads' pins in the old signal_wiring.csv columns; calibration_ports."""

    def read(self, text):
        d = Path(tempfile.mkdtemp())
        p = d / "wiring.csv"
        p.write_text(HEAD + text, encoding="utf-8")
        return p

    def test_a_two_head_mast_and_a_single_head(self):
        p = self.read('1,head,Head 24RA Top,,,,,2,0,OU1,"1,2,3",wired,\n1,head,Head 24RA Bottom,,,,,2,6,OU1,"4,5,6",wired,\n'
                      '1,head,Head 6LB,,,,,4,0,OU2,"1,2,3",wired,\n1,calibration,C4 calibration relay,,,,,4,,OU2,8,wired,\n')
        rows = W.digicon_rows(p)
        self.assertEqual([(r["port_id"], r["system_name"], r["user_name"], r["head_role"], r["topic"]) for r in rows[:4]],
                         [("C2-OU1-1", "IH232", "Head 24RA T R", "T", "track/signalhead/232"),
                          ("C2-OU1-2", "IH232", "Head 24RA T Y", "T", "track/signalhead/232"),
                          ("C2-OU1-3", "IH232", "Head 24RA T G", "T", "track/signalhead/232"),
                          ("C2-OU1-4", "IH238", "Head 24RA B R", "B", "track/signalhead/238")])
        self.assertEqual({r["mast_user_name"] for r in rows}, {"Mast 24RA", "Mast 6LB"})
        single = [r for r in rows if r["mast_user_name"] == "Mast 6LB"]
        self.assertEqual([(r["uid"], r["head_role"], r["user_name"]) for r in single],
                         [("32", "S", "Head 6LB R"), ("32", "S", "Head 6LB Y"), ("32", "S", "Head 6LB G")])
        self.assertEqual({r["board_location"] for r in rows}, {"North - Staging", "West - Staging"})
        self.assertEqual(W.calibration_ports(p), {"C4-OU2-8"})

    def test_a_planned_head_is_no_digicon_head(self):
        """Only wired heads are Digicon heads, as the old signal_wiring.csv held: a planned head's ports are
        reserved, nothing is on them yet."""
        p = self.read('1,head,Head 24RA Top,,,,,2,0,OU1,"1,2,3",planned,\n1,head,Head 6LB,,,,,4,0,OU2,"1,2,3",wired,\n')
        self.assertEqual({r["mast_user_name"] for r in W.digicon_rows(p)}, {"Mast 6LB"})

    def test_the_committed_heads_are_6lb(self):
        self.assertEqual({r["system_name"] for r in W.digicon_rows()}, {"IH432"})

    def test_a_head_that_is_not_named_as_a_head_stops(self):
        with self.assertRaisesRegex(FactsError, "is not a head name"):
            W.digicon_rows(self.read('1,head,Signal 6LB,,,,,4,0,OU2,"1,2,3",wired,\n'))



class Spans(unittest.TestCase):
    """A head is on one node, but its three pins may span two OU boards (owner, 2026-11-21)."""

    def read(self, text):
        d = Path(tempfile.mkdtemp())
        p = d / "wiring.csv"
        p.write_text(HEAD + text, encoding="utf-8")
        return p

    def test_a_head_across_two_boards(self):
        p = self.read('1,head,Head 32R,,,,,12,2,OU2,"7,OU3-8,OU3-7",wired,\n')
        [w] = W.read(p)
        self.assertEqual(w.pins, [("OU2", 7), ("OU3", 8), ("OU3", 7)])
        self.assertEqual(w.wiring_text, "Node: 12 Signal: 2 | OU: 2 Ports: 7 | OU: 3 Ports: 8,7")
        self.assertEqual([r["port_id"] for r in W.digicon_rows(p)], ["C12-OU2-7", "C12-OU3-8", "C12-OU3-7"])

    def test_what_a_span_may_not_do_stops(self):
        for text, msg in (('1,turnout,Switch 1,,,,,4,0,OU1,"1,OU2-2",wired,', "only a head's pins may span"),
                          ('1,head,Head 1L,,,,,4,0,OU2,"OU3-1,2,3",wired,', "the first pin OU3-1 is on the row's board"),
                          ('1,head,Head 1L,,,,,4,0,OU2,"1,OU2-2,3",wired,', "given as a pin alone, not OU2-<pin>"),
                          ('1,head,Head 1L,,,,,4,0,OU2,"7,OU3-8,6",wired,', "on OU2 come first, then those on"),
                          ('1,head,Head 1L,,,,,4,0,OU2,"7,OU5-8,OU5-7",wired,', "port 'OU5-8' is a pin 1 to 8"),
                          ('1,head,Head 1L,,,,,4,0,OU1,"1,OU2-1,OU3-1",wired,', "at most two boards"),
                          ('1,head,Head 1L,,,,,4,0,OU2,"1,1,2",wired,', "a pin is given twice"),
                          ('1,head,Head 1L,,,,,4,0,OU2,"6,7,8",wired,\n1,head,Head 2L,,,,,4,1,OU3,"8,OU2-8,OU2-7",wired,',
                           "node 4 OU2-8 is line 2's, OU2-7 is line 2's")):
            with self.subTest(msg=msg), self.assertRaisesRegex(FactsError, msg):
                W.read(self.read(text + "\n"))


class OneWay(unittest.TestCase):
    """wiring.csv changes only through freeze_wiring.py: held() and audit() tell what else did."""
    NOTE = "frozen from the device map's rule (CP 9, 2026-11-21)"

    def file(self, rows):
        p = Path(tempfile.mkdtemp()) / "wiring.csv"
        p.write_text(W.canonical(rows), encoding="utf-8")
        return p

    def row(self, level, kind, device, node, index, status, notes="", board="OU1", ports="1,2"):
        return dict(zip(W.COLUMNS, [level, kind, device, "", "", "", "", node, index,
                                    "" if kind == "detector" else board, "" if kind == "detector" else ports,
                                    status, notes]))

    def test_held_names_the_frozen_control_points(self):
        p = self.file([self.row("1", "turnout", "Switch 1", "4", "0", "wired"),
                       self.row("2", "turnout", "Switch 9", "42", "0", "wired", self.NOTE),
                       self.row("2", "detector", "OS Switch 9", "42", "1", "planned", "the owner's pin")])
        got = W.held(p)
        self.assertEqual([w.device for w in got.devices], ["Switch 9"])
        self.assertEqual([w.device for w in got.detectors], ["OS Switch 9"])
        self.assertEqual(got.cps, {"CP 9"})
        self.assertEqual(W.audit(p), [])

    def test_a_note_round_trips(self):
        w = W.read(self.file([self.row("2", "turnout", "Switch 9", "42", "0", "wired",
                                       "pin; " + W.freeze_note("CP 9", "2026-11-21"))]))[0]
        self.assertEqual(W.frozen_cp(w), "CP 9")

    def test_a_hand_wired_main_row_fails(self):
        p = self.file([self.row("2", "turnout", "Switch 9", "42", "0", "wired", "by hand")])
        self.assertRegex(W.audit(p)[0], "line 2: main/upper turnout Switch 9 is wired, but no freeze wrote it")

    def test_a_frozen_control_point_with_a_row_not_wired_fails(self):
        p = self.file([self.row("2", "turnout", "Switch 9", "42", "0", "wired", self.NOTE),
                       self.row("2", "detector", "OS Switch 9", "42", "1", "planned", self.NOTE)])
        self.assertRegex("; ".join(W.audit(p)), "OS Switch 9 is of CP 9, which is frozen, but is planned")

    def test_staging_by_hand_and_planned_main_rows_pass(self):
        p = self.file([self.row("1", "turnout", "Switch 1", "4", "0", "wired", "as built"),
                       self.row("2", "detector", "OS Switch 9", "42", "1", "planned")])
        self.assertEqual(W.audit(p), [])

    def test_text_not_in_the_freeze_format_fails(self):
        p = self.file([self.row("1", "turnout", "Switch 1", "4", "0", "wired")])
        p.write_text(p.read_text().replace("\n", "\r\n"), encoding="utf-8", newline="")
        self.assertRegex("; ".join(W.audit(p)), "not the form freeze_wiring.py writes")

    def test_a_row_with_a_stray_field_stops_cleanly(self):
        p = self.file([self.row("1", "turnout", "Switch 1", "4", "0", "wired")])
        p.write_text(p.read_text().replace("wired,", "wired,,extra,"), encoding="utf-8")
        with self.assertRaisesRegex(FactsError, "more fields than columns"):    # the check prints it as a FAIL
            W.audit(p)

    def test_the_committed_file_passes(self):
        self.assertEqual(W.audit(), [])


if __name__ == "__main__":
    unittest.main()
