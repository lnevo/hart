"""launch_cats.sh (Mac) and the Pi's copy: both launch paths pass the same cats.csh options, an unknown
CATS_LAUNCH_VIA is refused, and both refuse to start while a JMRI JVM runs, found with hartlib's one pattern.

Runs the scripts against a stub JMRI install, a stub java and stub pgrep/osascript on PATH, so nothing real starts.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "cats/scripts/launch_cats.sh"
PI_SCRIPT = ROOT / "tools/hosts/pi/launch_cats.sh"
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib.tables import _JMRI_PROCESS  # noqa: E402


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
        self.pgrep = self.tmp / "pgrep.txt"
        # pgrep: log its arguments, one per line; FAKE_JMRI=1 means a JMRI JVM runs
        _stub(bin_dir / "pgrep", f'printf "%s\\n" "$@" >> "{self.pgrep}"; [ "${{FAKE_JMRI:-0}}" = 1 ]')
        _stub(bin_dir / "java", 'echo "stub java"')
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

    def _run(self, via: str, script: Path = SCRIPT, **env: str) -> subprocess.CompletedProcess[str]:
        env = dict(self.env, CATS_LAUNCH_VIA=via, **env)
        return subprocess.run(["bash", str(script), str(self.panel)], env=env,
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
        home, jmri, java = self.env["HOME"], self.env["JMRI_HOME"], self.env["JAVA_HOME"]
        cmd = (f"export JAVA_HOME={java}; export ARCH=aarch64; cd {jmri} && exec ./cats.csh "
               f"-Dcats.folder={home}/JMRI_UserFiles/cats/panels --profile=My_JMRI_Railroad.3ef75bfd {self.panel}")
        self.assertEqual(script, f'tell application "Terminal" to do script "{cmd}"\n')

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


    def test_a_running_jmri_stops_both_copies_with_the_one_pattern(self) -> None:
        for script in (SCRIPT, PI_SCRIPT):
            with self.subTest(script=script.name, host=script.parent.name):
                self.pgrep.unlink(missing_ok=True)
                proc = self._run("direct", script, FAKE_JMRI="1")
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertIn("already running", proc.stderr)
                self.assertFalse(self.record.exists(), "cats.csh must not start")
                calls = self.pgrep.read_text(encoding="utf-8").splitlines()
                self.assertEqual(calls[:4], ["-u", calls[1], "-f", _JMRI_PROCESS])
                self.assertEqual(calls[4:], ["-lf", _JMRI_PROCESS])

    def test_the_force_override_starts_cats_anyway(self) -> None:
        proc = self._run("direct", FAKE_JMRI="1", CATS_FORCE_LAUNCH="1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.record.exists())

    def test_the_pi_copy_passes_the_cats_folder_and_logs(self) -> None:
        log = self.tmp / "cats.log"
        proc = self._run("direct", PI_SCRIPT, CATS_LAUNCH_LOG=str(log))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        args = self.record.read_text(encoding="utf-8").splitlines()
        folder = f"-Dcats.folder={self.env['HOME']}/JMRI_UserFiles/cats/panels"
        self.assertEqual(args, [folder, "--profile=TCS_MQTT.3f32a166", str(self.panel)])
        self.assertTrue(log.is_file())


if __name__ == "__main__":
    unittest.main()
