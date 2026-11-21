"""write_inventory.py: v86 is written from scratch from devices.csv, wiring.csv and lcos_nodes.csv (owner, 2026-11-20):
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
            elif x["layer"] == "head" and m:          # staging's lamps are named as signal_wiring.csv names them
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
        its detectors, nothing from the old plan (owner, 2026-11-20): no reserved pins and no old signal LEDs."""
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
        """The relay that resets the DCC power so the detectors calibrate (owner, 2026-11-21): staging's from
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
        """Fascia buttons are live with no JMRI device (owner, 2026-11-20): wiring.csv puts them on the sheets, a
        turnout's button on its TurnoutSummary row."""
        buttons = [r for r in V86["DNIN8"][1:] if r[5] == "Button"]
        self.assertEqual(len(buttons), 20)
        self.assertEqual(next(r for r in buttons if r[0] == "C1-IN2-1")[4], "Switch 35 BTN")
        c13 = [(r[0], r[4], r[6]) for r in buttons if r[1] == "C13"]          # planned: not connected yet
        self.assertEqual([x[:2] for x in c13], [("C13-IN2-1", "Switch 7 BTN"), ("C13-IN2-2", "Switch 11 BTN"),
                                                ("C13-IN2-3", "Switch 9 BTN")])
        self.assertTrue(all(x[2].startswith("planned, not connected") for x in c13))
        turnouts = {r[0]: r for r in V86["TurnoutSummary"][1:]}
        self.assertEqual(turnouts["Switch 35"][4], "C1-IN2-1")
        c1 = next(r for r in V86["Nodes"] if r[0] == "C1")
        self.assertEqual(c1[WI.NODE_COLUMNS.index("Num Buttons")], 3)

    def test_a_wired_staging_mast_is_on_its_switchs_row(self):
        """Mast 6LB stands on Switch 5's closed leg (Track East Ext): its normal exit signal."""
        row = dict(zip(WI.TURNOUT_COLUMNS, next(r for r in V86["TurnoutSummary"] if r[0] == "Switch 5")))
        self.assertEqual((row["Normal Exit Signal"], row["Normal Exit R Port"], row["Normal Exit G Port"]),
                         ("6LB", "C4-OU2-1", "C4-OU2-3"))
        self.assertIsNone(row["Entry Signal"])

    def test_the_lamps_are_named_as_the_digicon_sheet_names_them(self):
        names = {r[0]: r[4] for r in V86["DNOU8"][1:]}
        self.assertEqual([names[f"C4-OU2-{p}"] for p in (1, 2, 3)], ["Head 6LB T R", "Head 6LB T Y", "Head 6LB T G"])

    def test_the_power_districts_are_left_blank(self):
        """Not mapped yet (owner, 2026-11-21): the old inventory's districts were old names, not real."""
        self.assertEqual({r[7] for r in V86["BlockSensors"][1:]}, {None})

    def test_the_main_radio_and_dcc_nodes_keep_their_ids(self):
        nodes = {r[2]: r for r in V86["Nodes"][1:]}
        self.assertEqual((nodes[0][0], nodes[0][4]), ("M1", "Main"))
        self.assertEqual((nodes[5][0], nodes[5][1], nodes[5][4]), ("D5", "D1", "DCC"))
        self.assertEqual((nodes[1][1], nodes[11][4]), ("C1", "Client"))

    def test_a_row_with_a_node_and_no_port_stops(self):
        row = dict(next(x for x in MAP if x["layer"] == "fb" and x["node"]), comment="")
        with self.assertRaisesRegex(WI.FactsError, "is on node .* but its wiring '' gives no port"):
            WI.gather([row], WI.read_node_rows())

    def test_a_device_on_an_unlisted_node_stops(self):
        row = dict(next(x for x in MAP if x["layer"] == "turnout" and x["node"] and x["system_name"].startswith("M2T")),
                   node="77")
        with self.assertRaisesRegex(SystemExit, "node 77 is in devices.csv but not in lcos_nodes.csv"):
            WI.gather([row], WI.read_node_rows())


if __name__ == "__main__":
    unittest.main()
