"""The read-only checks make orient's "waiting to ingest" lines ask: tools/hosts/deploy/pi_unpulled.sh (the deploy
gate's own Pi check, pi_unpulled_words in common.sh), tools/ops/pull_tables.sh --status and
tools/hosts/sync_roster_from_pi.sh --status.

ssh is a stand-in that runs the piped script here against a local folder (or fails as an unreachable host does,
exit 255) and logs every call; scp and rsync stand-ins fail the test if a status check ever calls them. Nothing
reaches a host, and the pulls' own behaviour stays covered by test_pull_tables.py and test_pi_unpulled_changes.py.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pull_tables import GENERATED, STORE, PullCase, sha  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
PI_UNPULLED = ROOT / "tools/hosts/deploy/pi_unpulled.sh"
OPS_FILES = ("Operations.xml", "OperationsCarRoster.xml", "OperationsEngineRoster.xml",
             "OperationsLocationRoster.xml", "OperationsRouteRoster.xml", "OperationsTrainRoster.xml")


def stand_ins(bin_dir: Path, log: Path, down: bool = False) -> None:
    """ssh runs its last argument here (bash -s -- ..., the piped script), or answers as a host that is down."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    body = ('echo "ssh: connect to host pi.example.invalid port 22: Operation timed out" >&2\nexit 255\n' if down
            else 'cmd="${@: -1}"\nif [[ "$cmd" == "bash -s -- "* ]]; then eval "exec $cmd"; fi\nexit 99\n')
    (bin_dir / "ssh").write_text(f'#!/bin/bash\necho "ssh $*" >>"{log}"\n{body}', encoding="utf-8")
    for tool in ("scp", "rsync"):
        (bin_dir / tool).write_text(f'#!/bin/bash\necho "{tool} $*" >>"{log}"\nexit 98\n', encoding="utf-8")
    for tool in ("ssh", "scp", "rsync"):
        (bin_dir / tool).chmod(0o755)


def clean_env(tmp: Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HART_", "_hart"))}
    env.update(HOME=str(tmp / "home"), PATH=f"{tmp / 'bin'}{os.pathsep}{env['PATH']}",
               HART_ENV_FILE=str(tmp / "none.env"), HART_PI_SSH="pi.example.invalid", HART_SSH_MUX="0", **extra)
    return env


class PiUnpulledTest(unittest.TestCase):
    """The gate's Pi check, asked alone: the Pi's files against what this checkout would ship."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = self.tmp / "network.log"
        stand_ins(self.tmp / "bin", self.log)
        self.uf = self.tmp / "pi/JMRI_UserFiles"
        ops = self.uf / "operations"
        ops.mkdir(parents=True)
        for name in OPS_FILES:
            (ops / name).write_text(f"deployed {name}")
        (ops / ".deployed.sha256").write_text(
            hashlib.sha256(b"".join((ops / n).read_bytes() for n in OPS_FILES)).hexdigest() + "\n")
        (self.uf / "tables.xml").write_text("<layout-config/>")
        (self.uf / "cats").mkdir()
        (self.uf / "cats/deploy_stamp.txt").write_text(
            f"commit=abc\ntables_sha256={hashlib.sha256(b'<layout-config/>').hexdigest()}\n")

    def ask(self) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(PI_UNPULLED)], cwd=self.tmp, capture_output=True, text=True, timeout=60,
                              env=clean_env(self.tmp, HART_PI_USERFILES=str(self.uf)))

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_nothing_waiting(self) -> None:
        done = self.ask()
        self.assertEqual((done.returncode, done.stdout), (0, ""), done.stderr)
        # one ssh call, in batch mode with orient's 10 s ConnectTimeout, and nothing else
        self.assertEqual(len(self.calls()), 1, self.calls())
        self.assertIn("-o BatchMode=yes -o ConnectTimeout=10 pi.example.invalid bash -s -- ", self.calls()[0])
        self.assertIn(" ops:", self.calls()[0])  # the Operations files this checkout ships count as taken

    def test_a_session_and_a_store_are_named(self) -> None:
        (self.uf / "operations/OperationsCarRoster.xml").write_text("moved cars")
        (self.uf / "tables.xml").write_text("<layout-config><stored/></layout-config>")
        done = self.ask()
        self.assertEqual((done.returncode, done.stdout.split()), (0, ["ops", "tables"]), done.stderr)
        # it only reads: the Pi's files are as they were, and nothing was pulled or marked
        self.assertEqual((self.uf / "operations/OperationsCarRoster.xml").read_text(), "moved cars")
        self.assertEqual(len(self.calls()), 1, self.calls())

    def test_an_unreachable_pi_is_ssh_s_status(self) -> None:
        stand_ins(self.tmp / "bin", self.log, down=True)
        done = self.ask()
        self.assertEqual(done.returncode, 255)
        self.assertEqual(done.stdout, "")
        self.assertIn("Operation timed out", done.stderr)

    def test_it_takes_no_arguments(self) -> None:
        done = subprocess.run(["bash", str(PI_UNPULLED), "--pi"], capture_output=True, text=True, timeout=30,
                              env=clean_env(self.tmp, HART_PI_USERFILES=str(self.uf)))
        self.assertEqual(done.returncode, 2)
        self.assertEqual(self.calls(), [])


class MacTablesStatusTest(PullCase):
    """make tables-pull's own check, asked with --status: it answers and keeps nothing."""

    def status(self) -> str:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HART_", "_hart"))}
        env.update(HOME=str(self.home), PATH=f"{self.bin}{os.pathsep}{env['PATH']}",
                   HART_ENV_FILE=str(self.tmp / "none.env"))
        done = subprocess.run(["bash", str(self.root / "tools/ops/pull_tables.sh"), "--status"], env=env,
                              cwd=self.tmp, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.pulled(), [])
        self.assertFalse((self.root / "media").exists())
        return done.stdout.strip()

    def test_absent(self) -> None:
        self.assertEqual(self.status(), "absent")

    def test_nothing_waiting_after_a_deploy(self) -> None:
        (self.uf / "tables.xml").write_text(GENERATED, encoding="utf-8")
        self.stamp(self.uf, sha(GENERATED))
        self.assertEqual(self.status(), "nothing")

    def test_a_store_is_waiting_until_it_is_split_in(self) -> None:
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        self.stamp(self.uf, sha(GENERATED))
        self.assertEqual(self.status(), "waiting")
        self.split_in(STORE)
        self.assertEqual(self.status(), "nothing")


class RosterStatusTest(unittest.TestCase):
    """sync_roster_from_pi.sh --status: the Pi's roster files against the Mac's JMRI_UserFiles."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "checkout"
        for rel in ("tools/hosts/sync_roster_from_pi.sh", "tools/hosts/roster_digest.sh", "tools/env/load_env.sh",
                    "tools/env/defaults.env"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, self.root / rel)
        self.log = self.tmp / "network.log"
        stand_ins(self.tmp / "bin", self.log)
        self.pi = self.tmp / "pi/JMRI_UserFiles"
        self.mac = self.tmp / "home/JMRI_UserFiles"
        for uf in (self.pi, self.mac):
            (uf / "roster").mkdir(parents=True)
            (uf / "roster.xml").write_text("<roster/>")
            (uf / "roster/D749.xml").write_text("<locomotive id='D749'/>")

    def status(self) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.root / "tools/hosts/sync_roster_from_pi.sh"), "--status"],
                              cwd=self.tmp, capture_output=True, text=True, timeout=60,
                              env=clean_env(self.tmp, HART_PI_USERFILES=str(self.pi)))

    def answer(self) -> str:
        done = self.status()
        self.assertEqual(done.returncode, 0, done.stderr)
        # one ssh call with a ConnectTimeout, no copy, no stage folder
        calls = self.log.read_text().splitlines()
        self.assertEqual(len(calls), 1, calls)
        self.assertIn("-o BatchMode=yes -o ConnectTimeout=10", calls[0])
        self.assertFalse((self.root / "jmri").exists())
        self.log.unlink()
        return done.stdout.strip()

    def test_nothing_waiting_when_the_mac_copy_matches(self) -> None:
        (self.mac / "roster/extra-on-the-mac.xml").write_text("only here")  # the pull leaves it, so it is no change
        (self.pi / "roster/._D749.xml").write_text("AppleDouble")              # never counted
        self.assertEqual(self.answer(), "nothing")

    def test_changed_and_new_files_on_the_pi_are_waiting(self) -> None:
        (self.pi / "roster.xml").write_text("<roster><locomotive/></roster>")
        (self.pi / "roster/NVL 1 copy.xml").write_text("<locomotive id='NVL 1'/>")
        self.assertEqual(self.answer(), "waiting 2")

    def test_no_mac_copy_yet_counts_every_pi_file(self) -> None:
        shutil.rmtree(self.mac)
        self.assertEqual(self.answer(), "waiting 2")

    def test_an_unreachable_pi_is_ssh_s_status(self) -> None:
        stand_ins(self.tmp / "bin", self.log, down=True)
        done = self.status()
        self.assertEqual(done.returncode, 255)
        self.assertEqual(done.stdout, "")
        self.assertFalse((self.root / "jmri").exists())


if __name__ == "__main__":
    unittest.main()
