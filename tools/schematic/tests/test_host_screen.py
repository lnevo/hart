"""host_screen: the layout hosts' screen, the one setting the Layout Editor panel's and the CATS desks' windows are
derived from, checked before either is set."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import host_screen as hs  # noqa: E402

GOOD = {"host_screen": {"size": [1920, 1080], "taskbar": 48}}


class WindowTest(unittest.TestCase):
    def test_the_window_is_the_screen_less_the_taskbar(self) -> None:
        self.assertEqual(hs.window(GOOD), (1920, 1032))
        self.assertEqual(hs.window({"host_screen": {"size": [800, 600], "taskbar": 0}}), (800, 600))

    def test_a_missing_or_malformed_setting_stops_naming_it(self) -> None:
        bad = [
            (None, "is not set"),
            ([1920, 1080], "exactly the keys size and taskbar"),
            ({"size": [1920, 1080]}, "exactly the keys size and taskbar"),
            ({"size": [1920, 1080], "taskbar": 48, "dpi": 96}, "exactly the keys size and taskbar"),
            ({"size": [1920], "taskbar": 48}, "two whole px above zero"),
            ({"size": [1920, 0], "taskbar": 0}, "two whole px above zero"),
            ({"size": [1920.0, 1080], "taskbar": 48}, "two whole px above zero"),
            ({"size": [True, 1080], "taskbar": 48}, "two whole px above zero"),
            ({"size": [1920, 1080], "taskbar": 1080}, "less than the height 1080"),
            ({"size": [1920, 1080], "taskbar": -1}, "less than the height"),
            ({"size": [1920, 1080], "taskbar": "48"}, "taskbar must be whole px"),
        ]
        for value, why in bad:
            with self.subTest(value=value), self.assertRaisesRegex(hs.HostScreenError, why):
                hs.window({} if value is None else {"host_screen": value})


class ApplyTest(unittest.TestCase):
    def test_both_windows_come_from_the_one_setting(self) -> None:
        opts = {"title": "x"}
        self.assertIs(hs.apply(opts, GOOD), opts)
        self.assertEqual(opts, {"title": "x", "le_window": [1920, 1032], "cats_window": [1920, 1032]})
        hs.apply(opts, GOOD)                          # again (a cached sheet handed back): the same, no stop
        self.assertEqual(opts["le_window"], [1920, 1032])

    def test_a_window_set_by_hand_in_the_preferences_stops(self) -> None:
        for key in hs.DERIVED:
            with self.subTest(key=key), self.assertRaisesRegex(hs.HostScreenError, f"sets {key}: they come from"):
                hs.apply({}, dict(GOOD, **{key: [1900, 1140]}))


if __name__ == "__main__":
    unittest.main()
