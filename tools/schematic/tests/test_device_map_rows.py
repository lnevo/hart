"""device_map_rows: the row makers' columns and refusals, bean_cells' comments and refusals on small rows, and
follow_swaps' copies. The whole-map behaviour is pinned by test_bean_goldens.py and test_swap_by_row.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import device_map_rows as rows  # noqa: E402
from device_map_records import DeviceMapRow  # noqa: E402
from map_error import MapError  # noqa: E402
from hartlib import level_devices, railroad  # noqa: E402

NOTE = level_devices.VIRTUAL_NOTE


def row(**cells: str) -> dict[str, str]:
    """A main-level master row with the cells bean_cells and follow_swaps read, `cells` over the defaults."""
    base = dict(level="2", layer="block", role="track", id="", assignment="virtual", user_name="", system_name="",
                jmri_name="", jmri_comment="", cp="", part_of="", notes="", wiring="",
                dcc="", node="", description="", **dict.fromkeys(railroad.DEVICE_FACTS, ""))
    return {**base, **cells}


class DeviceRow(unittest.TestCase):
    def test_every_column_of_the_record_and_the_facts_given(self) -> None:
        got = rows.device_row(2, "CP 107", "mast", "Mast 108L", role="home", ident="mast:107:A:west", dir="west",
                              facing="Track 107-109")
        self.assertEqual(set(got), set(DeviceMapRow.__annotations__))
        self.assertEqual({c: got[c] for c in railroad.DEVICE_FACTS},
                         dict.fromkeys(railroad.DEVICE_FACTS, "") | {"dir": "west", "facing": "Track 107-109"})

    def test_the_fact_columns_are_the_records(self) -> None:
        base = {"level", "cp", "layer", "id", "user_name", "system_name", "jmri_name", "node", "dcc", "comment",
                "trial_name", "notes", "role"}
        self.assertEqual(set(DeviceMapRow.__annotations__) - base, set(railroad.DEVICE_FACTS))

    def test_a_column_that_is_no_fact_stops(self) -> None:
        with self.assertRaisesRegex(MapError, r"mast Mast 108L: unknown fact columns \['colour'\]"):
            rows.device_row(2, "", "mast", "Mast 108L", role="home", ident="m", colour="red")


class BeanCells(unittest.TestCase):
    def setUp(self) -> None:
        self.det = row(layer="occupancy", role="detector", id="det:1", user_name="BS 107", jmri_name="IS:B:107",
                       blocks="Track 107; OS Switch 107", system_name="M2S3305")
        self.block = row(layer="block", id="block:1", user_name="Track 107", jmri_comment="CP 107")
        self.mast = row(layer="mast", role="home", id="mast:107:A:west", user_name="Mast 108L", cp="CP 107",
                        switch="107", dir="west", jmri_name="IF$shsm:basic:one-searchlight(IH:HART:C3:108L)",
                        system_name="IF$shsm:basic:one-searchlight(IH3332)")
        self.head = row(layer="head", role="head", id="mast:107:A:west:single", user_name="Head 108L",
                        jmri_name="IH:HART:C3:108L")

    def cells(self, *given: dict[str, str]) -> dict[str, tuple[str, str]]:
        return {r["user_name"]: (r["start"], r["bean_comment"]) for r in rows.bean_cells(list(given))}

    def test_each_layers_comment(self) -> None:
        got = self.cells(self.det, self.block, self.mast, self.head)
        self.assertEqual(got["BS 107"], ("inactive", f"{NOTE} | planned M2S3305 (draft)"))
        self.assertEqual(got["Track 107"], ("", "BS 107 / IS:B:107; CP 107"))
        self.assertEqual(got["Mast 108L"], ("", "CP 107 | Switch 107 | West | planned "
                                                "IF$shsm:basic:one-searchlight(IH3332) (draft)"))
        self.assertEqual(got["Head 108L"], ("", f"CP 107 | Switch 107 | {NOTE} | planned IH3332 (draft)"))

    def test_a_row_that_makes_no_bean_has_its_cells_emptied(self) -> None:
        staging = row(level="1", layer="block", user_name="Track 1", start="x", bean_comment="y")
        self.assertEqual(self.cells(staging), {"Track 1": ("", "")})

    def test_a_field_detector_starts_as_it_reports_and_names_its_wiring(self) -> None:
        det = dict(self.det, assignment="field", wiring="Node: 4 Sensor: 3")
        self.assertEqual(self.cells(det)["BS 107"], ("", "Node: 4 Sensor: 3"))

    def test_a_block_no_detector_names_stops(self) -> None:
        with self.assertRaisesRegex(MapError, "block Track 9 .level 2.: no detector row names it"):
            rows.bean_cells([row(layer="block", id="block:9", user_name="Track 9")])
        with self.assertRaisesRegex(MapError, "no detector row names its block Track 9"):
            rows.bean_cells([row(layer="block", id="block:9#1", user_name="Track 9 1", part_of="Track 9")])

    def test_a_head_with_no_mast_row_stops(self) -> None:
        with self.assertRaisesRegex(MapError, r"head Head 108L \(mast:107:A:west:single\): no mast row of its id"):
            rows.bean_cells([self.head])

    def test_a_thrown_switch_with_no_turnout_row_stops(self) -> None:
        with self.assertRaisesRegex(MapError, "switches 125 start Thrown"):
            rows.bean_cells([self.det, self.block], frozenset({"125"}))


class FollowSwaps(unittest.TestCase):
    def test_rows_with_no_swap_come_back_as_copies_with_the_same_cells(self) -> None:
        given = [row(layer="block", id="block:1", user_name="Track 107")]
        got = rows.follow_swaps(given, {})
        self.assertEqual(got, given)
        self.assertIsNot(got[0], given[0])

    def test_a_mast_whose_head_row_is_missing_stands_as_it_is(self) -> None:
        mast = row(layer="mast", id="mast:107:A:west", jmri_name="IF$shsm:basic:one-searchlight(IH:HART:C3:108L)")
        self.assertIs(rows.mast_on_heads(mast, {}), mast)

    def test_a_mast_over_a_field_head_takes_the_heads_name(self) -> None:
        mast = row(layer="mast", role="home", id="mast:107:A:west", user_name="Mast 108L", cp="CP 107",
                   jmri_name="IF$shsm:basic:one-searchlight(IH:HART:C3:108L)")
        head = row(layer="head", role="head", id="mast:107:A:west:single", user_name="Head 108L",
                   jmri_name="IH3332", assignment="field")
        got = rows.mast_on_heads(mast, {("2", head["id"]): head})
        self.assertEqual((got["jmri_name"], got["assignment"]),
                         ("IF$shsm:basic:one-searchlight(IH3332)", "field"))


if __name__ == "__main__":
    unittest.main()
