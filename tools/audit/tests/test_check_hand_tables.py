"""tools/audit/check_hand_tables.py, run on a small checkout: a new table of railroad names fails, a table of code
words passes, a listed table may not grow, a row for a table gone fails and --update drops it, and the real repo
passes."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("check_hand_tables", ROOT / "tools/audit/check_hand_tables.py")
assert SPEC is not None and SPEC.loader is not None
CHT = importlib.util.module_from_spec(SPEC)
sys.modules["check_hand_tables"] = CHT
SPEC.loader.exec_module(CHT)

ENTITIES = "kind,key,master\nstation,station_id,data/stations.csv\nnot a csv,id,data/notes.json\n"
STATIONS = "station_id,station,notes\nsouth_yard,South Yard,\neast_end,East End,\nbarn,Barn,two words\n"
HEADER = "file,table,entries,status,reason\n"
NAMES_PY = 'STOPS = {"South Yard": 1, "East End": 2, "Barn": 3, "west": 4}\n'
WORDS_PY = 'COLUMNS = ("id", "name", "level", "notes", "area", "cp", "role", "node")\n'
TEXT_PY = 'HELP = ["one long line of words", "two long lines of words", "three", "four", "five", "six", "7", "8"]\n'


class Checkout(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.write("docs/data/entities.csv", ENTITIES)
        self.write("data/stations.csv", STATIONS)
        self.write("tools/audit/hand_tables.csv", HEADER)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_check(self, *args: str) -> tuple[int, str]:
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = CHT.main(list(args), root=self.root)
        return code, out.getvalue()

    def test_a_new_table_of_railroad_names_fails(self):
        self.write("tools/stops.py", NAMES_PY)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("tools/stops.py:1: STOPS is a railroad table (3 railroad names", out)

    def test_code_words_pass_and_sentences_need_a_row(self):
        self.write("tools/cols.py", WORDS_PY)
        self.assertEqual(self.run_check()[0], 0)
        self.write("tools/help.py", TEXT_PY)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("HELP is an unclear table (holds sentences", out)

    def test_a_listed_table_passes_until_it_grows(self):
        self.write("tools/stops.py", NAMES_PY)
        self.write("tools/audit/hand_tables.csv", HEADER + "tools/stops.py,STOPS,4,move,stations\n")
        self.assertEqual(self.run_check()[0], 0)
        self.write("tools/stops.py", NAMES_PY.replace('"west": 4', '"west": 4, "north": 5'))
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("STOPS has 5 entries, more than its 4", out)

    def test_a_row_for_a_table_gone_fails_and_update_drops_it(self):
        self.write("tools/stops.py", NAMES_PY)
        self.write("tools/audit/hand_tables.csv",
                   HEADER + "tools/stops.py,STOPS,9,move,stations\ntools/old.py,OLD,5,keep,gone\n")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("tools/old.py OLD is no longer found", out)
        self.assertEqual(self.run_check("--update")[0], 0)
        self.assertEqual((self.root / "tools/audit/hand_tables.csv").read_text(),
                         HEADER + "tools/stops.py,STOPS,4,move,stations\n")
        self.assertEqual(self.run_check()[0], 0)

    def test_javascript_tables_and_tests_and_archive(self):
        self.write("www/play/game.js", 'const STN = [\n  "South Yard", // a comment, with commas\n  "East End",'
                                       ' `Barn`, "x", "y", "z", 1, 2];\nfunction f() { return {a: 1}; }\n')
        self.write("archive/old.py", NAMES_PY)
        self.write("tools/tests/test_x.py", NAMES_PY)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("www/play/game.js:1: STN is a railroad table", out)
        self.assertNotIn("archive/", out)
        self.assertNotIn("tests/", out)

    def test_a_bad_row_stops_with_exit_2(self):
        self.write("tools/audit/hand_tables.csv", HEADER + "tools/x.py,X,4,maybe,why\n")
        code, out = self.run_check()
        self.assertEqual(code, 2)
        self.assertIn("hand_tables.csv:2: status 'maybe' is not one of move, unreviewed, keep", out)


class Repo(unittest.TestCase):
    def test_the_repo_passes(self):
        done = subprocess.run([sys.executable, str(ROOT / "tools/audit/check_hand_tables.py")], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
