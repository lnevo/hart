"""tools/hosts/pi/jython_scripts.txt is the one list of the jython the Mac and the Pi install: common.sh builds the
Mac's and the package's arrays from it, and the Pi apply step reads the copy the package carries. The reader
(jython_list.sh) refuses a malformed list, and the Pi apply step refuses a package without a listed script before
it changes anything."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pi_drop import JYTHON, ROOT, applied, files_under, jython_rows  # noqa: E402

COMMON = ROOT / "tools/hosts/deploy/common.sh"
ARRAYS = {"startup": "JYTHON_STARTUP_SCRIPTS", "sibling": "JYTHON_SIBLING_MODULES", "part": "JYTHON_PANEL_STATUS_PARTS"}


def common_arrays() -> dict[str, list[str]]:
    """Each JYTHON_* array common.sh sets, by role, as paths relative to the repo."""
    out = {}
    for role, name in ARRAYS.items():
        done = subprocess.run(["bash", "-c", f'source "$1" && printf "%s\\n" "${{{name}[@]}}"', "common", str(COMMON)],
                              capture_output=True, text=True, timeout=60, check=False)
        if done.returncode != 0:
            raise AssertionError(f"sourcing common.sh failed ({done.returncode}): {done.stderr.strip()}")
        out[role] = [str(Path(p).relative_to(ROOT)) for p in done.stdout.splitlines()]
    return out


class OneList(unittest.TestCase):
    def test_the_mac_arrays_are_the_lists_rows_in_order(self) -> None:
        arrays = common_arrays()
        for role in ARRAYS:
            with self.subTest(role=role):
                self.assertEqual(arrays[role], [r.path for r in JYTHON if r.role == role])

    def test_the_pi_installs_every_row_and_nothing_else(self) -> None:
        with applied({}) as pi:
            self.assertEqual(pi.code, 0, pi.out)
            self.assertEqual(files_under(pi.user_files / "jython"), sorted(Path(r.path).name for r in JYTHON))

    def test_every_listed_script_is_in_the_repo(self) -> None:
        self.assertEqual([r.path for r in JYTHON if not (ROOT / r.path).is_file()], [])

    def test_the_pi_only_row_is_a_start_up_script_the_package_carries(self) -> None:
        self.assertEqual([r.path for r in JYTHON if r.role == "pi"], ["jmri/layouts/hart/scripts/mimic_relay.py"])


class MissingScript(unittest.TestCase):
    def test_the_pi_stops_before_any_change(self) -> None:
        gone = next(r.path for r in JYTHON if r.role == "sibling")
        with applied({}, omit=(gone,)) as pi:
            self.assertEqual(pi.code, 1, pi.out)
            self.assertIn(f"The package lacks jython the Pi installs (cats/scripts/pi/jython_scripts.txt): {gone}",
                          pi.out)
            self.assertFalse(pi.user_files.exists(), "the apply step changed JMRI_UserFiles")
            self.assertEqual(pi.calls, [], "the apply step ran a step after the check")

    def test_the_pi_stops_on_a_package_without_the_list(self) -> None:
        with applied({}, omit=("cats/scripts/pi/jython_scripts.txt",)) as pi:
            self.assertEqual(pi.code, 1, pi.out)
            self.assertIn("jython list missing:", pi.out)
            self.assertFalse(pi.user_files.exists())


class Reader(unittest.TestCase):
    """jython_list.sh on a list written here."""

    def rows(self, text: str) -> tuple[tuple[str, str], ...]:
        with tempfile.TemporaryDirectory() as tmp:
            listing = Path(tmp) / "jython_scripts.txt"
            listing.write_text(text, encoding="utf-8")
            return tuple(jython_rows(listing))

    def refused(self, text: str, message: str) -> None:
        with self.assertRaisesRegex(ValueError, message):
            self.rows(text)

    def test_reads_rows_in_order_without_comments_or_blank_lines(self) -> None:
        self.assertEqual(self.rows("# a comment\n\nstartup a/x.py\n  \npart b/y.py"),
                         (("startup", "a/x.py"), ("part", "b/y.py")))

    def test_refuses_an_unknown_role(self) -> None:
        self.refused("startup a/x.py\nmodule b/y.py\n", r":2: unknown role 'module'")

    def test_refuses_a_path_it_cannot_install(self) -> None:
        for line in ("startup", "startup /abs/x.py", "startup a/../x.py", "startup ./x.py", "startup a/x.txt",
                     "startup a/x.py extra"):
            with self.subTest(line=line):
                self.refused(line + "\n", r":1: expected 'startup PATH'")

    def test_refuses_a_path_listed_twice(self) -> None:
        self.refused("startup a/x.py\npi a/x.py\n", r":2: a/x.py is listed twice")

    def test_refuses_two_rows_of_one_file_name(self) -> None:
        self.refused("startup a/x.py\npart b/x.py\n", r":2: another row installs a file named x.py")
        self.refused("startup x.py\npart b/x.py\n", r":2: another row installs a file named x.py")
        self.refused("startup a/x.py\npart x.py\n", r":2: another row installs a file named x.py")
        self.assertEqual(self.rows("startup a/x.py\npart a/xx.py\npart b/ax.py\n"),
                         (("startup", "a/x.py"), ("part", "a/xx.py"), ("part", "b/ax.py")))

    def test_refuses_an_empty_or_missing_list(self) -> None:
        self.refused("# only comments\n", "names no script")
        with self.assertRaisesRegex(ValueError, "jython list missing"):
            jython_rows(ROOT / "no/such/jython_scripts.txt")


if __name__ == "__main__":
    unittest.main()
