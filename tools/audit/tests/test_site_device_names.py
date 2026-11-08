"""Website device data must name masts and heads as tables.xml does.

www/review-data/hart_devices_review.json is kept by hand and feeds
www/scripts/build_layout_index.py. It listed the dwarf masts as
AAR-1946:SL-1-low long after tables.xml moved them to basic:one-low.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEVICES = ROOT / "www/review-data/hart_devices_review.json"
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"

BEAN_RE = re.compile(
    r"<(?:signalmast|virtualsignalmast|signalhead) [^>]*>\s*"
    r"<systemName>([^<]*)</systemName>\s*<userName>([^<]*)</userName>"
)


class SiteDeviceNamesTest(unittest.TestCase):
    def test_signal_system_names_match_tables(self) -> None:
        live = {user: sys for sys, user in BEAN_RE.findall(TABLES.read_text(encoding="utf-8"))}
        devices = json.loads(DEVICES.read_text(encoding="utf-8"))
        for row in devices:
            if row.get("kind") not in ("Signal mast", "Virtual mast", "Signal head"):
                continue
            with self.subTest(device=row["userName"]):
                self.assertIn(row["userName"], live, "not in tables.xml")
                self.assertEqual(row["systemName"], live[row["userName"]])


if __name__ == "__main__":
    unittest.main()
