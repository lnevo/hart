"""Scripts moved onto hartlib read tables.xml the same way they did with ElementTree."""

from __future__ import annotations

import contextlib
import csv
import io
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
sys.path.insert(0, str(ROOT / "cats/scripts"))

import cats_turnout_io as tio  # noqa: E402
import digicon_lib as le  # noqa: E402


class LookupsMatchOldLoops(unittest.TestCase):
    """The old ElementTree loops, copied from before the move, against the hartlib versions."""

    def test_turnouts_match_old_loop(self):
        by_user: dict[str, str] = {}
        for t in ET.parse(TABLES).getroot().iter("turnout"):
            sn = (t.findtext("systemName") or t.get("systemName") or "").strip()
            un = (t.findtext("userName") or "").strip()
            if sn.startswith("M2T") and un:
                by_user[un] = sn[3:]
                by_user[sn] = sn[3:]
        want: dict[str, tuple[str, str]] = {}
        with tio.TURNOUT_CSV.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ident = row["layout_ident"].strip()
                key = row["turnout_user_or_system"].strip()
                addr = by_user.get(key)
                if not addr and key.startswith("M2T"):
                    addr = key[3:]
                if not addr:
                    continue
                uname = key
                for u, a in by_user.items():
                    if a == addr and u.startswith("Switch"):
                        uname = u
                        break
                want[ident] = (addr, uname)
        self.assertTrue(want)
        with contextlib.redirect_stderr(io.StringIO()):
            got = tio.load_turnouts()
        self.assertEqual(got, want)

    def test_occupancy_matches_old_loop(self):
        root = ET.parse(TABLES).getroot()
        addr: dict[str, str] = {}
        for s in root.iter("sensor"):
            sn = s.get("systemName") or s.findtext("systemName") or ""
            un = (s.findtext("userName") or "").strip()
            if sn.startswith("M2S") and un:
                addr[un] = sn[3:]
        want: dict[str, tuple[str, str]] = {}
        for lb in root.iter("layoutblock"):
            un = (lb.findtext("userName") or "").strip()
            occ = (lb.get("occupancysensor") or "").strip()
            if un and occ and occ in addr:
                want[un] = (addr[occ], occ)
        with le.OCC_CSV.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                name = row["block_user_name"].strip()
                sens = row["occupancy_sensor_user_name"].strip()
                if name not in want and sens in addr:
                    want[name] = (addr[sens], sens)
        self.assertTrue(want)
        self.assertEqual(le.load_occupancy(), want)


if __name__ == "__main__":
    unittest.main()
