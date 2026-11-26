"""card_template_sheet: the shared sticker-grid helpers that every sheet generator uses for its extra pages."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "card_pipeline"))

from docx import Document  # noqa: E402
from docx.opc.exceptions import PackageNotFoundError  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

import card_template_sheet as cts  # noqa: E402


def fake_sticker_sheet(path: Path) -> Path:
    """A stand-in for the sticker sheet: a 3x3 grid (the real template is not in git)."""
    doc = Document()
    doc.add_table(rows=3, cols=3)
    doc.save(path)
    return path


def page_breaks(tbl) -> int:
    return len(tbl.findall(".//" + qn("w:pageBreakBefore")))


class BlankStickerGrid(unittest.TestCase):
    def test_returns_a_3x3_grid_and_leaves_the_template_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet = fake_sticker_sheet(Path(tmp) / "sheet.docx")
            before = hashlib.sha256(sheet.read_bytes()).hexdigest()
            grid = cts.blank_sticker_grid(sheet)
            self.assertEqual(grid.tag, qn("w:tbl"))
            rows = grid.findall(qn("w:tr"))
            self.assertEqual([len(r.findall(qn("w:tc"))) for r in rows], [3, 3, 3])
            self.assertEqual(hashlib.sha256(sheet.read_bytes()).hexdigest(), before)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["sheet.docx"])

    def test_missing_template_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PackageNotFoundError):
                cts.blank_sticker_grid(Path(tmp) / "absent.docx")


class AppendGrid(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        sheet = fake_sticker_sheet(Path(tmp.name) / "sheet.docx")
        self.grid = cts.blank_sticker_grid(sheet)
        self.doc = Document(str(sheet))
        cts.keep_sticker_grid(self.doc)

    def test_each_page_is_a_new_table_starting_on_a_new_page(self):
        first = cts.append_grid(self.doc, self.grid)
        second = cts.append_grid(self.doc, self.grid)
        self.assertEqual(len(self.doc.tables), 3)
        self.assertIsNot(first._tbl, second._tbl)
        self.assertIsNot(first._tbl, self.grid)
        self.assertEqual(page_breaks(first._tbl), 1)
        self.assertEqual(page_breaks(self.grid), 0)  # the source grid is copied, not changed
        body = self.doc.element.body
        self.assertEqual(body[-1].tag, qn("w:sectPr"))

    def test_page_break_is_set_once(self):
        table = cts.append_grid(self.doc, self.grid)
        cts.set_page_break_before_table(table._tbl)
        self.assertEqual(page_breaks(table._tbl), 1)


if __name__ == "__main__":
    unittest.main()
