"""hartlib.paths: one checkout, one layout, and the shims at the old paths."""
import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "src"))

from hartlib import paths  # noqa: E402

CHECKOUT = HERE.parents[3]


class CheckoutTest(unittest.TestCase):
    def test_root_is_the_checkout_holding_hartlib(self):
        self.assertEqual(paths.REPO_ROOT, CHECKOUT)
        self.assertTrue(paths.TABLES_XML.is_file())
        self.assertTrue(paths.PUBLIC_NAME_MAP.is_file())
        self.assertTrue(paths.SIGNAL_WIRING.is_file())
        self.assertTrue(paths.SIGNAL_HEAD_PLAN.is_file())
        self.assertEqual(paths.TABLES_XML, CHECKOUT / "jmri/layouts/hart/output/tables.xml")

    def test_env_roots_do_not_move_paths(self):
        # One answer for where files live: this checkout, so a worktree never reads main's.
        env = {"HART_REPO_ROOT": "/x/repo", "HART_RUNTIME_ROOT": "/y", "HART_CAR_IMAGES_FINAL": ""}
        with mock.patch.dict(os.environ, env):
            fresh = importlib.reload(paths)
            self.assertEqual(fresh.REPO_ROOT, CHECKOUT)
            self.assertEqual(fresh.TABLES_XML, CHECKOUT / "jmri/layouts/hart/output/tables.xml")
            self.assertTrue(str(fresh.car_images_final()).startswith(str(CHECKOUT)))
            self.assertFalse(hasattr(fresh, "runtime_root"))

    def test_rel(self):
        self.assertEqual(paths.rel(paths.TABLES_XML), "jmri/layouts/hart/output/tables.xml")
        self.assertEqual(paths.rel("/nowhere/x"), "/nowhere/x")


class CarImagesTest(unittest.TestCase):
    """Moved from tools/audit/tests/test_hart_paths.py: no retired ~/Desktop/HART (ADR-007)."""

    def test_defaults_to_repo_copy(self):
        with mock.patch.dict(os.environ, {"HART_CAR_IMAGES_FINAL": ""}):
            self.assertEqual(paths.car_images_final(),
                             CHECKOUT / "ops/car-cards/car-images/CarImagesFinal")
            self.assertNotIn("Desktop/HART", str(paths.car_images_final()))

    def test_env_override_still_wins(self):
        with mock.patch.dict(os.environ, {"HART_CAR_IMAGES_FINAL": "/tmp/elsewhere"}):
            self.assertEqual(paths.car_images_final(), Path("/tmp/elsewhere").resolve())


class LayoutPathsTest(unittest.TestCase):
    KEYS = {"layout_dir", "anyrail", "authoritative", "output", "excel", "merge",
            "nx_pairs", "working", "style_defaults"}

    def test_keys_and_values(self):
        got = paths.layout_paths()
        self.assertEqual(set(got), self.KEYS)
        self.assertEqual(Path(got["authoritative"]), paths.TABLES_XML)
        self.assertTrue(got["output"].endswith("hart_blocked.xml"))
        self.assertTrue(Path(got["anyrail"]).is_file())
        self.assertTrue(Path(got["style_defaults"]).is_file())
        self.assertFalse(any(k.startswith("dispatcher") for k in got))

    def test_layout_is_pinned_to_hart(self):
        self.assertEqual(paths.LAYOUT, "hart")
        self.assertTrue(paths.layout_paths("other")["layout_dir"].endswith("layouts/other"))


class ShimsGoneTest(unittest.TestCase):
    def test_old_path_modules_are_gone(self):
        # Their callers moved onto hartlib; nothing may come back to them.
        for old in ("tools/ops/lib/hart_paths.py", "tools/ops/lib/hart_hosts.py", "jmri/layout_paths.py"):
            self.assertFalse((CHECKOUT / old).exists(), old)


class BootstrapTest(unittest.TestCase):
    """The two lines from README.md that scripts copy."""

    SNIPPET = (
        "import sys\n"
        "from pathlib import Path\n"
        'sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents\n'
        '                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")\n'
        "from hartlib import paths  # noqa: E402\n"
        "print(paths.REPO_ROOT)\n"
    )

    def run_script(self, where):
        import subprocess
        script = Path(where) / "probe.py"
        script.write_text(self.SNIPPET, encoding="utf-8")
        try:
            return subprocess.run([sys.executable, "-I", str(script)], capture_output=True, text=True, timeout=30)
        finally:
            script.unlink()

    def test_readme_holds_the_snippet(self):
        readme = (CHECKOUT / "tools/hartlib/README.md").read_text(encoding="utf-8")
        for line in self.SNIPPET.splitlines()[2:4]:
            self.assertIn(line, readme)

    def test_finds_this_checkout(self):
        done = self.run_script(CHECKOUT / "tools/hartlib/tests")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), str(CHECKOUT))

    def test_clear_message_outside_a_checkout(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            done = self.run_script(d)
        self.assertEqual(done.returncode, 1)
        self.assertIn("no tools/hartlib/src above", done.stderr)
        self.assertNotIn("StopIteration", done.stderr)


class PinnedLayout(unittest.TestCase):
    def test_stale_jmri_layout_does_not_move_paths(self) -> None:
        import subprocess
        import sys as _sys
        src = str(Path(paths.__file__).resolve().parents[1])
        out = subprocess.run(
            [_sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
             "from hartlib import paths; print(paths.LAYOUT, paths.TABLES_XML)", src],
            env={**os.environ, "JMRI_LAYOUT": "linear5"}, capture_output=True, text=True, check=True)
        self.assertTrue(out.stdout.startswith("hart "), out.stdout)
        self.assertIn("jmri/layouts/hart/output/tables.xml", out.stdout)


if __name__ == "__main__":
    unittest.main()
