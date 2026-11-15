"""check_ai_speak flags filler phrasing in study text and passes plain rule text."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("check_ai_speak", ROOT / "tools/audit/check_ai_speak.py")
cas = importlib.util.module_from_spec(spec)
sys.modules["check_ai_speak"] = cas
spec.loader.exec_module(cas)


class AiSpeakTest(unittest.TestCase):
    def test_flags_the_known_phrasings(self):
        for line in (
            "A schedule is one train's line in it. People mix the two up; the exam won't.",
            "The terms are often confused.",
            "Most TT&TO questions turn on a definition, so learn these exactly.",
            "<p>Picture eastbound No 7 due to leave Cedar at 9:40.</p>",
            "Think of the motion: a swing across the track stops you.",
            "the log is only as good as my notes.",
            "A good place to start reading is the wiki home page.",
            "The rule also works the other way.",
            "a clear next step, so a spare evening can go to it.",
            "That stops crews waiting forever on a train.",
            "This guide explains the ideas; the cards and tests check them.",
        ):
            with self.subTest(line=line):
                self.assertTrue(cas.find(line), line)

    def test_passes_rule_text(self):
        for line in (
            "Extra trains are inferior to regular trains.",
            "The time-table is the whole book: the authority for regular trains plus special instructions.",
            "Until the OK time is on the form, the warrant is just paper.",
            "Some signals differ between the two codes:",
            "Example: eastbound No 7 (first class) due to leave Cedar at 9:40.",
        ):
            with self.subTest(line=line):
                self.assertEqual(cas.find(line), [])

    def test_ignores_css_and_keeps_line_numbers(self):
        text = "<style>\n.robust{}\n</style>\nThe terms are often confused.\n"
        self.assertEqual([n for n, _, _ in cas.find(text)], [4])

    def test_sees_through_tags_entities_curly_quotes_and_wraps(self):
        for text in (
            "The terms are often <i>confused</i>.",
            "People <b>mix</b> the two up.",
            "the exam won\u2019t",
            "the exam won&rsquo;t",
            "the terms are often\n        confused.",
            'C("def","Meet","Picture a westbound extra at Dale.");',
            "        Picture a westbound extra.",
        ):
            with self.subTest(text=text):
                self.assertTrue(cas.find(text), text)

    def test_railroad_words_pass(self):
        for line in (
            "Most branch lines ran mixed trains.",
            "The test does not apply to extras.",
        ):
            with self.subTest(line=line):
                self.assertEqual(cas.find(line), [])

    def test_default_covers_article_pages(self):
        for g in cas.DEFAULT_GLOBS:
            with self.subTest(glob=g):
                self.assertTrue(any(ROOT.glob(g)), g)

    def test_skips_script_and_comments(self):
        self.assertEqual(cas.find("<script>// essentially robust</script><!-- the key is -->ok"), [])

    def test_missing_default_glob_fails(self):
        old = cas.DEFAULT_GLOBS
        cas.DEFAULT_GLOBS = old + ("www/no-such-dir/*.html",)
        try:
            self.assertEqual(cas.main([]), 2)
        finally:
            cas.DEFAULT_GLOBS = old

    def test_wrapped_hit_reports_its_first_line(self):
        self.assertEqual([n for n, _, _ in cas.find("a\nThe terms are often\nconfused.")], [2])


if __name__ == "__main__":
    unittest.main()
