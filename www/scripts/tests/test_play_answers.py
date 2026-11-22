"""Extra East: Neville Island answer key: play/answers.html is current with runs.js, and every shift has questions.
Runs build_play_answers.js with node; skipped when node is missing."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

WWW = Path(__file__).resolve().parents[2]
SCRIPT = WWW / "scripts" / "build_play_answers.js"
RUNS = WWW / "play" / "runs.js"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlayAnswers(unittest.TestCase):
    def test_answers_page_is_current(self):
        r = subprocess.run(["node", str(SCRIPT), "--check"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_shift_has_questions_with_one_right_answer(self):
        code = (f"const m=require({json.dumps(str(SCRIPT))});"
                f"const s=m.extract(require('fs').readFileSync({json.dumps(str(RUNS))},'utf8'));"
                "console.log(JSON.stringify(s.map(x=>({id:x.id,n:x.qs.length,bad:x.qs.filter(q=>!q.right||!q.wrong.length||q.wrong.some(w=>w[0]===q.right)).length}))))")
        out = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=60, check=True).stdout)
        self.assertEqual(len(out), 7)
        for shift in out:
            self.assertGreater(shift["n"], 0, shift["id"])
            self.assertEqual(shift["bad"], 0, shift["id"])


if __name__ == "__main__":
    unittest.main()
