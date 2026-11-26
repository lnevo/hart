"""write_inventory.py: v86 is written from scratch from devices.csv, wiring.csv and lcos_nodes.csv:
staging as JMRI has it wired, main and upper as the rule gives them, every port where its wiring text puts it."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("write_inventory", ROOT / "tools/wiring/write_inventory.py")
WI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WI)


def sheets(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    return {ws.title: [r for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]
            for ws in wb.worksheets}


V86 = sheets(WI.OUT)
MAP = WI.read_device_rows()
NODES = {int(r["node"]): r["level"] for r in WI.read_node_rows()}
IDS = {r[2]: r[0] for r in V86["Nodes"][1:]}          # address -> the node's ID on the sheets (M1, D5, C4, ...)
STAGING = {IDS[n] for n, lv in NODES.items() if lv == "1"}
DESIGN = {IDS[n] for n, lv in NODES.items() if lv != "1"}


class Inventory(unittest.TestCase):
    def test_v86_is_current(self):
        self.assertEqual(WI.main(["--check"]), 0)

    def test_a_detector_names_its_block_by_its_blocks_column_never_its_name(self):
        by_name = {"Track 9-11": {}, "OS Switch 9": {}}
        occ = dict(role="os", user_name="BS Switch 9", blocks="Track 9-11")
        self.assertEqual(WI.block_name(occ, by_name), "Track 9-11")
        self.assertIsNone(WI.block_name(dict(occ, role="spare", blocks=""), by_name))
        with self.assertRaisesRegex(WI.InventoryError, "occupancy BS Switch 9 names no block in its blocks column"):
            WI.block_name(dict(occ, blocks=""), by_name)
        with self.assertRaisesRegex(WI.InventoryError, "detects Track 1-3, which has no block row"):
            WI.block_name(dict(occ, blocks="Track 1-3"), by_name)
        with self.assertRaisesRegex(WI.devices.DevicesError, "has no role"):
            WI.block_name(dict(occ, role=""), by_name)

    def test_every_node_is_listed(self):
        self.assertEqual({r[2] for r in V86["Nodes"][1:]}, set(NODES))
        self.assertEqual(next(r for r in V86["Nodes"] if r[0] == "C2")[1], "C3")     # its legacy ID, from the source

    def test_every_device_port_is_in_the_workbook(self):
        out = {r[0]: r for r in V86["DNOU8"][1:]}
        inp = {r[0]: r for r in V86["DNIN8"][1:]}
        blocks = {r[8].split(" / ")[1]: r for r in V86["BlockSensors"][1:] if r[8] and " / M2S" in r[8]}
        for x in MAP + WI.spare_rows():
            if not x["node"] or x["system_name"].startswith("MTT"):
                continue
            node = f"C{x['node']}"
            m = WI.PORT.search(x["comment"])
            if x["layer"] == "turnout":
                for pin, nr in zip(m.group(3).split(","), "NR"):
                    self.assertEqual(out[f"{node}-OU{m.group(2)}-{pin}"][4], f"{x['user_name']} {nr}")
            elif x["layer"] == "head" and m:          # staging's lamps are named as wiring.csv's heads (digicon_rows)
                for pin, lamp in zip(m.group(3).split(","), "RYG"):
                    got = out[f"{node}-OU{m.group(2)}-{pin}"][4]
                    self.assertTrue(got.startswith(x["user_name"]) and got.endswith(f" {lamp}"), got)
            elif x["layer"] == "fb":
                self.assertEqual(inp[f"{node}-IN{m.group(2)}-{m.group(3)}"][4],
                                 x["user_name"].removeprefix("FB ") + " FB")
            elif x["layer"] == "occupancy":
                k = int(WI.NODE_K.match(x["comment"]).group(3)) - 1
                self.assertEqual(blocks[x["system_name"]][0], f"{node}-B{k // 2 + 1}-{k % 2 + 1}")

    def test_staging_holds_only_what_is_wired(self):
        """Staging's ports are what is wired: its turnouts, feedback, buttons, calibration relays, the 6LB head and
        its detectors, nothing from the old plan: no reserved pins and no old signal LEDs."""
        kinds = {r[5] for r in V86["DNOU8"][1:] if r[1] in STAGING and r[4]}
        self.assertEqual(kinds, {"Turnout Motor", "Searchlight Signal Head", "Calibration Relay"})
        self.assertEqual({r[5] for r in V86["DNIN8"][1:] if r[1] in STAGING and r[4]}, {"Turnout Feedback", "Button"})
        heads = [r for r in V86["DNOU8"][1:] if r[1] in STAGING and r[5] == "Searchlight Signal Head"]
        self.assertEqual([r[0] for r in heads], ["C4-OU2-1", "C4-OU2-2", "C4-OU2-3"])
        self.assertEqual(next(r for r in V86["DNOU8"] if r[0] == "C13-OU2-1")[4], "Switch 7 N")   # Engine House node
        spares = [r[0] for r in V86["BlockSensors"][1:] if r[4] == "Unused"]
        self.assertEqual(spares, ["C2-B1-2", "C3-B4-2"])

    def test_main_and_upper_rows_are_shaded_and_staging_rows_are_not(self):
        wb = load_workbook(WI.OUT)
        col = {"Nodes": 0, "DNOU8": 1, "DNIN8": 1, "TurnoutSummary": 1, "BlockSensors": 1}
        for sheet, c in col.items():
            ws = wb[sheet]
            width = sum(1 for h in ws[1] if h.value is not None)
            for row in ws.iter_rows(min_row=2):
                if row[c].value is None:
                    continue
                for cell in row[:width]:                             # the whole row, not only column A
                    shaded = cell.fill.fill_type == "solid" and str(cell.fill.fgColor.rgb).endswith("DDEBF7")
                    self.assertEqual(shaded, row[c].value in DESIGN, f"{sheet} {row[0].value} {cell.coordinate}")

    def test_every_node_with_detectors_has_its_calibration_relay(self):
        """The relay that resets the DCC power so the detectors calibrate: staging's from
        wiring.csv (C2's is C2 RELAY 1, C13's reserved), main and upper's by the rule, one each."""
        cal = [r for r in V86["DNOU8"][1:] if r[5] == "Calibration Relay"]
        self.assertEqual(sorted(r[1] for r in cal), sorted({r[1] for r in V86["BlockSensors"][1:]}))
        by = {r[1]: r for r in cal}
        self.assertEqual((by["C2"][0], by["C13"][0]), ("C2-OU2-8", "C13-OU1-8"))
        self.assertIn("reserved", by["C13"][7])

    def test_a_staging_detector_node_with_no_calibration_relay_stops(self):
        nodes = WI.gather(MAP + WI.spare_rows(), WI.read_node_rows())       # no wiring.csv rows added
        with self.assertRaisesRegex(WI.FactsError, "has block detectors but no calibration relay port"):
            WI.calibration(nodes)

    def test_the_buttons_are_wiring_csvs(self):
        """Fascia buttons are live with no JMRI device: wiring.csv puts them on the sheets, a
        turnout's button on its TurnoutSummary row."""
        buttons = [r for r in V86["DNIN8"][1:] if r[5] == "Button"]
        self.assertEqual(len(buttons), 20)
        self.assertEqual(next(r for r in buttons if r[0] == "C1-IN2-1")[4], "Switch 35 BTN")
        turnouts = {r[0]: r for r in V86["TurnoutSummary"][1:]}
        c13 = [(r[0], r[4], r[6]) for r in buttons if r[1] == "C13"]          # planned: not connected yet
        self.assertEqual([x[:2] for x in c13], [("C13-IN2-1", "Switch 7 BTN"), ("C13-IN2-2", "Switch 11 BTN"),
                                                ("C13-IN2-3", "Switch 9 BTN")])
        self.assertTrue(all(x[2] == "planned, not connected; (owner, 2026-11-21)" for x in c13))
        self.assertEqual(turnouts["Switch 7 (OS Switch 7)"][4], "C13-IN2-1 (planned)")
        self.assertIn("Switch 7 BTN (planned)", next(r for r in V86["Nodes"] if r[0] == "C13")[
            WI.NODE_COLUMNS.index("Button Devices")])
        self.assertEqual(turnouts["Switch 35 (OS Switch 35b)"][4], "C1-IN2-1")
        c1 = next(r for r in V86["Nodes"] if r[0] == "C1")
        self.assertEqual(c1[WI.NODE_COLUMNS.index("Num Buttons")], 3)

    def test_a_planned_relay_says_so(self):
        import tempfile
        p = Path(tempfile.mkdtemp()) / "wiring.csv"
        p.write_text(",".join(WI.wiring.COLUMNS) + "\n1,relay,,C3 relay 2,,,,,3,,OU2,7,planned,\n", encoding="utf-8")
        nodes = WI.gather([], WI.read_node_rows())
        WI.add_local(nodes, p)
        self.assertEqual(nodes[3].ou[2][7], ("C3 relay 2", "Relay", "5V", "planned, not connected"))

    def test_a_mast_role_is_matched_against_every_row_of_its_switch(self):
        """A crossover has a row per OS block: a facing on the first half's closed leg is a normal exit, not an entry
        because only the last row was read. One row behaves as it always did."""
        from types import SimpleNamespace as Row
        one = [Row(closed_leg="A", thrown_leg="B")]
        self.assertEqual([WI.mast_role(one, f) for f in ("A", "B", "C")], ["Normal Exit", "Reverse Exit", "Entry"])
        two = [Row(closed_leg="A", thrown_leg="X"), Row(closed_leg="C", thrown_leg="A")]
        self.assertEqual([WI.mast_role(two, f) for f in ("A", "C", "X", "Z")],
                         ["Normal Exit", "Normal Exit", "Reverse Exit", "Entry"])
        with self.assertRaisesRegex(WI.FactsError, "no switches.csv rows"):
            WI.mast_role([], "A")

    def test_staging_legs_hold_a_row_per_os_block(self):
        legs = WI.staging_legs()
        self.assertIs(type(legs), dict)
        self.assertEqual([len(legs[s]) for s in ("5", "23")], [1, 2])

    def test_two_wired_masts_in_one_role_of_one_half_stop(self):
        place = {}
        WI.take_role(place, "23", "Normal Exit", "24L", ["a", "b", "c"], "OS Switch 23a")
        with self.assertRaisesRegex(WI.FactsError,
                                    r"Switch 23 \(OS Switch 23a\): masts 24L and 24RB are both wired.*Normal Exit"):
            WI.take_role(place, "23", "Normal Exit", "24RB", ["d", "e", "f"], "OS Switch 23a")
        WI.take_role(place, "23", "Entry", "24RA", ["g", "h", "i"], "OS Switch 23a")     # another role is free
        WI.take_role(place, "23", "Normal Exit", "24RB", ["d", "e", "f"], "OS Switch 23b")   # the other half is free
        WI.take_role(place, "5", "Normal Exit", "A", [])
        with self.assertRaisesRegex(WI.FactsError, "Switch 5: masts A and B .*one Normal Exit slot per switch"):
            WI.take_role(place, "5", "Normal Exit", "B", [])

    def test_a_crossover_mast_goes_to_the_half_it_faces_into(self):
        legs = WI.staging_legs()
        self.assertIsNone(WI.mast_half(legs["5"], "5", "6LB", "anything"))        # one OS block: no halves
        self.assertEqual(WI.mast_half(legs["7"], "7", "8LB", "OS Switch 7b"), "OS Switch 7b")
        self.assertEqual(WI.mast_half(legs["7"], "7", "8LA", "OS Switch 7"), "OS Switch 7")
        with self.assertRaisesRegex(WI.FactsError, "devices.csv line 12: Mast 8LA on crossover Switch 7 protects 'OS Switch 9'"):
            WI.mast_half(legs["7"], "7", "8LA", "OS Switch 9", "devices.csv line 12")

    def test_a_main_or_upper_mast_never_lands_in_a_staging_slot(self):
        place = {}
        WI.take_role(place, "5", "Entry", "6LB", ["a", "b", "c"])
        WI.take_role(place, "5", "Entry", "M5", ["d", "e", "f"], design=True)     # same number, other level kind
        self.assertEqual((place[(False, "5", None)]["Entry"][0], place[(True, "5", None)]["Entry"][0]), ("6LB", "M5"))
        rows = [dict(zip(WI.TURNOUT_COLUMNS, r)) for r in V86["TurnoutSummary"][1:]]
        self.assertTrue(all(r["JMRI Turnout"] and r["Turnout"].startswith(r["JMRI Turnout"]) for r in rows))

    def test_a_crossover_has_a_row_per_half_and_a_plain_switch_one(self):
        rows = [r for r in V86["TurnoutSummary"][1:] if r[0].startswith("Switch ")]
        for sw, halves in (("7", ("OS Switch 7", "OS Switch 7b")), ("23", ("OS Switch 23a", "OS Switch 23b")),
                           ("35", ("OS Switch 35b", "OS Switch 35a"))):
            got = [r for r in rows if r[-1] == f"Switch {sw}"]            # the JMRI Turnout column
            self.assertEqual([r[0] for r in got], [f"Switch {sw} ({h})" for h in halves])
            self.assertEqual(len({r[1:7] for r in got}), 1)             # the turnout's facts repeat on both
        self.assertEqual([r[0] for r in rows if r[0].startswith("Switch 5")], ["Switch 5"])

    def test_each_half_of_a_crossover_has_its_own_slots(self):
        """Switch 7's four masts wired: 8RA faces Track Scale, the closed leg of half OS Switch 7 (normal exit), and
        8LA faces Track Barn into it (entry); 8LB faces Track Main East, the closed leg of 7b, and 8RB enters 7b."""
        def mast(name, facing, protects):
            return {"user_name": f"Mast {name}", "switch": "7", "facing": facing, "protects": protects}
        by_name = {m["user_name"]: m for m in (mast("8LA", "Track Barn", "OS Switch 7"),
                                               mast("8RA", "Track Scale", "OS Switch 7"),
                                               mast("8LB", "Track Main East", "OS Switch 7b"),
                                               mast("8RB", "Track East Ext", "OS Switch 7b"))}
        nodes = WI.gather(MAP + WI.spare_rows(), WI.read_node_rows())
        WI.add_local(nodes)
        n13 = next(n for n in nodes.values() if n.id == "C13")
        n13.heads = [(f"Head {m}", [(3, i * 3 + p) for p in (1, 2, 3)]) for i, m in enumerate(("8LA", "8RA", "8LB", "8RB"))]
        wb = WI.Workbook()
        WI.turnout_sheet(wb, nodes, by_name)
        rows = {r[0]: dict(zip(WI.TURNOUT_COLUMNS, r)) for r in wb["TurnoutSummary"].iter_rows(min_row=2, values_only=True)}
        a, b = rows["Switch 7 (OS Switch 7)"], rows["Switch 7 (OS Switch 7b)"]
        self.assertEqual((a["Entry Signal"], a["Normal Exit Signal"], a["Reverse Exit Signal"]), ("8LA", "8RA", None))
        self.assertEqual((b["Entry Signal"], b["Normal Exit Signal"], b["Reverse Exit Signal"]), ("8RB", "8LB", None))
        self.assertEqual(a["Entry Signal R Port"], "C13-OU3-1")

    def test_a_wired_staging_mast_is_on_its_switchs_row(self):
        """Mast 6LB stands on Switch 5's closed leg (Track East Ext): its normal exit signal."""
        row = dict(zip(WI.TURNOUT_COLUMNS, next(r for r in V86["TurnoutSummary"] if r[0] == "Switch 5")))
        self.assertEqual((row["Normal Exit Signal"], row["Normal Exit R Port"], row["Normal Exit G Port"]),
                         ("6LB", "C4-OU2-1", "C4-OU2-3"))
        self.assertIsNone(row["Entry Signal"])

    def test_the_lamps_are_named_as_the_digicon_sheet_names_them(self):
        names = {r[0]: r[4] for r in V86["DNOU8"][1:]}
        self.assertEqual([names[f"C4-OU2-{p}"] for p in (1, 2, 3)], ["Head 6LB R", "Head 6LB Y", "Head 6LB G"])

    def test_the_power_districts_are_left_blank(self):
        """Not mapped yet: the old inventory's districts were old names, not real."""
        self.assertEqual({r[7] for r in V86["BlockSensors"][1:]}, {None})

    def test_the_main_radio_and_dcc_nodes_keep_their_ids(self):
        nodes = {r[2]: r for r in V86["Nodes"][1:]}
        self.assertEqual((nodes[0][0], nodes[0][4]), ("M1", "Main"))
        self.assertEqual((nodes[5][0], nodes[5][1], nodes[5][4]), ("D5", "D1", "DCC"))
        self.assertEqual((nodes[1][1], nodes[11][4]), ("C1", "Client"))

    def test_a_head_across_two_boards_is_on_both(self):
        row = dict(next(x for x in MAP if x["layer"] == "head" and x["node"] == "4"),
                   comment="Node: 4 Signal: 0 | OU: 2 Ports: 7 | OU: 3 Ports: 8,7")
        n = WI.gather([row], WI.read_node_rows())[4]
        self.assertEqual((sorted(n.ou[2]), sorted(n.ou[3])), ([7], [7, 8]))

    def test_a_row_with_a_node_and_no_port_stops(self):
        row = dict(next(x for x in MAP if x["layer"] == "fb" and x["node"]), comment="")
        with self.assertRaisesRegex(WI.FactsError, "is on node .* but its wiring '' gives no port"):
            WI.gather([row], WI.read_node_rows())

    def test_a_device_on_an_unlisted_node_stops(self):
        row = dict(next(x for x in MAP if x["layer"] == "turnout" and x["node"] and x["system_name"].startswith("M2T")),
                   node="77")
        with self.assertRaisesRegex(WI.InventoryError, "node 77 is in devices_generated.csv but not in lcos_nodes.csv"):
            WI.gather([row], WI.read_node_rows())

    def test_main_exits_1_with_the_row_message(self):
        from unittest import mock

        with mock.patch.object(WI, "build", side_effect=WI.InventoryError("node 77 is not listed")), \
                self.assertRaises(SystemExit) as stop:
            WI.main([])
        self.assertEqual(stop.exception.code, "node 77 is not listed")


if __name__ == "__main__":
    unittest.main()
