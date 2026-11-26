"""car_paths takes the final car image folder from hartlib.paths: HART_CAR_IMAGES_FINAL, else the repo copy."""
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

    def test_default_ignores_cards_root(self):
        # The old default followed HART_CAR_CARDS_ROOT, and named ops/hart-ops/CarImagesFinal when it was unset.
        self.assertEqual(load(HART_CAR_CARDS_ROOT="/elsewhere").FINAL_DIR,
                         REPO / "ops/car-cards/car-images/CarImagesFinal")

    def test_env_wins(self):
        self.assertEqual(load(HART_CAR_IMAGES_FINAL="/x/final").FINAL_DIR, Path("/x/final"))


if __name__ == "__main__":
    unittest.main()
