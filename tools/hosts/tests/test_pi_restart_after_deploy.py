"""PanelPro quit for a deploy comes back after the Pi deploy; one the owner closed does not."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOSTS = ROOT / "tools/hosts"
MARKER = '"$HOME/.hart_panelpro_quit_for_deploy"'


def text(name: str) -> str:
    return (HOSTS / name).read_text(encoding="utf-8")


class PiRestartAfterDeployTest(unittest.TestCase):
    def test_quit_leaves_the_marker_only_when_it_quit_panelpro(self) -> None:
        src = text("pi_quit_panelpro.sh")
        branch = re.search(r"\n  0\) (.*?);;", src, re.S).group(1)
        self.assertIn(f"date -Is > {MARKER}", branch)
        self.assertEqual(1, src.count(".hart_panelpro_quit_for_deploy\""))
        # "not running" exits before the quit, so it never writes the marker
        not_running = src.index("nothing to quit")
        self.assertLess(not_running, src.index(f"> {MARKER}"))

    def test_start_clears_the_marker(self) -> None:
        self.assertIn(f"rm -f {MARKER}", text("pi_start_panelpro.sh"))

    def test_deploy_restarts_only_after_a_real_pi_deploy_with_the_marker(self) -> None:
        src = text("sync_hart_package.sh")
        done = src.index('echo "Pi deploy done."')
        block = src[done: src.index('if [[ "$DO_WIN" -eq 1 ]]; then', done)]
        self.assertIn('"$DRY_RUN" -eq 0', block)
        self.assertIn('HART_PI_RESTART:-1', block)
        self.assertIn("test -f \"$HOME/.hart_panelpro_quit_for_deploy\"", block)
        self.assertIn("pi_start_panelpro.sh", block)


if __name__ == "__main__":
    unittest.main()
