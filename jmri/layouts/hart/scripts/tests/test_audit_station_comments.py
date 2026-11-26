"""audit_panel_contracts.station_comments takes the Dispatcher stations and their comments from the device master's
staging block rows marked `stop` (2026-11-22: it replaced the hand-kept copy in check_bean_comments.BLOCK_COMMENTS).
The stations are parked since 2026-11-22, so the live master marks none."""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_panel_contracts as apc  # noqa: E402

devices = apc.devices


def row(name, comment, *, level=apc.levels.STAGING, layer="block", stop="yes"):
    return apc.railroad_facts.DeviceRow(level=level, layer=layer, user_name=name, role="track", jmri_comment=comment,
                                        stop=stop)


class StationComments(unittest.TestCase):
    def test_the_live_master_marks_no_station_while_they_are_parked(self):
        """The stations are parked with the stations topic (owner, 2026-11-22): the master's `stop` is empty."""
        self.assertEqual(apc.station_comments(), {})

    def test_the_detector_reads_first_as_the_tables_build_writes_it(self):
        got = apc.station_comments([row("Track K-1", "Princess balloon, Track K-1; occupancy Block 1-1 / M2S100; stop")])
        self.assertEqual(got, {"Track K-1": "Block 1-1 / M2S100; Princess balloon, Track K-1; stop"})

    def test_only_staging_block_rows_marked_stop_count(self):
        got = apc.station_comments([
            row("Track A", "a; stop"),
            row("Track B", "b", stop=""),               # not marked stop
            row("Track C", "c; stop", stop=""),
            row("Track Helix Outer", "CP 127", level=2),  # a main-level helix row
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


    def test_a_bad_master_is_an_audit_error_not_a_traceback(self):
        audit = apc.Audit("test", Path("tables.xml"))
        with mock.patch.object(apc, "station_comments", side_effect=devices.DevicesError("station 'Track A' ...")):
            apc.audit_stations(ET.Element("layout-config"), None, audit, required=True)
        self.assertEqual(audit.errors, ["Dispatcher stations: station 'Track A' ..."])


if __name__ == "__main__":
    unittest.main()
