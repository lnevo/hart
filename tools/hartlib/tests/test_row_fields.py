"""hartlib's readers of the device master take a MasterRow's fields, and its writers and checks take MasterRow.cells().
A row is no Mapping (row["layer"], dict(row) and len(row) raise), so each reader below runs on the real rows only
when it reads them by field."""
from __future__ import annotations

import sys
import unittest
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import (block_lengths, device_rows, devices, drawing_keys, occupancy_bindings, railroad,  # noqa: E402
                     railroad_facts, railroad_invariants, tables_build, wiring)


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
        cls.rows = devices.load()

    def test_a_row_is_no_mapping(self) -> None:
        r = self.rows[0]
        self.assertNotIsInstance(r, Mapping)
        for read in (lambda: r["layer"], lambda: dict(r), lambda: len(r), lambda: "layer" in r):  # type: ignore
            with self.assertRaises(TypeError):
                read()
        self.assertFalse(hasattr(r, "get"))
        self.assertNotEqual(r, r.cells())        # a row equals a row, not its cells

    def test_the_devices_readers(self) -> None:
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
        self.assertTrue(occupancy_bindings.rows())
        self.assertTrue(block_lengths.plan_blocks())
        self.assertTrue(drawing_keys.read(("1", "2", "3")).ids)
        wiring.field_heads()
        self.assertTrue(railroad_facts.read_staging_rows(devices.MASTER))
        self.assertTrue(railroad_facts.read_device_map(devices.MASTER).rows)
        self.assertTrue(railroad_invariants.master_rows(railroad.Railroad(upto="inputs")))

    def test_the_tables_build_reads_the_cells(self) -> None:
        self.assertTrue(tables_build.base().root is not None)


class TheRank(unittest.TestCase):
    def test_row_rank_is_the_masters_order(self) -> None:
        """By level (a level-less row last), then layer, then hand-kept rows before each writer's in WRITERS order."""
        def row(level: str, layer: str, writer: str = "") -> dict[str, str]:
            return dict.fromkeys(devices.COLUMNS, "") | dict(level=level, layer=layer, written_by=writer)
        last, first = devices.WRITERS[-1], devices.WRITERS[0]
        rows = [row("", "turnout"), row("2", "mast", last), row("1", "mast", last), row("1", "mast", first),
                row("1", "mast"), row("1", "turnout")]
        self.assertEqual([(r["level"], r["layer"], r["written_by"]) for r in sorted(rows, key=devices.row_rank)],
                         [("1", "turnout", ""), ("1", "mast", ""), ("1", "mast", first), ("1", "mast", last),
                          ("2", "mast", last), ("", "turnout", "")])


class TheReExport(unittest.TestCase):
    def test_railroad_facts_carries_every_public_name_of_device_rows(self) -> None:
        public = {n for n, v in vars(device_rows).items()
                  if not n.startswith("_") and getattr(v, "__module__", device_rows.__name__) == device_rows.__name__
                  and n.isidentifier() and not isinstance(v, type(sys))}
        self.assertTrue({"row_cells", "MasterRow", "DeviceRow"} <= public)
        self.assertEqual(sorted(n for n in public if not hasattr(railroad_facts, n)), [])


if __name__ == "__main__":
    unittest.main()
