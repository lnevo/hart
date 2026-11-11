"""pi_quit_panelpro.sh answers only JMRI's store-on-quit request, and only with No."""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/hosts/pi_quit_panelpro.sh"
JMRI_BUNDLE_REQUEST = (
    "<html>Table and/or panel changes have been made since the last store.<br> "
    "Do you want to <strong>Store ALL tables and panels</strong>?</html>"
)
JMRI_BUNDLE_DENIED = (
    "<html>Table and/or panel changes have been made since the last store but<br> "
    "you don't have permission to store. Do you want to abort the shutdown?</html>"
)


def jython() -> str:
    return subprocess.run(
        ["bash", str(SCRIPT), "--print"], check=True, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HART_PI_SSH": "example.invalid"},
    ).stdout


def store_request(src: str) -> tuple[str, ...]:
    m = re.search(r"STORE_REQUEST = \((.*?)\)\n", src)
    return tuple(re.findall(r'"([^"]+)"', m.group(1)))


class PiQuitPanelProTest(unittest.TestCase):
    def test_print_needs_no_ssh(self) -> None:
        self.assertIn("Apps.handleQuit()", jython())

    def test_matches_the_request_not_the_permission_dialog(self) -> None:
        parts = store_request(jython())
        self.assertTrue(all(p in JMRI_BUNDLE_REQUEST for p in parts))
        self.assertFalse(all(p in JMRI_BUNDLE_DENIED for p in parts))
        self.assertIn('STORE_BUTTONS = ["Cancel", "No", "Yes"]', jython())

    def test_clicks_only_no(self) -> None:
        src = jython()
        self.assertEqual(src.count("doClick"), 1)
        self.assertIn('unicode(b.getText()) == "No"][0].doClick()', src)
        self.assertNotRegex(src, r'== "(Yes|Cancel)"')

    def test_scans_swing_on_the_event_thread(self) -> None:
        src = jython()
        self.assertIn("SwingUtilities.invokeAndWait(_Scan(seen))", src)
        self.assertNotIn("Window.getWindows()", src[src.index('open(LOG, "w")'):])

    def test_jython_waits_as_long_as_the_shell(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        shell = int(re.search(r"^WAIT_S=(\d+)", text, re.M).group(1))
        jy = int(re.search(r"^WAIT_S = (\d+)", jython(), re.M).group(1))
        self.assertLess(jy, shell)
        self.assertGreater(jy, shell - 10)

    def test_remote_checks_are_safe(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        remote = text[text.index("<<'REMOTE'"):]
        # pgrep must not match the shell that runs it.
        self.assertNotRegex(remote, r"pgrep -f \"org")
        self.assertIn('pgrep -f "[o]rg.jmri.profile=$profile"', remote)
        # A ready file left from an earlier PanelPro does not count.
        self.assertIn('stat -c %Y "$READY") < started', remote)
        # An unread quit is never left for the next start.
        self.assertIn('if [[ -e "$CMD" ]]; then rm -f "$CMD"', remote)
        self.assertIn("^OTHER DIALOG", remote)
        self.assertIn("^QUIT FAILED", remote)

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
