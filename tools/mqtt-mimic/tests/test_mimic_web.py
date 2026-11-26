"""The JMRI-hosted mimic: generated layout, install step, and what the page may publish."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
WEB = ROOT / "jmri/resources/jmri-web/mimic"
PAGE = WEB / "index.html"
MAC_PAGE = SCRIPTS / "lcos_mqtt_mimic.html"
SHARED = ("mimic.css", "mimic_view.js")
INSTALL = ROOT / "cats/scripts/install_jmri_web_override.sh"
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import level_devices  # noqa: E402

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


class Levels(unittest.TestCase):
    """Staging is LCOS over MQTT; main and upper are virtual JMRI devices, each on its own tab."""

    @classmethod
    def setUpClass(cls):
        cls.mimic = _load("lcos_mqtt_mimic")
        cls.layout = cls.mimic.load_layout()

    def test_every_level_has_turnouts_blocks_and_heads(self):
        for kind in ("turnouts", "blocks", "heads"):
            self.assertEqual({it["level"] for it in self.layout[kind]}, {"staging", "main", "upper"}, kind)

    def test_only_main_and_upper_are_virtual(self):
        for kind, prefix in (("turnouts", level_devices.TURNOUT_PREFIX), ("blocks", level_devices.SENSOR_PREFIX)):
            for it in self.layout[kind]:
                if it["level"] == "staging":
                    self.assertFalse(it.get("virtual"), it)
                    self.assertRegex(it["name"], r"^M2[TS]\d+$")
                else:
                    self.assertTrue(it["virtual"], it)
                    self.assertTrue(it["name"].startswith(prefix), it)
                    self.assertEqual(it["addr"], it["name"])

    def test_every_record_has_a_group(self):
        for kind in ("turnouts", "blocks", "heads"):
            for it in self.layout[kind]:
                self.assertTrue(it["plant"], it)

    def test_tab_titles_cover_the_levels(self):
        view = (WEB / "mimic_view.js").read_text(encoding="utf-8")
        titles = re.search(r"LEVEL_TITLES = \{(.+?)\}", view).group(1)
        self.assertEqual(set(re.findall(r"(\w+):", titles)), {"staging", "main", "upper"})

    def test_mac_mimic_keeps_staging_only(self):
        staged = self.mimic.load_layout(levels=False)
        for kind, rows in staged.items():
            self.assertTrue(rows, kind)
            self.assertEqual({it["level"] for it in rows}, {"staging"})


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

    def test_sets_only_virtual_devices_directly(self):
        # A JSON turnout post commands an LCOS motor, so LCOS feedback goes through the relay memory.
        # Only the main and upper levels' virtual devices are set directly, behind the VIRTUAL guard.
        named = re.findall(r'type: "(\w+)", method: "post"', self.script)
        self.assertEqual(set(named), {"memory"})
        self.assertEqual(self.script.count('method: "post"'), len(named) + 1)
        guarded = self.script[self.script.index("function setVirtual("):]
        guarded = guarded[:guarded.index("\n    }\n")]
        self.assertIn("{ type, method: \"post\"", guarded)
        self.assertIn("if (!prefix || !name.startsWith(prefix)", guarded)
        self.assertNotIn('method: "put"', self.script)

    def test_virtual_guard_is_the_level_device_prefixes(self):
        guard = re.search(r"const VIRTUAL = \{ turnout: \"([^\"]+)\", sensor: \"([^\"]+)\" \};", self.script)
        self.assertEqual(guard.groups(), (level_devices.TURNOUT_PREFIX, level_devices.SENSOR_PREFIX))

    def test_no_mac_mimic_endpoints(self):
        self.assertNotIn("/api/", self.script)


class SharedView(unittest.TestCase):
    """Both pages draw with the same style and render code; only the transport differs."""

    view = (WEB / "mimic_view.js").read_text(encoding="utf-8")

    def test_both_pages_load_the_shared_files(self):
        jmri = PAGE.read_text(encoding="utf-8")
        mac = MAC_PAGE.read_text(encoding="utf-8")
        self.assertIn('href="mimic.css"', jmri)
        self.assertIn('src="mimic_view.js"', jmri)
        self.assertIn('href="/mimic.css"', mac)
        self.assertIn('src="/mimic_view.js"', mac)
        for text in (jmri, mac):
            self.assertNotIn("<style>", text)
            self.assertNotIn("function render(", text)
            self.assertIn("mountMimic(", text)

    def test_shared_view_sends_nothing(self):
        for word in ("fetch(", "WebSocket", "EventSource", "track/", "method:", "send("):
            self.assertNotIn(word, self.view)

    def test_mac_server_serves_the_shared_files(self):
        mimic = _load("lcos_mqtt_mimic")
        self.assertEqual(mimic.SHARED_WEB, WEB)
        self.assertEqual({name.lstrip("/") for name in mimic.SHARED_FILES}, set(SHARED))


# Runs render() under node with a stub DOM and prints every innerHTML it set.
_RENDER_HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const [viewPath, statePath] = process.argv.slice(1);
const html = [];
function node(id) {
  const el = { id, hidden: false, value: "", className: "", dataset: {},
    appendChild() {}, addEventListener() {}, insertAdjacentHTML() {} };
  Object.defineProperty(el, "innerHTML", { get() { return ""; }, set(v) { html.push(v); } });
  return el;
}
const els = {};
const document = { body: node("body"), getElementById: (id) => (els[id] ||= node(id)),
  createElement: (t) => node(t) };
const ctx = vm.createContext({ document, location: { hash: "" }, console });
vm.runInContext(fs.readFileSync(viewPath, "utf8"), ctx);
const given = JSON.parse(fs.readFileSync(statePath, "utf8"));
vm.runInContext("Object.assign(state, " + JSON.stringify(given) + "); render();", ctx);
process.stdout.write(JSON.stringify(html));
"""

EVIL = '<img src=x onerror=alert(1)>"\''


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RenderEscapes(unittest.TestCase):
    """Layout names and the live head aspect from the JSON socket never reach innerHTML as markup."""

    def _render(self, given: dict) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps(given), encoding="utf-8")
            out = subprocess.run(
                ["node", "-e", _RENDER_HARNESS, str(WEB / "mimic_view.js"), str(state_path)],
                capture_output=True, text=True, check=True,
            ).stdout
        return "".join(json.loads(out))

    def test_names_and_aspect_are_escaped(self) -> None:
        rec = {"level": "staging", "plant": EVIL}
        given = {
            "level": "staging",
            "layout": {
                "turnouts": [dict(rec, label=EVIL, name=EVIL, addr=EVIL, tip=EVIL, n_addr=EVIL, r_addr=EVIL)],
                "blocks": [dict(rec, label=EVIL, userName=EVIL, name=EVIL, addr=EVIL)],
                "heads": [dict(rec, id="IH1", systemName=EVIL, mast=EVIL)],
            },
            "heads": {"1": EVIL + ";x"},
        }
        html = self._render(given)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;&quot;&#39;", html)
        self.assertNotIn('"\'', html)

    def test_plain_names_render_unchanged(self) -> None:
        given = {
            "level": "staging",
            "layout": {"turnouts": [], "blocks": [],
                       "heads": [{"level": "staging", "plant": "East", "id": "IH7", "systemName": "IH7", "mast": "6LB"}]},
            "heads": {"7": "Green"},
        }
        html = self._render(given)
        self.assertIn('<i class="lamp Green" title="IH7 Green"></i><span class="lbl" title="6LB">6LB</span>', html)


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
        for name in SHARED:
            (web / "mimic" / name).write_text(name, encoding="utf-8")
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
        for name in SHARED:
            self.assertEqual((web / "mimic" / name).read_text(encoding="utf-8"), name)
        self.assertTrue((web / "servlet/home/Home.html").is_file())

    def test_skips_page_without_layout(self):
        web = self._run(with_layout=False)
        self.assertFalse((web / "mimic").exists())


class Deploy(unittest.TestCase):
    sync = "\n".join((ROOT / "tools/hosts/deploy" / n).read_text(encoding="utf-8") for n in ("common.sh", "stage.sh"))
    pi = (ROOT / "tools/hosts/pi/apply_hart_package_local.sh").read_text(encoding="utf-8")

    def test_stage_builds_layout_and_carries_relay(self):
        self.assertIn('build_mimic_web.py" --out "$stage/cats/resources/jmri-web/mimic"', self.sync)
        self.assertIn("jmri/layouts/hart/scripts/mimic_relay.py", self.sync)

    def test_pi_installs_and_starts_relay(self):
        self.assertIn('"$HART/jmri/layouts/hart/scripts/mimic_relay.py"', self.pi)
        self.assertIn("--script preference:jython/mimic_relay.py", self.pi)


if __name__ == "__main__":
    unittest.main()
