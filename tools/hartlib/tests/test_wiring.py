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
# Each device by its ID (naming-layers step 5); a file with no device master beside it is named by the repo's
GOOD = (HEAD + "1,turnout,switch:1,,,,,,4,0,OU1,\"1,2\",wired,\n"
        "1,fb,fb:1:N,,,,,,4,3,IN1,1,wired,\n"
        "1,head,mast:5:B:west:single,,,,,,4,0,OU2,\"1,2,3\",wired,\n"
        "1,detector,det:block:7A-13C,,,,,,13,1,,,wired,\n"
        "1,detector,,,,,,,2,2,,,wired,spare\n"
        "3,detector,,,227,241,,2,41,4,,,planned,\n")


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
        local = self.read(GOOD + "1,button,,Switch 1 BTN,,,,,4,,IN2,1,wired,\n1,relay,,Relay 1,,,,,2,,OU2,8,wired,\n")
        self.assertEqual([(w.kind, w.index, w.wiring_text) for w in local[-2:]],
                         [("button", None, "Node: 4 | IN: 2 Ports: 1"), ("relay", None, "Node: 2 | OU: 2 Ports: 8")])
        with self.assertRaisesRegex(ValueError, "no JMRI address"):
            local[-1].address

    def test_a_device_is_named_by_the_name_store(self):
        """A row gives its device's ID; read names it from the name store (a detector by its block's name), so a
        rename in devices_field.csv changes no row of wiring.csv."""
        got = [(w.kind, w.id, w.device) for w in self.read(GOOD)]
        self.assertEqual(got, [("turnout", "switch:1", "Switch 1"), ("fb", "fb:1:N", "FB Switch 1 N"),
                               ("head", "mast:5:B:west:single", "Head 6LB"),
                               ("detector", "det:block:7A-13C", "Track Barn"), ("detector", "", ""),
                               ("detector", "", "")])
        d = Path(tempfile.mkdtemp())
        (d / "wiring.csv").write_text(GOOD, encoding="utf-8")
        names = {("1", "switch:1"): "Switch One", ("1", "fb:1:N"): "FB Switch 1 N",
                 ("1", "mast:5:B:west:single"): "Head 6LB", ("1", "mast:5:B:west"): "Mast 6LB",
                 ("1", "block:7A-13C"): "Track Barn Lead"}
        self.assertEqual([w.device for w in W.read(d / "wiring.csv", names)][:4],
                         ["Switch One", "FB Switch 1 N", "Head 6LB", "Track Barn Lead"])

    def test_a_staging_turnout_with_no_field_row_is_named_by_its_id(self):
        """Naming-layers step 7: the builder generates a staging turnout or feedback with no field row, so read names
        it as the generator does (Switch <n>, FB Switch <n> N) when the staging plan has the switch (switch:2, which
        it has not, stops: test_bad_rows)."""
        from hartlib import devices
        d = Path(tempfile.mkdtemp())
        rows = [dict(r) for r in devices.field_rows() if r["id"] not in ("switch:1", "fb:1:N")]
        (d / devices.FIELD_FILE).write_text(devices.master_text(rows), encoding="utf-8")
        (d / "wiring.csv").write_text(GOOD, encoding="utf-8")
        got = W.read(d / "wiring.csv")
        self.assertEqual([(w.id, w.device) for w in got[:2]], [("switch:1", "Switch 1"), ("fb:1:N", "FB Switch 1 N")])

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
        for extra, msg in (("4,turnout,switch:3,,,,,,4,1,OU1,\"3,4\",wired,", "level is 1, 2 or 3"),
                           ("1,motor,switch:3,,,,,,4,1,OU1,\"3,4\",wired,", "kind is one of"),
                           ("1,turnout,switch:3,,,,,,4,1,OU1,\"3,4\",built,", "status is wired or planned"),
                           ("1,turnout,switch:3,,,,,,four,1,OU1,\"3,4\",wired,", "are numbers"),
                           ("1,turnout,switch:3,,,,,,4,8,OU1,\"3,4\",wired,", "a turnout's index is 0 to 7"),
                           ("1,detector,det:block:9B-end,,,,,,4,0,,,wired,", "a detector's index is 1 to 8"),
                           ("1,turnout,switch:3,,,,,,4,1,IN1,\"3,4\",wired,", "lands on an OU board"),
                           ("1,turnout,switch:3,,,,,,4,1,OU1,3,wired,", "takes 2 port"),
                           ("1,fb,fb:3:N,,,,,,4,4,IN1,9,wired,", "takes 1 port"),
                           ("1,turnout,,,,,,,4,1,OU1,\"3,4\",wired,", "needs its id"),
                           ("1,turnout,switch:3,,101,,,,4,1,OU1,\"3,4\",wired,", "named by its id alone"),
                           ("1,detector,det:block:9B-end,,,,,,4,1,OU1,1,wired,", "no board or ports"),
                           ("3,detector,det:block:227B-231A,,227,241,,1,41,5,,,planned,", "not both"),
                           ("1,detector,,,13,15,,,3,1,,,wired,", "a staging detector is named by its block's id alone"),
                           ("1,button,,Switch 1 BTN,,,,,4,0,IN2,1,wired,", "a button has no JMRI device, so no index"),
                           ("1,button,,Switch 1 BTN,,,,,4,,OU2,1,wired,", "lands on an IN board"),
                           ("1,relay,,Relay 2,,,,,4,,OU1,2,wired,", "node 4 OU1-2 is line 2's"),
                           ("1,turnout,switch:1,,,,,,4,1,OU1,\"3,4\",wired,", "turnout switch:1 is line 2's"),
                           ("1,turnout,switch:3,,,,,,4,0,OU1,\"3,4\",wired,", "node 4 Turnout 0 is line 2's"),
                           ("1,turnout,switch:3,,,,,,4,1,OU1,\"2,3\",wired,", "node 4 OU1-2 is line 2's"),
                           ("1,detector,det:block:9B-end,,,,,,13,1,,,wired,", "node 13 Block 1 is line 5's"),
                           ("1,turnout,switch:3,,,,,,4,1,OU1,\"3,4\",wired,,extra", "more fields"),
                           # naming-layers step 5: a device by its ID only, which the device master must have
                           ("1,turnout,,Switch 3,,,,,4,1,OU1,\"3,4\",wired,", "a turnout is named by its id, not device"),
                           ("1,turnout,fb:3:N,,,,,,4,1,OU1,\"3,4\",wired,", "a turnout's id starts switch:"),
                           ("1,turnout,switch:2,,,,,,4,1,OU1,\"3,4\",wired,", "switch:2 is no level 1 device"),
                           ("1,detector,det:block:9Z-end,,,,,,4,3,,,wired,", "block:9Z-end is no level 1 device"),
                           ("1,button,switch:1,Switch 1 BTN,,,,,4,,IN2,1,wired,", "a button has no JMRI device, so no id"),
                           ("1,relay,,,,,,,4,,OU2,7,wired,", "give its label in device")):
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
        p = self.read('1,head,mast:23:A-1A:A:east:top,,,,,,2,0,OU1,"1,2,3",wired,\n'
                      '1,head,mast:23:A-1A:A:east:bottom,,,,,,2,6,OU1,"4,5,6",wired,\n'
                      '1,head,mast:5:B:west:single,,,,,,4,0,OU2,"1,2,3",wired,\n'
                      '1,calibration,,C4 calibration relay,,,,,4,,OU2,8,wired,\n')
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
        p = self.read('1,head,mast:23:A-1A:A:east:top,,,,,,2,0,OU1,"1,2,3",planned,\n'
                      '1,head,mast:5:B:west:single,,,,,,4,0,OU2,"1,2,3",wired,\n')
        self.assertEqual({r["mast_user_name"] for r in W.digicon_rows(p)}, {"Mast 6LB"})

    def test_the_committed_heads_are_6lb(self):
        self.assertEqual({r["system_name"] for r in W.digicon_rows()}, {"IH432"})

    def test_a_main_head_is_a_digicon_head_by_its_rows_assignment(self):
        """A main or upper head is a Digicon head when its device row's assignment is field (a head swapped in by its
        row), its pins from the row's wiring text; a virtual one is not, whatever wiring.csv freezes for it."""
        import unittest.mock
        from hartlib import devices

        def head(assignment, jmri, wiring="Node: 33 Signal: 0 | OU: 3 Ports: 1 | OU: 4 Ports: 2 | OU: 3 Ports: 3", place="top"):
            return dict.fromkeys(devices.COLUMNS, "") | dict(
                level="2", layer="head", id=f"mast:107:B:west:{place}", user_name=f"Head 108LA {place.title()}",
                assignment=assignment, jmri_name=jmri, wiring=wiring, role="head")
        mast = dict.fromkeys(devices.COLUMNS, "") | dict(level="2", layer="mast", id="mast:107:B:west",
                                                         user_name="Mast 108LA", role="home")
        p = self.read('2,head,mast:107:B:west:bottom,,,,,,33,1,OU3,"4,5,6",wired,\n')
        bottom = head("virtual", "IH:HART:C3:108LA_Bottom", "Node: 33 Signal: 1 | OU: 3 Ports: 4,5,6", "bottom")
        with unittest.mock.patch.object(devices, "load", lambda files=None: devices.as_device_rows([mast, head("field", "IH3332"), bottom])):
            rows = W.digicon_rows(p)
        self.assertEqual([(r["port_id"], r["system_name"], r["user_name"], r["mast_user_name"]) for r in rows],
                         [("C33-OU3-1", "IH3332", "Head 108LA T R", "Mast 108LA"),
                          ("C33-OU4-2", "IH3332", "Head 108LA T Y", "Mast 108LA"),
                          ("C33-OU3-3", "IH3332", "Head 108LA T G", "Mast 108LA")])
        for bad, msg in ((head("field", "IH3333"), "jmri_name 'IH3333' is not the LCOS head IH3332"),
                         (head("field", "IH3332", "Node: 33 Block: 1"), "is not Node: <n> Signal: <i>")):
            with self.subTest(msg=msg), unittest.mock.patch.object(devices, "load", lambda files=None, b=bad: devices.as_device_rows([mast, b])), \
                    self.assertRaisesRegex(FactsError, msg):
                W.field_heads()

    def test_a_head_that_is_not_named_as_a_head_stops(self):
        # mast:5:B:west is the mast, Mast 6LB, not one of its heads: a head's id ends in its place
        with self.assertRaisesRegex(FactsError, "a head's id is its mast's id and its place"):
            W.digicon_rows(self.read('1,head,mast:5:B:west,,,,,,4,0,OU2,"1,2,3",wired,\n'))

    def test_a_renamed_head_keeps_its_mast_and_lamps(self):
        # the mast and the place come from the id, so an owner's name for the head changes no lamp
        d = Path(tempfile.mkdtemp())
        (d / "wiring.csv").write_text(",".join(W.COLUMNS) + '\n1,head,mast:5:B:west:single,,,,,,4,0,OU2,"1,2,3",wired,\n',
                                      encoding="utf-8")
        names = {("1", "mast:5:B:west:single"): "Head Plane West", ("1", "mast:5:B:west"): "Mast 6LB"}
        w = W.read(d / "wiring.csv", names)[0]
        self.assertEqual((w.device, w.mast, w.place), ("Head Plane West", "Mast 6LB", "single"))



class Spans(unittest.TestCase):
    """A head is on one node, but its three pins may span two OU boards (owner, 2026-11-21)."""

    def read(self, text):
        d = Path(tempfile.mkdtemp())
        p = d / "wiring.csv"
        p.write_text(HEAD + text, encoding="utf-8")
        return p

    def test_a_head_across_two_boards(self):
        p = self.read('1,head,mast:31:C:east:single,,,,,,12,2,OU2,"7,OU3-8,OU3-7",wired,\n')
        [w] = W.read(p)
        self.assertEqual(w.pins, [("OU2", 7), ("OU3", 8), ("OU3", 7)])
        self.assertEqual(w.wiring_text, "Node: 12 Signal: 2 | OU: 2 Ports: 7 | OU: 3 Ports: 8,7")
        self.assertEqual([r["port_id"] for r in W.digicon_rows(p)], ["C12-OU2-7", "C12-OU3-8", "C12-OU3-7"])

    def test_what_a_span_may_not_do_stops(self):
        for text, msg in (('1,turnout,switch:1,,,,,,4,0,OU1,"1,OU2-2",wired,', "only a head's pins may span"),
                          ('1,head,mast:1:A:west:top,,,,,,4,0,OU2,"OU3-1,2,3",wired,', "the first pin OU3-1 is on the row's board"),
                          ('1,head,mast:1:A:west:top,,,,,,4,0,OU2,"1,OU2-2,3",wired,', "given as a pin alone, not OU2-<pin>"),
                          ('1,head,mast:1:A:west:top,,,,,,4,0,OU2,"7,OU3-8,6",wired,', "on OU2 come first, then those on"),
                          ('1,head,mast:1:A:west:top,,,,,,4,0,OU2,"7,OU5-8,OU5-7",wired,', "port 'OU5-8' is a pin 1 to 8"),
                          ('1,head,mast:1:A:west:top,,,,,,4,0,OU1,"1,OU2-1,OU3-1",wired,', "at most two boards"),
                          ('1,head,mast:1:A:west:top,,,,,,4,0,OU2,"1,1,2",wired,', "a pin is given twice"),
                          ('1,head,mast:1:A:west:top,,,,,,4,0,OU2,"6,7,8",wired,\n1,head,mast:1:A:west:bottom,,,,,,4,1,OU3,"8,OU2-8,OU2-7",wired,',
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

    def row(self, level, kind, ident, node, index, status, notes="", board="OU1", ports="1,2"):
        return dict(zip(W.COLUMNS, [level, kind, ident, "", "", "", "", "", node, index,
                                    "" if kind == "detector" else board, "" if kind == "detector" else ports,
                                    status, notes]))

    def test_held_names_the_frozen_control_points(self):
        p = self.file([self.row("1", "turnout", "switch:1", "4", "0", "wired"),
                       self.row("2", "turnout", "switch:101", "42", "0", "wired", self.NOTE),
                       self.row("2", "detector", "det:os:101", "42", "1", "planned", "the owner's pin")])
        got = W.held(p)
        self.assertEqual([w.device for w in got.devices], ["Switch 101"])
        self.assertEqual([w.device for w in got.detectors], ["OS Switch 101"])
        self.assertEqual(got.cps, {"CP 9"})
        self.assertEqual(W.audit(p), [])

    def test_a_note_round_trips(self):
        w = W.read(self.file([self.row("2", "turnout", "switch:101", "42", "0", "wired",
                                       "pin; " + W.freeze_note("CP 9", "2026-11-21"))]))[0]
        self.assertEqual(W.frozen_cp(w), "CP 9")

    def test_a_hand_wired_main_row_fails(self):
        p = self.file([self.row("2", "turnout", "switch:101", "42", "0", "wired", "by hand")])
        self.assertRegex(W.audit(p)[0], "line 2: main/upper turnout Switch 101 is wired, but no freeze wrote it")

    def test_a_frozen_control_point_with_a_row_not_wired_fails(self):
        p = self.file([self.row("2", "turnout", "switch:101", "42", "0", "wired", self.NOTE),
                       self.row("2", "detector", "det:os:101", "42", "1", "planned", self.NOTE)])
        self.assertRegex("; ".join(W.audit(p)), "OS Switch 101 is of CP 9, which is frozen, but is planned")

    def test_staging_by_hand_and_planned_main_rows_pass(self):
        p = self.file([self.row("1", "turnout", "switch:1", "4", "0", "wired", "as built"),
                       self.row("2", "detector", "det:os:101", "42", "1", "planned")])
        self.assertEqual(W.audit(p), [])

    def test_text_not_in_the_freeze_format_fails(self):
        p = self.file([self.row("1", "turnout", "switch:1", "4", "0", "wired")])
        p.write_text(p.read_text().replace("\n", "\r\n"), encoding="utf-8", newline="")
        self.assertRegex("; ".join(W.audit(p)), "not the form freeze_wiring.py writes")

    def test_a_row_with_a_stray_field_stops_cleanly(self):
        p = self.file([self.row("1", "turnout", "switch:1", "4", "0", "wired")])
        p.write_text(p.read_text().replace("wired,", "wired,,extra,"), encoding="utf-8")
        with self.assertRaisesRegex(FactsError, "more fields than columns"):    # the check prints it as a FAIL
            W.audit(p)

    def test_the_committed_file_passes(self):
        self.assertEqual(W.audit(), [])


if __name__ == "__main__":
    unittest.main()
