"""tools/audit/layout_facts_xml.py: a missing element or attribute is a named error; a changed file is read again."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "tools/audit"), str(ROOT / "tools/hartlib/src")]
import layout_facts_xml as X  # noqa: E402


class Xml(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.desk = Path(self._tmp.name) / "desk.xml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_need_names_the_element_and_the_attribute(self) -> None:
        el = ET.fromstring('<layoutturnout ident="LT1"/>')
        with self.assertRaisesRegex(X.LayoutFactsError, "ident='LT1'.* has no blockname"):
            X.need(el, "blockname")
        self.assertEqual(X.need(el, "ident"), "LT1")

    def test_a_desk_with_no_trackplan_stops(self) -> None:
        self.desk.write_text("<CATS/>", encoding="utf-8")
        with self.assertRaisesRegex(X.LayoutFactsError, "no TRACKPLAN"):
            X.trackplan(self.desk)

    def test_a_changed_file_is_read_again(self) -> None:
        self.desk.write_text("<CATS><TRACKPLAN A='1'/></CATS>", encoding="utf-8")
        self.assertEqual(X.trackplan(self.desk).get("A"), "1")
        self.desk.write_text("<CATS><TRACKPLAN A='22'/></CATS>", encoding="utf-8")
        st = self.desk.stat()
        os.utime(self.desk, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        self.assertEqual(X.trackplan(self.desk).get("A"), "22")


if __name__ == "__main__":
    unittest.main()
