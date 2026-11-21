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
                           ("1,relay,Relay 2,,,,,4,,OU1,2,wired,", r"OU1 port\(s\) \[2\] are line 2's"),
                           ("1,turnout,Switch 1,,,,,4,1,OU1,\"3,4\",wired,", "turnout Switch 1 is line 2's"),
                           ("1,turnout,Switch 2,,,,,4,0,OU1,\"3,4\",wired,", "node 4 Turnout 0 is line 2's"),
                           ("1,turnout,Switch 2,,,,,4,1,OU1,\"2,3\",wired,", r"OU1 port\(s\) \[2\] are line 2's"),
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
        self.assertEqual([r["uid"] for r in rows if r["mast_user_name"] == "Mast 6LB"], ["32"] * 3)
        self.assertEqual(W.calibration_ports(p), {"C4-OU2-8"})

    def test_the_committed_heads_are_6lb(self):
        self.assertEqual({r["system_name"] for r in W.digicon_rows()}, {"IH432"})

    def test_a_head_that_is_not_named_as_a_head_stops(self):
        with self.assertRaisesRegex(FactsError, "is not a head name"):
            W.digicon_rows(self.read('1,head,Signal 6LB,,,,,4,0,OU2,"1,2,3",wired,\n'))


if __name__ == "__main__":
    unittest.main()
