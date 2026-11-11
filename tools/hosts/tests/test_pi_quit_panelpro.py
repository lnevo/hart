"""pi_quit_panelpro.sh answers only JMRI's store-on-quit prompt, and only with No."""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/hosts/pi_quit_panelpro.sh"
# The label JMRI 5.16 shows (configurexml/swing/Bundle.properties StoreAndCompareRequest).
STORE_PROMPT = "Table and/or panel changes have been made since the last store"


def jython() -> str:
    return subprocess.run(
        ["bash", str(SCRIPT), "--print"], check=True, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HART_PI_SSH": "example.invalid"},
    ).stdout


class PiQuitPanelProTest(unittest.TestCase):
    def test_print_needs_no_ssh(self) -> None:
        self.assertIn("Apps.handleQuit()", jython())

    def test_clicks_only_no_on_the_store_prompt(self) -> None:
        src = jython()
        self.assertIn('STORE_PROMPT = "%s"' % STORE_PROMPT, src)
        self.assertIn('unicode(b.getText()) == "No"', src)
        self.assertEqual(src.count("doClick"), 1)
        click = src.index("_Click(no[0])")
        self.assertLess(src.index("if STORE_PROMPT in text"), click)
        self.assertNotRegex(src, r'== "(Yes|Cancel)"')

    def test_never_stores_or_publishes(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for banned in ("storeAll", "StoreXml", "ConfigureManager", "mosquitto_pub", "track/cmd", "publish("):
            self.assertNotIn(banned, text, banned)

    def test_matches_the_start_script_profile(self) -> None:
        start = (ROOT / "tools/hosts/pi_start_panelpro.sh").read_text(encoding="utf-8")
        profile = re.search(r'PROFILE="([^"]+)"', start).group(1)
        self.assertIn('PROFILE="%s"' % profile, SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
