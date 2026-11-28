"""win_run.sh refuses before it reaches Windows: while the operating flag is set (CATS has the box), and with no
command. A stand-in ssh on PATH records any call, so a refusal that still connected would show."""
from __future__ import annotations

import hashlib
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
        self.assertNotIn(f"{self.tmp}/home/.cache/hart/ruff/", done.stdout)    # the caller's own PATH may hold one
        self.assertFalse((self.tmp / "home/.cache/hart/ruff/9.9.9").exists())

    def test_no_pin_warns_and_a_commit_without_the_check_installs_nothing(self) -> None:
        done = self.run_block(pin="check_ruff: no pin", pin_rc="2")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("no ruff pin (check_ruff: no pin)", done.stderr)
        (self.wt / "tools/audit/check_ruff.py").unlink()
        done = self.run_block()
        self.assertEqual(("", 0), (done.stderr, done.returncode))
        self.assertFalse(self.uv_log.exists())


def block_of(text: str, marker: str) -> str:
    """The lines between "# --- <marker>" and "# --- end <marker>" in `text` (win_run.sh or its --print-script)."""
    return text.split(f"# --- {marker}", 1)[1].split(f"# --- end {marker}", 1)[0].split("\n", 1)[1]


class WinRunVenv(unittest.TestCase):
    """The block that brings ~/hart/.venv up to the commit's requirements.txt when the file changed. Rendered with
    --print-script and run alone in a fake checkout, with a fake uv (the install)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.wt = self.tmp / "wt"
        self.wt.mkdir()
        (self.wt / "requirements.txt").write_text("mypy==1.0\n")
        (self.tmp / "home/hart/.venv/bin").mkdir(parents=True)
        self.stamp = self.tmp / "home/hart/.venv/.requirements.sha256"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.uv_log = self.tmp / "uv.log"
        if not FLOCK:
            self.fake("flock", "exit 0")
        if not shutil.which("sha256sum"):      # the Mac has shasum only
            self.fake("sha256sum", 'shasum -a 256 "$@"')
        self.fake("uv", f'echo "$@" >> {self.uv_log}; exit "${{FAKE_UV_RC:-0}}"')
        env = dict(os.environ, HART_WIN_SSH="nobody@example.invalid")
        script = subprocess.run(["bash", str(WIN_RUN), "--print-script", "--", "true"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=60, check=True).stdout
        block = script.split("# --- venv", 1)[1].split("# --- end venv", 1)[0]
        self.block = self.tmp / "venv.sh"
        self.block.write_text(f'set -euo pipefail\ntrap "echo SETUP FAILED >&2; exit 3" ERR\n#{block}\n')

    def fake(self, name: str, body: str) -> None:
        (self.bin / name).write_text(f"#!/bin/sh\n{body}\n")
        (self.bin / name).chmod(0o755)

    def run_block(self, **env: str) -> subprocess.CompletedProcess:
        full = dict(os.environ, HOME=str(self.tmp / "home"), PATH=f"{self.bin}:{os.environ['PATH']}",
                    **{f"FAKE_{k.upper()}": v for k, v in env.items()})
        return subprocess.run(["bash", str(self.block)], cwd=self.wt, env=full, capture_output=True, text=True,
                              timeout=30)

    def installs(self) -> int:
        return len(self.uv_log.read_text().splitlines()) if self.uv_log.exists() else 0

    def test_a_changed_requirements_file_is_installed_once(self) -> None:
        for _ in range(2):
            done = self.run_block()
            self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(1, self.installs())                  # the second run finds the stamp current
        want = hashlib.sha256(b"mypy==1.0\n").hexdigest()
        self.assertEqual(want, self.stamp.read_text().strip())
        self.assertIn(f"--python {self.tmp}/home/hart/.venv/bin/python -r requirements.txt",
                      self.uv_log.read_text())
        (self.wt / "requirements.txt").write_text("mypy==2.0\n")
        self.assertEqual(0, self.run_block().returncode)
        self.assertEqual(2, self.installs())

    def test_a_failed_install_warns_records_nothing_and_the_run_goes_on(self) -> None:
        done = self.run_block(uv_rc="1")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("SETUP FAILED", done.stderr)
        self.assertIn("could not install requirements.txt", done.stderr)
        self.assertFalse(self.stamp.exists())
        self.assertEqual(0, self.run_block().returncode)      # so the next run tries again
        self.assertEqual(2, self.installs())

    def test_a_commit_without_requirements_installs_nothing(self) -> None:
        (self.wt / "requirements.txt").unlink()
        done = self.run_block()
        self.assertEqual(("", 0), (done.stderr, done.returncode))
        self.assertEqual(0, self.installs())


class WinRunFetch(unittest.TestCase):
    """The fetch into the box's shared clone: the run's commit and origin/main, so check.sh's changed paths (the diff
    from the merge base with origin/main) are the branch's own. Rendered with --print-script and run alone against a
    scratch origin, with a fake flock where there is none."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        origin, work, self.clone = self.tmp / "origin.git", self.tmp / "work", self.tmp / "clone"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        if not FLOCK:
            (self.bin / "flock").write_text('#!/bin/sh\nshift\nexec "$@"\n')
            (self.bin / "flock").chmod(0o755)
        g = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(work), *g, "commit", "-q", "--allow-empty", "-m", "c1"], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "HEAD:main"], check=True)
        subprocess.run(["git", "clone", "-q", str(origin), str(self.clone)], check=True)     # origin/main at c1
        subprocess.run(["git", "-C", str(work), *g, "commit", "-q", "--allow-empty", "-m", "c2"], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "HEAD:main"], check=True)
        subprocess.run(["git", "-C", str(work), *g, "commit", "-q", "--allow-empty", "-m", "branch"], check=True)
        subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "HEAD:refs/heads/agent/x"], check=True)
        self.main_sha, self.branch_sha = (self.rev(work, r) for r in ("HEAD^", "HEAD"))
        env = dict(os.environ, HART_WIN_SSH="nobody@example.invalid")
        script = subprocess.run(["bash", str(WIN_RUN), "--print-script", "--", "true"], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=60, check=True).stdout
        rendered = self.rev(ROOT, "HEAD")      # --print-script fills in this checkout's HEAD
        self.block = self.tmp / "fetch.sh"
        self.block.write_text(f'set -euo pipefail\nmain="{self.clone}"\n'
                              f'{block_of(script, "fetch").replace(rendered, self.branch_sha)}\n')

    @staticmethod
    def rev(repo: Path, ref: str) -> str:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", ref], check=True, capture_output=True,
                              text=True).stdout.strip()

    def test_the_run_commit_and_origin_main_are_fetched(self) -> None:
        done = subprocess.run(["bash", str(self.block)], capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}"))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.main_sha, self.rev(self.clone, "origin/main"))
        self.assertEqual("commit", subprocess.run(["git", "-C", str(self.clone), "cat-file", "-t", self.branch_sha],
                                                  capture_output=True, text=True).stdout.strip())


class WinRunStampName(unittest.TestCase):
    """stamp_name, the Mac's half: the name of a ref's stamp folder on Windows. Run alone in a scratch repo."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        git = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "c"], check=True)
        self.sha = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        for b in ("agent/claude/x", "agent_claude_x", "odd.name+1", "x" * 80):
            subprocess.run([*git, "branch", b], check=True)
        for r in ("refs/remotes/origin/main", "refs/remotes/origin/feature/y"):
            subprocess.run([*git, "update-ref", r, self.sha], check=True)
        self.block = self.tmp / "name.sh"
        self.block.write_text(f'set -euo pipefail\n{block_of(WIN_RUN.read_text(), "stamp name")}\n'
                              'stamp_name "$@"\n')

    def name(self, ref: str, sha: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.block), str(self.repo), ref, sha or self.sha], capture_output=True,
                              text=True, timeout=30)

    def suffix(self, branch: str) -> str:
        data = branch.encode()
        return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()[:10]

    def test_a_non_ascii_name_is_cut_by_bytes(self) -> None:
        subprocess.run(["git", "-C", str(self.repo), "branch", "agent/éclair"], check=True)
        done = subprocess.run(["bash", str(self.block), str(self.repo), "agent/éclair", self.sha], capture_output=True,
                              text=True, timeout=30, env=dict(os.environ, LC_ALL="en_US.UTF-8"))
        self.assertEqual(f"agent___clair-{self.suffix('agent/éclair')}", done.stdout.strip(), done.stderr)

    def test_slashes_and_odd_characters_become_underscores_with_the_name_hash(self) -> None:
        self.assertEqual(f"agent_claude_x-{self.suffix('agent/claude/x')}", self.name("agent/claude/x").stdout.strip())
        self.assertEqual(f"odd_name_1-{self.suffix('odd.name+1')}", self.name("odd.name+1").stdout.strip())

    def test_names_that_sanitise_alike_get_two_folders(self) -> None:
        self.assertNotEqual(self.name("agent/claude/x").stdout, self.name("agent_claude_x").stdout)

    def test_a_long_name_is_cut_to_60(self) -> None:
        self.assertEqual(f"{'x' * 60}-{self.suffix('x' * 80)}", self.name("x" * 80).stdout.strip())

    def test_main_and_remote_branches(self) -> None:
        self.assertEqual("main", self.name("main").stdout.strip())
        self.assertEqual("main", self.name("origin/main").stdout.strip())
        self.assertEqual(f"feature_y-{self.suffix('feature/y')}", self.name("origin/feature/y").stdout.strip())

    def test_a_detached_commit_or_tag_uses_the_commit(self) -> None:
        self.assertEqual(self.sha, self.name(self.sha).stdout.strip())
        self.assertEqual(self.sha, self.name("HEAD~0").stdout.strip())

    def test_no_branch_and_no_sha_is_refused(self) -> None:
        done = self.name("nope", sha="not-a-sha")
        self.assertEqual(2, done.returncode)
        self.assertIn("not a commit sha", done.stderr)
        self.assertEqual("", done.stdout)


class WinRunStamps(unittest.TestCase):
    """The block that picks the run's CHECK_STAMPS_DIR on Windows: main keeps the shared folder, any other ref gets its
    own copy under check-stamps-by-ref. Rendered with --print-script (the name replaced) and run alone."""

    SHARED_STAMPS = ("a-1.json", "b-2.json")

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.main = self.tmp / "main"      # not a git checkout: hart_main_checkout answers with the folder itself
        self.shared = self.main / ".cache/hart/check-stamps"
        self.byref = self.main / ".cache/hart/check-stamps-by-ref"
        self.shared.mkdir(parents=True)
        for n in self.SHARED_STAMPS:
            (self.shared / n).write_text(n)
        (self.shared / "filehash.json").write_text("{}")
        (self.shared / "c-3.json.99.tmp").write_text("half")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        if not FLOCK:       # the Mac: the lock is not what these tests check
            self.fake("flock", "exit 0")
        env = dict(os.environ, HART_WIN_SSH="nobody@example.invalid")
        script = subprocess.run(["bash", str(WIN_RUN), "--print-script", "--ref", "HEAD", "--", "true"], cwd=ROOT,
                                env=env, capture_output=True, text=True, timeout=60, check=True).stdout
        self.rendered = block_of(script, "stamps")
        self.sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                  check=True).stdout.strip()

    def fake(self, name: str, body: str) -> None:
        (self.bin / name).write_text(f"#!/bin/sh\n{body}\n")
        (self.bin / name).chmod(0o755)

    def run_block(self, name: str = "feat-x") -> subprocess.CompletedProcess:
        block = self.tmp / "stamps.sh"
        block.write_text(f'set -euo pipefail\ntrap "echo SETUP FAILED >&2; exit 3" ERR\nmain="{self.main}"\n'
                         f'{self.rendered.replace(self.sha, name)}\necho "DIR=$CHECK_STAMPS_DIR"\n')
        env = {k: v for k, v in os.environ.items() if k != "HART_CACHE_DIR"}
        return subprocess.run(["bash", str(block)], env=dict(env, PATH=f"{self.bin}:{env['PATH']}"),
                              capture_output=True, text=True, timeout=30)

    def test_the_rendered_block_names_the_refs_folder(self) -> None:
        self.assertIn(f'CHECK_STAMPS_DIR="$byref/{self.sha}"', self.rendered)

    def test_first_use_copies_the_shared_stamps_and_the_second_reuses_them(self) -> None:
        done = self.run_block()
        self.assertEqual(0, done.returncode, done.stderr)
        mine = self.byref / "feat-x"
        self.assertIn(f"DIR={mine}\n", done.stdout)
        self.assertIn("new, 2 stamps copied", done.stderr)
        self.assertEqual(sorted(self.SHARED_STAMPS), sorted(p.name for p in mine.iterdir()))
        self.assertFalse((mine / "a-1.json").is_symlink())
        self.assertEqual([".lock", "feat-x"], sorted(p.name for p in self.byref.iterdir()))   # no temp folder left
        (mine / "a-1.json").write_text("this ref's record")
        (self.shared / "b-2.json").write_text("main's record")
        done = self.run_block()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("reused", done.stderr)
        self.assertEqual("a-1.json", (self.shared / "a-1.json").read_text())    # a copy: neither changes the other
        self.assertEqual("b-2.json", (mine / "b-2.json").read_text())

    def test_main_writes_the_shared_folder(self) -> None:
        done = self.run_block("main")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"DIR={self.shared}\n", done.stdout)
        self.assertIn("main's, shared", done.stderr)
        self.assertFalse(self.byref.exists())

    def test_folders_untouched_for_14_days_are_removed(self) -> None:
        old = time.time() - 15 * 86400
        for n in ("gone-1", "gone-2", "feat-x", ".feat-y.tmp.123"):
            (self.byref / n).mkdir(parents=True)
            (self.byref / n / "stale.json").write_text("old")
            os.utime(self.byref / n, (old, old))
        (self.byref / "recent").mkdir()
        os.utime(self.byref / "recent", (time.time() - 3 * 86400,) * 2)
        done = self.run_block()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("4 stamp folders untouched for 14 days removed", done.stderr)
        self.assertEqual([".lock", "feat-x", "recent"], sorted(p.name for p in self.byref.iterdir()))
        self.assertIn("new, 2 stamps copied", done.stderr)      # this ref's own old folder was made again
        self.assertFalse((self.byref / "feat-x/stale.json").exists())
        self.assertGreater((self.byref / "feat-x").stat().st_mtime, time.time() - 60)

    def test_an_old_folder_that_will_not_go_warns_and_the_run_goes_on(self) -> None:
        old = time.time() - 15 * 86400
        (self.byref / "stuck").mkdir(parents=True)
        os.utime(self.byref / "stuck", (old, old))
        self.fake("rm", 'case "$*" in *stuck*) exit 1 ;; esac; exec /bin/rm "$@"')
        done = self.run_block()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("could not remove the old stamp folder", done.stderr)
        self.assertIn("0 stamp folders untouched for 14 days removed", done.stderr)
        self.assertIn(f"DIR={self.byref / 'feat-x'}\n", done.stdout)

    def test_no_shared_folder_says_so_and_starts_empty(self) -> None:
        shutil.rmtree(self.shared)
        done = self.run_block()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("no shared stamps", done.stderr)
        self.assertEqual([], list((self.byref / "feat-x").iterdir()))

    def test_a_failed_copy_stops_the_run_and_leaves_no_folder(self) -> None:
        self.fake("cp", "echo 'cp: disk full' >&2; exit 1")
        done = self.run_block()
        self.assertEqual(3, done.returncode, done.stderr)
        self.assertIn("could not copy the stamps", done.stderr)
        self.assertIn("was not set up", done.stderr)
        self.assertNotIn("SETUP FAILED", done.stderr)
        self.assertNotIn("DIR=", done.stdout)
        self.assertEqual([".lock"], sorted(p.name for p in self.byref.iterdir()))

    def test_a_short_copy_is_caught_by_the_count(self) -> None:
        self.fake("cp", "exit 0")
        done = self.run_block()
        self.assertEqual(3, done.returncode, done.stderr)
        self.assertIn("copied 0 of 2 stamps", done.stderr)
        self.assertEqual([".lock"], sorted(p.name for p in self.byref.iterdir()))

    def test_a_by_ref_folder_that_cannot_be_made_stops_the_run(self) -> None:
        (self.main / ".cache/hart/check-stamps-by-ref").write_text("a file, not a folder")
        done = self.run_block()
        self.assertEqual(3, done.returncode, done.stderr)
        self.assertIn("could not make", done.stderr)
        self.assertNotIn("DIR=", done.stdout)

class WinRunLog(unittest.TestCase):
    """The log block, the Mac's half: every run's whole output saved, its failed jobs and the log's path printed last,
    the newest WIN_RUN_KEEP_LOGS kept. Run alone with a stand-in remote_script and a stand-in ssh."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.logs = self.tmp / "remote-logs"
        self.block = self.tmp / "log.sh"
        self.block.write_text('set -euo pipefail\nremote_script() { echo "the script"; }\n'
                              f'{block_of(WIN_RUN.read_text(), "log")}\n"$@"\n')
        self.ssh = self.tmp / "fake-ssh"

    def bash(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["/bin/bash", str(self.block), *args], capture_output=True, text=True, timeout=30)

    def fake_ssh(self, body: str) -> None:
        self.ssh.write_text(f"#!/bin/bash\n{body}\n")
        self.ssh.chmod(0o755)

    def run_logged(self, log: Path) -> subprocess.CompletedProcess:
        return self.bash("run_logged", str(log), "header line", str(self.ssh))

    def test_the_whole_stream_and_stderr_go_to_the_log_and_the_exit_code_stays(self) -> None:
        self.fake_ssh('read -r got; echo "ran: $got"; echo "--- unit-a (3s)"; echo "--- unit-b FAILED (4s)"\n'
                      'echo "oops" >&2; exit 1')
        log = self.tmp / "one.log"
        done = self.run_logged(log)
        self.assertEqual(done.returncode, 1, done.stderr)
        text = log.read_text()
        for line in ("header line", "ran: the script", "--- unit-b FAILED (4s)", "oops", "win_run.sh: exit 1"):
            self.assertIn(line, text)
        self.assertIn("--- unit-b FAILED (4s)", done.stdout)       # still shown as it runs

    def test_a_passing_run_exits_0(self) -> None:
        self.fake_ssh("cat >/dev/null; echo ALL PASSED")
        done = self.run_logged(self.tmp / "ok.log")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_unreachable_keeps_255(self) -> None:
        self.fake_ssh("cat >/dev/null; exit 255")
        self.assertEqual(self.run_logged(self.tmp / "gone.log").returncode, 255)

    def test_a_stopped_run_still_ends_with_its_log_line(self) -> None:
        """TERM mid-run (a superseded run stopped) still prints the failed jobs and the path, as win_run.sh's trap does."""
        self.fake_ssh('cat >/dev/null; echo "--- unit-a FAILED (1s)"; sleep 4')
        log = self.tmp / "stopped.log"
        script = self.tmp / "stop.sh"
        script.write_text(f'set -euo pipefail\nremote_script() {{ echo s; }}\n{block_of(WIN_RUN.read_text(), "log")}\n'
                          f'trap \'finish_log "{log}" "{self.tmp}" 20\' EXIT\ntrap "exit 143" TERM\n'
                          f'run_logged "{log}" header "{self.ssh}"\n')
        p = subprocess.Popen(["/bin/bash", str(script)], stdout=subprocess.PIPE, text=True)
        time.sleep(1.5)
        p.terminate()
        out, _ = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 143)
        self.assertEqual(out.splitlines()[-2:], ["--- unit-a FAILED (1s)", f"log: {log}"])

    def test_end_log_names_the_failed_jobs_then_the_path_last(self) -> None:
        log = self.tmp / "x.log"
        log.write_text("--- a (1s)\n--- b FAILED (2s)\nnoise --- c FAILED\n--- d FAILED (killed before it finished, no s)\n")
        out = self.bash("end_log", str(log)).stdout.splitlines()
        self.assertEqual(out, ["--- b FAILED (2s)", "--- d FAILED (killed before it finished, no s)", f"log: {log}"])

    def test_end_log_of_a_clean_run_prints_only_the_path(self) -> None:
        log = self.tmp / "y.log"
        log.write_text("--- a (1s)\nALL PASSED\n")
        self.assertEqual(self.bash("end_log", str(log)).stdout.splitlines(), [f"log: {log}"])

    def test_start_log_makes_the_folder_and_an_empty_file(self) -> None:
        done = self.bash("start_log", str(self.logs), "main-20261125-2300-1")
        self.assertEqual(done.stdout.strip(), str(self.logs / "main-20261125-2300-1.log"))
        self.assertEqual((self.logs / "main-20261125-2300-1.log").read_text(), "")

    def test_start_log_that_cannot_write_prints_nothing_and_fails(self) -> None:
        blocker = self.tmp / "file"
        blocker.write_text("")
        done = self.bash("start_log", str(blocker / "sub"), "n")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(done.stdout, "")

    def test_prune_keeps_the_newest(self) -> None:
        self.logs.mkdir()
        for i in range(5):
            f = self.logs / f"r-{i}.log"
            f.write_text("x")
            os.utime(f, (1_000_000 + i, 1_000_000 + i))
        (self.logs / "notes.txt").write_text("not a log")
        done = self.bash("prune_logs", str(self.logs), "2")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sorted(p.name for p in self.logs.iterdir()), ["notes.txt", "r-3.log", "r-4.log"])

    def test_prune_with_fewer_logs_than_kept_removes_nothing(self) -> None:
        self.logs.mkdir()
        (self.logs / "a.log").write_text("x")
        self.assertEqual(self.bash("prune_logs", str(self.logs), "20").returncode, 0)
        self.assertTrue((self.logs / "a.log").exists())

    def test_a_bad_keep_count_is_a_usage_error(self) -> None:
        env = dict(os.environ, WIN_RUN_KEEP_LOGS="0", HART_WIN_SSH="nobody@example.invalid")
        done = subprocess.run(["bash", str(WIN_RUN), "--print-script", "--", "true"], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("WIN_RUN_KEEP_LOGS", done.stderr)


class WinRunMacLock(unittest.TestCase):
    """The mac lock block: at most WIN_RUN_SLOTS remote runs at once from the Mac, a run waiting with a line only when
    every slot is held, a stale slot reclaimed, and the slot released on every exit. Run alone with the slot folders
    in a temp folder."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.lock = self.tmp / "remote.lock"
        self.block = self.tmp / "lock.sh"
        self.block.write_text('set -euo pipefail\nslots="${WIN_RUN_SLOTS:-2}"\n'
                              f'{block_of(WIN_RUN.read_text(), "mac lock")}\n'
                              'trap release_lock EXIT\ntake_lock some/branch\necho "TAKEN $lock_dir"\n'
                              'cat "$lock_dir/owner"\nsleep "${END_SLEEP:-0}"\nexit "${END_RC:-0}"\n')
        self.env = dict(os.environ, WIN_RUN_LOCK=str(self.lock), WIN_RUN_LOCK_POLL="1", WIN_RUN_LOCK_SAY="60")

    def slot(self, n: int) -> Path:
        return Path(f"{self.lock}.{n}")

    def bash(self, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(["/bin/bash", str(self.block)], capture_output=True, text=True, timeout=30,
                              env={**self.env, **env})

    def start(self, **env: str) -> subprocess.Popen:
        return subprocess.Popen(["/bin/bash", str(self.block)], env={**self.env, **env}, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    def hold(self, n: int, pid: int, since: int) -> None:
        self.slot(n).mkdir()
        (self.slot(n) / "owner").write_text(f"{pid} {since} other/branch\n")

    def dead_pid(self) -> int:
        proc = subprocess.Popen(["true"])
        proc.wait()
        return proc.pid

    def test_a_free_slot_is_taken_and_released_on_exit(self) -> None:
        for rc in ("0", "1"):
            with self.subTest(rc=rc):
                done = self.bash(END_RC=rc)
                self.assertEqual(int(rc), done.returncode, done.stderr)
                self.assertIn(f"TAKEN {self.slot(1)}", done.stdout)
                self.assertIn("some/branch", done.stdout)
                self.assertFalse(self.slot(1).exists())

    def test_two_runs_hold_the_two_slots_at_once(self) -> None:
        first = self.start(END_SLEEP="3")
        time.sleep(0.5)
        second = self.start(END_SLEEP="3")
        outs = [p.communicate(timeout=20) for p in (first, second)]
        self.assertEqual([0, 0], [first.returncode, second.returncode], outs)
        taken = sorted(out.split()[1] for out, _ in outs)
        self.assertEqual([str(self.slot(1)), str(self.slot(2))], taken)
        self.assertTrue(all("waiting" not in err for _, err in outs), outs)
        self.assertFalse(self.slot(1).exists() or self.slot(2).exists())

    def test_a_third_run_waits_with_a_line(self) -> None:
        for n in (1, 2):
            self.hold(n, os.getpid(), int(time.time()) - 4000)
        proc = self.start()
        time.sleep(2.5)
        proc.terminate()
        out, err = proc.communicate(timeout=10)
        self.assertNotIn("TAKEN", out)
        self.assertIn("all 2 remote slots", err)
        self.assertTrue((self.slot(1) / "owner").exists() and (self.slot(2) / "owner").exists(),
                        "the other holders' slots stay")

    def test_one_slot_waits_when_win_run_slots_is_1(self) -> None:
        self.hold(1, os.getpid(), int(time.time()))
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run(["/bin/bash", str(self.block)], env={**self.env, "WIN_RUN_SLOTS": "1"},
                           capture_output=True, text=True, timeout=3)
        self.assertFalse(self.slot(2).exists())

    def test_a_stale_slot_is_reclaimed(self) -> None:
        self.hold(1, os.getpid(), int(time.time()))
        self.hold(2, self.dead_pid(), int(time.time()) - 3000)
        done = self.bash()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"{self.slot(2)} is stale", done.stderr)
        self.assertIn(f"TAKEN {self.slot(2)}", done.stdout)
        self.assertFalse(self.slot(2).exists())
        self.assertTrue((self.slot(1) / "owner").exists())

    def test_a_gone_holder_younger_than_the_limit_is_waited_for(self) -> None:
        self.hold(1, os.getpid(), int(time.time()))
        self.hold(2, self.dead_pid(), int(time.time()))
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run(["/bin/bash", str(self.block)], env=self.env, capture_output=True, text=True, timeout=3)
        self.assertTrue((self.slot(2) / "owner").exists())

    def test_an_old_slot_with_no_owner_file_is_reclaimed(self) -> None:  # a holder killed between mkdir and write
        self.hold(1, os.getpid(), int(time.time()))
        self.slot(2).mkdir()
        old = time.time() - 3000
        os.utime(self.slot(2), (old, old))
        done = self.bash()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"{self.slot(2)} is stale (holder none gone", done.stderr)
        self.assertIn(f"TAKEN {self.slot(2)}", done.stdout)

    def test_a_new_slot_with_no_owner_file_yet_is_waited_for(self) -> None:  # mkdir done, owner not yet written
        self.hold(1, os.getpid(), int(time.time()))
        self.slot(2).mkdir()
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run(["/bin/bash", str(self.block)], env=self.env, capture_output=True, text=True, timeout=3)
        self.assertTrue(self.slot(2).is_dir())

    def test_a_stale_slot_another_waiter_has_just_claimed_is_left_alone(self) -> None:
        # the owner changes between this waiter's read and its clear: the fresh claim must survive
        self.hold(1, os.getpid(), int(time.time()))
        self.hold(2, self.dead_pid(), int(time.time()) - 3000)
        fresh = f"{os.getpid()} {int(time.time())} fresh/claim"
        shim = self.tmp / "bin"
        shim.mkdir()
        real_cat = shutil.which("cat")
        (shim / "cat").write_text(f'#!/bin/sh\n"{real_cat}" "$@"\n[ "$1" != "{self.slot(2)}/owner" ] || [ -f "{self.tmp}/swapped" ] || '
                                  f'{{ printf "%s\\n" "{fresh}" > "{self.slot(2)}/owner"; : > "{self.tmp}/swapped"; }}\n')
        (shim / "cat").chmod(0o755)
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run(["/bin/bash", str(self.block)], env={**self.env, "PATH": f"{shim}:{os.environ['PATH']}"},
                           capture_output=True, text=True, timeout=3)
        self.assertEqual(fresh, (self.slot(2) / "owner").read_text().strip())


if __name__ == "__main__":
    unittest.main()
