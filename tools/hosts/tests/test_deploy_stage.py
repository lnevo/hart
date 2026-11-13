"""The layout deploy in --stage-only mode, with fake hosts and no ssh.

The package is what lands on the Pi and Windows. Its layout must not change when the
repo moves the scripts around (ADR-007 amendment 2026-11-12): the host scripts stay at
cats/scripts/pi and cats/scripts/windows inside it.
"""
from __future__ import annotations

import filecmp
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SYNC = ROOT / "tools/hosts/sync_hart_package.sh"
WRAPPER = ROOT / "cats/scripts/sync_hart_package.sh"
PI_SRC = ROOT / "tools/hosts/pi"
WIN_SRC = ROOT / "tools/hosts/windows"
STAMP_KEYS = ("commit", "branch", "dirty", "dirty_paths", "tables_sha256", "tables_modified_by_deploy",
              "date", "deployed_from", "target")


def fake_bin(tmp: Path) -> Path:
    """ssh and scp that record any call and fail, so a stage that reached for the network fails."""
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    for name in ("ssh", "scp"):
        tool = bin_dir / name
        tool.write_text(f'#!/bin/sh\necho "{name} $*" >>"{tmp}/network.log"\nexit 99\n', encoding="utf-8")
        tool.chmod(0o755)
    return bin_dir


def stage_env(tmp: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(("HART_", "_hart")) or name in ("MQTT_HOST", "JMRI_JSON", "PI_HOST"):
            del env[name]
    env.update(
        PATH=f"{fake_bin(tmp)}{os.pathsep}{env.get('PATH', '')}",
        HART_ENV_FILE=str(tmp / "no-hart.env"),
        HART_PI_SSH="pi.example.invalid",
        HART_WIN_SSH="nobody@win.example.invalid",
        HART_WIN_SSH_PORT="1",
        HART_PI_USERFILES="/srv/fake-pi/JMRI_UserFiles",
        HART_WIN_USERFILES="X:/fake-win/JMRI_UserFiles",
    )
    return env


def run(script: Path, out: Path, env: dict[str, str], *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(script), *flags, "--stage-only", str(out)],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)


def read_stamp(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))


def tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


class StageOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp())
        cls.env = stage_env(cls.tmp)
        cls.out = cls.tmp / "stage"
        cls.done = run(WRAPPER, cls.out, cls.env)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_runs_without_the_network(self) -> None:
        self.assertEqual(self.done.returncode, 0, self.done.stderr[-2000:])
        self.assertFalse((self.tmp / "network.log").exists(), "stage-only called ssh or scp")
        self.assertIn("DONE (stage only)", self.done.stdout)

    def test_builds_both_packages(self) -> None:
        for host in ("pi", "win"):
            pkg = self.out / host
            self.assertTrue((pkg / "tables.xml").is_file(), host)
            self.assertTrue((pkg / "cats/panels/HART_CTC.xml").is_file(), host)
            self.assertTrue((pkg / "operations/Operations.xml").is_file(), host)

    def test_host_scripts_keep_their_package_paths(self) -> None:
        """tools/hosts/pi and tools/hosts/windows land at cats/scripts/pi and cats/scripts/windows."""
        for host in ("pi", "win"):
            for src, dest in ((PI_SRC, "cats/scripts/pi"), (WIN_SRC, "cats/scripts/windows")):
                staged = self.out / host / dest
                self.assertEqual(tree(staged), tree(src), f"{host}:{dest}")
                for name in tree(src):
                    if (src / name).is_file():
                        self.assertTrue(filecmp.cmp(src / name, staged / name, shallow=False), name)
            for name in ("install_ops_files.sh", "patch_jmri_startup.py",
                         "rewrite_button_icon_paths.py", "install_jmri_web_override.sh"):
                self.assertTrue((self.out / host / "cats/scripts" / name).is_file(), name)
        self.assertTrue(os.access(self.out / "pi/cats/scripts/pi/apply_hart_package_local.sh", os.X_OK))

    def test_apply_scripts_are_where_deploy_calls_them(self) -> None:
        source = SYNC.read_text(encoding="utf-8")
        self.assertIn("${PI_DROP}/cats/scripts/pi/apply_hart_package_local.sh", source)
        self.assertIn("\\\\cats\\\\scripts\\\\windows\\\\apply_hart_package_local.ps1", source)
        self.assertTrue((self.out / "pi/cats/scripts/pi/apply_hart_package_local.sh").is_file())
        self.assertTrue((self.out / "win/cats/scripts/windows/apply_hart_package_local.ps1").is_file())

    def test_stamp_names_what_was_shipped(self) -> None:
        dirty = bool(git("status", "--porcelain"))
        for host in ("pi", "win"):
            stamp = read_stamp(self.out / host / "cats/deploy_stamp.txt")
            self.assertEqual(tuple(stamp), STAMP_KEYS)
            self.assertEqual(stamp["commit"], git("rev-parse", "HEAD"))
            self.assertEqual(stamp["branch"], git("rev-parse", "--abbrev-ref", "HEAD"))
            self.assertEqual(stamp["dirty"], "yes" if dirty else "no")
            self.assertEqual(stamp["target"], host)
            self.assertRegex(stamp["date"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4}$")
            shipped = hashlib.sha256((self.out / host / "tables.xml").read_bytes()).hexdigest()
            self.assertEqual(stamp["tables_sha256"], shipped)
            committed = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:jmri/layouts/hart/output/tables.xml"],
                                       capture_output=True, check=True).stdout
            want = "no" if hashlib.sha256(committed).hexdigest() == shipped else "yes"
            self.assertEqual(stamp["tables_modified_by_deploy"], want)
        if dirty:
            self.assertIn("WARNING: this checkout has", self.done.stderr)

    def test_wrapper_and_script_stage_the_same_package(self) -> None:
        out = self.tmp / "direct"
        done = run(SYNC, out, self.env, "--pi")
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertFalse((out / "win").exists(), "--pi stages the Pi package only")
        self.assertEqual(tree(out / "pi"), tree(self.out / "pi"))
        cmp = filecmp.dircmp(out / "pi", self.out / "pi")

        def differing(d: filecmp.dircmp, prefix: str = "") -> list[str]:
            found = [prefix + n for n in d.diff_files]
            for name, sub in d.subdirs.items():
                found += differing(sub, f"{prefix}{name}/")
            return found

        # Only the stamp may differ (its date is taken per run).
        self.assertLessEqual(set(differing(cmp)), {"cats/deploy_stamp.txt"})


class StageOnlyRefusals(unittest.TestCase):
    def test_needs_a_folder(self) -> None:
        done = subprocess.run(["bash", str(SYNC), "--stage-only"], cwd=ROOT, capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("--stage-only needs a folder", done.stderr)

    def test_empty_equals_form_never_deploys(self) -> None:
        """--stage-only= (an unset variable) must stop, not fall through to a real deploy."""
        with tempfile.TemporaryDirectory() as tmp:
            env = stage_env(Path(tmp))
            for flags in (["--stage-only="], ["--pi", "--stage-only="], ["--stage-only", ""]):
                done = subprocess.run(["bash", str(SYNC), *flags], cwd=ROOT, env=env,
                                      capture_output=True, text=True, timeout=60)
                self.assertNotEqual(done.returncode, 0, flags)
                self.assertIn("--stage-only needs a folder", done.stderr, flags)
            self.assertFalse((Path(tmp) / "network.log").exists())

    def test_apply_steps_get_the_configured_user_files(self) -> None:
        source = SYNC.read_text(encoding="utf-8")
        self.assertIn("JMRI_USERFILES='${PI_USERFILES}'", source)
        self.assertIn('-UserFiles \\"${WIN_USERFILES}\\"', source)
        win = (WIN_SRC / "apply_hart_package_local.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$UserFiles = ''", win)
        # Only the default when the deploy passes nothing; every install path uses $UserFiles.
        self.assertEqual(win.count("Join-Path $env:USERPROFILE 'JMRI_UserFiles"), 1)
        self.assertIn("& $desk -UserFiles $UserFiles", win)

    def test_refuses_a_folder_with_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            keep = Path(tmp) / "keep.txt"
            keep.write_text("mine", encoding="utf-8")
            done = subprocess.run(["bash", str(SYNC), "--stage-only", tmp], cwd=ROOT,
                                  capture_output=True, text=True)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("is not empty", done.stderr)
            self.assertEqual(keep.read_text(encoding="utf-8"), "mine")


class HostApplyInstallsStampLast(unittest.TestCase):
    def test_pi(self) -> None:
        source = (PI_SRC / "apply_hart_package_local.sh").read_text(encoding="utf-8")
        stamp = source.index('cp -f "$HART/cats/deploy_stamp.txt" "$CATS_HOME/deploy_stamp.txt"')
        self.assertGreater(stamp, source.index("install_desktop_icons.sh"))
        self.assertGreater(stamp, source.index("install_ops_files.sh"))

    def test_windows(self) -> None:
        source = (WIN_SRC / "apply_hart_package_local.ps1").read_text(encoding="utf-8")
        stamp = source.index("'cats\\deploy_stamp.txt'")
        self.assertGreater(stamp, source.index("& $desk"))
        self.assertIn("Join-Path $catsHome 'deploy_stamp.txt'", source)


if __name__ == "__main__":
    unittest.main()


class DirtyListUnderPipefail(unittest.TestCase):
    """A long dirty-path list must warn, not kill the deploy with SIGPIPE (exit 141)."""

    def test_long_list_prints_ten_and_exits_zero(self) -> None:
        line = next(l for l in SYNC.read_text(encoding="utf-8").splitlines()
                    if 'printf \'%s\\n\' "$DEPLOY_CHANGES" |' in l and "wc -l" not in l)
        script = ("set -euo pipefail\n"
                  "DEPLOY_CHANGES=\"$(seq 1 20000 | sed 's/^/ M file/')\"\n"
                  + line.strip() + "\necho done\n")
        done = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines()[-1], "done")
        self.assertEqual(len(done.stdout.splitlines()), 11)
