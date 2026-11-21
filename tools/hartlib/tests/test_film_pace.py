"""film_pace: the shared step and hold of the four site films (no ffmpeg)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hartlib import film_pace  # noqa: E402


class FilmPaceTest(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(film_pace.durations(3), [0.4, 0.4, 2.0])

    def test_length_grows_with_frames(self):
        self.assertEqual(film_pace.film_length(2), 2.4)
        self.assertAlmostEqual(film_pace.film_length(16), 0.4 * 15 + 2.0)
        self.assertAlmostEqual(film_pace.film_length(70), 0.4 * 69 + 2.0)

    def test_one_frame_is_an_error(self):
        with self.assertRaises(ValueError):
            film_pace.durations(1)


if __name__ == "__main__":
    unittest.main()
