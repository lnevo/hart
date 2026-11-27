"""hartlib's readers of the device master take a MasterRow's fields, and its writers and checks take MasterRow.cells():
none of them reads a row through its Mapping view (row["layer"], dict(row), len(row)), which only the callers outside
hartlib still use."""
from __future__ import annotations

import sys
import unittest
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import (block_lengths, device_rows, devices, drawing_keys, occupancy_bindings, railroad,  # noqa: E402
                     railroad_facts, railroad_invariants, tables_build, wiring)


@contextmanager
def no_mapping_view() -> Iterator[None]:
    """MasterRow's Mapping methods raise while the block runs, naming the method."""
    def refuse(name: str) -> Callable[..., object]:
        def call(self: object, *args: object, **kwargs: object) -> object:
            raise AssertionError(f"a hartlib reader used MasterRow.{name}")
        return call
    names = ("__getitem__", "__iter__", "__len__", "__contains__", "get", "keys", "items", "values", "__or__")
    with ExitStack() as stack:
        for n in names:
            stack.enter_context(mock.patch.object(device_rows.MasterRow, n, refuse(n)))
        yield


BEAN = ('{"beans":[{"section":["turnouts","jmri.jmrix.openlcb.configurexml.OlcbTurnoutManagerXml"],'
        '"element":{"tag":"turnout","attrs":{"feedback":"MONITORING"},"children":[{"tag":"systemName","attrs":{},'
        '"text":"MTT999"},{"tag":"userName","column":"user_name"}]}}]}')


def store_row() -> device_rows.MasterRow:
    """A Store's level-less device as the merged view holds it: no level, no role."""
    cells = dict.fromkeys(devices.COLUMNS, "") | dict(layer="turnout", user_name="Test 999", assignment="field",
                                                      system_name="MTT999", jmri_name="MTT999", jmri_bean=BEAN)
    return device_rows.MasterRow.from_master(cells, 999, "a Store's row")


class TheTwoRowForms(unittest.TestCase):
    """The helpers a writer and a reader share (a row's key, name, place, role and comment) take a MasterRow or a row
    of the master's text, and give the same answer for both forms of one row."""

    def test_every_row_gives_the_same_answers_in_both_forms(self) -> None:
        index = devices.index()
        for row in (*devices.load(), store_row()):
            cells = row.cells()
            with self.subTest(devices.row_text(cells)):
                for helper in (devices.key_of, devices.name_key, devices.row_text, devices.is_unplaced,
                               devices.comment_of, devices.device_map_row, devices.place, index.where):
                    self.assertEqual(helper(row), helper(cells), getattr(helper, "__name__", helper))
                if row.role:
                    self.assertEqual(devices.row_role(row), devices.row_role(cells))

    def test_a_level_less_row_with_no_role_stops_in_both_forms(self) -> None:
        row = store_row()
        self.assertEqual((devices.key_of(row), devices.is_unplaced(row)), (("", "turnout", "Test 999"), True))
        for form in (row, row.cells()):
            with self.subTest(type(form).__name__), \
                    self.assertRaisesRegex(devices.DevicesError, "'Test 999' has no role"):
                devices.row_role(form, "here")

    def test_the_readers_text_forms_are_the_merged_views_cells(self) -> None:
        rows = devices.load()
        parts = devices.part_lines(("1", "2", "3"))
        self.assertEqual(parts, [(r.line, r.cells()) for r in rows if r.role == "part"])
        self.assertTrue(all(type(r) is dict for _n, r in parts))
        self.assertEqual(dict(devices.user_names()),
                         {(r.level_cell, r.id): r.user_name for r in rows if r.level and r.id})


class TheReadersTakeFields(unittest.TestCase):
    rows: tuple[device_rows.MasterRow, ...]

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = devices.load()          # read (and cached) before the view is refused

    def test_the_devices_readers(self) -> None:
        with no_mapping_view():
            index = devices.index()
            self.assertTrue(devices.device_map_lines(("1", "2", "3")))
            self.assertTrue(devices.user_names())
            devices.part_lines(("1", "2", "3"))
            self.assertTrue(index.names("block", roles=devices.LINE_ROLES))
            self.assertTrue(index.names("turnout", levels=("2",)))
            for r in self.rows[:40]:
                index.where(r)
                index.role(r.layer, r.user_name)
                self.assertEqual(index.is_unplaced(r.layer, r.user_name), r.level is None)
                devices.row_text(r)
                devices.key_of(r)
            self.assertEqual(devices.stale(), [])

    def test_the_other_readers(self) -> None:
        with no_mapping_view():
            self.assertTrue(occupancy_bindings.rows())
            self.assertTrue(block_lengths.plan_blocks())
            self.assertTrue(drawing_keys.read(("1", "2", "3")).ids)
            wiring.field_heads()
            self.assertTrue(railroad_facts.read_staging_rows(devices.MASTER))
            self.assertTrue(railroad_facts.read_device_map(devices.MASTER).rows)
            self.assertTrue(railroad_invariants.master_rows(railroad.Railroad(upto="inputs")))

    def test_the_tables_build_reads_the_cells(self) -> None:
        with no_mapping_view():
            self.assertTrue(tables_build.base().root is not None)


if __name__ == "__main__":
    unittest.main()
