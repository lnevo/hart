"""Every deploy list ships each of signal_coordinator.py's sibling modules and of panel_status.py's parts, and none
makes one a Start Up item.

The script loads the modules named in its SIBLING_MODULES from the jython folder it runs in, and stops with an
error naming the one that is missing. So each list that installs the script into preference:jython must name
exactly those modules beside it: the Mac (common.sh and ship_mac.sh) and the package (stage.sh), from
tools/hosts/pi/jython_scripts.txt, the Pi apply step, from the same file in the package, the Windows apply script,
and live_paths.txt. Both scripts import their siblings through jython_siblings.py (LOADER), which
ships in the same lists. A module is imported, not run: no Start Up item or retarget may name one.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import coordinator  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pi_drop import applied  # noqa: E402
from win_jython import windows_jython  # noqa: E402

DEPLOY = ROOT / "tools/hosts/deploy"
PI_APPLY = ROOT / "tools/hosts/pi/apply_hart_package_local.sh"
WIN_APPLY = ROOT / "tools/hosts/windows/apply_hart_package_local.ps1"
LIVE_PATHS = ROOT / "tools/hosts/live_paths.txt"
SIBLINGS = coordinator.sibling_modules()
# The loader both scripts import their siblings with: shipped with signal_coordinator.py's modules, first.
LOADER = "jython_siblings"
SHIPPED = (LOADER, *SIBLINGS)
# The Mac's copy loop: the Start Up scripts, the coordinator's modules and panel_status.py's parts.
MAC_LOOP = ('for f in "${JYTHON_STARTUP_SCRIPTS[@]}" "${JYTHON_SIBLING_MODULES[@]}" '
            '"${JYTHON_PANEL_STATUS_PARTS[@]}"; do')


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def common_array(name: str) -> list[str]:
    """The bash array `name` (a shell name) as tools/hosts/deploy/common.sh sets it when a deploy step sources it."""
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
        raise ValueError(f"not a bash array name: {name!r}")
    script = f'source "$1" && printf "%s\\n" "${{{name}[@]}}"'
    done = subprocess.run(["bash", "-c", script, "common", str(DEPLOY / "common.sh")],
                          capture_output=True, text=True, timeout=60, check=False)
    if done.returncode != 0:
        raise AssertionError(f"sourcing common.sh failed ({done.returncode}): {done.stderr.strip()}")
    return done.stdout.splitlines()


def pi_jython() -> list[str]:
    """The module names the Pi apply step installs into JMRI_UserFiles/jython from a package built to its list."""
    with applied({}) as pi:
        if pi.code != 0:
            raise AssertionError(f"Pi apply failed ({pi.code}): {pi.out[-2000:]}")
        return sorted(p.stem for p in (pi.user_files / "jython").glob("*.py"))


def block(text: str, opener: str, where: str) -> str:
    """The text of the one list that starts at `opener`, to its closing parenthesis on a line of its own."""
    found = re.findall(re.escape(opener) + r"\n(.*?)^\)", text, re.M | re.S)
    if len(found) != 1:
        raise AssertionError(f"{where}: expected one list opened by {opener!r}, found {len(found)}")
    return found[0]


def named_modules(text: str, sep: str) -> list[str]:
    """The jmri/scripts/*.py module names a list holds (sep: the path separator the list writes), in order."""
    return re.findall(r"jmri" + re.escape(sep) + r"scripts" + re.escape(sep) + r"(\w+)\.py", text)


class CoordinatorShipping(unittest.TestCase):
    def assert_lists_siblings(self, names: list[str], where: str) -> None:
        got = [n for n in names if n != "signal_coordinator"]
        self.assertIn("signal_coordinator", names, f"{where} no longer installs signal_coordinator.py")
        self.assertEqual(sorted(got), sorted(SHIPPED),
                         f"{where} must list exactly the script's SIBLING_MODULES and {LOADER}.py")

    def test_mac_and_package_lists(self) -> None:
        startup = named_modules("\n".join(common_array("JYTHON_STARTUP_SCRIPTS")), "/")
        siblings = named_modules("\n".join(common_array("JYTHON_SIBLING_MODULES")), "/")
        self.assertEqual(siblings, list(SHIPPED), "common.sh JYTHON_SIBLING_MODULES: the loader, then load order")
        self.assertFalse(set(startup) & set(SHIPPED), "a sibling module is in JYTHON_STARTUP_SCRIPTS")
        self.assertIn(MAC_LOOP, read(DEPLOY / "ship_mac.sh"))
        self.assertIn('cp -f "$ROOT/jmri/scripts/signal_coordinator.py" "${JYTHON_SIBLING_MODULES[@]}" '
                      '"$stage/jmri/scripts/"', read(DEPLOY / "stage.sh"))

    def test_pi_list(self) -> None:
        names = [n for n in pi_jython() if n == "signal_coordinator" or n in SHIPPED or n.startswith("sml_")]
        self.assert_lists_siblings(names, "Pi apply")

    def test_windows_list(self) -> None:
        self.assert_lists_siblings(named_modules("\n".join(windows_jython()), "/"), "Windows apply")

    def test_live_paths(self) -> None:
        lines = {ln.strip() for ln in read(LIVE_PATHS).splitlines()}
        missing = [m for m in SHIPPED if f"jmri/scripts/{m}.py" not in lines]
        self.assertEqual(missing, [], "live_paths.txt")

    def test_no_sibling_is_a_start_up_item(self) -> None:
        texts = {p.name: read(p) for p in [*sorted(DEPLOY.glob("*.sh")), PI_APPLY]}
        for name, text in texts.items():
            for m in SHIPPED:
                self.assertNotRegex(text, rf"--script\s+(?:\S*/)?{m}\.py", f"{name} makes {m}.py a Start Up item")
        retarget = block(read(WIN_APPLY), "$retargetNames = @(", "Windows apply")
        for m in SHIPPED:
            self.assertNotIn(f"'{m}.py'", retarget)

    # Jython writes <module>$py.class beside a module it imports and reuses it while it is not older than the .py:
    # a deploy that keeps the source's time (Copy-Item) or rolls back could leave a newer stale class that wins.
    MAC_RM = 'rm -f "$dest/$(basename "$f" .py)\\$py.class"'
    PI_RM = 'rm -f "$UF/jython/$(basename "$f" .py)\\$py.class"'
    WIN_RM = "[System.IO.Path]::GetFileNameWithoutExtension($src) + '$py.class'"

    def copy_loop(self, text: str, opener: str, where: str) -> str:
        """The body of the loop that copies the jython files, from `opener` to its `done`."""
        found = re.findall(re.escape(opener) + r"(.*?)^\s*done\s*$", text, re.M | re.S)
        self.assertEqual(len(found), 1, f"{where}: one copy loop opened by {opener!r}")
        return found[0]

    def test_each_site_deletes_the_compiled_class_of_what_it_copies(self) -> None:
        mac = self.copy_loop(read(DEPLOY / "ship_mac.sh"), MAC_LOOP, "ship_mac.sh")
        self.assertIn(self.MAC_RM, mac)
        win = read(WIN_APPLY)
        loop = win[win.index("foreach ($src in $jythonSrc) {"):win.index("Write-Host (\"preference:jython scripts")]
        self.assertIn(self.WIN_RM, loop)
        self.assertIn("Remove-Item -LiteralPath $compiled -Force", loop)

    def test_the_pi_deletes_the_compiled_class_of_each_module_it_installs(self) -> None:
        stale = {f"JMRI_UserFiles/jython/{n}$py.class": "stale" for n in ("signal_coordinator", *SHIPPED)}
        with applied({}, installed={**stale, "JMRI_UserFiles/jython/other$py.class": "keep"}) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertEqual(sorted(p.name for p in (pi.user_files / "jython").glob("*$py.class")),
                             ["other$py.class"])

    def test_the_bash_deletes_remove_each_modules_class_only(self) -> None:
        names = ["signal_coordinator", *SHIPPED]
        for line, var in ((self.MAC_RM, "dest"), (self.PI_RM, "UF")):
            with tempfile.TemporaryDirectory() as tmp:
                jython = Path(tmp) / "jython" if var == "UF" else Path(tmp)
                jython.mkdir(exist_ok=True)
                for n in names:
                    (jython / f"{n}$py.class").write_text("stale", encoding="utf-8")
                (jython / "other$py.class").write_text("keep", encoding="utf-8")
                script = "\n".join(f'f="/pkg/jmri/scripts/{n}.py"; {line}' for n in names)
                subprocess.run(["bash", "-c", script], check=True, env={var: tmp if var == "UF" else str(jython),
                                                                        "PATH": "/usr/bin:/bin"})
                self.assertEqual(sorted(p.name for p in jython.iterdir()), ["other$py.class"], var)

    def test_block_reader_refuses_a_missing_or_doubled_list(self) -> None:
        with self.assertRaisesRegex(AssertionError, "found 0"):
            block("X=(\n  a\n)\n", "JYTHON=(", "here")
        with self.assertRaisesRegex(AssertionError, "found 2"):
            block("JYTHON=(\n  a\n)\nJYTHON=(\n  b\n)\n", "JYTHON=(", "here")


PARTS = coordinator.panel_status_parts()


def named_parts(text: str, sep: str) -> list[str]:
    """The panel_status*.py names under jmri/layouts/hart/scripts a list holds, in order."""
    return re.findall(r"jmri{0}layouts{0}hart{0}scripts{0}(panel_status\w*)\.py".format(re.escape(sep)), text)


class PanelStatusShipping(unittest.TestCase):
    """The same holds for panel_status.py and its PARTS: every list that installs the script names exactly those
    parts beside it, and none is a Start Up item (panel_status.py stops, naming the part, when one is missing)."""

    def assert_lists_parts(self, names: list[str], where: str) -> None:
        self.assertIn("panel_status", names, f"{where} no longer installs panel_status.py")
        self.assertEqual(sorted(n for n in names if n != "panel_status"), sorted(PARTS),
                         f"{where} must list exactly panel_status.py's PARTS")

    def test_there_are_parts(self) -> None:
        self.assertGreater(len(PARTS), 0)

    def test_mac_and_package_lists(self) -> None:
        startup = named_parts("\n".join(common_array("JYTHON_STARTUP_SCRIPTS")), "/")
        parts = named_parts("\n".join(common_array("JYTHON_PANEL_STATUS_PARTS")), "/")
        self.assertEqual(parts, list(PARTS), "common.sh JYTHON_PANEL_STATUS_PARTS, in PARTS order")
        self.assertEqual(startup, ["panel_status"], "only the script itself is a Start Up item")
        self.assertIn(MAC_LOOP, read(DEPLOY / "ship_mac.sh"))
        self.assertIn('cp -f "${JYTHON_PANEL_STATUS_PARTS[@]}" "$stage/jmri/layouts/hart/scripts/"',
                      read(DEPLOY / "stage.sh"))

    def test_pi_list(self) -> None:
        self.assert_lists_parts([n for n in pi_jython() if n.startswith("panel_status")], "Pi apply")

    def test_windows_list(self) -> None:
        self.assert_lists_parts(named_parts("\n".join(windows_jython()), "/"), "Windows apply")

    def test_live_paths(self) -> None:
        lines = {ln.strip() for ln in read(LIVE_PATHS).splitlines()}
        missing = [m for m in PARTS if f"jmri/layouts/hart/scripts/{m}.py" not in lines]
        self.assertEqual(missing, [], "live_paths.txt")

    def test_no_part_is_a_start_up_item(self) -> None:
        texts = {p.name: read(p) for p in [*sorted(DEPLOY.glob("*.sh")), PI_APPLY]}
        for name, text in texts.items():
            for m in PARTS:
                self.assertNotRegex(text, rf"--script\s+(?:\S*/)?{m}\.py", f"{name} makes {m}.py a Start Up item")
        retarget = block(read(WIN_APPLY), "$retargetNames = @(", "Windows apply")
        for m in PARTS:
            self.assertNotIn(f"'{m}.py'", retarget)

    def test_parts_reader(self) -> None:
        self.assertEqual(named_parts("x jmri/layouts/hart/scripts/panel_status_a.py jmri/scripts/panel_status_b.py",
                                     "/"), ["panel_status_a"])
        self.assertEqual(named_parts("'jmri\\layouts\\hart\\scripts\\panel_status.py'", "\\"), ["panel_status"])


if __name__ == "__main__":
    unittest.main()
