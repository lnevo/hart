"""docs/INDEX.md links must survive file names with odd spaces (macOS screenshots use U+202F)."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_docs_index", ROOT / "tools/ops/build_docs_index.py")
INDEX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INDEX)


class DocLinkTest(unittest.TestCase):
    def test_plain_path(self) -> None:
        self.assertEqual(INDEX.doc_link("docs/ctc/SIGNAL_FACING.md"), "ctc/SIGNAL_FACING.md")

    def test_ascii_space(self) -> None:
        self.assertEqual(INDEX.doc_link("docs/ops/STRR Speed Match.pdf"), "ops/STRR%20Speed%20Match.pdf")

    def test_narrow_no_break_space(self) -> None:
        link = INDEX.doc_link("docs/ctc/history/Screenshot 2026-08-19 at 5.44.55\u202fPM.png")
        self.assertEqual(link, "ctc/history/Screenshot%202026-08-19%20at%205.44.55%E2%80%AFPM.png")
        self.assertFalse(any(ch.isspace() for ch in link))


if __name__ == "__main__":
    unittest.main()
