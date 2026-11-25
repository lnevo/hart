#!/usr/bin/env python3
"""make_drawings.detected_sections, read through hartlib.railroad.read_block_lengths (naming-layers step 13).

    python3 docs/ap/electrical/test_make_drawings.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_drawings  # noqa: E402
from hartlib import railroad  # noqa: E402  on the path through make_drawings


def row(name, sensor, plan, measured=None):
    return railroad.BlockLength(2, name, sensor, plan, measured, "timed" if measured else "plan", "1", name)


class DetectedSections(unittest.TestCase):
    def test_detectors_only_sorted_by_node_and_channel_measured_first(self):
        rows = {r.user_name: r for r in (row("Track B", "Block 4-2", 10.0, 11.5), row("OS Switch 1", "Block 3-7", 5.0),
                                         row("Track Hidden", "", 7.0), row("Track A", "Block 3-1", 20.0))}
        with mock.patch.object(make_drawings.railroad, "read_block_lengths", return_value=rows):
            got = make_drawings.detected_sections()
        self.assertEqual(got, [
            {"name": "A", "node": 3, "ch": 1, "inches": 20.0, "estimate": True},
            {"name": "OS Switch 1", "node": 3, "ch": 7, "inches": 5.0, "estimate": True},
            {"name": "B", "node": 4, "ch": 2, "inches": 11.5, "estimate": False},
        ])

    def test_the_committed_file_reads(self):
        got = make_drawings.detected_sections()
        self.assertTrue(got)
        self.assertEqual(got, sorted(got, key=lambda s: (s["node"], s["ch"])))


if __name__ == "__main__":
    unittest.main()
