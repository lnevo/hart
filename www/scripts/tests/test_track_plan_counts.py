"""The turnout counts the track plan article states match the turnouts drawn in its own figures."""
import re
import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parents[2] / "build" / "track-plan.html"


class TrackPlanCounts(unittest.TestCase):
    def test_stated_turnouts_match_drawing(self):
        html = PAGE.read_text(encoding="utf-8")
        intro = re.search(r"main level has (\d+) turnouts.*?upper level (\d+) turnouts", html).groups()
        for level, stated in zip(("main", "upper"), intro):
            sec = re.search(r'<section id="%s">(.*?)</section>' % level, html, re.S).group(1)
            drawn = len(re.findall(r'<text class="tl"', sec))   # one label per turnout or crossover
            self.assertEqual(int(stated), drawn, level + " intro count vs drawn turnouts")
            body = re.search(r"<p>(\d+) turnouts and", sec).group(1)
            self.assertEqual(int(body), drawn, level + " section count vs drawn turnouts")


if __name__ == "__main__":
    unittest.main()
