"""The builders take the owner's cells from devices_field.csv, never back from devices_generated.csv (ADR-029
amendment, 2026-11-21).

Under a Python audit hook (as tools/schematic/audit_reads.py runs a script), build_device_map's staging rows
(staging_rows, staging_wired_rows) and build_masts' owner's cells (field_rows, wiring_heads) open the generated file
for no read at all; the one read-back each makes of its own output is its name memory (devices.allocated_names:
part bean numbers, virtual mast ordinals), taken before the hook and passed in. Outside these, a builder reads the
generated file only to keep the other writers' rows when it writes (devices.outputs_after_rows) and for its --check
compare, and the masts builder reads the staging rows build_device_map wrote before it (an earlier step's output).
"""
from __future__ import annotations

import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build_device_map as bdm  # noqa: E402
import device_map_masts as dmm  # noqa: E402
from hartlib import devices  # noqa: E402

GENERATED = os.path.realpath(devices.MASTER)
FIELD = os.path.realpath(devices.FIELD)
_WATCH: list | None = None


def _hook(event: str, args: tuple) -> None:
    if _WATCH is None or event != "open" or not isinstance(args[0], (str, os.PathLike)):
        return
    path = os.path.realpath(os.fspath(args[0]))
    mode = args[1] if isinstance(args[1], str) else "r"
    if path in (GENERATED, FIELD) and not any(c in mode for c in "wxa+"):
        _WATCH.append(path)


sys.addaudithook(_hook)


@contextmanager
def opens():
    """The master files opened for reading inside the block, in order (devices' read caches cleared first, so a
    cached read cannot hide an open)."""
    global _WATCH
    devices._read.cache_clear()
    devices._merged.cache_clear()
    _WATCH = []
    try:
        yield _WATCH
    finally:
        _WATCH = None


class TheStagingRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_layout_le as bl
        try:
            cls.bands, cls.joined, runs, _corners = bdm.solve()
            cls.runs = staticmethod(runs)
        except bl.BuildError as exc:
            raise unittest.SkipTest(str(exc))

    def test_staging_rows_read_the_field_file_and_never_the_generated_one(self):
        names = bdm.staging_part_names()            # the name memory: the generated file, read before the watch
        with opens() as got:
            rows, drawn = bdm.staging_rows(self.bands, self.joined, self.runs, part_names=names)
        self.assertNotIn(GENERATED, got)
        self.assertIn(FIELD, got)
        self.assertGreater(len(rows), 100)
        # drawn: every block row's id, and only those, by the name the drawing gives it
        blocks = {r["id"]: r for r in rows if r["layer"] == "block" and not r["part_of"]}
        self.assertEqual(set(drawn), set(blocks))
        self.assertEqual(len(set(drawn.values())), len(drawn))                 # one generated name per block

    def test_staging_wired_rows_read_the_field_file_and_never_the_generated_one(self):
        with opens() as got:
            rows = bdm.staging_wired_rows()
        self.assertEqual(set(got), {FIELD})       # the field file only (wiring.csv names staging by it too)
        self.assertEqual(len(rows), 80)

    def test_a_blanked_generated_file_gives_the_same_staging_rows(self):
        """The builder's own last rows, blanked, change nothing it builds from the owner's cells: it does not read
        them."""
        want = bdm.staging_wired_rows()
        self.assertEqual(want, bdm.staging_wired_rows(devices.Files.here().but(master=Path("/nonexistent/x.csv"))))


class TheMasts(unittest.TestCase):
    """device_map_masts (build_device_map.py's staging masts) reads the owner's cells by ID from the field file."""

    def test_the_owners_mast_and_head_cells_come_from_the_field_file(self):
        with opens() as got:
            owned = dmm.field_by_id(devices.Files.here())
            wired = dmm.wired_heads(owned)
        self.assertEqual(set(got), {FIELD})       # the field file only (wiring.csv names staging by it too)
        self.assertIn("Mast 6LB", [r["user_name"] for r in owned.values() if r["layer"] == "mast"])
        self.assertEqual(wired["mast:5:B:west:single"]["notes"], "one high head (owner 2026-11-19); IH433 dropped")

    def test_the_ordinals_are_the_one_read_back(self):
        with opens() as got:
            masts = list(devices.allocated_names(("1",), "mast").values())
        self.assertEqual(got, [GENERATED])
        self.assertTrue(any(r["jmri_name"].startswith("IF$vsm") for r in masts))


if __name__ == "__main__":
    unittest.main()
