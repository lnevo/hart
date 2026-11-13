"""Website device data must name masts and heads as tables.xml does.

www/review-data/hart_devices_review.json is kept by hand and feeds
www/scripts/build_layout_index.py. It listed the dwarf masts as
AAR-1946:SL-1-low long after tables.xml moved them to basic:one-low.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

ROOT = paths.REPO_ROOT
DEVICES = ROOT / "www/review-data/hart_devices_review.json"
TABLES = paths.TABLES_XML

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
