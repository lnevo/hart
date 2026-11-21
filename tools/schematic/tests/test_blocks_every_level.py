"""The block layer of every level, pinned (wiki/projects/level-unification-handoff.md, step 5). Two views:

- the committed block and occupancy rows of devices.csv, read as plain CSV: staging's row by row (name, role, control
  point, trial name; its parts: name, part_of, trial name; occupancy: blocks and detector), and every level's other
  columns by a digest, so a change to any cell of those rows is seen. Step 5 part 1 (owner, 2026-11-20) changed only
  this: staging's block and occupancy rows went from hand-kept to the one block builder's (written_by, left out of
  the digests), devices.csv gained part_of (left out too), staging's 14 links (and the piece of Scale in OS Switch 7)
  became part rows, and the OS blocks' trial names lost the link pieces those rows now carry. Step 5 part 2 (owner,
  2026-11-20): the piece of Scale in OS Switch 7 went (Track Scale one block), and main and upper's 25 links became
  part rows, their block and occupancy rows gone;
- the block layer the readers build from those rows: staging_device_map.load's {strand: blocks} over the staging
  drawing, by the drawing's own keys (OS placeholders and track pieces, from the first end of each piece), and the
  main and upper rows build_device_map.build() writes.

A change here is a change to where blocks are, which needs Signal Mast Logic discovery and the owner's approval of the
panel (the approval fingerprints rule).
"""
from __future__ import annotations

import csv
import hashlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_device_map as bdm  # noqa: E402
import staging_device_map as sdm  # noqa: E402
from repo_read_only import RepoReadOnly  # noqa: E402

DEVICES = bdm.OUT

STAGING_BLOCKS = (
    ('OS Switch 1', 'os', 'Brick', 'OS Switch 1'),
    ('OS Switch 3', 'os', 'Brick', 'OS Switch 3'),
    ('OS Switch 5', 'os', 'Plane', 'OS Switch 5'),
    ('OS Switch 7', 'os', 'Barn', 'OS 7 A-13C'),
    ('OS Switch 7b', 'xover_corner', 'Barn', 'OS 7 A-5B'),
    ('OS Switch 9', 'os', 'Engine House', 'OS Switch 9'),
    ('OS Switch 11', 'os', 'Engine House', 'OS Switch 11'),
    ('OS Switch 13', 'os', 'Engine House', 'OS Switch 13'),
    ('OS Switch 15', 'os', 'South Yard', 'OS Switch 15'),
    ('OS Switch 17', 'os', 'South Yard', 'OS Switch 17'),
    ('OS Switch 19', 'os', 'South Yard', 'OS Switch 19'),
    ('OS Switch 21', 'os', 'South Yard', 'OS Switch 21'),
    ('OS Switch 23a', 'xover_corner', 'East End', 'OS 23 A-1A'),
    ('OS Switch 23b', 'xover_corner', 'East End', 'OS 23 A-31B'),
    ('OS Switch 25', 'os', 'East End', 'OS Switch 25'),
    ('OS Switch 27', 'os', 'East End', 'OS Switch 27'),
    ('OS Switch 29', 'os', 'East End', 'OS Switch 29'),
    ('OS Switch 31', 'os', 'East End', 'OS Switch 31'),
    ('OS Switch 33', 'os', 'East End', 'OS Switch 33'),
    ('OS Switch 35a', 'xover_corner', 'Princess', 'OS 35 A-33A'),
    ('OS Switch 35b', 'xover_corner', 'Princess', 'OS 35 A-39A'),
    ('OS Switch 37', 'os', 'Princess', 'OS Switch 37'),
    ('OS Switch 39', 'os', 'Princess', 'OS Switch 39'),
    ('Track Barn', 'track', '', 'Track 7A-13C'),
    ('Track Brick-Plane', 'track', '', 'Track 1C-5A #2, Track 1C-5A #1'),
    ('Track EH-1', 'track', '', 'Track 11B-end'),
    ('Track EH-2', 'track', '', 'Track 9B-end'),
    ('Track EH-3', 'track', '', 'Track 9C-end'),
    ('Track East Ext', 'track', '', 'Track 5B-7A'),
    ('Track East Lead', 'track', '', 'Track 33A-35A'),
    ('Track Helix Inner', 'helix', '', 'Track 37B-helix'),
    ('Track Helix Outer', 'helix', '', 'Track 39B-helix'),
    ('Track K-1', 'track', '', 'Track 37C-39C #2'),
    ('Track K-2', 'track', '', 'Track 37C-39C #1'),
    ('Track Main East', 'track', '', 'Track 7B-33C'),
    ('Track Main West', 'track', '', 'Track 1A-23A'),
    ('Track S-1', 'track', '', 'Track 17C-29C'),
    ('Track S-2', 'track', '', 'Track 19C-27C'),
    ('Track S-3', 'track', '', 'Track 21C-25C'),
    ('Track S-4', 'track', '', 'Track 21B-25B'),
    ('Track S-R', 'track', '', 'Track 15B-23B'),
    ('Track Scale', 'track', '', 'Track 5C-7B'),
    ('Track W-1', 'track', '', 'Track 3B-end'),
    ('Track W-2', 'track', '', 'Track 3C-end'),
    ('Track West Ext', 'track', '', 'Track 23B-35B'),
)
# (name, part_of, trial_name) of staging's parts: pieces of track inside another block (owner, 2026-11-20)
STAGING_PARTS = (
    ('Track 1-3 at 1', 'OS Switch 1', 'Track 1B-3A 1/2'),
    ('Track 1-3 at 3', 'OS Switch 3', 'Track 1B-3A 2/2'),
    ('Track 9-11', 'OS Switch 9', 'Track 9A-11C'),
    ('Track 11-13', 'OS Switch 11', 'Track 11A-13B'),
    ('Track 13-15', 'OS Switch 15', 'Track 13A-15A'),
    ('Track 15-17', 'OS Switch 15', 'Track 15C-17A'),
    ('Track 17-19', 'OS Switch 17', 'Track 17B-19A'),
    ('Track 19-21', 'OS Switch 19', 'Track 19B-21A'),
    ('Track 23-31', 'OS Switch 31', 'Track 23A-31B'),
    ('Track 25-27', 'OS Switch 25', 'Track 25A-27B'),
    ('Track 27-29', 'OS Switch 27', 'Track 27A-29B'),
    ('Track 29-31', 'OS Switch 29', 'Track 29A-31C'),
    ('Track 31-33', 'OS Switch 31', 'Track 31A-33B'),
    ('Track 35-37', 'OS Switch 35a', 'Track 35B-37A'),
    ('Track 35-39 at 35', 'OS Switch 35b', 'Track 35A-39A 1/2'),
    ('Track 35-39 at 39', 'OS Switch 39', 'Track 35A-39A 2/2'),
)
STAGING_OCCUPANCY = (
    ('BS Barn', 'track', 'Track Barn', 'M2S1300'),
    ('BS Brick-Plane', 'track', 'Track Brick-Plane', 'M2S405'),
    ('BS EH-1', 'track', 'Track EH-1', 'M2S1306'),
    ('BS EH-2', 'track', 'Track EH-2', 'M2S1305'),
    ('BS EH-3', 'track', 'Track EH-3', 'M2S1304'),
    ('BS East Ext', 'track', 'Track East Ext', 'M2S406'),
    ('BS East Lead', 'track', 'Track East Lead', 'M2S106'),
    ('BS K-1', 'track', 'Track K-1', 'M2S100'),
    ('BS K-2', 'track', 'Track K-2', 'M2S101'),
    ('BS Main East', 'track', 'Track Main East', 'M2S202'),
    ('BS Main West', 'track', 'Track Main West', 'M2S200'),
    ('BS S-1', 'track', 'Track S-1', 'M2S206'),
    ('BS S-2', 'track', 'Track S-2', 'M2S205'),
    ('BS S-3', 'track', 'Track S-3', 'M2S204'),
    ('BS S-4', 'track', 'Track S-4', 'M2S203'),
    ('BS S-R', 'track', 'Track S-R', 'M2S207'),
    ('BS Scale', 'track', 'Track Scale', 'M2S407'),
    ('BS Switch 1', 'os', 'OS Switch 1', 'M2S401'),
    ('BS Switch 3', 'os', 'OS Switch 3', 'M2S400'),
    ('BS Switch 5', 'os', 'OS Switch 5', 'M2S404'),
    ('BS Switch 7', 'os', 'OS Switch 7', 'M2S1302'),
    ('BS Switch 7b', 'xover_corner', 'OS Switch 7b', 'M2S1303'),
    ('BS Switch 9', 'os', 'OS Switch 9', 'M2S1307'),
    ('BS Switch 11', 'os', 'OS Switch 11', 'M2S1301'),
    ('BS Switch 13', 'os', 'OS Switch 13', 'M2S300'),
    ('BS Switch 15', 'os', 'OS Switch 15', 'M2S301'),
    ('BS Switch 17', 'os', 'OS Switch 17', 'M2S302'),
    ('BS Switch 19', 'os', 'OS Switch 19', 'M2S304'),
    ('BS Switch 21', 'os', 'OS Switch 21', 'M2S306'),
    ('BS Switch 23a', 'xover_corner', 'OS Switch 23a', 'M2S1203'),
    ('BS Switch 23b', 'xover_corner', 'OS Switch 23b', 'M2S1205'),
    ('BS Switch 25', 'os', 'OS Switch 25', 'M2S1200'),
    ('BS Switch 27', 'os', 'OS Switch 27', 'M2S1202'),
    ('BS Switch 29', 'os', 'OS Switch 29', 'M2S1204'),
    ('BS Switch 31', 'os', 'OS Switch 31', 'M2S1206'),
    ('BS Switch 33', 'os', 'OS Switch 33', 'M2S1207'),
    ('BS Switch 35a', 'xover_corner', 'OS Switch 35a', 'M2S105'),
    ('BS Switch 35b', 'xover_corner', 'OS Switch 35b', 'M2S104'),
    ('BS Switch 37', 'os', 'OS Switch 37', 'M2S102'),
    ('BS Switch 39', 'os', 'OS Switch 39', 'M2S103'),
    ('BS W-1', 'track', 'Track W-1', 'M2S403'),
    ('BS W-2', 'track', 'Track W-2', 'M2S402'),
    ('BS West Ext', 'track', 'Track West Ext', 'M2S107'),
    ('unused Block 2-2', 'spare', '', 'M2S201'),
    ('unused Block 3-8', 'spare', '', 'M2S307'),
)

# (level, name, part_of, trial_name) of the main and upper parts: the 25 links, each in the lower-numbered switch's OS
# block or, where a home mast stands at a switch's points facing it, the OS block at its other end (125-129, 201-205,
# 227-231, 229-233); 225's in the corner block of its leg (step 5 part 2, owner 2026-11-20)
MAIN_UPPER_PARTS = (
    ('2', 'Track 101-103', 'OS Switch 101', 'Track e28'),
    ('2', 'Track 105-109', 'OS Switch 105', 'Track e20'),
    ('2', 'Track 109-111', 'OS Switch 109', 'Track e18'),
    ('2', 'Track 111-117', 'OS Switch 111', 'Track e23'),
    ('2', 'Track 113-115', 'OS Switch 113', 'Track e11'),
    ('2', 'Track 115-117', 'OS Switch 115', 'Track e14'),
    ('2', 'Track 117-119', 'OS Switch 117', 'Track e16'),
    ('2', 'Track 121-123', 'OS Switch 121', 'Track e6'),
    ('2', 'Track 123-125', 'OS Switch 123', 'Track e29'),
    ('2', 'Track 125-129', 'OS Switch 129', 'Track e3'),
    ('2', 'Track 127-131 2', 'OS Switch 127', 'Track e66'),
    ('3', 'Track 201-203', 'OS Switch 201', 'Track e59'),
    ('3', 'Track 201-205', 'OS Switch 205', 'Track e60'),
    ('3', 'Track 201-219', 'OS Switch 201', 'Track e58'),
    ('3', 'Track 205-209', 'OS Switch 205', 'Track e83'),
    ('3', 'Track 213-215', 'OS Switch 213', 'Track e80'),
    ('3', 'Track 219-221', 'OS Switch 219', 'Track e68'),
    ('3', 'Track 225-227', 'OS Switch 225c', 'Track e65'),
    ('3', 'Track 225-229', 'OS Switch 225b', 'Track e61'),
    ('3', 'Track 227-231', 'OS Switch 231', 'Track e48'),
    ('3', 'Track 229-233', 'OS Switch 233', 'Track e37'),
    ('3', 'Track 231-237', 'OS Switch 231', 'Track e42'),
    ('3', 'Track 235-243', 'OS Switch 235', 'Track e50'),
    ('3', 'Track 237-239', 'OS Switch 237', 'Track e43'),
    ('3', 'Track 239-245', 'OS Switch 239', 'Track e45'),
)

# the staging layer: {drawing key: blocks from the key's first end}
STAGING_LAYER = {
    'OS 23 A-1A': ('OS Switch 23a',),
    'OS 23 A-31B': ('OS Switch 23b',),
    'OS 35 A-33A': ('OS Switch 35a',),
    'OS 35 A-39A': ('OS Switch 35b',),
    'OS 7 A-13C': ('OS Switch 7',),
    'OS 7 A-5B': ('OS Switch 7b',),
    'OS Switch 1': ('OS Switch 1',),
    'OS Switch 11': ('OS Switch 11',),
    'OS Switch 13': ('OS Switch 13',),
    'OS Switch 15': ('OS Switch 15',),
    'OS Switch 17': ('OS Switch 17',),
    'OS Switch 19': ('OS Switch 19',),
    'OS Switch 21': ('OS Switch 21',),
    'OS Switch 25': ('OS Switch 25',),
    'OS Switch 27': ('OS Switch 27',),
    'OS Switch 29': ('OS Switch 29',),
    'OS Switch 3': ('OS Switch 3',),
    'OS Switch 31': ('OS Switch 31',),
    'OS Switch 33': ('OS Switch 33',),
    'OS Switch 37': ('OS Switch 37',),
    'OS Switch 39': ('OS Switch 39',),
    'OS Switch 5': ('OS Switch 5',),
    'OS Switch 9': ('OS Switch 9',),
    'Track 11A-13B': ('OS Switch 11',),
    'Track 11B-end': ('Track EH-1',),
    'Track 13A-15A': ('OS Switch 15',),
    'Track 15B-23B': ('Track S-R',),
    'Track 15C-17A': ('OS Switch 15',),
    'Track 17B-19A': ('OS Switch 17',),
    'Track 17C-29C': ('Track S-1',),
    'Track 19B-21A': ('OS Switch 19',),
    'Track 19C-27C': ('Track S-2',),
    'Track 1A-23A': ('Track Main West',),
    'Track 1B-3A': ('OS Switch 1', 'OS Switch 3'),
    'Track 1C-5A #1': ('Track Brick-Plane',),
    'Track 1C-5A #2': ('Track Brick-Plane',),
    'Track 21B-25B': ('Track S-4',),
    'Track 21C-25C': ('Track S-3',),
    'Track 23A-31B': ('OS Switch 31',),
    'Track 23B-35B': ('Track West Ext',),
    'Track 25A-27B': ('OS Switch 25',),
    'Track 27A-29B': ('OS Switch 27',),
    'Track 29A-31C': ('OS Switch 29',),
    'Track 31A-33B': ('OS Switch 31',),
    'Track 33A-35A': ('Track East Lead',),
    'Track 35A-39A': ('OS Switch 35b', 'OS Switch 39'),
    'Track 35B-37A': ('OS Switch 35a',),
    'Track 37B-helix': ('Track Helix Inner',),
    'Track 37C-39C #1': ('Track K-2',),
    'Track 37C-39C #2': ('Track K-1',),
    'Track 39B-helix': ('Track Helix Outer',),
    'Track 3B-end': ('Track W-1',),
    'Track 3C-end': ('Track W-2',),
    'Track 5B-7A': ('Track East Ext',),
    'Track 5C-7B': ('Track Scale',),
    'Track 7A-13C': ('Track Barn',),
    'Track 7B-33C': ('Track Main East',),
    'Track 9A-11C': ('OS Switch 9',),
    'Track 9B-end': ('Track EH-2',),
    'Track 9C-end': ('Track EH-3',),
}

# (rows, sha256) of each level's block and occupancy rows but the parts, every column but written_by and part_of (and,
# on staging, trial_name, pinned row by row above), joined by commas, one row a line, in file order
DIGESTS = {"1": (90, 'ad63b0020d35c033f89db37d6008e69f9fcbfee42168039db7e4f2499bf90533'), "2": (76, 'a6ab6b691e99672675b5f796ed5cea062da133a5bf828858a4d59a079e091846'), "3": (118, 'a35766af132630b83b97b13feb58091ae10cd3a69595c77f862bd388b3dea053')}
SKIP = {"1": ("written_by", "trial_name", "part_of"), "2": ("written_by", "part_of"),
        "3": ("written_by", "part_of")}


def skip_or_fail(exc: Exception) -> None:
    """Skip without the plugin, as the schematic checks do; with SCHEMATIC_REQUIRED=1 (CI) a missing plugin fails."""
    if os.environ.get("SCHEMATIC_REQUIRED") == "1":
        raise AssertionError(f"the block pins need the plugin (SCHEMATIC_REQUIRED=1): {exc}")
    raise unittest.SkipTest(str(exc))


def committed() -> list[dict]:
    with open(DEVICES, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def digest(rows: list[dict], level: str) -> tuple[int, str]:
    cols = [c for c in rows[0] if c not in SKIP[level]]
    sel = [r for r in rows if r["level"] == level and r["layer"] in ("block", "occupancy") and r["role"] != "part"]
    return len(sel), hashlib.sha256("\n".join(",".join(r[c] for c in cols) for r in sel).encode()).hexdigest()


class Committed(unittest.TestCase):
    """devices.csv as committed: plain CSV, no builder."""

    @classmethod
    def setUpClass(cls):
        cls.rows = committed()

    def test_staging_block_rows(self):
        got = tuple((r["user_name"], r["role"], r["cp"], r["trial_name"]) for r in self.rows
                    if r["level"] == "1" and r["layer"] == "block" and r["role"] != "part")
        self.assertEqual(got, STAGING_BLOCKS)

    def test_staging_parts(self):
        got = tuple((r["user_name"], r["part_of"], r["trial_name"]) for r in self.rows
                    if r["level"] == "1" and r["role"] == "part")
        self.assertEqual(got, STAGING_PARTS)

    def test_main_and_upper_parts(self):
        got = tuple((r["level"], r["user_name"], r["part_of"], r["trial_name"]) for r in self.rows
                    if r["level"] != "1" and r["role"] == "part")
        self.assertEqual(got, MAIN_UPPER_PARTS)

    def test_staging_occupancy_rows(self):
        got = tuple((r["user_name"], r["role"], r["blocks"], r["system_name"]) for r in self.rows
                    if r["level"] == "1" and r["layer"] == "occupancy")
        self.assertEqual(got, STAGING_OCCUPANCY)

    def test_every_levels_block_and_occupancy_cells(self):
        for level in "123":
            with self.subTest(level=level):
                self.assertEqual(digest(self.rows, level), DIGESTS[level])


class Readers(RepoReadOnly, unittest.TestCase):
    """The block layer the readers make of the committed rows (needs the plugin at its pinned commit)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            band, _o, _c = sdm.staging_band()
        except sdm.lc.BuildError as exc:
            skip_or_fail(exc)
        cls.band = band
        cls.names = sdm.load(band, with_masts=False)

    def test_staging_layer(self):
        _t, os_ph, refs = sdm.placeholders(self.band)
        got = {ph: (self.names["os"][n],) for n, ph in os_ph.items()}
        for sid, (piece, against) in refs.items():
            blocks = self.names["blocks"][sid]
            got["Track " + piece] = tuple(blocks[::-1] if against else blocks)
        self.assertEqual(got, STAGING_LAYER)

    def test_main_and_upper_rows_are_the_builders(self):
        import build_layout_le as bl
        try:
            bands, joined, runs, corners = bdm.solve()
        except bl.BuildError as exc:
            skip_or_fail(exc)
        rr = bdm.railroad.Railroad(bdm.sources(), upto="inputs")
        _cp, rows, _parts = bdm.build(bands, joined, runs, rr.plan_overrides.data, rr.level_control_points,
                                      rr.lcos_nodes, rr.local_switches, corners)
        mine = [(str(r["level"]), r["user_name"], r["trial_name"], r["notes"]) for r in rows
                if r["layer"] in ("block", "occupancy") and str(r["level"]) in ("2", "3")]
        want = [(r["level"], r["user_name"], r["trial_name"], r["notes"]) for r in committed()
                if r["level"] in ("2", "3") and r["layer"] in ("block", "occupancy")
                and r["role"] != "part"]
        self.assertEqual(mine, want)


if __name__ == "__main__":
    unittest.main()
