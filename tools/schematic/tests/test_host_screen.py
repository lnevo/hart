"""host_screen: the layout hosts' screen, the one setting the Layout Editor panel's and the CATS desks' windows are
derived from, checked before either is set; publish_draft.apply_host_screen, which reads it for the solved sheet; and
le_common.schematic, which turns its stop into a BuildError."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import host_screen as hs  # noqa: E402
import le_common as LC  # noqa: E402
import publish_draft as pd  # noqa: E402

SCREEN = {"size": [1920, 1080], "taskbar": 48}
GOOD = {"host_screen": SCREEN}
PAGE = "main_upper"


def sections(page=None, **others):
    """preferences.json as written: a staging section and the page's."""
    return {"_sections": True, "_note": "x", "staging": others.get("staging", {}), PAGE: GOOD if page is None else page}


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
        self.assertIs(hs.apply(opts, sections(), PAGE), opts)
        self.assertEqual(opts, {"title": "x", "le_window": [1920, 1032], "cats_window": [1920, 1032]})
        hs.apply(opts, sections(), PAGE)               # again (a cached sheet handed back): the same, no stop
        self.assertEqual(opts["le_window"], [1920, 1032])

    def test_a_window_set_by_hand_in_any_section_stops(self) -> None:
        for key in hs.DERIVED:
            for where in (dict(page=dict(GOOD, **{key: [1900, 1140]})), dict(staging={key: [1900, 1140]})):
                with self.subTest(key=key, where=where), \
                        self.assertRaisesRegex(hs.HostScreenError, rf"sets (main_upper|staging)\.{key}: "):
                    hs.apply({}, sections(**where), PAGE)

    def test_a_window_merged_into_the_options_from_elsewhere_stops(self) -> None:
        for key in hs.DERIVED:
            with self.subTest(key=key), self.assertRaisesRegex(hs.HostScreenError, f"{key} \\[1900, 1140\\], which did "
                                                                                    "not come from host_screen"):
                hs.apply({key: [1900, 1140]}, sections(), PAGE)
        opts = hs.apply({}, sections(), PAGE)
        opts["cats_window"] = [1900, 1020]             # changed after this module set it: not its own any more
        with self.assertRaisesRegex(hs.HostScreenError, "cats_window \\[1900, 1020\\]"):
            hs.apply(opts, sections(), PAGE)

    def test_a_missing_page_section_stops(self) -> None:
        whole = sections()
        del whole[PAGE]
        with self.assertRaisesRegex(hs.HostScreenError, "no section 'main_upper'"):
            hs.apply({}, whole, PAGE)


class SolvedSheetTest(unittest.TestCase):
    """A bad host_screen is a HostScreenError from publish_draft (not a SystemExit), and a BuildError from
    le_common.schematic, the way the Layout Editor builders get the page."""

    def data(self, tmp: str, page: dict) -> Path:
        folder = Path(tmp)
        (folder / "preferences.json").write_text(json.dumps(sections(page)), encoding="utf-8")
        return folder

    def test_a_bad_taskbar_is_a_host_screen_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.data(tmp, {"host_screen": {"size": [1920, 1080], "taskbar": 2000}})
            with self.assertRaisesRegex(hs.HostScreenError, "taskbar must be whole px"):
                pd.apply_host_screen({}, folder)
            self.assertEqual(pd.apply_host_screen({}, self.data(tmp, GOOD))["le_window"], [1920, 1032])

    def test_an_unreadable_or_extra_preferences_file_is_a_host_screen_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(hs.HostScreenError, "the page's preferences: .*cannot be read"):
                pd.apply_host_screen({}, Path(tmp))
            folder = self.data(tmp, GOOD)
            (folder / "sheet.preferences.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(hs.HostScreenError, "the page's preferences: sheet.preferences.json"):
                pd.apply_host_screen({}, folder)

    def test_le_common_turns_it_into_a_build_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.data(tmp, {"host_screen": {"size": [1920, 1080], "taskbar": 2000}})
            LC.schematic.cache_clear()
            try:
                with mock.patch.object(LC, "plugin", return_value=(object(), None, None)), \
                        mock.patch.object(pd, "solved_sheet", lambda _sheet: pd.apply_host_screen({}, folder)), \
                        self.assertRaisesRegex(LC.BuildError, "taskbar must be whole px"):
                    LC.schematic()
            finally:
                LC.schematic.cache_clear()


if __name__ == "__main__":
    unittest.main()
