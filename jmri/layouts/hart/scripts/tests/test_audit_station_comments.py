"""audit_panel_contracts.station_comments takes the Dispatcher stations and their comments from the device master's
staging block rows marked `stop` (2026-11-22: it replaced the hand-kept copy in refresh_bean_comments.BLOCK_COMMENTS)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_panel_contracts as apc  # noqa: E402

devices = apc.devices


def row(name, comment, *, level=devices.FIELD_LEVEL, layer="block", stop="yes"):
    return {"level": level, "layer": layer, "user_name": name, "jmri_comment": comment, "stop": stop}


class StationComments(unittest.TestCase):
    def test_the_live_master_gives_the_twelve_staging_stations(self):
        got = apc.station_comments()
        self.assertEqual(len(got), 12)
        self.assertEqual(got["Track K-1"], "Princess balloon, Track K-1; occupancy Block 1-1 / M2S100; stop")
        self.assertTrue(all(c.endswith("; stop") or c == "stop" for c in got.values()))

    def test_only_staging_block_rows_marked_stop_count(self):
        got = apc.station_comments([
            row("Track A", "a; stop"),
            row("Track B", "b", stop=""),               # not marked stop
            row("Track C", "c; stop", stop=""),
            row("Track Helix Outer", "CP 127", level="2"),  # a main-level helix row
            row("BS A", "a; stop", layer="occupancy"),
        ])
        self.assertEqual(got, {"Track A": "a; stop"})

    def test_a_stop_row_whose_comment_does_not_end_in_stop_is_an_error(self):
        with self.assertRaisesRegex(devices.DevicesError, "'Track A' is marked stop .* does not end in 'stop'"):
            apc.station_comments([row("Track A", "a")])

    def test_one_station_with_two_comments_is_an_error(self):
        with self.assertRaisesRegex(devices.DevicesError, "'Track A' has two comments"):
            apc.station_comments([row("Track A", "a; stop"), row("Track A", "b; stop")])

    def test_the_same_comment_twice_is_one_station(self):
        self.assertEqual(apc.station_comments([row("Track A", "a; stop"), row("Track A", "a; stop")]),
                         {"Track A": "a; stop"})


if __name__ == "__main__":
    unittest.main()
