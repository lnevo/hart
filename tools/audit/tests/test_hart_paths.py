"""hart_paths must not point at the retired ~/Desktop/HART folder (ADR-007, 2026-11-09)."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/ops/lib"))

import hart_paths  # noqa: E402


class CarImagesFinalTest(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("HART_CAR_IMAGES_FINAL", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["HART_CAR_IMAGES_FINAL"] = self._saved

    def test_defaults_to_repo_copy(self):
        self.assertEqual(
            hart_paths.car_images_final(),
            hart_paths.hart_repo_root() / "ops/car-cards/car-images/CarImagesFinal",
        )

    def test_env_override_still_wins(self):
        os.environ["HART_CAR_IMAGES_FINAL"] = "/tmp/elsewhere"
        self.assertEqual(hart_paths.car_images_final(), Path("/tmp/elsewhere").resolve())

    def test_no_desktop_mirror(self):
        self.assertFalse(hasattr(hart_paths, "mirror_desktop_hart"))
        self.assertNotIn("DESKTOP_HART", hart_paths.all_mirror_sources())
        for path in hart_paths.all_mirror_sources().values():
            self.assertNotIn("Desktop/HART", str(path))


if __name__ == "__main__":
    unittest.main()
