"""tools/ops/cs105.sh sends each subcommand to its drop, and consist is refused while the operating flag is set.

Stub `ssh` and `scp` on PATH stand in for the Pi: ssh answers the watcher's files from a scratch folder and scp keeps
the dropped script there, so nothing here touches the network or the CS-105."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "tools/ops/cs105.sh"
CONSIST = ROOT / "jmri/layouts/hart/scripts/cs105_consist.py"
REBOOT = ROOT / "jmri/layouts/hart/scripts/cs105_reboot.py"
ROSTER = ROOT / "external/jmri-cs105-roster-sync/cs105_roster_sync.py"
CLEAR = ("HART_PI_SSH", "PI_HOST", "HART_ENV_FILE", "HART_REPO_ROOT", "_hart_env_loaded", "CS105_TIMEOUT")

SSH = """#!/bin/sh
echo "$*" >> "$FAKE_PI/ssh.log"
for last; do :; done
case "$last" in
  "test -f /tmp/jmri_watcher.ready") exit 0 ;;
  "test -f /tmp/jmri_cmd.py") exit 1 ;;
  "test -f /tmp/jmri_cmd.out") exit 0 ;;
  "cat /tmp/jmri_cmd.out") printf 'ok\\nstarted\\n' ;;
  "cat /tmp/cs105_consist.log 2>/dev/null") cat "$FAKE_PI/consist.log" ;;
esac
exit 0
"""
SCP = """#!/bin/sh
n=0
for a; do n=$((n+1)); done
i=0
for a; do i=$((i+1)); [ "$i" -eq $((n-1)) ] && cp "$a" "$FAKE_PI/dropped.py"; done
exit 0
"""


class Cs105Cli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.pi = Path(self.tmp.name)
        stub = self.pi / "bin"
        stub.mkdir()
        for name, text in (("ssh", SSH), ("scp", SCP)):
            (stub / name).write_text(text, encoding="utf-8")
            (stub / name).chmod(0o755)
        (self.pi / "consist.log").write_text("06.01.00.00.C8.49 listeners: 1\nEND\n", encoding="utf-8")
        (self.pi / "hart.env").write_text("", encoding="utf-8")
        self.flag = self.pi / "operating"
        self.env = {k: v for k, v in os.environ.items() if k not in CLEAR}
        self.env.update(PATH=f"{stub}:/usr/bin:/bin", FAKE_PI=str(self.pi), HART_PI_SSH="fakepi.invalid",
                        HART_ENV_FILE=str(self.pi / "hart.env"), HART_OPERATING_FLAG=str(self.flag),
                        CS105_TIMEOUT="3")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(CLI), *args], env=self.env, capture_output=True, text=True,
                              cwd=self.pi, timeout=60)

    def dropped(self) -> str:
        return (self.pi / "dropped.py").read_text(encoding="utf-8")

    def ssh_calls(self) -> str:
        log = self.pi / "ssh.log"
        return log.read_text(encoding="utf-8") if log.exists() else ""

    # dispatch

    def test_help_and_bad_subcommands(self) -> None:
        self.assertEqual(self.run_cli("--help").returncode, 0)
        for args in ((), ("bogus",), ("reboot", "extra"), ("consist",), ("consist", "merge")):
            done = self.run_cli(*args)
            self.assertEqual(done.returncode, 2, (args, done.stderr))
        self.assertEqual(self.ssh_calls(), "")

    def test_reboot_drops_the_reboot_script(self) -> None:
        done = self.run_cli("reboot")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.dropped(), REBOOT.read_text(encoding="utf-8"))
        self.assertIn("restarting the CS-105 (up to 3s)", done.stdout)
        self.assertIn("fakepi.invalid mv /tmp/jmri_cmd.py.tmp /tmp/jmri_cmd.py", self.ssh_calls())

    def test_roster_sync_prepends_its_settings(self) -> None:
        if not ROSTER.is_file():
            self.skipTest("external/jmri-cs105-roster-sync is not checked out here")
        done = self.run_cli("roster-sync")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(self.dropped().startswith(
            'CS105_APPLY=False\nCS105_RENAME=False\nCS105_ONLY=""\nCS105_NAMES="id"\n'))
        self.assertIn("[PLAN]", done.stdout)
        done = self.run_cli("roster-sync", "--apply", "--rename", "--only", "1993,572", "--names", "road")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(self.dropped().startswith(
            'CS105_APPLY=True\nCS105_RENAME=True\nCS105_ONLY="1993,572"\nCS105_NAMES="road"\n'))
        self.assertTrue(self.dropped().endswith(ROSTER.read_text(encoding="utf-8")))
        self.assertEqual(self.run_cli("roster-sync", "--force").returncode, 2)

    # consist

    def test_consist_query_drops_the_consist_script_and_prints_its_log(self) -> None:
        done = self.run_cli("consist", "query", "06.01.00.00.C8.49", "06.01.00.00.CA.B2")
        self.assertEqual(done.returncode, 0, done.stderr)
        head = 'ACTION = "query"\nNODES = ["06.01.00.00.C8.49", "06.01.00.00.CA.B2", ]\n'
        self.assertTrue(self.dropped().startswith(head), self.dropped()[:200])
        self.assertIn('LOGF = "/tmp/cs105_consist.log"\n', self.dropped())
        self.assertTrue(self.dropped().endswith(CONSIST.read_text(encoding="utf-8")))
        self.assertIn("06.01.00.00.C8.49 listeners: 1\nEND", done.stdout)

    def test_consist_attach_and_detach_set_lead_follow_and_flags(self) -> None:
        done = self.run_cli("consist", "attach", "06.01.00.00.C8.49", "06.01.00.00.CA.B2")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('ACTION = "attach"\nNODES = []\nLEAD = "06.01.00.00.C8.49"\nFOLLOW = "06.01.00.00.CA.B2"\n'
                      'FLAGS = 6\n', self.dropped())
        done = self.run_cli("consist", "attach", "06.01.00.00.C8.49", "06.01.00.00.CA.B2", "--flags", "2")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("FLAGS = 2\n", self.dropped())
        done = self.run_cli("consist", "detach", "06.01.00.00.CA.B2", "06.01.00.00.C8.49")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('ACTION = "detach"\n', self.dropped())

    def test_consist_bad_arguments_send_nothing(self) -> None:
        for args in (("query",), ("query", "06.01.00.00.C8"), ("attach", "06.01.00.00.C8.49"),
                     ("attach", "06.01.00.00.C8.49", "06.01.00.00.C8.49"),
                     ("attach", "06.01.00.00.C8.49", "06.01.00.00.CA.B2", "--flags", "256"),
                     ("attach", "06.01.00.00.C8.49", "06.01.00.00.CA.B2", "--flags"),
                     ("detach", "06.01.00.00.C8.49", "06.01.00.00.CA.B2", "--flags", "6")):
            done = self.run_cli("consist", *args)
            self.assertEqual(done.returncode, 2, (args, done.stderr))
        self.assertEqual(self.ssh_calls(), "")

    def test_consist_is_refused_while_operating(self) -> None:
        self.flag.write_text("by=owner\nsince=now\nreason=session\n", encoding="utf-8")
        for args in (("query", "06.01.00.00.C8.49"), ("attach", "06.01.00.00.C8.49", "06.01.00.00.CA.B2"),
                     ("detach", "06.01.00.00.C8.49", "06.01.00.00.CA.B2")):
            done = self.run_cli("consist", *args)
            self.assertEqual(done.returncode, 3, done.stderr)
            self.assertIn("REFUSED: the operating flag is set", done.stderr)
        self.assertEqual(self.ssh_calls(), "")
        self.assertFalse((self.pi / "dropped.py").exists())

    def test_an_unreadable_flag_still_refuses(self) -> None:
        self.flag.mkdir()  # exists, but is no readable flag file
        done = self.run_cli("consist", "query", "06.01.00.00.C8.49")
        self.assertEqual(done.returncode, 3, done.stderr)
        self.assertEqual(self.ssh_calls(), "")

    def test_an_error_in_the_consist_log_fails(self) -> None:
        (self.pi / "consist.log").write_text("ERROR no LCC connection\nEND\n", encoding="utf-8")
        done = self.run_cli("consist", "query", "06.01.00.00.C8.49")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("ERROR no LCC connection", done.stdout)


if __name__ == "__main__":
    unittest.main()
