"""The DecoderPro roster as a repo master (ADR-039 amendment 2026-11-26, lane N8).

WHY: DecoderPro writes the roster on the Pi (a programming session, a new loco), and a deploy now installs the repo's
roster over it. These tests pin the pieces that keep a Pi session from being lost: the one roster hash
(tools/hosts/pi/roster_sha.sh), the Pi check's "roster" word (unpulled_changes.sh), the install
(install_roster.sh), the real deploy gate stopping on it, and the pull (tools/ops/pull_roster.sh).

Everything runs on temporary folders, private clones and an ssh stand-in that runs the piped script here against a
fake JMRI_UserFiles: nothing reaches a host, the live checkout or ~/JMRI_UserFiles.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_deploy_gates import GateHarness  # noqa: E402  (the gate harness: recorders, autopull stand-ins)
from test_deploy_stage import keep_repo_tables, stage_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
SHA = ROOT / "tools/hosts/pi/roster_sha.sh"
INSTALL = ROOT / "tools/hosts/pi/install_roster.sh"
CHECK = ROOT / "tools/hosts/pi/unpulled_changes.sh"
SYNC = ROOT / "tools/hosts/sync_hart_package.sh"
MASTER = ROOT / "jmri/layouts/hart/roster"

INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<roster-config>
  <roster>
{entries}
  </roster>
</roster-config>
"""
ENTRY = """<?xml version="1.0" encoding="UTF-8"?>
<locomotive-config>
  <locomotive id="{id}" fileName="{file}" dccAddress="{addr}">
    <locoaddress>
      <dcclocoaddress number="{addr}" longaddress="yes" />
    </locoaddress>
  </locomotive>
</locomotive-config>
"""


def write_roster(folder: Path, locos: dict[str, tuple[str, str]]) -> None:
    """A roster at folder: roster.xml and roster/<file> for each id -> (file, address)."""
    (folder / "roster").mkdir(parents=True, exist_ok=True)
    lines = [f'    <locomotive id="{i}" fileName="{f}" dccAddress="{a}">\n    </locomotive>' for i, (f, a) in locos.items()]
    (folder / "roster.xml").write_text(INDEX.format(entries="\n".join(lines)), encoding="utf-8")
    for i, (f, a) in locos.items():
        (folder / "roster" / f).write_text(ENTRY.format(id=i, file=f, addr=a), encoding="utf-8")


def roster_sha(folder: Path) -> str:
    return subprocess.run(["bash", str(SHA), str(folder)], capture_output=True, text=True, check=True).stdout.strip()


TWO = {"CSX 2121": ("2121.xml", "2121"), "BO 2235": ("22350.xml", "2235")}


class Temp(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)


class RosterHash(Temp):
    def test_only_roster_xml_and_the_files_it_names_count(self) -> None:
        """JMRI's .bak files and old entry files (the Mac and Windows keep 13) do not change the hash."""
        write_roster(self.tmp, TWO)
        before = roster_sha(self.tmp)
        (self.tmp / "roster/2121.xml.bak").write_text("old")
        (self.tmp / "roster/2235.xml").write_text("old naming, not named by roster.xml")
        (self.tmp / "roster.xml.bak").write_text("old")
        self.assertEqual(before, roster_sha(self.tmp))
        (self.tmp / "roster/22350.xml").write_text("a programming session")
        self.assertNotEqual(before, roster_sha(self.tmp))

    def test_a_named_file_that_is_missing_changes_the_hash(self) -> None:
        write_roster(self.tmp, TWO)
        before = roster_sha(self.tmp)
        (self.tmp / "roster/2121.xml").unlink()
        self.assertNotEqual(before, roster_sha(self.tmp))

    def test_no_roster_is_none(self) -> None:
        self.assertEqual("none", roster_sha(self.tmp))

    def test_a_path_in_a_file_name_is_refused(self) -> None:
        write_roster(self.tmp, {"X 1": ("../evil.xml", "1")})
        done = subprocess.run(["bash", str(SHA), str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(1, done.returncode)
        self.assertIn("not a plain roster/*.xml file name", done.stderr)

    def test_the_repo_master_hashes(self) -> None:
        self.assertRegex(roster_sha(MASTER), r"^[0-9a-f]{64}$")


class PiCheckNamesTheRoster(Temp):
    """unpulled_changes.sh with roster:<repo sha>: "roster" when the Pi's roster is neither the repo's nor the one the
    last deploy installed (.roster_deployed.sha256)."""

    def setUp(self) -> None:
        super().setUp()
        self.uf = self.tmp / "uf"
        write_roster(self.uf, TWO)
        self.deployed = roster_sha(self.uf)
        (self.uf / ".roster_deployed.sha256").write_text(self.deployed + "\n")

    def words(self, repo_sha: str | None) -> list[str]:
        args = ["", f"roster:{repo_sha}"] if repo_sha else []
        done = subprocess.run(["bash", str(CHECK), str(self.uf), *args], capture_output=True, text=True, check=True)
        return done.stdout.split()

    def program(self) -> None:
        (self.uf / "roster/2121.xml").write_text(ENTRY.format(id="CSX 2121", file="2121.xml", addr="2121") + "<!-- CVs -->")

    def test_clean_after_a_deploy(self) -> None:
        self.assertEqual([], self.words("0" * 64))

    def test_a_programming_session_is_named(self) -> None:
        self.program()
        self.assertEqual(["roster"], self.words("0" * 64))

    def test_a_session_the_repo_holds_is_taken(self) -> None:
        self.program()
        self.assertEqual([], self.words(roster_sha(self.uf)))

    def test_with_no_stamp_only_the_repo_counts(self) -> None:
        """The first deploy: no stamp on the Pi. Equal to the repo is clean; anything else may be a session."""
        (self.uf / ".roster_deployed.sha256").unlink()
        self.assertEqual([], self.words(self.deployed))
        self.assertEqual(["roster"], self.words("0" * 64))

    def test_old_entry_files_do_not_count(self) -> None:
        (self.uf / "roster/2235.xml").write_text("old naming")
        (self.uf / "roster/2121.xml.bak").write_text("backup")
        self.assertEqual([], self.words("0" * 64))

    def test_a_pi_without_a_roster_has_nothing_to_keep(self) -> None:
        (self.uf / "roster.xml").unlink()
        self.assertEqual([], self.words("0" * 64))

    def test_without_roster_sha_the_roster_is_not_asked(self) -> None:
        """The Store pulls pass no roster:<sha>; they ask only for tables."""
        self.program()
        self.assertEqual([], self.words(None))

    def test_a_roster_xml_naming_a_bad_file_is_changed_not_a_failed_check(self) -> None:
        """Review finding 7: roster_sha fails on a path in fileName; the check still answers, with the other words."""
        idx = self.uf / "roster.xml"
        idx.write_text(idx.read_text().replace('fileName="2121.xml"', 'fileName="../2121.xml"'))
        (self.uf / "tables.xml").write_text("<a Store/>")
        (self.uf / "cats").mkdir()
        (self.uf / "cats/deploy_stamp.txt").write_text("tables_sha256=" + "0" * 64 + "\n")
        done = subprocess.run(["bash", str(CHECK), str(self.uf), "", "roster:" + "0" * 64], capture_output=True,
                              text=True)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["tables", "roster"], done.stdout.split())

    def test_piped_with_roster_sha_in_front_as_the_gate_sends_it(self) -> None:
        self.program()
        script = SHA.read_text() + CHECK.read_text()
        done = subprocess.run(["bash", "-s", "--", str(self.uf), "", "roster:" + "0" * 64], input=script,
                              cwd=self.tmp, capture_output=True, text=True, check=True)
        self.assertEqual(["roster"], done.stdout.split())


class Install(Temp):
    def setUp(self) -> None:
        super().setUp()
        self.src = self.tmp / "src"
        self.uf = self.tmp / "uf"
        write_roster(self.src, TWO)

    def install(self) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(INSTALL), str(self.src), str(self.uf)], capture_output=True, text=True)

    def test_installs_and_stamps(self) -> None:
        done = self.install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(roster_sha(self.src), roster_sha(self.uf))
        self.assertEqual(roster_sha(self.src), (self.uf / ".roster_deployed.sha256").read_text().strip())
        self.assertIn("already current", self.install().stdout)

    def test_backs_up_what_it_replaces_and_leaves_unnamed_files(self) -> None:
        write_roster(self.uf, {"CSX 2121": ("2121.xml", "2121")})
        (self.uf / "roster/2121.xml").write_text("the host's own copy")
        (self.uf / "roster/2121.xml.bak").write_text("JMRI backup")
        (self.uf / "roster/2235.xml").write_text("old naming")
        done = self.install()
        self.assertEqual(0, done.returncode, done.stderr)
        backups = list((self.uf / "backups/roster").iterdir())
        self.assertEqual(1, len(backups))
        self.assertEqual("the host's own copy", (backups[0] / "roster/2121.xml").read_text())
        self.assertTrue((backups[0] / "roster.xml").is_file())
        self.assertEqual("JMRI backup", (self.uf / "roster/2121.xml.bak").read_text())
        self.assertEqual("old naming", (self.uf / "roster/2235.xml").read_text())
        self.assertEqual(roster_sha(self.src), roster_sha(self.uf))

    def test_a_package_naming_a_missing_file_installs_nothing(self) -> None:
        (self.src / "roster/22350.xml").unlink()
        done = self.install()
        self.assertEqual(1, done.returncode)
        self.assertIn("names roster/22350.xml, which is not in", done.stderr)
        self.assertFalse(self.uf.exists())

    def test_no_roster_in_the_package_installs_nothing(self) -> None:
        (self.src / "roster.xml").unlink()
        done = self.install()
        self.assertEqual(1, done.returncode)
        self.assertIn("STOP: no roster.xml in", done.stderr)


class DeployStopsOnAnUnpulledRoster(Temp):
    """The real gate (sync_hart_package.sh --pi) against a fake Pi: a roster DecoderPro changed since the last deploy
    stops it before anything is sent, and names make roster-pull. HART_NO_AUTOPULL=1 (stage_env): the plain stop."""

    def setUp(self) -> None:
        super().setUp()
        self.uf = self.tmp / "uf"
        self.uf.mkdir()
        self.env = stage_env(self.tmp)
        self.env.update(HOME=str(self.tmp / "home"), HART_PI_USERFILES=str(self.uf), HART_NO_AUTOPULL="1")
        keep_repo_tables(self.tmp)
        (self.tmp / "bin/ssh").write_text(
            "#!/bin/bash\n"
            f'echo "ssh $*" >>"{self.tmp}/network.log"\n'
            'cmd="${@: -1}"\n'
            '[[ "$cmd" == true ]] && exit 0\n'
            "if [[ \"$cmd\" == \"bash -s -- '\"* ]]; then eval \"exec $cmd\"; fi\n"
            "exit 99\n", encoding="utf-8")
        # the Pi as the last deploy left it: the repo's roster and its stamp
        shutil.copytree(MASTER, self.uf, dirs_exist_ok=True)
        (self.uf / ".roster_deployed.sha256").write_text(roster_sha(self.uf) + "\n")

    def deploy(self) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(SYNC), "--pi", "--check-pi-only"], cwd=ROOT, env=self.env,
                              capture_output=True, text=True, timeout=600)

    def test_clean_roster_passes(self) -> None:
        done = self.deploy()
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        self.assertIn("nothing unpulled", done.stdout)

    def test_a_programming_session_stops_it(self) -> None:
        entry = sorted((self.uf / "roster").glob("*.xml"))[0]
        entry.write_text(entry.read_text() + "<!-- new CV values -->\n")
        done = self.deploy()
        self.assertEqual(1, done.returncode, done.stderr[-2000:])
        self.assertIn("STOP: the Pi's DecoderPro roster changed since the last deploy", done.stderr)
        self.assertIn("make roster-pull", done.stderr)
        calls = (self.tmp / "network.log").read_text().splitlines()
        self.assertFalse(any(c.startswith(("rsync", "scp")) for c in calls), calls)


class PiRosterIsSavedByTheGate(GateHarness):
    """A DecoderPro roster changed on the Pi (lane N8): the plain stop names make roster-pull; the gate's own pull
    runs tools/ops/pull_roster.sh (no PanelPro quit: it only reads) into the same checkout or worktree as an
    Operations pull, and the deploy still stops with nothing shipped."""

    def setUp(self) -> None:
        """GateHarness's autopull stand-ins plus one for tools/ops/pull_roster.sh: it logs where it ran, fails while
        fail_roster exists and exits 3 (pulled, check_roster.py found a problem) while check_roster exists."""
        super().setUp()
        d, log, t = self.tmp / "autopull", self.tmp / "autopull.log", self.tmp
        (d / "roster.sh").write_text(
            f'echo "roster in $(pwd) $* from_main=$HART_AUTOPULL_FROM_MAIN" >>"{log}"\n'
            f'[[ ! -f "{t}/fail_roster" ]] || {{ echo "ssh dropped" >&2; exit 1; }}\n'
            'echo "Pulled: the Pi\'s DecoderPro roster (abc) -> $(pwd)/jmri/layouts/hart/roster"\n'
            f'[[ ! -f "{t}/check_roster" ]] || {{ echo "FAIL     ZZ 1: no locos.csv row"; exit 3; }}\n', encoding="utf-8")
        self.env["HART_AUTOPULL_ROSTER"] = str(d / "roster.sh")

    def test_the_plain_stop_names_the_roster_pull(self) -> None:
        self.env["HART_NO_AUTOPULL"] = "1"
        self.unpulled("roster")
        done = self.deploy("--pi", "--win")
        self.assertIn("STOP: the Pi's DecoderPro roster changed since the last deploy", done.stderr)
        self.assertIn("make roster-pull", done.stderr)
        self.assertNotIn("make ops-pull", done.stderr)
        self.assertEqual([], self.autopull_log())
        self.assert_nothing_shipped(done)

    def test_the_roster_is_pulled_without_a_quit_then_the_deploy_stops(self) -> None:
        self.unpulled("roster")
        done = self.deploy("--pi")
        self.assertEqual([f"roster in {ROOT}  from_main=0"], self.autopull_log())
        self.assertIn(f"brought the Pi's DecoderPro roster into {ROOT}/jmri/layouts/hart/roster; review, commit and "
                      "merge it, then deploy", done.stderr)
        self.assertIn("STOP: the Pi's changes are saved, not shipped.", done.stderr)
        self.assert_nothing_shipped(done)

    def test_from_main_operations_and_roster_share_one_new_worktree(self) -> None:
        self.env["HART_AUTOPULL_FROM_MAIN"] = "1"
        self.unpulled("ops", "roster")
        done = self.deploy("--pi")
        log = self.autopull_log()
        self.assertEqual(4, len(log), log)
        self.assertRegex(log[1], r"^newwt ops-pull-\d{8}-\d{6}$")
        wt = self.tmp / "wt" / log[1].split()[1]
        self.assertEqual([f"ops in {wt} --no-mark", f"roster in {wt}  from_main=0"], log[2:])
        self.assertIn(f"into {wt}/jmri/layouts/hart/roster", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_failed_roster_pull_says_nothing_was_kept_and_drops_its_worktree(self) -> None:
        self.env["HART_AUTOPULL_FROM_MAIN"] = "1"
        (self.tmp / "fail_roster").touch()
        self.unpulled("roster")
        done = self.deploy("--pi")
        self.assertIn("the pull of the Pi's DecoderPro roster failed (see above); nothing was kept for it", done.stderr)
        topic = self.autopull_log()[0].split()[1]
        self.assertIn(f"rmwt {topic}", self.autopull_log())
        self.assertNotIn("brought the Pi's DecoderPro roster", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_failed_roster_pull_keeps_a_worktree_the_operations_pull_wrote(self) -> None:
        self.env["HART_AUTOPULL_FROM_MAIN"] = "1"
        (self.tmp / "fail_roster").touch()
        self.unpulled("ops", "roster")
        done = self.deploy("--pi")
        self.assertFalse(any(c.startswith("rmwt") for c in self.autopull_log()), self.autopull_log())
        self.assertIn("brought the Pi's Operations session into", done.stderr)
        self.assertIn("keeps the other pull", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_pull_whose_link_check_failed_still_counts_as_kept(self) -> None:
        (self.tmp / "check_roster").touch()
        self.unpulled("roster")
        done = self.deploy("--pi")
        self.assertIn("brought the Pi's DecoderPro roster into", done.stderr)
        self.assertIn("check_roster.py found problems (see above): fix locos.csv", done.stderr)
        self.assertNotIn("the pull failed", done.stderr)
        self.assert_nothing_shipped(done)

    def test_a_reused_worktree_without_the_roster_pull_says_so(self) -> None:
        """Review finding 2: a worktree from before this change has no pull_roster.sh; the stop names it."""
        self.env["HART_AUTOPULL_FROM_MAIN"] = "1"
        del self.env["HART_AUTOPULL_ROSTER"]
        self.unpulled("roster")
        done = self.deploy("--pi")
        self.assertIn("is from before the roster pull (no tools/ops/pull_roster.sh); nothing was kept for the "
                      "DecoderPro roster", done.stderr)
        self.assertNotIn("brought the Pi's DecoderPro roster", done.stderr)
        self.assert_nothing_shipped(done)

    def test_the_gate_asks_with_the_hash_of_the_roster_it_would_ship(self) -> None:
        self.unpulled("roster")
        self.deploy("--pi")
        asks = [c for c in self.calls() if "bash -s -- '" in c]
        sha = ROOT / "tools/hosts/pi/roster_sha.sh"
        want = subprocess.run(["bash", str(sha), str(ROOT / "jmri/layouts/hart/roster")],
                              capture_output=True, text=True, check=True).stdout.strip()
        self.assertTrue(asks and f" roster:{want}" in asks[0], asks)


def private_clone(tmp: Path) -> Path:
    """A clone of HEAD with this checkout's pull, check, host scripts, roster master and locos.csv copied in, so the
    pull writes into the clone, never into the live checkout."""
    repo = tmp / "repo"
    subprocess.run(["git", "clone", "-q", "--shared", str(ROOT), str(repo)], check=True, capture_output=True)
    for rel in ("tools/hosts", "jmri/layouts/hart/roster"):
        shutil.copytree(ROOT / rel, repo / rel, dirs_exist_ok=True)
    for rel in ("tools/ops/pull_roster.sh", "tools/ops/check_roster.py", "ops/hart-ops/data/locos.csv"):
        shutil.copy2(ROOT / rel, repo / rel)
    return repo


class Pull(Temp):
    """tools/ops/pull_roster.sh against a fake Pi (the ssh stand-in runs the piped script here)."""

    def setUp(self) -> None:
        super().setUp()
        self.repo = private_clone(self.tmp)
        self.uf = self.tmp / "pi-uf"
        shutil.copytree(MASTER, self.uf)
        bins = self.tmp / "bin"
        bins.mkdir()
        self.log = self.tmp / "ssh.log"
        (bins / "ssh").write_text(
            "#!/bin/bash\n"
            f'echo "ssh ${{@: -1}}" >>"{self.log}"\n'
            'cmd="${@: -1}"\n'
            "if [[ \"$cmd\" == \"bash -s -- '\"* ]]; then eval \"exec $cmd\"; fi\n"
            "exit 99\n", encoding="utf-8")
        (bins / "ssh").chmod(0o755)
        self.env = dict(os.environ, PATH=f"{bins}{os.pathsep}{os.environ['PATH']}",
                        HART_ENV_FILE=str(self.tmp / "none"), HART_PI_SSH="pi.example.invalid",
                        HART_PI_USERFILES=str(self.uf), HART_AUTOPULL_FROM_MAIN="0", HART_SSH_MUX="0")

    def pull(self) -> subprocess.CompletedProcess:
        self.before = self.master_files()
        return subprocess.run(["bash", str(self.repo / "tools/ops/pull_roster.sh")], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, timeout=300)

    def master_files(self) -> dict[str, bytes]:
        """The clone's roster master, file by file (it may be untracked until the master is committed)."""
        m = self.repo / "jmri/layouts/hart/roster"
        return {p.relative_to(m).as_posix(): p.read_bytes() for p in m.rglob("*") if p.is_file()}

    def test_a_clean_pi_says_so_and_changes_nothing(self) -> None:
        before = roster_sha(self.repo / "jmri/layouts/hart/roster")
        done = self.pull()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Nothing to pull: the Pi's DecoderPro roster is the repo's", done.stdout)
        self.assertEqual(before, roster_sha(self.repo / "jmri/layouts/hart/roster"))

    def test_a_session_is_copied_and_the_pi_is_not_written(self) -> None:
        entry = sorted((self.uf / "roster").glob("*.xml"))[0]
        entry.write_text(entry.read_text().replace("</locomotive-config>", "<!-- CVs --></locomotive-config>"))
        (self.uf / "roster" / "2235.xml").write_text("old naming: not named, never pulled")
        pi_before = {p: p.read_bytes() for p in self.uf.rglob("*") if p.is_file()}
        done = self.pull()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("Pulled: the Pi's DecoderPro roster", done.stdout)
        self.assertEqual(roster_sha(self.uf), roster_sha(self.repo / "jmri/layouts/hart/roster"))
        self.assertFalse((self.repo / "jmri/layouts/hart/roster/roster/2235.xml").exists())
        self.assertEqual(pi_before, {p: p.read_bytes() for p in self.uf.rglob("*") if p.is_file()},
                         "the pull wrote on the Pi")
        self.assertFalse((self.uf / ".roster_deployed.sha256").exists(), "the pull marked the Pi")

    def test_a_pi_without_a_roster_pulls_nothing(self) -> None:
        (self.uf / "roster.xml").unlink()
        done = self.pull()
        self.assertEqual(1, done.returncode)
        self.assertIn("STOP: the Pi has no", done.stderr)
        self.assertEqual(self.before, self.master_files(), "the pull changed the master")

    def test_a_new_loco_the_master_lacks_keeps_the_files_and_exits_3(self) -> None:
        idx = self.uf / "roster.xml"
        idx.write_text(idx.read_text().replace(
            "  </roster>", '    <locomotive id="ZZ 1" fileName="ZZ1.xml" dccAddress="1">\n    </locomotive>\n  </roster>'))
        (self.uf / "roster/ZZ1.xml").write_text(ENTRY.format(id="ZZ 1", file="ZZ1.xml", addr="1"))
        done = self.pull()
        self.assertEqual(3, done.returncode, done.stdout + done.stderr)
        self.assertIn("ZZ 1: no locos.csv row has this roster_id", done.stdout)
        self.assertTrue((self.repo / "jmri/layouts/hart/roster/roster/ZZ1.xml").is_file())

    def test_a_named_file_the_pi_lacks_pulls_nothing(self) -> None:
        entry = sorted((self.uf / "roster").glob("*.xml"))[0]
        entry.unlink()
        done = self.pull()
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("could not copy the Pi's roster", done.stderr)
        self.assertEqual(self.before, self.master_files(), "the pull changed the master")

    def from_main(self, target: Path | None) -> Path:
        """Run as from the main checkout; the worktree maker logs its call and prints target (or fails)."""
        newwt = self.tmp / "newwt.sh"
        calls = self.tmp / "newwt.log"
        newwt.write_text(f'echo "$1" >>"{calls}"\n' + (f'echo "{target}"\n' if target else "exit 1\n"))
        self.env.update(HART_AUTOPULL_FROM_MAIN="1", HART_AUTOPULL_NEWWT=str(newwt),
                        HART_AUTOPULL_WT_DIR=str(self.tmp / "wt"))
        return calls

    def test_from_the_main_checkout_nothing_to_pull_makes_no_worktree(self) -> None:
        """Review finding 1: a clean Pi, or a pull that stops, leaves no ops-pull-* worktree behind."""
        calls = self.from_main(self.tmp / "unused")
        done = self.pull()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Nothing to pull", done.stdout)
        self.assertFalse(calls.exists(), "a worktree was made for nothing")
        (self.uf / "roster.xml").unlink()
        self.assertEqual(1, self.pull().returncode)
        self.assertFalse(calls.exists(), "a worktree was made for a pull that stopped")

    def test_from_the_main_checkout_a_session_goes_into_the_worktree(self) -> None:
        wt = private_clone(self.tmp / "wtclone")
        calls = self.from_main(wt)
        entry = sorted((self.uf / "roster").glob("*.xml"))[0]
        entry.write_text(entry.read_text().replace("</locomotive-config>", "<!-- CVs --></locomotive-config>"))
        done = self.pull()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(1, len(calls.read_text().splitlines()))
        self.assertEqual(roster_sha(self.uf), roster_sha(wt / "jmri/layouts/hart/roster"))
        self.assertEqual(self.before, self.master_files(), "the main checkout's master changed")

    def test_from_the_main_checkout_a_failed_worktree_pulls_nothing(self) -> None:
        entry = sorted((self.uf / "roster").glob("*.xml"))[0]
        entry.write_text(entry.read_text() + "<!-- CVs -->")
        newwt = self.tmp / "newwt.sh"
        newwt.write_text("exit 1\n")
        self.env.update(HART_AUTOPULL_FROM_MAIN="1", HART_AUTOPULL_NEWWT=str(newwt),
                        HART_AUTOPULL_WT_DIR=str(self.tmp / "wt"))
        done = self.pull()
        self.assertEqual(1, done.returncode)
        self.assertIn("could not make the worktree ops-pull-", done.stderr)
        self.assertEqual(self.before, self.master_files(), "the pull changed the master")


if __name__ == "__main__":
    unittest.main()
