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
        self.assertEqual(paths.TABLES_XML, CHECKOUT / "jmri/layouts/hart/output/tables.xml")

    def test_env_roots_move_only_the_functions(self):
        env = {"HART_REPO_ROOT": "/x/repo", "HART_RUNTIME_ROOT": ""}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(paths.configured_repo_root(), Path("/x/repo").resolve())
            self.assertEqual(paths.runtime_root(), Path("/x/repo").resolve())
            self.assertEqual(paths.REPO_ROOT, CHECKOUT)
        with mock.patch.dict(os.environ, {"HART_REPO_ROOT": "", "HART_RUNTIME_ROOT": "/y"}):
            self.assertEqual(paths.runtime_root(), Path("/y").resolve())
            self.assertEqual(paths.configured_repo_root(), CHECKOUT)

    def test_rel(self):
        self.assertEqual(paths.rel(paths.TABLES_XML), "jmri/layouts/hart/output/tables.xml")
        self.assertEqual(paths.rel("/nowhere/x"), "/nowhere/x")


class CarImagesTest(unittest.TestCase):
    """Moved from tools/audit/tests/test_hart_paths.py: no retired ~/Desktop/HART (ADR-007)."""

    def test_defaults_to_repo_copy(self):
        with mock.patch.dict(os.environ, {"HART_CAR_IMAGES_FINAL": "", "HART_REPO_ROOT": ""}):
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
        self.assertTrue(got["output"].endswith("hart_blocked.xml"))  # check_hart_phase02.py
        self.assertTrue(Path(got["anyrail"]).is_file())
        self.assertTrue(Path(got["style_defaults"]).is_file())
        self.assertFalse(any(k.startswith("dispatcher") for k in got))

    def test_jmri_layout_is_read(self):
        self.assertEqual(paths.LAYOUT, (os.environ.get("JMRI_LAYOUT") or "").strip() or "hart")
        self.assertTrue(paths.layout_paths("other")["layout_dir"].endswith("layouts/other"))


class ShimTest(unittest.TestCase):
    def _import(self, directory, name):
        sys.path.insert(0, str(directory))
        try:
            sys.modules.pop(name, None)
            return importlib.import_module(name)
        finally:
            sys.path.remove(str(directory))

    def test_jmri_layout_paths(self):
        old = self._import(CHECKOUT / "jmri", "layout_paths")
        self.assertEqual(old.layout_paths(), paths.layout_paths())
        self.assertEqual(old.layout_root(), str(paths.LAYOUT_DIR))
        self.assertEqual(old.JMRI_ROOT, str(CHECKOUT / "jmri"))
        self.assertEqual(old.ACTIVE_LAYOUT, paths.LAYOUT)

    def test_hart_paths(self):
        old = self._import(CHECKOUT / "tools/ops/lib", "hart_paths")
        with mock.patch.dict(os.environ, {"HART_REPO_ROOT": "", "HART_RUNTIME_ROOT": ""}):
            self.assertEqual(old.path_tables_xml(), paths.TABLES_XML)
            self.assertEqual(old.path_signal_wiring(), paths.SIGNAL_WIRING)
            self.assertEqual(old.hart_runtime_root(), CHECKOUT)
            self.assertEqual(old.hart_repo_root(), CHECKOUT)
        self.assertFalse(hasattr(old, "mirror_desktop_hart"))


if __name__ == "__main__":
    unittest.main()
