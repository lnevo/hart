"""Every script that checks whether JMRI is open must recognise each JMRI 5 program.

JMRI 5 runs DecoderPro as apps.gui3.dp3.DecoderPro3, which the older apps.DecoderPro
pattern misses, so a script would think JMRI was closed while DecoderPro held the tables.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAIN_CLASSES = ("apps.PanelPro.PanelPro", "apps.gui3.dp3.DecoderPro3", "cats.apps.Crandic")
# A process check: a pattern that names the PanelPro class, in a live script (not archive/).
CHECK = re.compile(r"(\[a\]|a)pps\\?\.PanelPro")


def checking_scripts():
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "*.sh", "*.ps1", "*.py"],
                           capture_output=True, text=True, check=True).stdout.split()
    for name in files:
        # main_guard.py splits its pattern over two lines; test_guards covers it.
        if name.startswith(("archive/", "external/", ".claude/hooks/")) or "/tests/" in name:
            continue
        text = (ROOT / name).read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if CHECK.search(line) and re.search(r"pgrep|\$rx\s*=|PROCESS\s*=", line):
                yield name, line


class ProcessPatterns(unittest.TestCase):
    def test_every_check_matches_decoderpro3(self) -> None:
        found = list(checking_scripts())
        self.assertTrue(found, "no process checks found; the search pattern is stale")
        for name, line in found:
            # The pattern is the quoted part of the line; ps1 and Python use the same regex syntax.
            # Single quotes first: pull_ops.sh nests the pattern inside ssh "...".
            quoted = re.findall(r"'([^']*PanelPro[^']*)'", line) or re.findall(r'"([^"]*PanelPro[^"]*)"', line)
            self.assertTrue(quoted, f"{name}: process check without a quoted pattern; add it to this test")
            pattern = quoted[0]
            pattern = pattern.replace("[a]", "a").replace("[c]", "c")
            for cls in MAIN_CLASSES:
                if cls == "cats.apps.Crandic" and "Crandic" not in line:
                    continue  # a JMRI-only check (kill scripts name CATS by jar)
                self.assertRegex(f"java -cp x {cls}", pattern, f"{name}: {cls}")


if __name__ == "__main__":
    unittest.main()
