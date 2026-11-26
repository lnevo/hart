"""launch_cats.sh: both launch paths pass the same cats.csh options; an unknown CATS_LAUNCH_VIA is refused.

Runs the script against a stub JMRI install, a stub java and stub pgrep/osascript on PATH, so nothing real starts.
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "cats/scripts/launch_cats.sh"


def _stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)


class LaunchCats(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)  # pwd in the script prints this unresolved
        self.record = self.tmp / "record.txt"
        self.jmri = self.tmp / "JMRI"
        (self.jmri / "cats.jar").parent.mkdir(parents=True)
        (self.jmri / "cats.jar").write_bytes(b"")
        _stub(self.jmri / "cats.csh", f'printf "%s\\n" "$@" > "{self.record}"')
        _stub(self.tmp / "java/bin/java", 'echo "stub java"')
        bin_dir = self.tmp / "bin"
        _stub(bin_dir / "pgrep", "exit 1")
        _stub(bin_dir / "osascript", f'printf "%s\\n" "$2" > "{self.record}"')
        self.panel = self.tmp / "panel.xml"
        self.panel.write_text("<panel/>", encoding="utf-8")
        self.env = {
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(self.tmp / "home"),
            "JMRI_HOME": str(self.jmri),
            "JAVA_HOME": str(self.tmp / "java"),
            "CATS_LAUNCH_LOG": "",
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, via: str) -> subprocess.CompletedProcess[str]:
        env = dict(self.env, CATS_LAUNCH_VIA=via)
        return subprocess.run(["bash", str(SCRIPT), str(self.panel)], env=env,
                              capture_output=True, text=True, timeout=30)

    def test_direct_passes_the_cats_folder(self) -> None:
        proc = self._run("direct")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        args = self.record.read_text(encoding="utf-8").splitlines()
        folder = f"-Dcats.folder={self.env['HOME']}/JMRI_UserFiles/cats/panels"
        self.assertEqual(args, [folder, "--profile=My_JMRI_Railroad.3ef75bfd", str(self.panel)])

    def test_terminal_passes_the_cats_folder(self) -> None:
        proc = self._run("terminal")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        script = self.record.read_text(encoding="utf-8")
        self.assertIn(f"./cats.csh -Dcats.folder={self.env['HOME']}/JMRI_UserFiles/cats/panels --profile=", script)

    def test_an_empty_log_setting_writes_no_log(self) -> None:
        proc = self._run("direct")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Logging stdout+stderr", proc.stdout)

    def test_auto_is_direct(self) -> None:
        self.assertEqual(self._run("auto").returncode, 0)
        self.assertTrue(self.record.read_text(encoding="utf-8").startswith("-Dcats.folder="))

    def test_unknown_via_is_refused(self) -> None:
        proc = self._run("bogus")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Unknown CATS_LAUNCH_VIA=bogus", proc.stderr)
        self.assertFalse(self.record.exists())


if __name__ == "__main__":
    unittest.main()
