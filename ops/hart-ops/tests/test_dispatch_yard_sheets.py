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
# Measured in Word: about 57 characters a line. A rough guard for CI; FitsInCalibri measures.
MAX_ACTION_CHARS = 115

# Calibri ships with Microsoft Office on the Mac; CI has no Calibri, so the measured check skips there.
CALIBRI = Path("/Applications/Microsoft Word.app/Contents/Resources/DFonts")
if not (CALIBRI / "Calibri.ttf").exists():
    CALIBRI = Path("/Applications/Microsoft Excel.app/Contents/Resources/DFonts")
LINE = 1.22  # Calibri's line height, per point of font size


def lines_needed(runs, width_pt):
    """Lines a cell's runs [(text, bold, size_pt)] wrap to at width_pt, word by word, in Calibri."""
    from PIL import ImageFont

    fonts = {}
    def font(bold, size):
        key = (bold, size)
        if key not in fonts:
            fonts[key] = ImageFont.truetype(str(CALIBRI / ("Calibrib.ttf" if bold else "Calibri.ttf")), int(size * 20))
        return fonts[key]
    lines, x = 1, 0.0
    for text, bold, size in runs:
        for word in text.split():
            f = font(bold, size)
            w, space = f.getlength(word) / 20, f.getlength(" ") / 20
            if x and x + space + w > width_pt:
                lines, x = lines + 1, w
            else:
                x = w if not x else x + space + w
    return lines


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


@unittest.skipUnless((CALIBRI / "Calibri.ttf").exists(), "Calibri not installed (Microsoft Office)")
class FitsInCalibri(unittest.TestCase):
    """Exact row heights clip a line that does not fit, so measure each row as Word lays it out."""

    def test_lineup_rows_fit_their_height(self):
        width, room = 3.25 * 72 - 4, 23 - 3.2  # column less 40-twip side margins; row less 32-twip top and bottom
        for _n, train, route, action in ds.LINEUP:
            lines = lines_needed([(route, True, 8), (action, False, 8)], width)
            self.assertLessEqual(lines * 8 * LINE, room, f"{train}: {lines} lines")

    def test_sequence_rows_fit_their_height(self):
        width, room = 2.8 * 72 - 4, 28 - 3.6  # 36-twip top and bottom margins
        for _n, train, action in ym.SEQUENCE:
            lines = lines_needed([(action, False, 9.5)], width)
            self.assertLessEqual(lines * 9.5 * LINE, room, f"{train}: {lines} lines")


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
        self.assertEqual([r["train"] for r in disp["lineup"]], [t for _n, t, _r, _a in ds.LINEUP])
        self.assertIn(ds.RULES, disp["summary"])
        for rule in ym.YARD_RULES:
            self.assertIn(rule, yard["summary"])

    def test_site_colors_name_the_printed_blocks(self):
        # The site lists the colored blocks; Yard storage has no color and no spot, so it is print-only.
        site = {c["label"]: c["train"] for c in json.loads((REPO / "www/data/crew.json").read_text())["colors"]}
        printed = {label: block for label, _f, _t, _d, block in ym.BLOCK_LEGEND if label != "NONE"}
        self.assertEqual(site, printed)


if __name__ == "__main__":
    unittest.main()
