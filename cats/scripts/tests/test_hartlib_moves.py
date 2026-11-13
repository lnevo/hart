"""Scripts moved onto hartlib read tables.xml the same way they did with ElementTree."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
sys.path.insert(0, str(ROOT / "cats/scripts"))

import cats_turnout_io as tio  # noqa: E402
import digicon_lib as le  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LookupsMatchOldLoops(unittest.TestCase):
    def test_turnouts_match_root_iter(self):
        by_user: dict[str, str] = {}
        for t in ET.parse(TABLES).getroot().iter("turnout"):
            sn = (t.findtext("systemName") or t.get("systemName") or "").strip()
            un = (t.findtext("userName") or "").strip()
            if sn.startswith("M2T") and un:
                by_user[un] = sn[3:]
                by_user[sn] = sn[3:]
        want = {v for v in by_user.values()}
        got = {addr for addr, _name in tio.load_turnouts().values()}
        self.assertTrue(got <= want and got)

    def test_occupancy_matches_root_iter(self):
        root = ET.parse(TABLES).getroot()
        addr: dict[str, str] = {}
        for s in root.iter("sensor"):
            sn = s.get("systemName") or s.findtext("systemName") or ""
            un = (s.findtext("userName") or "").strip()
            if sn.startswith("M2S") and un:
                addr[un] = sn[3:]
        want = {}
        for lb in root.iter("layoutblock"):
            un = (lb.findtext("userName") or "").strip()
            occ = (lb.get("occupancysensor") or "").strip()
            if un and occ and occ in addr:
                want[un] = (addr[occ], occ)
        got = le.load_occupancy()
        for name, val in want.items():
            self.assertEqual(got[name], val)


class PolishCpLabels(unittest.TestCase):
    def test_second_apply_changes_nothing(self):
        mod = _load("polish_hart_cp_labels", ROOT / "jmri/scripts/polish_hart_cp_labels.py")
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "tables.xml"
            shutil.copy(TABLES, copy)
            n = mod.apply(copy)
            first = copy.read_bytes()
            self.assertEqual(mod.apply(copy), n)
            self.assertEqual(copy.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
