"""export_track_lengths: the document is rendered from hartlib.block_lengths (the plan blocks, the measured rows and
the operating length JMRI holds), each row's note included, and importing the script writes nothing (naming-layers
step 13, ADR-039 lane L8)."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
