"""Extra East answer key: answers.html is current with run.html, every question is read, and the game and the
study deck use the same section names. Runs build_exam_answers.js with node; skipped when node is missing."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

WWW = Path(__file__).resolve().parents[2]
SCRIPT = WWW / "scripts" / "build_exam_answers.js"
RUN = WWW / "exam" / "run.html"
INDEX = WWW / "exam" / "index.html"


def node(code):
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise AssertionError(r.stdout + r.stderr)
    return r.stdout


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ExamAnswers(unittest.TestCase):
    def test_answers_page_is_current(self):
        r = subprocess.run(["node", str(SCRIPT), "--check"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_question_read_with_answers(self):
        out = node(
            f"const m=require({json.dumps(str(SCRIPT))});"
            f"const src=require('fs').readFileSync({json.dumps(str(RUN))},'utf8');"
            "console.log(JSON.stringify(m.extract(src)))"
        )
        qs = json.loads(out)
        calls = len(re.findall(r"\bask\(\{", RUN.read_text()))
        self.assertEqual(len(qs), calls)
        for q in qs:
            self.assertTrue(q["right"] and q["wrong"] and q["why"], q["title"])
            # Values filled in at play time must read as a friendly name, never a raw stub.
            for field in (q["title"], q["body"], q["right"], *(w["t"] for w in q["wrong"])):
                self.assertNotRegex(field, r"\[\w+\.[\w.\[\]]*\]|NaN|\[object", f"run.html line {q['line']}")

    def test_bad_question_stops_the_build(self):
        with self.assertRaisesRegex(AssertionError, "no why"):
            node(
                f"const m=require({json.dumps(str(SCRIPT))});"
                "m.extract('const ROAD_TTO=[];const STN_TTO=[];const ROAD_TWC=[];"
                "ask({sec:\"def\",title:\"t\",body:\"b\",right:\"r\",wrong:[[\"w\"]]})')"
            )


class SectionNames(unittest.TestCase):
    def test_guide_game_and_cards_share_sections(self):
        index = INDEX.read_text()
        cards = re.search(r"const SECTIONS=(\{[^}]*\})", index).group(1)
        game = re.search(r"const SEC=(\{[^}]*\})", RUN.read_text()).group(1)
        self.assertEqual(cards, game, "run.html SEC must match the deck's SECTIONS")
        names = dict(re.findall(r'(\w+):"([^"]+)"', cards))
        guide = re.findall(r'<article id="learn-(\w+)" data-sec="\1" data-short="([^"]+)">\s*<h3>\d+\. ([^<]+)</h3>', index)
        self.assertEqual([k for k, _, _ in guide], list(names), "study guide sections follow the card order")
        for k, short, h3 in guide:
            want = names[k].replace("&", "&amp;")
            self.assertEqual((short, h3), (want, want), k)

    def test_guide_notes_link_the_answer_key(self):
        notes = INDEX.read_text().split('id="view-notes"', 1)[1].split("</section>", 1)[0]
        self.assertIn('href="answers.html"', notes)


if __name__ == "__main__":
    unittest.main()
