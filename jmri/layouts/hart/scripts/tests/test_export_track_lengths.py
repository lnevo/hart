"""export_track_lengths: the document is rendered from hartlib.railroad.read_block_lengths, each row's note included,
and importing the script writes nothing (naming-layers step 13)."""
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_track_lengths as m  # noqa: E402  the import runs no main
from hartlib import railroad  # noqa: E402  on the path through the script


class Render(unittest.TestCase):
    def test_the_committed_document_is_what_the_reader_renders(self):
        self.assertEqual(m.DOC.read_text(encoding="utf-8"), m.render(railroad.read_block_lengths()))

    def test_the_note_column_is_the_rows_note(self):
        rows = railroad.read_block_lengths()
        name, b = next(iter(rows.items()))
        rows[name] = replace(b, note="a test note")
        line = next(t for t in m.render(rows).splitlines() if t.startswith(f"| {name} |"))
        self.assertTrue(line.endswith("| a test note |"), line)


if __name__ == "__main__":
    unittest.main()
