"""hartlib.hosts: one broker setting for the Mac tools, and its lookup order."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import hosts  # noqa: E402
from hartlib.paths import REPO_ROOT as ROOT  # noqa: E402

NO_FILE: dict = {}
DEFAULTS = hosts.read_env_file(ROOT / "tools/env/defaults.env")
PI = DEFAULTS["HART_MQTT_BROKER"]


class LookupTest(unittest.TestCase):
    def test_defaults_to_the_pi(self):
        self.assertEqual(hosts.mqtt_broker({}, NO_FILE), PI)
        self.assertEqual(hosts.mqtt_port({}, NO_FILE), int(DEFAULTS["HART_MQTT_PORT"]))
        self.assertEqual(hosts.jmri_json_url({}, NO_FILE), DEFAULTS["HART_JMRI_JSON"])

    def test_defaults_file_is_the_one_read(self):
        self.assertEqual(hosts.DEFAULTS_FILE.resolve(), (ROOT / "tools/env/defaults.env").resolve())
        self.assertEqual(hosts.default("HART_PI_WEB_HOST"), DEFAULTS["HART_PI_WEB_HOST"])
        with self.assertRaises(hosts.HostsError) as ctx:
            hosts.default("HART_NO_SUCH_SETTING")
        self.assertIn("defaults.env", str(ctx.exception))

    def test_new_name_beats_old_names(self):
        env = {"HART_MQTT_BROKER": "a.example.invalid", "MQTT_HOST": "b.example.invalid",
               "HART_MQTT_HOST": "c.example.invalid"}
        self.assertEqual(hosts.mqtt_broker(env, NO_FILE), "a.example.invalid")

    def test_old_names_still_honoured(self):
        self.assertEqual(hosts.mqtt_broker({"MQTT_HOST": "b.example.invalid"}, NO_FILE),
                         "b.example.invalid")
        self.assertEqual(hosts.mqtt_broker({"HART_MQTT_HOST": "c.example.invalid"}, NO_FILE),
                         "c.example.invalid")
        self.assertEqual(
            hosts.jmri_json_url({"JMRI_JSON": "http://j.example.invalid:12080/json/"}, NO_FILE),
            "http://j.example.invalid:12080/json")

    def test_blank_value_is_unset(self):
        self.assertEqual(hosts.mqtt_broker({"HART_MQTT_BROKER": "  "}, NO_FILE), PI)

    def test_environment_beats_env_file(self):
        file_values = {"HART_MQTT_BROKER": "file.example.invalid"}
        self.assertEqual(hosts.mqtt_broker({}, file_values), "file.example.invalid")
        self.assertEqual(hosts.mqtt_broker({"MQTT_HOST": "env.example.invalid"}, file_values),
                         "env.example.invalid")

    def test_bad_port_stops(self):
        with self.assertRaises(hosts.HostsError) as ctx:
            hosts.mqtt_port({"HART_MQTT_PORT": "x"}, NO_FILE)
        self.assertIsInstance(ctx.exception.__cause__, ValueError)


class EnvFileTest(unittest.TestCase):
    def test_reads_the_example_format(self):
        example = (ROOT / "tools/env/hart.env.example").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hart.env"
            path.write_text(example + "\nHART_MQTT_BROKER=file.example.invalid   # override\nexport X='q'\n",
                            encoding="utf-8")
            values = hosts.read_env_file(path)
        self.assertEqual(values["HART_MQTT_BROKER"], "file.example.invalid")
        self.assertEqual(values["X"], "q")
        self.assertNotIn("# HART_REPO_ROOT", values)
        # The example sets no host value itself: defaults.env is the one copy.
        self.assertNotIn("HART_MQTT_PORT", values)

    def test_reads_the_defaults_file(self):
        self.assertEqual(set(DEFAULTS), {
            "HART_MQTT_BROKER", "HART_MQTT_PORT", "HART_JMRI_JSON", "HART_PI_SSH", "HART_PI_USERFILES",
            "HART_PI_WEB_HOST", "HART_WIN_SSH", "HART_WIN_SSH_PORT", "HART_WIN_USERFILES"})

    def test_reads_like_source(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hart.env"
            path.write_text(
                "HART_MQTT_BROKER=b.example.invalid\n"
                "HART_JMRI_JSON=http://${HART_MQTT_BROKER}:12080/json  # comment\n"
                'QUOTED="a # b"\n'
                "LITERAL='$HART_MQTT_BROKER'\n",
                encoding="utf-8")
            values = hosts.read_env_file(path)
        self.assertEqual(values["HART_JMRI_JSON"], "http://b.example.invalid:12080/json")
        self.assertEqual(values["QUOTED"], "a # b")
        self.assertEqual(values["LITERAL"], "$HART_MQTT_BROKER")

    def test_path_follows_repo_root(self):
        saved = {k: os.environ.pop(k, None) for k in ("HART_ENV_FILE", "HART_REPO_ROOT")}
        try:
            self.assertEqual(hosts.env_file_path(), ROOT / "tools/env/hart.env")
            os.environ["HART_REPO_ROOT"] = "/x"
            self.assertEqual(hosts.env_file_path(), Path("/x/tools/env/hart.env"))
            os.environ["HART_ENV_FILE"] = "/y/h.env"
            self.assertEqual(hosts.env_file_path(), Path("/y/h.env"))
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_missing_file_is_empty(self):
        self.assertEqual(hosts.read_env_file(Path("/nonexistent/hart.env")), {})

    def test_a_file_that_cannot_be_read_stops(self):
        # only a missing file counts as none: a folder in its place is an error naming the path
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(hosts.HostsError) as ctx:
                hosts.read_env_file(Path(d))
        self.assertIn(d, str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, OSError)


class StandaloneTest(unittest.TestCase):
    def test_imports_without_a_checkout(self):
        import shutil
        import subprocess
        src = Path(hosts.__file__).parent
        with tempfile.TemporaryDirectory() as d:
            pkg = Path(d) / "hartlib"
            pkg.mkdir()
            for name in ("__init__.py", "hosts.py"):
                shutil.copy(src / name, pkg / name)
            env = {k: v for k, v in os.environ.items() if k not in ("HART_ENV_FILE", "HART_REPO_ROOT")}
            code = ("from hartlib import hosts\n"
                    "print(hosts.mqtt_broker({'HART_MQTT_BROKER': 'set.example.invalid'}, {}))\n"
                    "hosts.mqtt_broker({}, {})\n")
            done = subprocess.run([sys.executable, "-c", code],
                                  cwd=d, capture_output=True, text=True, timeout=30, env=env)
        # Imports and honours a set value; with nothing set it stops and names the defaults file.
        self.assertEqual(done.stdout.strip(), "set.example.invalid")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("defaults.env", done.stderr)


if __name__ == "__main__":
    unittest.main()
