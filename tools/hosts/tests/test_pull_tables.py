"""make tables-pull and tables-pull-pi (tools/ops/pull_tables.sh, pull_tables_pi.sh) never copy a Store over the
generated tables.xml (ADR-029). A Store that differs from what was last deployed or pulled (or, with no reference
at all, from the generated tables.xml) is kept once per hash in the pulled folder, ~/JMRI_UserFiles-pulled
(HART_PULLED_DIR), outside every checkout, with STORE.base naming what the host had before (tables_base.sh). It is
not recorded as taken (R9d): the deploy stays stopped until tools/schematic/split_store.py has split it in and
store_splits.csv names its hash, and then the pull finds nothing to take.

Each script runs from a copy in a temporary checkout, with a temporary HOME and, for the Pi, ssh and scp stand-ins
that run against a local folder and log every call: nothing reaches a host or the repo."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GENERATED = "<layout-config>\n  <sensors />\n</layout-config>\n"
STORE = "<layout-config>\n  <sensors />\n  <filehistory />\n</layout-config>\n"
COMMIT = "7f2d3e262e921d6a203878c19822859af0a1c8c0"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class PullCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "checkout"
        for rel in ("tools/ops/pull_tables.sh", "tools/ops/pull_tables_pi.sh", "tools/env/load_env.sh",
                    "tools/env/defaults.env", "tools/hosts/pi/unpulled_changes.sh", "tools/hosts/pi/tables_base.sh",
                    "tools/hosts/profile_tables_guard.sh"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, self.root / rel)
        self.tables = self.root / "jmri/layouts/hart/output/tables.xml"
        self.tables.parent.mkdir(parents=True)
        self.tables.write_text(GENERATED, encoding="utf-8")
        self.home = self.tmp / "home"
        self.uf = self.home / "JMRI_UserFiles"
        self.uf.mkdir(parents=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.pi_uf = self.tmp / "pi/JMRI_UserFiles"
        self.pi_uf.mkdir(parents=True)
        # scp copies the Pi's local stand-in file; ssh runs its command here, as the Pi would
        (self.bin / "scp").write_text(f'#!/bin/bash\necho "scp $*" >>"{self.tmp}/network.log"\n'
                                      f'cp "{self.pi_uf}/tables.xml" "${{@: -1}}"\n', encoding="utf-8")
        (self.bin / "ssh").write_text(f'#!/bin/bash\necho "ssh $*" >>"{self.tmp}/network.log"\nshift\n'
                                      'exec bash -c "$*"\n', encoding="utf-8")
        for tool in ("scp", "ssh"):
            (self.bin / tool).chmod(0o755)

    def run_pull(self, script: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HART_", "_hart"))}
        env.update(HOME=str(self.home), PATH=f"{self.bin}{os.pathsep}{env['PATH']}",
                   HART_ENV_FILE=str(self.tmp / "none.env"), HART_PI_SSH="pi.example.invalid",
                   HART_PI_USERFILES=str(self.pi_uf))
        return subprocess.run(["bash", str(self.root / "tools/ops" / script)], env=env, cwd=self.tmp,
                              capture_output=True, text=True, timeout=60)

    def pulled(self) -> list[Path]:
        folder = self.home / "JMRI_UserFiles-pulled"            # the default, outside the checkout
        return sorted(p for p in folder.iterdir() if p.suffix == ".xml") if folder.exists() else []

    def stamp(self, uf: Path, tables_sha: str) -> None:
        (uf / "cats").mkdir(exist_ok=True)
        (uf / "cats/deploy_stamp.txt").write_text(f"commit={COMMIT}\ntables_sha256={tables_sha}\n", encoding="utf-8")

    def split_in(self, text: str) -> None:
        splits = self.root / "jmri/layouts/hart/data/store_splits.csv"
        splits.parent.mkdir(parents=True, exist_ok=True)
        splits.write_text("store_sha256,host,store_file,base,plan,split_date\n"
                          f"{sha(text)},pi,pi-1.xml,none,abc,2026-11-20\n", encoding="utf-8")


class MacPull(PullCase):
    def test_a_store_is_kept_with_its_base_and_not_taken(self) -> None:
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        self.stamp(self.uf, sha(GENERATED))
        done = self.run_pull("pull_tables.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(GENERATED, self.tables.read_text(encoding="utf-8"))      # never replaced
        [saved] = self.pulled()
        self.assertTrue(saved.name.startswith("mac-"), saved)
        self.assertEqual(STORE, saved.read_text(encoding="utf-8"))
        self.assertEqual(f"deploy {sha(GENERATED)} {COMMIT}", Path(f"{saved}.base").read_text().strip())
        self.assertFalse((self.uf / ".tables_deployed.sha256").exists())          # not recorded as taken
        for words in ("not recorded as taken", "split_store.py", "make wt"):
            self.assertIn(words, done.stdout)
        again = self.run_pull("pull_tables.sh")                                     # the same Store: kept once
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertIn(str(saved), again.stdout)
        self.assertEqual([saved], self.pulled())

    def test_a_second_pull_names_the_base_the_store_was_kept_with(self) -> None:
        """The stamp moved on between two pulls of the same Store: the kept .base wins, and the message says so."""
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        self.stamp(self.uf, sha(GENERATED))
        self.assertEqual(0, self.run_pull("pull_tables.sh").returncode)
        [saved] = self.pulled()
        first = f"deploy {sha(GENERATED)} {COMMIT}"
        self.stamp(self.uf, sha("<later/>"))
        again = self.run_pull("pull_tables.sh")
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertEqual(first, Path(f"{saved}.base").read_text().strip())
        self.assertIn(f"its base ({first})", again.stdout)
        self.assertNotIn(sha("<later/>"), again.stdout)

    def test_a_base_not_known_at_the_first_pull_is_taken_at_the_next(self) -> None:
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        self.assertEqual(0, self.run_pull("pull_tables.sh").returncode)
        [saved] = self.pulled()
        self.assertEqual("none", Path(f"{saved}.base").read_text().strip())
        self.stamp(self.uf, sha(GENERATED))
        again = self.run_pull("pull_tables.sh")
        self.assertEqual(0, again.returncode, again.stderr)
        self.assertEqual(f"deploy {sha(GENERATED)} {COMMIT}", Path(f"{saved}.base").read_text().strip())
        self.assertEqual([saved], self.pulled())

    def test_a_store_split_in_is_nothing_to_pull(self) -> None:
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        self.stamp(self.uf, sha(GENERATED))
        self.split_in(STORE)
        done = self.run_pull("pull_tables.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Nothing to pull", done.stdout)
        self.assertEqual([], self.pulled())

    def test_the_last_deployed_hash_decides_not_the_repo_file(self) -> None:
        """The profile holds what was last deployed, though the repo's generated file has moved on since: nothing
        to pull."""
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        (self.uf / ".tables_deployed.sha256").write_text(sha(STORE) + "\n", encoding="utf-8")
        done = self.run_pull("pull_tables.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Nothing to pull", done.stdout)
        self.assertEqual([], self.pulled())

    def test_with_no_reference_a_store_unlike_the_generated_file_is_kept(self) -> None:
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        done = self.run_pull("pull_tables.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        [saved] = self.pulled()
        self.assertEqual("none", Path(f"{saved}.base").read_text().strip())
        (self.uf / "tables.xml").write_text(GENERATED, encoding="utf-8")      # the generated bytes: nothing to take
        self.assertIn("Nothing to pull", self.run_pull("pull_tables.sh").stdout)

    def test_a_failed_check_is_never_nothing_to_pull(self) -> None:
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        (self.root / "tools/hosts/pi/unpulled_changes.sh").write_text("exit 7\n", encoding="utf-8")
        done = self.run_pull("pull_tables.sh")
        self.assertEqual(1, done.returncode)
        self.assertIn("Could not check", done.stderr)
        self.assertNotIn("Nothing to pull", done.stdout)

    def test_a_pulled_folder_inside_a_checkout_is_refused(self) -> None:
        (self.uf / "tables.xml").write_text(STORE, encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        env_dir = self.root / "kept"
        done = subprocess.run(["bash", str(self.root / "tools/ops/pull_tables.sh")], capture_output=True,
                              text=True, timeout=60, cwd=self.tmp,
                              env={**{k: v for k, v in os.environ.items() if not k.startswith("HART_")},
                                   "HOME": str(self.home), "HART_PULLED_DIR": str(env_dir)})
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("inside a git checkout", done.stderr)
        self.assertFalse(env_dir.exists())


class PiPull(PullCase):
    def unpulled(self, *split: str) -> str:
        return subprocess.run(["bash", str(ROOT / "tools/hosts/pi/unpulled_changes.sh"), str(self.pi_uf), "",
                               *split], capture_output=True, text=True).stdout.strip()

    def test_a_store_is_kept_and_the_deploy_still_stops(self) -> None:
        (self.pi_uf / "tables.xml").write_text(STORE, encoding="utf-8")
        self.stamp(self.pi_uf, sha(GENERATED))
        done = self.run_pull("pull_tables_pi.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(GENERATED, self.tables.read_text(encoding="utf-8"))
        [saved] = self.pulled()
        self.assertTrue(saved.name.startswith("pi-"), saved)
        self.assertEqual(STORE, saved.read_text(encoding="utf-8"))
        self.assertEqual(f"deploy {sha(GENERATED)} {COMMIT}", Path(f"{saved}.base").read_text().strip())
        self.assertFalse((self.pi_uf / ".tables_deployed.sha256").exists())
        self.assertIn("deploys to the Pi stay stopped", done.stdout)
        self.assertEqual("tables", self.unpulled())                     # the deploy's own check still stops
        self.assertEqual("", self.unpulled(sha("<other/>"), sha(STORE)))  # until a split names the Store

    def test_a_store_split_in_is_nothing_to_pull(self) -> None:
        (self.pi_uf / "tables.xml").write_text(STORE, encoding="utf-8")
        self.stamp(self.pi_uf, sha(GENERATED))
        self.split_in(STORE)
        done = self.run_pull("pull_tables_pi.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Nothing to pull", done.stdout)
        self.assertEqual([], self.pulled())

    def test_an_earlier_pull_is_the_base(self) -> None:
        """A pull from before R9d recorded its Store as taken (.tables_deployed.sha256, newer than the stamp): that
        Store is the base."""
        (self.pi_uf / "tables.xml").write_text(STORE, encoding="utf-8")
        self.stamp(self.pi_uf, sha(GENERATED))
        taken = self.pi_uf / ".tables_deployed.sha256"
        taken.write_text(sha("<earlier/>") + "\n", encoding="utf-8")
        os.utime(self.pi_uf / "cats/deploy_stamp.txt", (1, 1))
        done = self.run_pull("pull_tables_pi.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        [saved] = self.pulled()
        self.assertEqual(f"store {sha('<earlier/>')}", Path(f"{saved}.base").read_text().strip())

    def test_nothing_unpulled_takes_nothing(self) -> None:
        (self.pi_uf / "tables.xml").write_text(STORE, encoding="utf-8")
        (self.pi_uf / ".tables_deployed.sha256").write_text(sha(STORE) + "\n", encoding="utf-8")
        done = self.run_pull("pull_tables_pi.sh")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Nothing to pull", done.stdout)
        self.assertEqual([], self.pulled())
        calls = (self.tmp / "network.log").read_text().splitlines()
        self.assertFalse([c for c in calls if c.startswith("scp ")], calls)


if __name__ == "__main__":
    unittest.main()
