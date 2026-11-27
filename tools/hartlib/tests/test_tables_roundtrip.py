"""hartlib.tables_normal and hartlib.tables_roundtrip: a Store's envelope and block paths taken out, and the round
trip's command line (python3 -m hartlib.tables_roundtrip, run by tools/hosts/run_panelpro_roundtrip.sh) and its exit
codes."""
from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import paths, tables, tables_normal as tn, tables_roundtrip as rt  # noqa: E402
from hartlib.tables_sections import finish  # noqa: E402
from xml_need import need  # noqa: E402


def store_of(data: bytes) -> bytes:
    """A Store as JMRI writes one: file history, the "Written by" comment, a clock time, derived block paths."""
    doc = tables.loads(data)
    need(doc.root, "timebase").set("time", "Fri Nov 20 17:36:00 EST 2026")
    for b in tables.blocks(doc.root):
        ET.SubElement(b, "path", block="IB1")
    ET.SubElement(doc.root, "filehistory")
    doc.root.append(ET.Comment("Written by JMRI"))
    finish(doc.root)
    return doc.tobytes()


class Normal(unittest.TestCase):
    def test_a_store_s_additions_come_out_and_twice_changes_nothing(self) -> None:
        doc = tables.loads(store_of(paths.REPO_TABLES_XML.read_bytes()))
        self.assertEqual(["filehistory", "the 'Written by' comment", "timebase@time"], tn.envelope_items(doc.root))
        tn.normalise_store(doc.root)
        self.assertEqual([], tn.envelope_items(doc.root))
        self.assertEqual([], [p for b in tables.blocks(doc.root) for p in b.findall("path")])
        once = doc.tobytes()
        tn.normalise_store(doc.root)
        self.assertEqual(once, doc.tobytes())


class CommandLine(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.store = self.tmp / "store.xml"
        self.store.write_bytes(store_of(paths.REPO_TABLES_XML.read_bytes()))
        self.counts = self.tmp / "paths.tsv"

    def run_main(self) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rt.main(["roundtrip", "--store", str(self.store), "--paths", str(self.counts)])
        return code, out.getvalue(), err.getvalue()

    def test_a_staging_block_with_no_path_fails_with_1(self) -> None:
        self.counts.write_text("IB1\tOS Switch 13\t3\n", encoding="utf-8")
        code, out, _err = self.run_main()
        self.assertEqual(1, code)
        self.assertIn("FAIL: staging blocks with no derived path", out)

    def test_a_bad_counts_file_stops_with_2_and_its_line(self) -> None:
        self.counts.write_text("IB1 broken\n", encoding="utf-8")
        code, out, err = self.run_main()
        self.assertEqual((2, ""), (code, out))
        self.assertRegex(err, r"^tables_roundtrip: .*paths.tsv: line 1 is not system name")

    def test_a_missing_store_fails_naming_it(self) -> None:
        self.counts.write_text("", encoding="utf-8")
        self.store.unlink()
        code, out, _err = self.run_main()
        self.assertEqual(1, code)
        self.assertIn("cannot read", out)


if __name__ == "__main__":
    unittest.main()
