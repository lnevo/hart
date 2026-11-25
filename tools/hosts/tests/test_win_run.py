"""win_run.sh refuses before it reaches Windows: while the operating flag is set (CATS has the box), and with no
command. A stand-in ssh on PATH records any call, so a refusal that still connected would show."""
from __future__ import annotations

import os
import shutil
import time
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WIN_RUN = ROOT / "tools/hosts/win_run.sh"


class WinRunRefuses(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.called = self.tmp / "ssh-called"
        ssh = self.bin / "ssh"
        ssh.write_text(f"#!/bin/sh\ntouch '{self.called}'\nexit 0\n")
        ssh.chmod(0o755)
        self.flag = self.tmp / "operating"

    def run_it(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", HART_OPERATING_FLAG=str(self.flag),
                   HART_WIN_SSH="nobody@example.invalid", HART_WIN_SSH_PORT="2222")
        return subprocess.run(["bash", str(WIN_RUN), *args], cwd=ROOT, env=env, capture_output=True, text=True,
                              timeout=60)

    def test_operating_flag_set_exits_3_without_ssh(self) -> None:
        self.flag.write_text("by=owner\nsince=2026-11-20T00:00:00\nreason=test\n")
        r = self.run_it("--", "true")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("operating flag", r.stderr)
        self.assertFalse(self.called.exists())

    def test_no_command_is_a_usage_error(self) -> None:
        r = self.run_it()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertFalse(self.called.exists())

    def test_make_remote_without_cmd_is_a_usage_error(self) -> None:
        r = subprocess.run(["make", "-s", "remote"], cwd=ROOT, capture_output=True, text=True, timeout=60,
                           env=dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("set CMD", r.stderr)
        self.assertFalse(self.called.exists())


if __name__ == "__main__":
    unittest.main()


FLOCK = shutil.which("flock")


@unittest.skipUnless(FLOCK, "flock is a Linux tool (CI and the Windows box have it)")
class WinRunSlots(unittest.TestCase):
    """The block that runs on Windows before the command: at most WIN_RUN_SLOTS runs at once, each with
    nproc/slots check.sh jobs. Rendered with --print-script and run alone against a fake main clone."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "main/.git").mkdir(parents=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "nproc").write_text("#!/bin/sh\necho 8\n")
        (self.bin / "nproc").chmod(0o755)
        env = dict(os.environ, WIN_RUN_SLOTS="2", HART_WIN_SSH="nobody@example.invalid")
        script = subprocess.run(["bash", str(WIN_RUN), "--print-script", "--", "true"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=60, check=True).stdout
        block = script.split("# --- slots", 1)[1].split("# --- end slots", 1)[0]
        self.block = self.tmp / "slots.sh"
        self.block.write_text(f'set -euo pipefail\nmain="{self.tmp}/main"\n#{block}\necho "jobs=$CHECK_MAX_JOBS slot=$got"\n')

    def run_block(self, timeout: float) -> subprocess.CompletedProcess:
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")
        try:
            return subprocess.run(["bash", str(self.block)], env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(exc.cmd, -1, exc.stdout or "", (exc.stderr or b"").decode()
                                               if isinstance(exc.stderr, bytes) else (exc.stderr or ""))

    def hold(self, slot: int) -> subprocess.Popen:
        p = subprocess.Popen([FLOCK, str(self.tmp / f"main/.git/win_run.slot{slot}"), "sleep", "30"])
        self.addCleanup(p.kill)
        return p

    def test_a_free_slot_gives_half_the_cpus(self) -> None:
        done = self.run_block(10)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("jobs=4 slot=0", done.stdout)

    def test_the_second_slot_is_used_when_the_first_is_held(self) -> None:
        self.hold(0)
        time.sleep(0.5)
        done = self.run_block(10)
        self.assertIn("slot=1", done.stdout)

    def test_a_third_run_waits(self) -> None:
        self.hold(0), self.hold(1)
        time.sleep(0.5)
        done = self.run_block(3)
        self.assertEqual(-1, done.returncode)
        self.assertIn("waiting for a free slot", done.stderr)


class WinRunRuff(unittest.TestCase):
    """The block that installs the commit's ruff pin, once per version, and puts it first on PATH. Rendered with
    --print-script and run alone in a fake checkout, with a fake python3 (the pin) and a fake uv (the install)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.wt = self.tmp / "wt"
        (self.wt / "tools/audit").mkdir(parents=True)
        (self.wt / "tools/audit/check_ruff.py").write_text("")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.uv_log = self.tmp / "uv.log"
        self.fake("python3", 'echo "${FAKE_PIN:-ruff==9.9.9}"; exit "${FAKE_PIN_RC:-0}"')
        if not FLOCK:       # the Mac: the lock is not what these tests check
            self.fake("flock", "exit 0")
        # uv pip install -q --target <dir> <spec>: makes <dir>/bin/ruff, or fails with FAKE_UV_RC
        self.fake("uv", f'echo "$@" >> {self.uv_log}; [ "${{FAKE_UV_RC:-0}}" = 0 ] || exit "$FAKE_UV_RC"\n'
                        'mkdir -p "$5/bin" && printf "#!/bin/sh\\n" > "$5/bin/ruff" && chmod +x "$5/bin/ruff"')
        env = dict(os.environ, HART_WIN_SSH="nobody@example.invalid")
        script = subprocess.run(["bash", str(WIN_RUN), "--print-script", "--", "true"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=60, check=True).stdout
        block = script.split("# --- ruff", 1)[1].split("# --- end ruff", 1)[0]
        self.block = self.tmp / "ruff.sh"
        self.block.write_text(f'set -euo pipefail\ntrap "echo SETUP FAILED >&2; exit 3" ERR\n#{block}\necho "PATH=$PATH"\n')

    def fake(self, name: str, body: str) -> None:
        (self.bin / name).write_text(f"#!/bin/sh\n{body}\n")
        (self.bin / name).chmod(0o755)

    def run_block(self, **env: str) -> subprocess.CompletedProcess:
        full = dict(os.environ, HOME=str(self.tmp / "home"), PATH=f"{self.bin}:{os.environ['PATH']}",
                    **{f"FAKE_{k.upper()}": v for k, v in env.items()})
        return subprocess.run(["bash", str(self.block)], cwd=self.wt, env=full, capture_output=True, text=True,
                              timeout=30)

    def test_the_pin_is_installed_once_and_put_first_on_path(self) -> None:
        rdir = self.tmp / "home/.cache/hart/ruff/9.9.9"
        for _ in range(2):
            done = self.run_block()
            self.assertEqual(0, done.returncode, done.stderr)
            self.assertIn(f"PATH={rdir}/bin:", done.stdout)
        self.assertEqual(1, len(self.uv_log.read_text().splitlines()))     # the second run reuses the install
        self.assertTrue((rdir / "bin/ruff").is_file())
        self.assertFalse(Path(f"{rdir}.tmp").exists())

    def test_two_versions_get_two_folders(self) -> None:
        self.assertEqual(0, self.run_block().returncode)
        done = self.run_block(pin="ruff==8.0.0")
        self.assertIn(f"PATH={self.tmp}/home/.cache/hart/ruff/8.0.0/bin:", done.stdout)
        self.assertTrue((self.tmp / "home/.cache/hart/ruff/9.9.9/bin/ruff").is_file())

    def test_a_failed_install_warns_and_the_run_goes_on(self) -> None:
        done = self.run_block(uv_rc="1")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("SETUP FAILED", done.stderr)
        self.assertIn("could not install ruff==9.9.9", done.stderr)
        self.assertNotIn("/.cache/hart/ruff/", done.stdout)
        self.assertFalse((self.tmp / "home/.cache/hart/ruff/9.9.9").exists())

    def test_no_pin_warns_and_a_commit_without_the_check_installs_nothing(self) -> None:
        done = self.run_block(pin="check_ruff: no pin", pin_rc="2")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("no ruff pin (check_ruff: no pin)", done.stderr)
        (self.wt / "tools/audit/check_ruff.py").unlink()
        done = self.run_block()
        self.assertEqual(("", 0), (done.stderr, done.returncode))
        self.assertFalse(self.uv_log.exists())
