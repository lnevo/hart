"""Every deploy list ships each of signal_coordinator.py's sibling modules, and none makes one a Start Up item.

The script loads the modules named in its SIBLING_MODULES from the jython folder it runs in, and stops with an
error naming the one that is missing. So each list that installs the script into preference:jython must name
exactly those modules beside it: the Mac (common.sh and ship_mac.sh), the package (stage.sh), the Pi and Windows
apply scripts, and live_paths.txt. A module is imported, not run: no Start Up item or retarget may name one.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import coordinator  # noqa: E402

DEPLOY = ROOT / "tools/hosts/deploy"
PI_APPLY = ROOT / "tools/hosts/pi/apply_hart_package_local.sh"
WIN_APPLY = ROOT / "tools/hosts/windows/apply_hart_package_local.ps1"
LIVE_PATHS = ROOT / "tools/hosts/live_paths.txt"
SIBLINGS = coordinator.sibling_modules()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def block(text: str, opener: str, where: str) -> str:
    """The text of the one list that starts at `opener`, to its closing parenthesis on a line of its own."""
    found = re.findall(re.escape(opener) + r"\n(.*?)^\)", text, re.M | re.S)
    if len(found) != 1:
        raise AssertionError(f"{where}: expected one list opened by {opener!r}, found {len(found)}")
    return found[0]


def named_modules(text: str, sep: str) -> list[str]:
    """The jmri/scripts/*.py module names a list holds (sep: the path separator the list writes), in order."""
    return re.findall(r"jmri" + re.escape(sep) + r"scripts" + re.escape(sep) + r"(\w+)\.py", text)


class CoordinatorShipping(unittest.TestCase):
    def assert_lists_siblings(self, names: list[str], where: str) -> None:
        got = [n for n in names if n != "signal_coordinator"]
        self.assertIn("signal_coordinator", names, f"{where} no longer installs signal_coordinator.py")
        self.assertEqual(sorted(got), sorted(SIBLINGS), f"{where} must list exactly the script's SIBLING_MODULES")

    def test_mac_and_package_lists(self) -> None:
        common = read(DEPLOY / "common.sh")
        startup = named_modules(block(common, "JYTHON_STARTUP_SCRIPTS=(", "common.sh"), "/")
        siblings = named_modules(block(common, "JYTHON_SIBLING_MODULES=(", "common.sh"), "/")
        self.assertEqual(siblings, list(SIBLINGS), "common.sh JYTHON_SIBLING_MODULES, in load order")
        self.assertFalse(set(startup) & set(SIBLINGS), "a sibling module is in JYTHON_STARTUP_SCRIPTS")
        self.assertIn('for f in "${JYTHON_STARTUP_SCRIPTS[@]}" "${JYTHON_SIBLING_MODULES[@]}"; do',
                      read(DEPLOY / "ship_mac.sh"))
        self.assertIn('cp -f "$ROOT/jmri/scripts/signal_coordinator.py" "${JYTHON_SIBLING_MODULES[@]}" '
                      '"$stage/jmri/scripts/"', read(DEPLOY / "stage.sh"))

    def test_pi_list(self) -> None:
        self.assert_lists_siblings(named_modules(block(read(PI_APPLY), "JYTHON=(", "Pi apply"), "/"), "Pi apply")

    def test_windows_list(self) -> None:
        text = block(read(WIN_APPLY), "$jythonSrc = @(", "Windows apply")
        self.assert_lists_siblings(named_modules(text, "\\"), "Windows apply")

    def test_live_paths(self) -> None:
        lines = {ln.strip() for ln in read(LIVE_PATHS).splitlines()}
        missing = [m for m in SIBLINGS if f"jmri/scripts/{m}.py" not in lines]
        self.assertEqual(missing, [], "live_paths.txt")

    def test_no_sibling_is_a_start_up_item(self) -> None:
        texts = {p.name: read(p) for p in [*sorted(DEPLOY.glob("*.sh")), PI_APPLY]}
        for name, text in texts.items():
            for m in SIBLINGS:
                self.assertNotRegex(text, rf"--script\s+(?:\S*/)?{m}\.py", f"{name} makes {m}.py a Start Up item")
        retarget = block(read(WIN_APPLY), "$retargetNames = @(", "Windows apply")
        for m in SIBLINGS:
            self.assertNotIn(f"'{m}.py'", retarget)

    def test_block_reader_refuses_a_missing_or_doubled_list(self) -> None:
        with self.assertRaisesRegex(AssertionError, "found 0"):
            block("X=(\n  a\n)\n", "JYTHON=(", "here")
        with self.assertRaisesRegex(AssertionError, "found 2"):
            block("JYTHON=(\n  a\n)\nJYTHON=(\n  b\n)\n", "JYTHON=(", "here")


if __name__ == "__main__":
    unittest.main()
