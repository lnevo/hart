"""The JMRI home page's STS and mimic links: the Pi follows its own host, Windows names the Pi, the Mac uses localhost."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HOME_PATH = ROOT / "jmri/resources/jmri-web/servlet/home/Home.html"
HOME = HOME_PATH.read_text(encoding="utf-8")
WIN = (ROOT / "cats/scripts/windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
INSTALL = ROOT / "cats/scripts/install_jmri_web_override.sh"
MARKER = 'var HART_APPS_HOST = "";'
MIMIC_MARKER = 'var HART_MIMIC_URL = "";'
SYNC = (ROOT / "cats/scripts/sync_hart_package.sh").read_text(encoding="utf-8")
NODE = shutil.which("node")


def _link_script(html):
    start = html.index(MARKER.split("=")[0])
    return html[html.rindex("<script>", 0, start) + len("<script>"): html.index("</script>", start)]


def _links(html, page_host):
    """Run the page's link script under Node with a fake DOM; return the two hrefs."""
    links = {"sts-link": None, "mimic-link": "/web/mimic/"}  # the page gives STS no static address
    js = (
        "const links = %s;\n"
        "const document = { getElementById: (id) => ({ set href(v) { links[id] = v; } }) };\n"
        "const location = { hostname: %s };\n%s\nconsole.log(JSON.stringify(links));"
        % (json.dumps(links), json.dumps(page_host), _link_script(html))
    )
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _filled(host, mimic=""):
    html = HOME.replace(MARKER, 'var HART_APPS_HOST = "%s";' % host)
    return html.replace(MIMIC_MARKER, 'var HART_MIMIC_URL = "%s";' % mimic)


class Source(unittest.TestCase):
    def test_home_has_one_empty_marker(self):
        self.assertEqual(HOME.count(MARKER), 1)
        self.assertEqual(HOME.count(MIMIC_MARKER), 1)

    def test_mac_deploy_uses_localhost(self):
        self.assertIn("HART_APPS_HOST=localhost HART_MIMIC_URL=http://localhost:8765/", SYNC)

    def test_sts_link_has_no_static_address(self):
        # Only the script sets it, so the link never points at a Mac or localhost STS.
        tag = re.search(r'<a id="sts-link"[^>]*>', HOME).group(0)
        self.assertNotIn("href", tag)
        self.assertNotIn("localhost:8980", HOME)

    def test_windows_fills_the_same_marker(self):
        self.assertIn("$marker = '" + MARKER + "'", WIN)
        self.assertRegex(WIN, r"\$PiHost = '[^']+'")
        self.assertIn("Write-Warning", WIN)  # a missing marker must not stop the Windows deploy


@unittest.skipUnless(NODE, "node not installed")
class Behaviour(unittest.TestCase):
    def test_on_the_pi_links_follow_the_page_host(self):
        self.assertEqual(
            _links(HOME, "10.0.0.150"),
            {"sts-link": "http://10.0.0.150:8980/sts/", "mimic-link": "/web/mimic/"},
        )

    def test_off_the_pi_links_name_the_pi(self):
        self.assertEqual(
            _links(_filled("RPi-JMRI.local"), "10.0.0.28"),
            {"sts-link": "http://RPi-JMRI.local:8980/sts/",
             "mimic-link": "http://RPi-JMRI.local:12080/web/mimic/"},
        )

    def test_on_the_mac_links_go_to_localhost(self):
        self.assertEqual(
            _links(_filled("localhost", "http://localhost:8765/"), "localhost"),
            {"sts-link": "http://localhost:8980/sts/", "mimic-link": "http://localhost:8765/"},
        )

    def test_windows_host_is_a_working_value(self):
        host = re.search(r"\$PiHost = '([^']+)'", WIN).group(1)
        links = _links(_filled(host), "10.0.0.28")
        self.assertEqual(links["sts-link"], "http://%s:8980/sts/" % host)


class Install(unittest.TestCase):
    def _run(self, apps_host, mimic_url=None):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "cats/scripts").mkdir(parents=True)
        shutil.copy(INSTALL, tmp / "cats/scripts" / INSTALL.name)
        web = tmp / "jmri/resources/jmri-web/servlet/home"
        web.mkdir(parents=True)
        shutil.copy(HOME_PATH, web / "Home.html")
        home = tmp / "home"
        (home / "JMRI_UserFiles").mkdir(parents=True)
        env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        if apps_host:
            env["HART_APPS_HOST"] = apps_host
        if mimic_url:
            env["HART_MIMIC_URL"] = mimic_url
        subprocess.run(["bash", str(tmp / "cats/scripts" / INSTALL.name)], env=env, check=True,
                       capture_output=True)
        return (home / "JMRI_UserFiles/web/servlet/home/Home.html").read_text(encoding="utf-8")

    def test_pi_install_keeps_the_marker_empty(self):
        self.assertIn(MARKER, self._run(None))

    def test_mac_install_names_the_pi(self):
        installed = self._run("RPi-JMRI.local")
        self.assertIn('var HART_APPS_HOST = "RPi-JMRI.local";', installed)
        self.assertNotIn(MARKER, installed)
        self.assertIn(MIMIC_MARKER, installed)  # no mimic URL given: left empty

    def test_mac_install_fills_the_mimic_url(self):
        installed = self._run("localhost", "http://localhost:8765/")
        self.assertIn('var HART_MIMIC_URL = "http://localhost:8765/";', installed)


if __name__ == "__main__":
    unittest.main()
