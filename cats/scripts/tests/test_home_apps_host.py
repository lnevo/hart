"""The JMRI home page's STS and mimic links: the Pi follows its own host, Windows names the Pi."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOME = (ROOT / "jmri/resources/jmri-web/servlet/home/Home.html").read_text(encoding="utf-8")
WIN = (ROOT / "cats/scripts/windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
MARKER = 'var HART_APPS_HOST = "";'


class AppsHost(unittest.TestCase):
    def test_home_has_one_empty_marker(self):
        self.assertEqual(HOME.count(MARKER), 1)

    def test_windows_fills_the_same_marker(self):
        self.assertIn("$marker = '" + MARKER + "'", WIN)
        self.assertRegex(WIN, r"\$PiHost = '[\w.-]+\.local'")

    def test_links_use_the_host(self):
        self.assertIn('"http://" + host + ":8980/sts/"', HOME)
        self.assertIn('"http://" + host + ":12080/web/mimic/"', HOME)
        self.assertIsNotNone(re.search(r'id="mimic-link" href="/web/mimic/"', HOME))


if __name__ == "__main__":
    unittest.main()
