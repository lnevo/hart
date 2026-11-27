"""The JMRI-hosted mimic: generated layout, install step, and what the page may publish."""
from __future__ import annotations

import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

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


# Runs mimic_view.js under node with a small fake DOM. Input (JSON file): `state` to
# merge, the filter box value `q`, the URL `hash`, the body `headsTitle`, and `mount`
# to call mountMimic() first. Output: each root's element tree, every innerHTML the
# view set (mountMimic's fixed markup goes through insertAdjacentHTML instead), and
# the level render() settled on.
_RENDER_HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const [viewPath, inputPath] = process.argv.slice(1);
const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
const markup = [];
class Text { constructor(t) { this.text = t; } }
class El {
  constructor(tag) { this.tag = tag; this.attrs = {}; this.kids = []; this.hidden = false; this.value = "";
    this.dataset = {}; }
  set className(v) { this.attrs.class = v; }
  get className() { return this.attrs.class || ""; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  appendChild(c) { this.kids.push(c); return c; }
  replaceChildren(...c) { this.kids = c; }
  set textContent(v) { this.kids = [new Text(String(v))]; }
  set innerHTML(v) { markup.push(v); }
  addEventListener() {}
  insertAdjacentHTML() {}
}
const tree = (n) => n instanceof Text ? n.text
  : { tag: n.tag, attrs: n.attrs, hidden: n.hidden, kids: n.kids.map(tree) };
const els = {};
const body = new El("body");
body.dataset.headsTitle = input.headsTitle || "";
const document = { body, getElementById: (id) => (els[id] ||= new El(id)),
  createElement: (t) => new El(t), createTextNode: (t) => new Text(t) };
const ctx = vm.createContext({ document, location: { hash: input.hash || "" }, window: new El("window"),
  history: { replaceState() {} }, console });
vm.runInContext(fs.readFileSync(viewPath, "utf8"), ctx);
document.getElementById("q").value = input.q || "";
if (input.mount) vm.runInContext("mountMimic();", ctx);
vm.runInContext("Object.assign(state, " + JSON.stringify(input.state) + "); render();", ctx);
const roots = {};
for (const id of ["tabs", "turnouts", "blocks", "heads", "heads-title"]) roots[id] = tree(document.getElementById(id));
const level = vm.runInContext("state.level", ctx);
process.stdout.write(JSON.stringify({ roots, markup, level }));
"""

EVIL = '<img src=x onerror=alert(1)>"\''


class Node(TypedDict):
    tag: str
    attrs: dict[str, str]
    hidden: bool
    kids: list[Node | str]


class Rendered(TypedDict):
    roots: dict[str, Node]
    markup: list[str]
    level: str


def _html(node: Node | str) -> str:
    """The node as HTML, with text and attribute values escaped."""
    if isinstance(node, str):
        return html.escape(node, quote=False)
    attrs = "".join(f' {k}="{html.escape(v)}"' for k, v in node["attrs"].items())
    return f"<{node['tag']}{attrs}>{''.join(_html(k) for k in node['kids'])}</{node['tag']}>"


def _walk(node: Node | str) -> list[Node]:
    if isinstance(node, str):
        return []
    found = [node]
    for kid in node["kids"]:
        found += _walk(kid)
    return found


def _text(node: Node | str) -> str:
    return node if isinstance(node, str) else "".join(_text(k) for k in node["kids"])


def _elements(node: Node) -> list[Node]:
    return [k for k in node["kids"] if not isinstance(k, str)]


def _rec(level: str = "staging", plant: str = "East", **fields: object) -> dict[str, object]:
    return {"level": level, "plant": plant, **fields}


def _layout(turnouts: Sequence[dict] = (), blocks: Sequence[dict] = (),
            heads: Sequence[dict] = ()) -> dict[str, list[dict]]:
    return {"turnouts": list(turnouts), "blocks": list(blocks), "heads": list(heads)}


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Render(unittest.TestCase):
    """render() draws the shown level from `state`; layout names and live values stay text."""

    def _run(self, state: dict, **opts: object) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps({"state": state, **opts}), encoding="utf-8")
            return subprocess.run(
                ["node", "-e", _RENDER_HARNESS, str(WEB / "mimic_view.js"), str(path)],
                capture_output=True, text=True, check=False,
            )

    def _render(self, state: dict, **opts: object) -> Rendered:
        done = self._run(state, **opts)
        self.assertEqual(done.returncode, 0, done.stderr)
        out: Rendered = json.loads(done.stdout)
        self.assertEqual(out["markup"], [], "the view sets no innerHTML")
        return out

    def _rows(self, out: Rendered, root: str) -> list[Node]:
        return [n for n in _walk(out["roots"][root]) if n["attrs"].get("class", "").startswith("row")]

    def _buttons(self, out: Rendered, root: str) -> list[Node]:
        return [n for n in _walk(out["roots"][root]) if n["tag"] == "button"]

    def test_names_and_aspect_stay_text(self) -> None:
        rec = _rec(plant=EVIL)
        out = self._render({
            "level": "staging",
            "layout": _layout(
                [dict(rec, label=EVIL, name=EVIL, addr=EVIL, tip=EVIL, n_addr=EVIL, r_addr=EVIL)],
                [dict(rec, label=EVIL, userName=EVIL, name=EVIL, addr=EVIL)],
                [dict(rec, id="IH1", systemName=EVIL, mast=EVIL)]),
            "heads": {"1": EVIL + ";x"},
        }, mount=True, headsTitle=EVIL)
        everything = [n for root in out["roots"].values() for n in _walk(root)]
        self.assertNotIn("img", {n["tag"] for n in everything})
        for root in ("turnouts", "blocks", "heads"):
            h3 = next(n for n in _walk(out["roots"][root]) if n["tag"] == "h3")
            self.assertEqual(_text(h3), EVIL)
        self.assertEqual({b["attrs"]["data-to"] for b in self._buttons(out, "turnouts")}, {EVIL})
        self.assertEqual(self._buttons(out, "blocks")[0]["attrs"]["data-occ"], EVIL)
        lamp = next(n for n in _walk(out["roots"]["heads"]) if n["tag"] == "i")
        self.assertEqual(lamp["attrs"]["title"], f"{EVIL} {EVIL}")
        self.assertEqual(_text(out["roots"]["heads-title"]), EVIL)

    def test_plain_heads_render_unchanged(self) -> None:
        out = self._render({
            "level": "staging",
            "layout": _layout(heads=[_rec(id="IH7", systemName="IH7", mast="6LB")]),
            "heads": {"7": "Green"},
        })
        self.assertEqual(_html(out["roots"]["heads"]["kids"][0]),
                         '<div class="plant"><h3>East</h3><div class="lamps"><div class="mast">'
                         '<i class="lamp Green" title="IH7 Green"></i><span class="lbl" title="6LB">6LB</span>'
                         '</div></div></div>')

    def test_head_aspect_is_the_first_field_and_dark_without_a_report(self) -> None:
        heads = [_rec(id="IH7", mast="A"), _rec(id="IH8", systemName="West 8", mast="A"), _rec(id="IH9", mast="B")]
        out = self._render({"level": "staging", "layout": _layout(heads=heads),
                            "heads": {"7": "FlashingYellow ; 3", "IH9": "Red"}})
        lamps = [n["attrs"] for n in _walk(out["roots"]["heads"]) if n["tag"] == "i"]
        self.assertEqual(lamps, [{"class": "lamp FlashingYellow", "title": "IH7 FlashingYellow"},
                                 {"class": "lamp Dark", "title": "West 8 Dark"},
                                 {"class": "lamp Red", "title": "IH9 Red"}])
        masts = [n for n in _walk(out["roots"]["heads"]) if n["attrs"].get("class") == "mast"]
        self.assertEqual([_text(m) for m in masts], ["A", "B"])

    def test_tabs_follow_the_levels_in_order(self) -> None:
        layout = _layout(blocks=[_rec("upper", addr="U"), _rec("staging", addr="S"), _rec("main", addr="M")])
        out = self._render({"level": "main", "layout": layout})
        tabs = out["roots"]["tabs"]
        self.assertFalse(tabs["hidden"])
        self.assertEqual([(_text(b), b["attrs"]) for b in _elements(tabs)], [
            ("Staging", {"class": "tab", "data-level": "staging"}),
            ("Main", {"class": "tab on", "data-level": "main"}),
            ("Upper", {"class": "tab", "data-level": "upper"}),
        ])
        self.assertEqual([b["attrs"]["data-occ"] for b in self._buttons(out, "blocks")], ["M"])

    def test_every_level_the_build_emits_gets_a_tab(self) -> None:
        # a level the layout build writes but the view has no title for would be dropped with no tab and no error
        layout = _load("lcos_mqtt_mimic").load_layout()
        built = {it["level"] for kind in ("turnouts", "blocks", "heads") for it in layout[kind]}
        out = self._render({"level": "staging", "layout": layout})
        self.assertEqual(built, {b["attrs"]["data-level"] for b in _elements(out["roots"]["tabs"])})

    def test_one_level_hides_the_tabs(self) -> None:
        out = self._render({"level": "staging", "layout": _layout(blocks=[_rec(addr="S")])})
        self.assertTrue(out["roots"]["tabs"]["hidden"])

    def test_unknown_level_takes_the_hash_then_the_first(self) -> None:
        layout = _layout(blocks=[_rec("staging", addr="S"), _rec("upper", addr="U")])
        self.assertEqual(self._render({"level": "nope", "layout": layout}, hash="#upper")["level"], "upper")
        self.assertEqual(self._render({"level": "nope", "layout": layout}, hash="#nope")["level"], "staging")

    def test_turnout_state_and_feedback(self) -> None:
        turnouts = [
            _rec(label="Switch 1", name="M2T1", addr="1", tip="tip one", n_addr="10", r_addr="11"),
            _rec(label="Switch 2", name="M2T2", addr="2", feedback="DIRECT"),
            _rec(label="Switch 3", name="IT3", addr="IT3", virtual=True, tip="not shown"),
        ]
        out = self._render({"level": "staging", "layout": _layout(turnouts),
                            "turnouts": {"1": "thrown", "2": "CLOSED"}, "sensors": {"10": "active", "11": "INACTIVE"}})
        rows = self._rows(out, "turnouts")
        self.assertEqual([_text(r) for r in rows], [
            "Switch 1 M2T1tip oneFB N 10 ACTIVE · R 11ClosedThrown",
            "Switch 2 M2T2DIRECTDIRECT — turnout topic onlyClosedThrown",
            "Switch 3 IT3Virtual turnout, set in JMRI (no MQTT)ClosedThrown",
        ])
        spans = [n["attrs"]["class"] for n in _walk(rows[0]) if n["tag"] == "span"]
        self.assertEqual(spans, ["sub", "n on", "r"])
        self.assertEqual([(b["attrs"]["class"], b["attrs"]["data-to"], b["attrs"]["data-st"])
                          for b in self._buttons(out, "turnouts")], [
            ("sw", "1", "CLOSED"), ("sw on-thrown", "1", "THROWN"),
            ("sw on-closed", "2", "CLOSED"), ("sw", "2", "THROWN"),
            ("sw", "IT3", "CLOSED"), ("sw", "IT3", "THROWN"),
        ])

    def test_block_button_offers_the_other_state(self) -> None:
        blocks = [_rec(label="B1", userName="One", name="M2S1", addr="1"),
                  _rec(label="B2", userName="Two", name="M2S2", addr="2")]
        out = self._render({"level": "staging", "layout": _layout(blocks=blocks), "sensors": {"1": "ACTIVE"}})
        self.assertEqual([(_text(b), b["attrs"]) for b in self._buttons(out, "blocks")], [
            ("Occupied", {"class": "occ active", "data-occ": "1", "data-st": "INACTIVE"}),
            ("Clear", {"class": "occ inactive", "data-occ": "2", "data-st": "ACTIVE"}),
        ])
        self.assertEqual(_text(self._rows(out, "blocks")[1]), "B2Two · M2S2Clear")

    def test_filter_hides_rows_that_do_not_match(self) -> None:
        blocks = [_rec(label="Brick 1", userName="x", addr="1"),
                  _rec(plant="West", label="Yard", userName="x", addr="2")]
        out = self._render({"level": "staging", "layout": _layout(blocks=blocks)}, q="  WEST ")
        self.assertEqual([r["attrs"]["class"] for r in self._rows(out, "blocks")], ["row hidden", "row"])

    def test_plants_keep_first_seen_order(self) -> None:
        blocks = [_rec(plant="B", addr="1"), _rec(plant="A", addr="2"), _rec(plant="B", addr="3")]
        out = self._render({"level": "staging", "layout": _layout(blocks=blocks)})
        plants = _elements(out["roots"]["blocks"])
        self.assertEqual([_text(p["kids"][0]) for p in plants], ["B", "A"])
        self.assertEqual([len(p["kids"]) - 1 for p in plants], [2, 1])

    def test_a_layout_without_a_list_is_an_error(self) -> None:
        done = self._run({"level": "staging", "layout": {"turnouts": [], "blocks": []}})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn('mimic layout has no "heads" list', done.stderr)


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
        # the Pi installs the rows of the one jython list; "pi" marks a Start Up script on the Pi only
        rows = (ROOT / "tools/hosts/pi/jython_scripts.txt").read_text(encoding="utf-8").splitlines()
        self.assertIn("pi jmri/layouts/hart/scripts/mimic_relay.py", rows)
        self.assertIn("--script preference:jython/mimic_relay.py", self.pi)


if __name__ == "__main__":
    unittest.main()
