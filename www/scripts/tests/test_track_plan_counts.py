"""The switch-part counts the track plan article states match the turnouts drawn in its own figures."""
import re
import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parents[2] / "build" / "track-plan.html"


class TrackPlanCounts(unittest.TestCase):
    def test_stated_counts_match_drawing(self):
        html = PAGE.read_text(encoding="utf-8")
        table = re.search(r"<thead><tr><th>Level</th>.*?</tbody>", html, re.S).group(0)
        rows = re.findall(r'<tr><td>(\w+)</td><td class="n">[^<]*</td><td class="n">(\d+)</td>', table)
        stated = {name: int(count) for name, count in rows}
        self.assertEqual(sorted(stated), ["Main", "Staging", "Upper"])
        for level, count in stated.items():
            sec = re.search(r'<section id="%s">(.*?)</section>' % level.lower(), html, re.S).group(1)
            drawn = len(re.findall(r'<text class="tl"', sec))   # one label per switch part
            self.assertEqual(count, drawn, level + " table count vs drawn switch parts")
            self.assertIn("%d switch parts" % drawn, sec)


if __name__ == "__main__":
    unittest.main()
