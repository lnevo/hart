"""pi_quit_panelpro.sh answers only JMRI's store-on-quit request, and only with No; it and pi_start_panelpro.sh
find a JMRI app on the profile through pi/jmri_profile_match.sh."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/hosts/pi_quit_panelpro.sh"
JMRI_BUNDLE_REQUEST = (
    "<html>Table and/or panel changes have been made since the last store.<br> "
    "Do you want to <strong>Store ALL tables and panels</strong>?</html>"
)
JMRI_BUNDLE_DENIED = (
    "<html>Table and/or panel changes have been made since the last store but<br> "
    "you don't have permission to store. Do you want to abort the shutdown?</html>"
)


DEFAULT_PROFILE = "TCS_MQTT.3f32a166"


def ssh_calls(tmp: Path, name: str, env: dict[str, str]) -> list[str]:
    """Run tools/hosts/<name> with a stub ssh that logs its arguments and fails; return the logged calls."""
    stub = tmp / "bin"
    stub.mkdir()
    log = tmp / "ssh.log"
    (stub / "ssh").write_text(f'#!/bin/sh\necho "$*" >> "{log}"\nexit 1\n', encoding="utf-8")
    (stub / "ssh").chmod(0o755)
    base = {k: v for k, v in os.environ.items() if k not in ("_hart_env_loaded", "HART_PI_PROFILE")}
    base.update(env, PATH=f"{stub}:/usr/bin:/bin", HART_PI_SSH="pi.example.invalid",
                HART_ENV_FILE=str(tmp / "hart.env"))
    subprocess.run(["bash", str(ROOT / "tools/hosts" / name)], env=base, capture_output=True, text=True,
                   cwd=tmp, timeout=60)
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def jython() -> str:
    return subprocess.run(
        ["bash", str(SCRIPT), "--print"], check=True, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HART_PI_SSH": "example.invalid"},
    ).stdout


def store_request(src: str) -> tuple[str, ...]:
    m = re.search(r"STORE_REQUEST = \((.*?)\)\n", src)
    return tuple(re.findall(r'"([^"]+)"', m.group(1)))


class PiQuitPanelProTest(unittest.TestCase):
    def test_print_needs_no_ssh(self) -> None:
        self.assertIn("Apps.handleQuit()", jython())

    def test_matches_the_request_not_the_permission_dialog(self) -> None:
        parts = store_request(jython())
        self.assertTrue(all(p in JMRI_BUNDLE_REQUEST for p in parts))
        self.assertFalse(all(p in JMRI_BUNDLE_DENIED for p in parts))
        self.assertIn('STORE_BUTTONS = ["Cancel", "No", "Yes"]', jython())

    def test_clicks_only_no(self) -> None:
        src = jython()
        self.assertEqual(src.count("doClick"), 1)
        self.assertIn('unicode(b.getText()) == "No"][0].doClick()', src)
        self.assertNotRegex(src, r'== "(Yes|Cancel)"')

    def test_scans_swing_on_the_event_thread(self) -> None:
        src = jython()
        self.assertIn("SwingUtilities.invokeAndWait(_Scan(seen))", src)
        self.assertNotIn("Window.getWindows()", src[src.index('open(LOG, "w")'):])

    def test_jython_waits_as_long_as_the_shell(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        shell = int(re.search(r"^WAIT_S=(\d+)", text, re.M).group(1))
        jy = int(re.search(r"^WAIT_S = (\d+)", jython(), re.M).group(1))
        self.assertLess(jy, shell)
        self.assertGreater(jy, shell - 10)

    def test_remote_checks_are_safe(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        remote = text[text.index("<<'REMOTE'"):]
        # A ready file left from an earlier PanelPro does not count.
        self.assertIn('stat -c %Y "$READY") < started', remote)
        # An unread quit is never left for the next start.
        self.assertIn('if [[ -e "$CMD" ]]; then rm -f "$CMD"', remote)
        self.assertIn("^OTHER DIALOG", remote)
        self.assertIn("^QUIT FAILED", remote)

    def test_never_stores_or_publishes(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for banned in ("storeAll", "StoreXml", "ConfigureManager", "mosquitto_pub", "track/cmd", "publish("):
            self.assertNotIn(banned, text, banned)

    def test_every_pi_panelpro_script_sends_the_profile_load_env_names(self) -> None:
        """pi_quit and pi_start take the profile from HART_PI_PROFILE (load_env.sh);
        a stub ssh records what each sends and fails, so nothing reaches a host."""
        for env, want in (({}, DEFAULT_PROFILE), ({"HART_PI_PROFILE": "Rehearsal.0badf00d"}, "Rehearsal.0badf00d")):
            for name in ("pi_quit_panelpro.sh", "pi_start_panelpro.sh"):
                with self.subTest(script=name, env=env), tempfile.TemporaryDirectory() as tmp:
                    calls = ssh_calls(Path(tmp), name, env)
                    self.assertTrue(calls, name)
                    folder = want.split(".")[0]
                    self.assertTrue(f" {want} " in f" {calls[0]} " or f"~/.jmri/{folder}.jmri/" in calls[0],
                                    calls[0])


class PiHostRun:
    """pi_start_panelpro.sh or pi_quit_panelpro.sh with a stand-in ssh that runs what it is sent with bash on this
    machine: HOME is a temporary folder, ps lists the command lines a test gives (or fails), setsid runs its
    command, and ~/JMRI/PanelPro is a stand-in that adds a PanelPro JVM to that list and writes JMRI's start line.
    Nothing reaches a host."""

    def __init__(self, tmp: Path, processes: list[str], ps_fails: bool = False) -> None:
        self.tmp = tmp
        self.home = tmp / "home"
        self.procs = tmp / "processes.txt"
        self.starts = tmp / "starts.log"
        stub = tmp / "bin"
        for folder in (stub, self.home / "JMRI"):
            folder.mkdir(parents=True)
        self.procs.write_text("".join(f"{p}\n" for p in processes), encoding="utf-8")
        tools = {
            "ssh": 'while [ "$1" = -o ]; do shift 2; done\nshift\nexec "$@"',
            "ps": ("exit 1" if ps_fails else
                   f'n=100; while IFS= read -r l; do n=$((n + 1)); echo "$n $l"; done <"{self.procs}"'),
            "setsid": 'exec "$@"',
        }
        for name, body in tools.items():
            (stub / name).write_text(f"#!/bin/bash\n{body}\n", encoding="utf-8")
            (stub / name).chmod(0o755)
        panelpro = self.home / "JMRI/PanelPro"
        panelpro.write_text(
            "#!/bin/bash\n"
            f'echo "$*" >>"{self.starts}"\n'
            'sleep 1.2    # the start line is newer than the marker the script made before it\n'
            'mkdir -p "$HOME/.jmri/log"\n'
            'echo "PanelPro version 5.16.0 starts" >"$HOME/.jmri/log/session.log"\n'
            f'echo "java -Dorg.jmri.profile=$2 -cp .:jmri.jar apps.PanelPro.PanelPro" >>"{self.procs}"\n',
            encoding="utf-8")
        panelpro.chmod(0o755)
        self.marker = self.home / ".hart_panelpro_quit_for_deploy"
        self.marker.write_text("quit", encoding="utf-8")
        self.path = f"{stub}:/usr/bin:/bin"

    def run(self, name: str) -> subprocess.CompletedProcess[str]:
        env = {"HOME": str(self.home), "PATH": self.path, "HART_PI_SSH": "pi.example.invalid",
               "HART_ENV_FILE": str(self.tmp / "hart.env")}
        return subprocess.run(["bash", str(ROOT / "tools/hosts" / name)], env=env, capture_output=True, text=True,
                              cwd=self.tmp, timeout=60)

    def started(self) -> list[str]:
        return self.starts.read_text(encoding="utf-8").splitlines() if self.starts.exists() else []


JVM = "java -Djava.awt.headless=false {word} -cp .:jmri.jar apps.PanelPro.PanelPro"
CATS_SH = "/bin/bash ./cats.csh -Dcats.folder=/home/pi/JMRI_UserFiles/cats/panels --profile={id} HART_CTC.xml"


class Started(NamedTuple):
    """One pi_start_panelpro.sh run: its result, the stand-in PanelPro's arguments per start, and whether the
    quit-for-deploy marker is still there."""
    done: subprocess.CompletedProcess[str]
    started_lines: list[str]
    marker_left: bool


class PiStartSeesTheProfile(unittest.TestCase):
    def start(self, processes: list[str], ps_fails: bool = False) -> Started:
        with tempfile.TemporaryDirectory() as name:
            pi = PiHostRun(Path(name), processes, ps_fails)
            done = pi.run("pi_start_panelpro.sh")
            return Started(done, pi.started(), pi.marker.exists())

    def test_a_jmri_app_on_the_profile_in_any_form_refuses_the_start(self) -> None:
        for line in (JVM.format(word=f"-Dorg.jmri.profile={DEFAULT_PROFILE}"), CATS_SH.format(id=DEFAULT_PROFILE),
                     JVM.format(word="")):
            with self.subTest(line=line):
                pi = self.start([line])
                done = pi.done
                self.assertEqual(done.returncode, 3, done.stderr)
                self.assertIn("already running on the Pi; nothing started", done.stderr)
                self.assertEqual(pi.started_lines, [])
                self.assertFalse(pi.marker_left)

    def test_a_profile_that_only_starts_the_same_does_not_stop_it(self) -> None:
        pi = self.start([JVM.format(word="-Dorg.jmri.profile=TCS_MQTT_test"), CATS_SH.format(id="TCS_MQTT_x")])
        done = pi.done
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f"PanelPro started on the Pi (profile {DEFAULT_PROFILE})", done.stdout)
        self.assertEqual(pi.started_lines, [f"-p {DEFAULT_PROFILE}"])
        self.assertFalse(pi.marker_left)

    def test_a_process_list_it_cannot_read_starts_nothing(self) -> None:
        pi = self.start([], ps_fails=True)
        done = pi.done
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("Cannot tell whether JMRI runs on the Pi", done.stderr)
        self.assertEqual(pi.started_lines, [])
        self.assertTrue(pi.marker_left)


class PiQuitSeesTheProfile(unittest.TestCase):
    """Only the paths that end before the quit is dropped: the drop goes to this machine's /tmp, where a PanelPro of
    its own could run it."""

    def test_a_profile_that_only_starts_the_same_is_not_quit(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            pi = PiHostRun(Path(name), [JVM.format(word="-Dorg.jmri.profile=TCS_MQTT_test.0badf00d")])
            done = pi.run("pi_quit_panelpro.sh")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("PanelPro is not running on the Pi; nothing to quit.", done.stdout)

    def test_a_process_list_it_cannot_read_is_exit_5(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            done = PiHostRun(Path(name), [], ps_fails=True).run("pi_quit_panelpro.sh")
        self.assertEqual(done.returncode, 5, done.stderr)
        self.assertIn("Cannot tell whether PanelPro runs on the Pi", done.stderr)


class PiQuitRefusesUnknownArguments(unittest.TestCase):
    """Any argument but --for-deploy or --print stops the script before ssh, naming the argument (exit 64)."""

    def run_it(self, *args: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
        with tempfile.TemporaryDirectory() as name:
            tmp = Path(name)
            stub = tmp / "bin"
            stub.mkdir()
            log = tmp / "ssh.log"
            (stub / "ssh").write_text(f'#!/bin/sh\necho "$*" >> "{log}"\nexit 1\n', encoding="utf-8")
            (stub / "ssh").chmod(0o755)
            done = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, cwd=tmp, timeout=60,
                                  env={"PATH": f"{stub}:/usr/bin:/bin", "HART_PI_SSH": "pi.example.invalid",
                                       "HART_ENV_FILE": str(tmp / "hart.env"), "HOME": str(tmp)})
            return done, log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def test_an_unknown_argument_is_named_and_nothing_runs(self) -> None:
        for args in (["--for-deploi"], ["--for-deploy", "now"], ["-h"], [""]):
            with self.subTest(args=args):
                done, calls = self.run_it(*args)
                self.assertEqual(64, done.returncode, done.stderr)
                self.assertIn(f"pi_quit_panelpro.sh: unknown argument: {args[-1]}\n", done.stderr)
                self.assertIn("usage: pi_quit_panelpro.sh [--for-deploy | --print]", done.stderr)
                self.assertEqual("", done.stdout)
                self.assertEqual([], calls)

    def test_for_deploy_and_print_together_are_refused(self) -> None:
        done, calls = self.run_it("--print", "--for-deploy")
        self.assertEqual(64, done.returncode, done.stderr)
        self.assertIn("--for-deploy and --print exclude each other", done.stderr)
        self.assertEqual("", done.stdout)
        self.assertEqual([], calls)

    def test_for_deploy_reaches_the_pi(self) -> None:
        done, calls = self.run_it("--for-deploy")
        self.assertEqual(1, done.returncode, done.stderr)      # the stub ssh's exit
        self.assertEqual(1, len(calls), calls)
        self.assertTrue(calls[0].endswith(" 1"), calls[0])      # the remote part's for_deploy argument


if __name__ == "__main__":
    unittest.main()
