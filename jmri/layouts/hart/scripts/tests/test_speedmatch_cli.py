"""Tests for speedmatch/speedmatch.py, the one command over the speed-matching tools.

The subcommands run their scripts unchanged. pom builds a drop for pom_write.py and sends it only through
drop_job.sh: here with stub ssh and scp on PATH and a temp operating flag, so nothing reaches the Pi, and the drop
itself runs in-process against the stand-in jmri module of test_pom_guard.py. No hardware, no MQTT, no network.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_pom_guard as tpg  # noqa: E402  (its roster, consist log and jmri stand-ins)

SM = HERE.parent / "speedmatch"
CLI = SM / "speedmatch.py"
CLEAR_ENV = ("HART_PI_SSH", "HART_PI_USERFILES", "HART_ENV_FILE", "HART_REPO_ROOT", "_hart_env_loaded",
             "HART_OPERATING_FLAG")

# A stub ssh that answers drop_job.sh's tests from files in $FAKE_PI (a folder standing for the Pi's /tmp) and
# logs every command; a stub scp that copies into $FAKE_PI. Neither opens a connection.
SSH = r"""#!/bin/bash
while [[ "$1" == -o ]]; do shift 2; done
host="$1"; shift
echo "$host $*" >> "$FAKE_PI/ssh.log"
cmd="${*//\/tmp\//$FAKE_PI/}"
if [[ "$cmd" == *"jmri_cmd.py.tmp"*"jmri_cmd.py" ]]; then mv "$FAKE_PI/jmri_cmd.py.tmp" "$FAKE_PI/jmri_cmd.py"
  echo started > "$FAKE_PI/jmri_cmd.out"; exit 0; fi
eval "$cmd"
"""
SCP = r"""#!/bin/bash
args=(); for a in "$@"; do [[ "$a" == -q ]] && continue; args+=("$a"); done
while [[ "${args[0]}" == -o ]]; do args=("${args[@]:2}"); done
dest="${args[1]#*:}"; cp "${args[0]}" "${dest//\/tmp\//$FAKE_PI/}"
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.pi = self.dir / "pi"
        self.pi.mkdir()
        (self.pi / "jmri_watcher.ready").write_text("")
        stub = self.dir / "bin"
        stub.mkdir()
        for name, text in (("ssh", SSH), ("scp", SCP)):
            (stub / name).write_text(text)
            (stub / name).chmod(0o755)
        self.flag = self.dir / "operating"
        self.env = {k: v for k, v in os.environ.items() if k not in CLEAR_ENV}
        self.env.update(PATH="%s:/usr/bin:/bin" % stub, FAKE_PI=str(self.pi), HART_PI_SSH="fakepi.invalid",
                        HART_PI_USERFILES="/home/tester/JMRI_UserFiles", HART_ENV_FILE=str(self.dir / "none.env"),
                        HART_OPERATING_FLAG=str(self.flag))
        self.prop = self.dir / "proposal.json"
        self.prop.write_text(json.dumps(tpg.proposal([(67, 14), (68, 30)])))

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)], env=self.env, capture_output=True,
                              text=True, cwd=self.dir, timeout=60)


class PassThrough(Base):
    def test_help_lists_every_subcommand(self):
        out = self.cli("--help").stdout
        for cmd in ("job", "drop", "pom", "compare preflight", "compare stoptest", "to-roster", "lengths",
                    "rename-ext", "ledger-dir"):
            self.assertIn("speedmatch.py " + cmd, out)

    def test_a_subcommand_runs_its_script_with_the_arguments_as_given(self):
        log = self.dir / "old.log"
        log.write_text("1.0 SENS BS East Main Ext ACTIVE\n")
        direct = subprocess.run([sys.executable, str(SM / "rename_extension_tracks.py"), str(log)],
                                capture_output=True, text=True)
        via = self.cli("rename-ext", log)
        self.assertEqual((via.returncode, via.stdout), (direct.returncode, direct.stdout))
        self.assertEqual(log.read_text(), "1.0 SENS BS East Main Ext ACTIVE\n")   # a dry run stays one
        self.assertEqual(self.cli("rename-ext", "--apply", log).returncode, 0)
        self.assertIn("BS East Ext", log.read_text())

    def test_compare_needs_its_kind_and_unknown_commands_fail(self):
        self.assertEqual(self.cli("compare").returncode, 2)
        self.assertEqual(self.cli("compare", "other").returncode, 2)
        self.assertEqual(self.cli("nothing").returncode, 2)
        r = self.cli("compare", "stoptest", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("log_a", r.stdout)

    def test_drop_without_arguments_prints_its_usage(self):
        r = self.cli("drop")
        self.assertEqual(r.returncode, 0)
        self.assertIn("drop_job.sh JOBFILE", r.stdout)


class PomBuild(Base):
    def test_apply_needs_consists_broken_and_a_bad_proposal_is_refused(self):
        r = self.cli("pom", self.prop, "--apply", "--out", self.dir / "d.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--consists-broken", r.stderr)
        self.prop.write_text(json.dumps({"roster_id": "CSX 2738", "writes": [{"cv": 29, "value": 1}]}))
        r = self.cli("pom", self.prop, "--out", self.dir / "d.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("REFUSED", r.stdout)
        self.assertFalse((self.dir / "d.py").exists())

    def test_rollback_is_a_name_and_the_paths_come_from_the_pi_user_files(self):
        self.assertEqual(self.cli("pom", self.prop, "--rollback", "../x.json", "--out", self.dir / "d.py")
                         .returncode, 2)
        r = self.cli("pom", self.prop, "--out", self.dir / "d.py", "--rollback", "rb.json", "--absent-ok", "NWR 06")
        self.assertEqual(r.returncode, 0, r.stderr)
        ns = {}
        text = (self.dir / "d.py").read_text()
        exec(text.split("import base64")[0], ns)
        self.assertEqual((ns["ROLLBACK"], ns["LEDGER_DIR"]),
                         ("/home/tester/speedmatch/rb.json", "/home/tester/speedmatch/ledger"))
        self.assertEqual((ns["APPLY"], ns["CONSISTS_BROKEN"], ns["ABSENT_OK"]), (False, False, ["NWR 06"]))
        self.assertEqual(ns["PROPOSAL"], "/tmp/speedmatch/proposal.json")
        self.assertIn("--ledger-dir /home/tester/speedmatch/ledger", r.stdout)       # the same folder, printed
        self.assertEqual(self.cli("ledger-dir").stdout, "/home/tester/speedmatch/ledger\n")
        self.assertIn("speedrun.active", text)     # what makes drop_job.sh run its runner checks
        self.assertTrue(text.endswith((SM / "pom_write.py").read_text()))
        self.assertNotRegex(text, r"""\bf["']""")  # Jython 2 source

    def run_drop(self, guard_missing=False):
        """Build the drop, then run it in-process: the stand-in jmri, a fake consist query that notes whether the
        active marker exists while the writer runs. Returns (log lines, programmer calls, the marker's path)."""
        pidir, logf = self.dir / "pidir", self.dir / "pom.log"
        self.env["HART_PI_USERFILES"] = str(self.dir / "home/JMRI_UserFiles")
        r = self.cli("pom", self.prop, "--out", self.dir / "d.py", "--pi-dir", pidir, "--log", logf)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.dir / "d.py").read_text()
        if guard_missing:
            text = text.replace("GUARD_PATH = %r" % (str(pidir) + "/pom_guard.py"), "GUARD_PATH = '/nonexistent.py'")
        roster_dir = tpg.make_roster(str(self.dir / "u"))
        active = self.dir / "speedrun.active"
        self.seen = []
        fake_query = 'with open(LOGF, "w") as q:\n    q.write(%r)\n' % tpg.CLEAR

        def execfile(path, e):
            self.seen.append(active.read_text() if active.exists() else None)
            exec(fake_query, e)
        calls = []
        env = {"__name__": "pom_drop_test", "RUN_INLINE": True, "OP_TIMEOUT": 0.05, "CONSIST_TIMEOUT": 2.0,
               "ACTIVE_FILE": str(active), "execfile": execfile}
        with mock.patch.dict(sys.modules, {"jmri": tpg.fake_jmri(roster_dir, calls)}):
            exec(compile(text, "d.py", "exec"), env)
        return logf.read_text().splitlines(), calls, active

    def test_the_drop_unpacks_its_files_and_runs_the_writer(self):
        lines, calls, active = self.run_drop()
        pidir = self.dir / "pidir"
        for p in ("pom_guard.py", "pom_guard_cli.py", "cs105_consist.py"):
            self.assertEqual((pidir / p).read_bytes(), (SM.parent / p if p.startswith("cs105") else SM / p)
                             .read_bytes())
        self.assertEqual(json.loads((pidir / "proposal.json").read_text())["roster_id"], "CSX 2738")
        self.assertTrue((self.dir / "home/speedmatch/ledger").is_dir())
        self.assertIn("PLAN 2738L CV67 old=12 (roster (may be a default)) new=14", lines)
        self.assertEqual(lines[-1], "END")
        self.assertFalse([c for c in calls if c[0] == "write"])

    def test_the_writer_holds_the_runners_active_marker_until_its_end(self):
        lines, calls, active = self.run_drop()
        self.assertEqual(self.seen, [str(self.dir / "pom.log")])   # held, naming its log, while it ran
        self.assertFalse(active.exists())                           # and gone at END
        self.assertEqual(lines[-1], "END")

    def test_a_runner_holding_the_marker_stops_the_writer_and_keeps_its_marker(self):
        (self.dir / "speedrun.active").write_text("steps CSX 2121")
        lines, calls, active = self.run_drop()
        self.assertTrue(lines[0].startswith("REFUSED") and "active" in lines[0], lines)
        self.assertEqual((calls, self.seen), ([], []))               # no programmer, no consist query
        self.assertEqual(active.read_text(), "steps CSX 2121")
        self.assertEqual(lines[-1], "END")

    def test_the_marker_goes_when_the_writer_stops_early(self):
        lines, calls, active = self.run_drop(guard_missing=True)
        self.assertTrue(any(line.startswith("REFUSED guard module") for line in lines), lines)
        self.assertFalse(active.exists())


class PomSend(Base):
    def send(self, *extra):
        return self.cli("pom", self.prop, "--out", self.dir / "d.py", "--send", *extra)

    def test_a_running_runner_stops_the_drop_and_clears_the_flag_it_set(self):
        (self.pi / "speedrun.active").write_text("steps CSX 2121")
        r = self.send()
        self.assertEqual(r.returncode, 1)
        self.assertIn("a runner is still active", r.stderr)
        self.assertFalse((self.pi / "jmri_cmd.py").exists())
        self.assertFalse(self.flag.exists())
        self.assertTrue((self.pi / "speedrun.active").exists())   # never --force

    def test_a_kill_flag_stops_the_drop(self):
        (self.pi / "speedrun.kill").write_text("")
        r = self.send()
        self.assertEqual(r.returncode, 1)
        self.assertIn("speedrun.kill exists", r.stderr)
        self.assertFalse((self.pi / "jmri_cmd.py").exists())

    def test_an_abbreviated_send_is_refused_not_sent(self):
        r = self.cli("pom", self.prop, "--out", self.dir / "d.py", "--se")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unrecognized arguments: --se", r.stderr)
        self.assertFalse((self.pi / "jmri_cmd.py").exists())
        self.assertFalse((self.dir / "d.py").exists())

    def test_the_owners_session_stops_the_drop(self):
        self.flag.write_text("by=owner\nsince=2026-11-25T10:00:00-0500\nreason=ops\n")
        r = self.send()
        self.assertEqual(r.returncode, 1)
        self.assertIn("the owner is operating", r.stderr)
        self.assertFalse((self.pi / "jmri_cmd.py").exists())
        self.assertIn("by=owner", self.flag.read_text())

    def test_a_clear_layout_gets_the_drop_and_the_flag_is_set(self):
        r = self.send()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.pi / "jmri_cmd.py").read_text(), (self.dir / "d.py").read_text())
        self.assertIn("by=speedmatch", self.flag.read_text())
        self.assertIn("started", r.stdout)
        self.assertTrue(all(line.startswith("fakepi.invalid ") for line in
                            (self.pi / "ssh.log").read_text().splitlines()))


if __name__ == "__main__":
    unittest.main()
