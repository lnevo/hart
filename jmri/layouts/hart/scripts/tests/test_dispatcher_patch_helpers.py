import unittest
from pathlib import Path


JYTHON_RUNTIME_SCRIPTS = (
    Path(__file__).resolve().parents[1] / "hide_cats_desk_windows.py",
    Path(__file__).resolve().parents[1] / "sync_turnout_buttons.py",
    Path(__file__).resolve().parents[1] / "jmri_cmd_watcher.py",
)


class DispatcherJythonRuntimeGuardTest(unittest.TestCase):
    def test_preference_jython_scripts_do_not_enable_print_function(self):
        for path in JYTHON_RUNTIME_SCRIPTS:
            self.assertTrue(path.is_file(), msg="missing %s" % path.name)
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                self.assertNotEqual(
                    stripped,
                    "from __future__ import print_function",
                    msg=(
                        "%s would leak print_function into JMRI's shared Jython "
                        "engine and break stock DispatcherSystem/Startup.py"
                        % path.name
                    ),
                )


if __name__ == "__main__":
    unittest.main()
