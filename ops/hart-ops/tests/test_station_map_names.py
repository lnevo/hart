"""The track names the station maps print are names the masters hold (the device master's occupancy names), so a
track renamed in the masters fails here instead of leaving a map with the old name. The maps keep their labels in
code, beside the positions they are drawn at (owner, the hand-tables review: drawing data used by one script)."""
import sys
import unittest
from pathlib import Path

HART = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(HART / "ops/station_maps/scripts"), str(HART / "ops/hart-ops/publications"),
                str(HART / "tools/hartlib/src")]

from hartlib import hand_tables  # noqa: E402
from local_station_maps import east_end  # noqa: E402
import render_shenango_station_map as shenango  # noqa: E402
import render_south_yard_station_map as south_yard  # noqa: E402


class StationMapTrackNames(unittest.TestCase):
    def test_every_track_name_on_a_map_is_a_master_name(self):
        names = hand_tables.railroad_names()
        printed = {
            "render_shenango_station_map.py LABELS": [lb.text for lb in shenango.LABELS if lb.font == "track"
                                                      and lb.text.startswith("Track ")],
            "render_south_yard_station_map.py TRACK_NAMES": [n for _, n in south_yard.TRACK_NAMES],
            "local_station_maps/east_end.py TRACK_INDUSTRIES": [t for t, _, _ in east_end.TRACK_INDUSTRIES],
        }
        for where, tracks in printed.items():
            self.assertTrue(tracks, f"{where}: no track names found")
            self.assertEqual([t for t in tracks if t not in names], [],
                             f"{where} prints track names the masters do not hold")


if __name__ == "__main__":
    unittest.main()
