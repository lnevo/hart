"""status_counts: the STATUS.md Counts line is generated from tables.xml and traininfo."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("status_counts", ROOT / "tools/ops/status_counts.py")
sc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sc)

TABLES = """<layout-config>
<signalmasts><signalmast/><signalmast/><virtualsignalmast/></signalmasts>
<sections><section/></sections>
<transits><transit/><transit/></transits>
<signalmastlogics><signalmastlogic><destinationMast/><destinationMast/></signalmastlogic></signalmastlogics>
<entryexitpairs><layoutPanel><source><destination/><destination/></source></layoutPanel></entryexitpairs>
</layout-config>"""


class StatusCounts(unittest.TestCase):
    def test_counts_and_line(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "t.xml").write_text(TABLES)
            (d / "ti").mkdir()
            for n in "ab":
                (d / "ti" / n).write_text("")
            c = sc.counts(d / "t.xml", d / "ti")
        self.assertEqual(c, {"masts": 3, "real": 2, "virtual": 1, "sections": 1, "transits": 2,
                             "nx": 2, "sml": 1, "dest": 2, "traininfo": 2})
        self.assertEqual(sc.line(c), "- **Counts:** 3 masts (2 real, 1 virtual), 1 sections, 2 transits, "
                         "2 NX pairs, 1 SML sources with 2 destinations, 2 traininfo files.")

    def test_rewrite_touches_only_between_markers(self):
        text = f"a\n{sc.START}\nold\n{sc.END}\nb\n"
        self.assertEqual(sc.rewrite(text, "new"), f"a\n{sc.START}\nnew\n{sc.END}\nb\n")

    def test_repo_status_is_current(self):
        text = sc.STATUS.read_text(encoding="utf-8")
        self.assertEqual(sc.rewrite(text, sc.line(sc.counts())), text)


if __name__ == "__main__":
    unittest.main()
