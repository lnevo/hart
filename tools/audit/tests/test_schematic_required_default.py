"""check.sh and build_panels.sh fail a schematic step that cannot load the plugin, as CI does (owner, 2026-11-23):
SCHEMATIC_REQUIRED defaults to 1 there, and SCHEMATIC_REQUIRED=0 is the opt-out that lets those steps print SKIPPED."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT = 'export SCHEMATIC_REQUIRED="${SCHEMATIC_REQUIRED:-1}"'


def default_line(script: Path) -> int:
    lines = script.read_text(encoding="utf-8").splitlines()
    return next(i for i, line in enumerate(lines) if line.strip() == DEFAULT)


class SchematicRequiredDefault(unittest.TestCase):
    def test_both_scripts_default_to_required_before_any_step_runs(self) -> None:
        for rel, first_step in (("tools/check.sh", "later "), ("tools/schematic/build_panels.sh", "step ")):
            with self.subTest(script=rel):
                script = ROOT / rel
                lines = script.read_text(encoding="utf-8").splitlines()
                at = default_line(script)
                calls = [i for i, line in enumerate(lines) if line.lstrip().startswith(first_step)]
                self.assertTrue(calls, f"{rel}: no {first_step.strip()} call found; update this test")
                self.assertLess(at, min(calls), f"{rel}: the default must be set before the first step")

    def test_the_default_keeps_a_value_already_set(self) -> None:
        for given, want in ((None, "1"), ("0", "0"), ("1", "1")):
            with self.subTest(given=given):
                env = {"PATH": "/usr/bin:/bin"} | ({"SCHEMATIC_REQUIRED": given} if given is not None else {})
                out = subprocess.run(["bash", "-c", DEFAULT + '; printf %s "$SCHEMATIC_REQUIRED"'], env=env,
                                     capture_output=True, text=True, check=True).stdout
                self.assertEqual(want, out)

    def test_check_sh_names_the_jobs_that_printed_skipped(self) -> None:
        text = (ROOT / "tools/check.sh").read_text(encoding="utf-8")
        self.assertIn("printed SKIPPED and checked only part of their inputs", text)


if __name__ == "__main__":
    unittest.main()
