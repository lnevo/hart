"""DS-01 and YM-01 Rev E: page 1 fits, and the site copy matches the scripts."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from docx import Document

PUB = Path(__file__).resolve().parents[1] / "publications"
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PUB))

import rebuild_dispatcher_train_list as ds  # noqa: E402
import rebuild_yardmaster_sequence as ym  # noqa: E402

# Lineup rows are 23 pt exact: two lines of 8 pt text in the 3.25 in action column.
# Measured in Word: about 57 characters a line.
MAX_ACTION_CHARS = 115


class DispatcherTrainList(unittest.TestCase):
    def test_actions_fit_two_lines(self):
        for _n, train, route, action in ds.LINEUP:
            self.assertLessEqual(len(route) + 1 + len(action), MAX_ACTION_CHARS, train)

    def test_lineup_numbers_run_in_order(self):
        self.assertEqual([n for n, *_ in ds.LINEUP], [str(i) for i in range(1, len(ds.LINEUP) + 1)])

    def test_rebuild_writes_route_bold_and_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = ds.rebuild(Path(tmp) / "ds.docx")
            doc = Document(str(out))
        lineup = doc.tables[0]
        self.assertEqual(len(lineup.rows), 1 + len(ds.LINEUP))
        # cell.text = "" leaves an empty first run; skip it.
        runs = [r for r in lineup.rows[1].cells[2].paragraphs[0].runs if r.text]
        self.assertTrue(runs[0].bold)
        self.assertEqual(runs[0].text.strip(), ds.LINEUP[0][2])
        self.assertIn(ds.RULES, "\n".join(p.text for p in doc.paragraphs))


class YardmasterSequence(unittest.TestCase):
    def test_every_color_has_a_block(self):
        blocks = {label: block for label, _f, _t, _d, block in ym.BLOCK_LEGEND}
        for c in ("YELLOW", "GREEN", "PURPLE", "RED", "PINK"):
            self.assertEqual(blocks[c], "NVL local")
        self.assertEqual(blocks["BLACK"], "CK1")
        self.assertEqual(blocks["NONE"], "Yard storage")

    def test_rebuild_writes_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = ym.rebuild(Path(tmp) / "ym.docx")
            text = "\n".join(p.text for p in Document(str(out)).paragraphs)
        for rule in ym.YARD_RULES:
            self.assertIn(rule, text)


class SiteCopy(unittest.TestCase):
    def test_crew_json_matches_scripts(self):
        jobs = {j["id"]: j for j in json.loads((REPO / "www/data/crew.json").read_text())["jobs"]}
        disp, yard = jobs["dispatcher"], jobs["yardmaster"]
        self.assertEqual(disp["revision"], ds.PUBLICATION["revision"])
        self.assertEqual(yard["revision"], ym.PUBLICATION["revision"])
        self.assertEqual(
            [r["action"] for r in disp["lineup"]],
            [f"{route} {action}" for _n, _t, route, action in ds.LINEUP],
        )
        self.assertIn(ds.RULES, disp["summary"])
        for rule in ym.YARD_RULES:
            self.assertIn(rule, yard["summary"])


if __name__ == "__main__":
    unittest.main()
