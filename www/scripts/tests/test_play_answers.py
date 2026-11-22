"""Extra East: HART Railroad answer key: play/answers.html is current with runs.js and road.js, and every run has questions.
Runs build_play_answers.js with node; skipped when node is missing."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

WWW = Path(__file__).resolve().parents[2]
SCRIPT = WWW / "scripts" / "build_play_answers.js"
RUNS = WWW / "play" / "runs.js"
INDEX = WWW / "play" / "index.html"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlayAnswers(unittest.TestCase):
    def test_answers_page_is_current(self):
        r = subprocess.run(["node", str(SCRIPT), "--check"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_run_has_questions_with_one_right_answer(self):
        code = (f"const m=require({json.dumps(str(SCRIPT))});"
                f"const s=m.extract(require('fs').readFileSync({json.dumps(str(RUNS))},'utf8'));"
                "console.log(JSON.stringify(s.map(x=>({id:x.id,n:x.qs.length,bad:x.qs.filter(q=>!q.right||!q.wrong.length||q.wrong.some(w=>w[0]===q.right)).length}))))")
        out = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=60, check=True).stdout)
        self.assertEqual(len(out), 8)  # seven island shifts and the coal extra
        for shift in out:
            self.assertGreater(shift["n"], 0, shift["id"])
            self.assertEqual(shift["bad"], 0, shift["id"])

    def test_every_run_is_on_the_start_screen_in_its_group(self):
        code = (f"const m=require({json.dumps(str(SCRIPT))});"
                f"const s=m.extract(require('fs').readFileSync({json.dumps(str(RUNS))},'utf8'));"
                "console.log(JSON.stringify(s.map(x=>({id:x.id,group:x.group}))))")
        out = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=60, check=True).stdout)
        html = INDEX.read_text()
        sections = {"island": html.split('id="gIsland"')[1].split("</section>")[0],
                    "chartiers": html.split('id="gChartiers"')[1].split("</section>")[0]}
        for run in out:
            self.assertIn(f'data-run="{run["id"]}"', sections[run["group"]], run["id"])

    def test_covers_matches_the_sections_each_shift_asks(self):
        # extract() sees only questions asked from build() (or listed there with H.key), not from after() or info
        # callbacks; a run that asks a section only from a callback must list that question or this test will miss it.
        code = (f"const m=require({json.dumps(str(SCRIPT))});"
                f"const s=m.extract(require('fs').readFileSync({json.dumps(str(RUNS))},'utf8'));"
                "console.log(JSON.stringify(s.map(x=>({id:x.id,covers:[...(x.def.covers||[])].sort(),asked:[...new Set(x.qs.map(q=>q.sec))].sort()}))))")
        out = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=60, check=True).stdout)
        for shift in out:
            self.assertEqual(shift["covers"], shift["asked"], shift["id"])


if __name__ == "__main__":
    unittest.main()
