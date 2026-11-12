"""The JMRI-hosted mimic: generated layout, install step, and what the page may publish."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
PAGE = ROOT / "jmri/resources/jmri-web/mimic/index.html"
INSTALL = ROOT / "cats/scripts/install_jmri_web_override.sh"
RELAY = (ROOT / "jmri/layouts/hart/scripts/mimic_relay.py").read_text(encoding="utf-8")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BuildLayout(unittest.TestCase):
    def test_matches_the_mac_mimic_layout(self):
        build = _load("build_mimic_web")
        with tempfile.TemporaryDirectory() as tmp:
            path = build.write(Path(tmp) / "mimic")
            self.assertEqual(path.name, "mimic_layout.json")
            written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written, json.loads(json.dumps(_load("lcos_mqtt_mimic").load_layout())))
        self.assertTrue(written["turnouts"] and written["blocks"] and written["heads"])


class Page(unittest.TestCase):
    text = PAGE.read_text(encoding="utf-8")
    script = text[text.index("<script>"):]

    def test_uses_jmri_json_and_the_relay_memory(self):
        self.assertIn("/json/", self.script)
        self.assertIn('fetch("mimic_layout.json"', self.script)
        memory = re.search(r'MEMORY = "(\w+)"', self.script).group(1)
        self.assertEqual(f'MEMORY = "{memory}"', re.search(r'MEMORY = "\w+"', RELAY).group(0))

    def test_only_builds_lcos_feedback_topics(self):
        topics = set(re.findall(r"`(track/[a-z]+)/", self.script))
        self.assertEqual(topics, {"track/sensor", "track/turnout"})
        self.assertNotIn("track/cmd", self.script)

    def test_never_sets_jmri_turnouts_or_sensors_directly(self):
        # A JSON turnout post commands the motor; feedback goes only through the relay memory.
        posts = re.findall(r'type: "(\w+)", method: "post"', self.script)
        self.assertEqual(posts, ["memory"])
        self.assertNotIn('method: "put"', self.script)

    def test_no_mac_mimic_endpoints(self):
        self.assertNotIn("/api/", self.script)


class Install(unittest.TestCase):
    def _run(self, with_layout):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        scripts = tmp / "cats/scripts"
        scripts.mkdir(parents=True)
        shutil.copy(INSTALL, scripts / INSTALL.name)
        web = tmp / "jmri/resources/jmri-web"
        (web / "servlet/home").mkdir(parents=True)
        (web / "servlet/home/Home.html").write_text("home", encoding="utf-8")
        (web / "mimic").mkdir()
        (web / "mimic/index.html").write_text("page", encoding="utf-8")
        if with_layout:
            (web / "mimic/mimic_layout.json").write_text("{}", encoding="utf-8")
        home = tmp / "home"
        (home / "JMRI_UserFiles").mkdir(parents=True)
        env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        subprocess.run(["bash", str(scripts / INSTALL.name)], env=env, check=True, capture_output=True)
        return home / "JMRI_UserFiles/web"

    def test_installs_page_with_its_layout(self):
        web = self._run(with_layout=True)
        self.assertEqual((web / "mimic/index.html").read_text(encoding="utf-8"), "page")
        self.assertTrue((web / "mimic/mimic_layout.json").is_file())
        self.assertTrue((web / "servlet/home/Home.html").is_file())

    def test_skips_page_without_layout(self):
        web = self._run(with_layout=False)
        self.assertFalse((web / "mimic").exists())


class Deploy(unittest.TestCase):
    sync = (ROOT / "cats/scripts/sync_hart_package.sh").read_text(encoding="utf-8")
    pi = (ROOT / "cats/scripts/pi/apply_hart_package_local.sh").read_text(encoding="utf-8")

    def test_stage_builds_layout_and_carries_relay(self):
        self.assertIn('build_mimic_web.py" --out "$stage/cats/resources/jmri-web/mimic"', self.sync)
        self.assertIn("jmri/layouts/hart/scripts/mimic_relay.py", self.sync)

    def test_pi_installs_and_starts_relay(self):
        self.assertIn('"$HART/jmri/layouts/hart/scripts/mimic_relay.py"', self.pi)
        self.assertIn("--script preference:jython/mimic_relay.py", self.pi)


if __name__ == "__main__":
    unittest.main()
