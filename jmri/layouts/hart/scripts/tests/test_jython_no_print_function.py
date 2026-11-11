"""No Jython script that runs inside JMRI may turn on print_function.

JMRI shares one Jython engine across scripts and keeps the __future__ compiler flag,
so one `from __future__ import print_function` in a Start Up script makes every later
Python-2 script fail to compile: stock Dispatcher System's Startup.py, and the Stage 1
launcher's own script (seen 2026-11-10: "no viable alternative at input"). See
wiki/DISPATCHER_LAYOUT_HOOPS.md.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SYNC = ROOT / "cats/scripts/sync_hart_package.sh"
FUTURE = re.compile(r"^\s*from\s+__future__\s+import\s+[^#\n]*\bprint_function\b", re.M)

# Run inside PanelPro by the automation launchers rather than installed by the deploy.
LAUNCHED = [
    "jmri/layouts/hart/scripts/run_dispatcher_stage1.py",
    "jmri/layouts/hart/scripts/discover_sml.py",
    "jmri/layouts/hart/scripts/discover_nx.py",
    "jmri/layouts/hart/scripts/dump_sml_criteria.py",
    "jmri/layouts/hart/scripts/repair_dispatcher_traininfo.py",
]


def deployed_scripts() -> list[str]:
    """Every .py the layout deploy installs into preference:jython."""
    text = SYNC.read_text(encoding="utf-8")
    found = re.findall(r"((?:jmri|cats)/[\w/.-]+\.py)", text)
    return sorted({path for path in found if (ROOT / path).is_file()})


class NoPrintFunction(unittest.TestCase):
    def test_deploy_list_is_found(self) -> None:
        scripts = deployed_scripts()
        self.assertIn("jmri/layouts/hart/scripts/sts_car_sync.py", scripts)
        self.assertIn("jmri/scripts/signal_coordinator.py", scripts)

    def test_no_jmri_script_imports_print_function(self) -> None:
        offenders = [path for path in deployed_scripts() + LAUNCHED
                     if FUTURE.search((ROOT / path).read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
