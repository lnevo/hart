"""export_track_lengths: the document is rendered from hartlib.block_lengths (the plan blocks, the measured rows and
the operating length JMRI holds), each row's note included, importing the script writes nothing, and --check
reports every disagreement with tables.xml or the document."""
import contextlib
import io
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_track_lengths as m  # noqa: E402  the import runs no main
from hartlib import block_lengths  # noqa: E402  on the path through the script


def render(rows=None):
    rows = block_lengths.plan_blocks() if rows is None else rows
    return m.render(rows, block_lengths.measured_lengths(), block_lengths.operating_lengths())


class Render(unittest.TestCase):
    def test_the_committed_document_is_what_the_reader_renders(self):
        self.assertEqual(m.DOC.read_text(encoding="utf-8"), render())

    def test_the_note_column_is_the_rows_note(self):
        rows = block_lengths.plan_blocks()
        name, b = next(iter(rows.items()))          # Track W-1: a plan block
        rows[name] = replace(b, note="a test note")
        line = next(t for t in render(rows).splitlines() if t.startswith(f"| {name} |"))
        self.assertTrue(line.endswith("| a test note |"), line)

    def test_a_timed_block_shows_its_measured_length_and_jmri_holds_it(self):
        line = next(t for t in render().splitlines() if t.startswith("| Track Main West |"))
        self.assertIn("| 231 | 217.3 | timed | 5519.4 | timed share", line)


class Check(unittest.TestCase):
    def setUp(self):
        self.rows = block_lengths.plan_blocks()
        self.operating = block_lengths.operating_lengths()
        self.text = m.render(self.rows, block_lengths.measured_lengths(), self.operating)
        self.held = {k: v * m.MM for k, v in self.operating.items()}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.doc = Path(tmp.name) / "TRACK_LENGTHS.md"
        self.doc.write_text(self.text, encoding="utf-8")

    def drift(self, held):
        with mock.patch.object(m, "table_lengths", return_value=held), mock.patch.object(m, "DOC", self.doc):
            return m.drift(self.rows, self.operating, self.text)

    def test_all_agree(self):
        self.assertEqual(self.drift(self.held), [])

    def test_a_length_off_by_more_than_the_tolerance(self):
        name = next(iter(self.held))
        self.assertEqual(self.drift({**self.held, name: self.held[name] + 0.9}), [])
        bad = self.drift({**self.held, name: self.held[name] + 1.5})
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0].startswith(f"{name}: operating length"), bad)

    def test_a_block_tables_lacks_and_one_the_csv_lacks(self):
        name = next(iter(self.held))
        held = {k: v for k, v in self.held.items() if k != name} | {"Track Nowhere": 10.0}
        bad = self.drift(held)
        self.assertIn(f"{name}: operating length {self.held[name]:.1f} mm, tables None; run "
                      "python3 tools/schematic/build_tables.py", bad)
        self.assertIn("Track Nowhere: in tables.xml (10.0 mm) but not in CSV", bad)

    def test_a_stale_or_missing_document(self):
        self.doc.write_text(self.text + "x", encoding="utf-8")
        self.assertEqual(self.drift(self.held), ["docs/jmri/TRACK_LENGTHS.md is stale; run the script without --check"])
        self.doc.unlink()
        self.assertEqual(len(self.drift(self.held)), 1)

    def test_a_length_that_is_not_a_number_is_named(self):
        root = m.tables.read(m.TABLES)
        b = next(b for b in m.tables.blocks(root) if b.get("length") and m.tables.user_name(b))
        b.set("length", "long")
        with mock.patch.object(m.tables, "read", return_value=root):
            with self.assertRaisesRegex(m.TableLengthError, f"block {m.tables.user_name(b)} has length 'long'"):
                m.table_lengths()

    def test_check_exits_1_and_prints_the_drift(self):
        out = io.StringIO()
        with mock.patch.object(m, "table_lengths", return_value={}), mock.patch.object(m, "DOC", self.doc), \
                contextlib.redirect_stdout(out):
            self.assertEqual(m.main(["--check"]), 1)
        self.assertIn("tables None", out.getvalue())

    def test_the_committed_files_agree(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(m.main(["--check"]), 0)
        self.assertEqual(out.getvalue(), "track lengths OK\n")


class Arguments(unittest.TestCase):
    def test_unknown_flags_are_refused_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "TRACK_LENGTHS.md"
            for argv in (["--tables"], ["--checks"], ["check"]):
                with self.subTest(argv=argv), mock.patch.object(m, "DOC", doc), \
                        contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
                    m.main(argv)
                self.assertEqual(stop.exception.code, 2)
                self.assertFalse(doc.exists())


if __name__ == "__main__":
    unittest.main()
