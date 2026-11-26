"""car_paths.FINAL_DIR: HART_CAR_IMAGES_FINAL, else under a set HART_CAR_CARDS_ROOT, else the repo copy (hartlib.paths)."""
import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

REPO = Path(__file__).resolve().parents[3]


def load(**env):
    clean = {k: v for k, v in os.environ.items() if k not in ("HART_CAR_IMAGES_FINAL", "HART_CAR_CARDS_ROOT")}
    with mock.patch.dict(os.environ, {**clean, **env}, clear=True):
        import car_paths
        return importlib.reload(car_paths)


class FinalDir(unittest.TestCase):
    def test_default_is_the_repo_copy(self):
        self.assertEqual(load().FINAL_DIR, REPO / "ops/car-cards/car-images/CarImagesFinal")

    def tearDown(self):
        importlib.reload(sys.modules["car_paths"])  # back to this process's own environment

    def test_follows_a_moved_cards_root(self):
        # The image trees stay together; only an unset root used to name ops/hart-ops/CarImagesFinal.
        self.assertEqual(load(HART_CAR_CARDS_ROOT="/elsewhere").FINAL_DIR, Path("/elsewhere/CarImagesFinal"))

    def test_env_wins_over_cards_root(self):
        self.assertEqual(load(HART_CAR_CARDS_ROOT="/elsewhere", HART_CAR_IMAGES_FINAL="/x/final").FINAL_DIR,
                         Path("/x/final"))

    def test_env_wins(self):
        self.assertEqual(load(HART_CAR_IMAGES_FINAL="/x/final").FINAL_DIR, Path("/x/final"))


if __name__ == "__main__":
    unittest.main()
