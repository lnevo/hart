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
        for sw in tio.facts.load_switches().values():
            ident, key = sw.le_ident, sw.hardware
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

    def test_each_plant_binds_its_switch(self):
        """Layout Editor turnout -> (M2T address, public name) that wire_digicon.py writes on the desk."""
        with contextlib.redirect_stderr(io.StringIO()) as err:
            got = tio.load_turnouts()
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(got, {
            "TO1": ("411", "Switch 13"), "TO10": ("1310", "Switch 9"), "TO11": ("1309", "Switch 11"),
            "TO111": ("1212", "Switch 23"), "TO113": ("108", "Switch 35"), "TO117": ("1308", "Switch 7"),
            "TOL15": ("309", "Switch 17"), "TOL17": ("310", "Switch 19"), "TOL19": ("311", "Switch 21"),
            "TOL23": ("1213", "Switch 33"), "TOL29": ("110", "Switch 39"), "TOL3": ("408", "Switch 1"),
            "TOL38": ("409", "Switch 3"), "TOL42": ("410", "Switch 5"), "TOL6": ("1211", "Switch 31"),
            "TOR11": ("1208", "Switch 25"), "TOR14": ("308", "Switch 15"), "TOR36": ("109", "Switch 37"),
            "TOR7": ("1210", "Switch 29"), "TOR9": ("1209", "Switch 27"),
        })

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
