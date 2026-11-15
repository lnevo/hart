"""add_main_upper_levels.py: v86 is v85 with the old upper-deck plan replaced by the device map's nodes."""
from __future__ import annotations

import csv
import importlib.util
import re
import unittest
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("add_main_upper_levels",
                                              ROOT / "docs/wiring/scripts/add_main_upper_levels.py")
AM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AM)


def sheets(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    return {ws.title: [r for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]
            for ws in wb.worksheets}


V85, V86 = sheets(AM.SRC), sheets(AM.OUT)
MAP = list(csv.DictReader(open(AM.DEVICE_MAP, newline="", encoding="utf-8")))


class Inventory(unittest.TestCase):
    def test_v86_is_current(self):
        self.assertEqual(AM.main(["--check"]), 0)

    def test_old_upper_deck_is_gone(self):
        self.assertFalse([r for r in V86["TurnoutSummary"] if AM.OLD_SWITCH.match(str(r[0] or ""))])
        for sheet in ("DNOU8", "DNIN8"):
            rows = [r for r in V86[sheet][1:] if r[1] in AM.OLD_UPPER]
            self.assertTrue(all(r[4] is None or not re.search(r"Switch (6|7|8|9)\d\b|\b(NIL|CB|BW|PTT)\b", str(r[4]))
                                for r in rows), sheet)
        c11 = {r[0]: r for r in V86["DNOU8"] if r[1] == "C11"}
        self.assertTrue(all(c11[f"C11-OU1-{p}"][4] is None for p in range(1, 7)))
        self.assertEqual([r for r in V85["BlockSensors"] if r[1] == "C11"],      # the helix is still there
                         [r for r in V86["BlockSensors"] if r[1] == "C11"])

    def test_staging_rows_unchanged(self):
        staging = {"C1", "C2", "C3", "C4", "C12", "C13"}
        for sheet, col in (("DNOU8", 1), ("DNIN8", 1), ("BlockSensors", 1), ("Nodes", 0)):
            old = [r for r in V85[sheet] if r[col] in staging]
            new = [r for r in V86[sheet] if r[col] in staging]
            self.assertEqual(old, new, sheet)
        self.assertEqual(V85["DigiconSignals"], V86["DigiconSignals"])

    def test_every_device_map_port_is_in_the_workbook(self):
        out = {r[0]: r for r in V86["DNOU8"][1:]}
        inp = {r[0]: r for r in V86["DNIN8"][1:]}
        blocks = {r[8].split(" / ")[1]: r for r in V86["BlockSensors"][1:] if r[8] and " / M2S" in r[8]}
        for x in MAP:
            if not x["node"] or x["system_name"].startswith("MTT"):
                continue
            node = f"C{x['node']}"
            m = AM.PORT.search(x["comment"])
            if x["layer"] == "turnout":
                for pin, nr in zip(m.group(3).split(","), "NR"):
                    self.assertEqual(out[f"{node}-OU{m.group(2)}-{pin}"][4], f"{x['user_name']} {nr}")
            elif x["layer"] == "head":
                for pin, lamp in zip(m.group(3).split(","), "RYG"):
                    self.assertEqual(out[f"{node}-OU{m.group(2)}-{pin}"][4], f"{x['user_name']} {lamp}")
            elif x["layer"] == "fb":
                self.assertEqual(inp[f"{node}-IN{m.group(2)}-{m.group(3)}"][4],
                                 x["user_name"].removeprefix("FB ") + " FB")
            elif x["layer"] == "occupancy":
                k = int(AM.NODE_K.match(x["comment"]).group(3)) - 1
                row = blocks[x["system_name"]]
                self.assertEqual(row[0], f"{node}-B{k // 2 + 1}-{k % 2 + 1}")

    def test_detector_nodes_keep_the_calibration_pin(self):
        detectors = {r[1] for r in V86["BlockSensors"][1:]}
        for n in {f"C{x['node']}" for x in MAP if x["layer"] == "occupancy"}:
            self.assertIn(n, detectors)
            self.assertTrue(any(r[1] == n and r[3] == 8 and r[4] == "Block sensor calibration"
                                for r in V86["DNOU8"]), n)


if __name__ == "__main__":
    unittest.main()
