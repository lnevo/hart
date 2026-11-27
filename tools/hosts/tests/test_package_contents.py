"""The panel background and HART's USS sensor icons reach every host's profile at the path tables.xml names; a parked
Dispatcher System's traininfo is mirrored only from a package that holds it. That no apply step deletes or names a
retired script is checked in test_apply_no_retired_names.py. The repo keeps apply_dispatcher_roster_profiles.py and
the deploy's script list leaves it out (KeptScripts); whether the repo still holds the other retired copies is not
checked.

The Pi's apply step runs here on a made-up drop (pi_drop). The staged package is checked in test_deploy_stage.py
(StageOnly), which stages for real. The Mac's step (ship_mac.sh) installs on this machine, so no test runs it, and
the Windows step is PowerShell, which does not run here: for those two the tests read the one install block each
check needs.
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools/hartlib/src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hartlib import parked, paths  # noqa: E402
from pi_drop import applied, files_under  # noqa: E402

ROOT = paths.REPO_ROOT
MAC = (ROOT / "tools/hosts/deploy/ship_mac.sh").read_text(encoding="utf-8")
WIN = (ROOT / "tools/hosts/windows/apply_hart_package_local.ps1").read_text(encoding="utf-8")
BACKGROUND = "resources/misc/hart_panel_bg_plain.jpg"
USS_ON = "resources/icons/USS/sensor/yellow-on.gif"
# where the stage puts a profile resource in the package: under cats/ (stage.sh, stage_package)
PACKAGE = {BACKGROUND: f"cats/{BACKGROUND}", USS_ON: f"cats/{USS_ON}"}


def windows_install(src_var: str) -> tuple[str, str]:
    """The Windows apply step's block for `$src_var`: the package folder it copies from and the profile folder,
    under each user-files root, it copies to."""
    found = re.search(rf"^\${src_var} = Join-Path \$hart '([^']+)'\n(.*?)^\}}", WIN, flags=re.MULTILINE | re.DOTALL)
    if found is None:
        raise AssertionError(f"apply_hart_package_local.ps1: no ${src_var} = Join-Path $hart '...' block")
    dests = re.findall(r"\$dest = Join-Path \$r '([^']+)'", found.group(2))
    if len(dests) != 1:
        raise AssertionError(f"apply_hart_package_local.ps1: ${src_var}'s block copies to {dests}, not one folder")
    return found.group(1).replace("\\", "/"), dests[0].replace("\\", "/")


def mac_install(function: str) -> str:
    """The profile folder ship_mac.sh's `function` copies into, and check it is called on ~/JMRI_UserFiles."""
    found = re.search(rf'^  {function}\(\) {{\n    local dest="\$1/([^"]+)"', MAC, flags=re.MULTILINE)
    if found is None:
        raise AssertionError(f"ship_mac.sh: no {function} with a local dest=\"$1/...\"")
    if f'\n  {function} "${{HOME}}/JMRI_UserFiles"\n' not in MAC:
        raise AssertionError(f"ship_mac.sh: {function} is not called on ${{HOME}}/JMRI_UserFiles")
    return found.group(1)


class ProfileResources(unittest.TestCase):
    """Each resource tables.xml loads through preference: lands at that path under every host's user files."""

    def test_tables_load_them_from_the_profile(self) -> None:
        tables = paths.TABLES_XML.read_text(encoding="utf-8")
        for rel in (BACKGROUND, USS_ON):
            with self.subTest(rel=rel):
                self.assertTrue((ROOT / "jmri" / rel).is_file())
                self.assertIn(f"preference:{rel}", tables)
        self.assertNotIn("program:resources/icons/USS/sensor/yellow", tables)

    def test_the_pi_installs_them_into_its_user_files_only(self) -> None:
        package = {PACKAGE[rel]: (ROOT / "jmri" / rel).read_bytes() for rel in (BACKGROUND, USS_ON)}
        with applied(package) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            for rel in (BACKGROUND, USS_ON):
                with self.subTest(rel=rel):
                    self.assertEqual((pi.user_files / rel).read_bytes(), (ROOT / "jmri" / rel).read_bytes())
            self.assertFalse((pi.home / "JMRI").exists(), "the apply step wrote into the JMRI install")
            self.assertEqual(pi.calls, [f"install_ops_files.sh {pi.drop}/operations {pi.user_files}/operations --guard",
                                        f"install_roster.sh {pi.drop}/roster {pi.user_files}"])

    def test_windows_copies_each_package_folder_to_the_same_profile_folder(self) -> None:
        self.assertEqual(windows_install("miscSrc"), ("cats/resources/misc", "resources/misc"))
        self.assertEqual(windows_install("ussSrc"), ("cats/resources/icons/USS/sensor", "resources/icons/USS/sensor"))

    def test_the_mac_copies_into_its_user_files(self) -> None:
        self.assertEqual(mac_install("_install_misc_into"), "resources/misc")
        self.assertEqual(mac_install("_install_uss_sensor_icons_into"), "resources/icons/USS/sensor")

    def test_windows_never_copies_into_program_files(self) -> None:
        for line in WIN.splitlines():
            if "Copy-Item" in line or "New-Item" in line:
                self.assertNotIn("Program Files", line)
        install = WIN[WIN.index("$ussSrc ="):WIN.index("$ctcSrc =")]
        self.assertNotIn("Program Files", install)


def shipped_jython() -> list[str]:
    """The Jython scripts stage.sh copies into the package: HART_JYTHON_SCRIPTS as common.sh's load_parked sets it."""
    done = subprocess.run(
        ["bash", "-c", 'source tools/hosts/deploy/common.sh && load_parked && printf "%s\\n" "${HART_JYTHON_SCRIPTS[@]}"'],
        cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    if done.returncode != 0:
        raise AssertionError(f"load_parked failed ({done.returncode}): {done.stderr.strip()}")
    return done.stdout.split()


class KeptScripts(unittest.TestCase):
    """A retired Jython script stays in the repo and out of the package: the deploy's script list leaves it out."""

    KEPT = "jmri/layouts/hart/scripts/apply_dispatcher_roster_profiles.py"

    def test_the_repo_keeps_it_and_the_package_leaves_it_out(self) -> None:
        self.assertTrue((ROOT / self.KEPT).is_file())
        shipped = shipped_jython()
        self.assertIn("jmri/layouts/hart/scripts/panel_status.py", shipped)
        self.assertNotIn(self.KEPT, shipped)


class ParkedFeatures(unittest.TestCase):
    """While a feature is parked (hartlib.parked) the deploy ships none of its files (StageOnly in
    test_deploy_stage.py), and no apply step removes the copies already installed on a host: they stay until
    removed by hand."""

    OLD = "JMRI_UserFiles/dispatcher/traininfo/Old_Route.xml"

    def test_the_parked_setting_names_the_folders_left_out(self) -> None:
        self.assertEqual(parked.shipped_dirs(frozenset({"dispatcher", "uss"})),
                         ["jmri/layouts/hart/dispatcher", "jmri/layouts/hart/ctc"])
        self.assertEqual(parked.shipped_jython(frozenset({"dispatcher"})), ["repair_dispatcher_traininfo.py"])
        self.assertEqual(parked.shipped_dirs(frozenset()), [])

    def test_the_pi_keeps_its_traininfo_when_the_package_has_none(self) -> None:
        with applied({}, installed={self.OLD: "<old/>\n"}) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertEqual(files_under(pi.user_files / "dispatcher"), ["traininfo/Old_Route.xml"])
            self.assertIn("dispatcher files not in the package (parked)", pi.out)

    def test_the_pi_mirrors_the_traininfo_a_package_holds(self) -> None:
        package = {"jmri/layouts/hart/dispatcher/traininfo/New_Route.xml": "<new/>\n"}
        with applied(package, installed={self.OLD: "<old/>\n"}) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertEqual(files_under(pi.user_files / "dispatcher"), ["traininfo/New_Route.xml"])

    def test_windows_and_the_mac_mirror_only_from_the_package(self) -> None:
        # the mirror that deletes (robocopy /PURGE, rsync --delete) runs only when the package holds the traininfo
        win = WIN[WIN.index("$trainInfoSrc = "):]
        self.assertLess(win.index("if (Test-Path $trainInfoSrc)"), win.index("/PURGE"))
        mac = MAC[MAC.index("install_jython_scripts() {"):]
        self.assertLess(mac.index("if parked_dir jmri/layouts/hart/dispatcher; then"), mac.index("rsync -a --delete"))


if __name__ == "__main__":
    unittest.main()
