from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "refresh_bean_comments", SCRIPTS / "refresh_bean_comments.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BeanCommentFormatTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.m = load_module()

    def test_wiring_comment_pipes_and_labels(self) -> None:
        fmt = self.m.format_lcos_comment
        self.assertEqual(
            fmt("Node 4 / OU-1 / Ports 1,2 / DCC 100"),
            "Node: 4 | OU-1: Port: 1,2 | DCC: 100",
        )
        self.assertEqual(
            fmt("Node 1 / OU-2 / Ports 8 / OU-3 / Ports 1"),
            "Node: 1 | OU-2: Port: 8 | OU-3: Port: 1",
        )
        self.assertEqual(fmt("Node 1 / IN-1 / Ports 1"), "Node: 1 | IN-1: Port: 1")
        self.assertEqual(
            fmt("Node: 4 | OU-1: Port: 1,2 | DCC: 100"),
            "Node: 4 | OU-1: Port: 1,2 | DCC: 100",
        )
        self.assertEqual(fmt("Block 4-2"), "Block 4-2")

    def test_mast_comment_includes_protected_switch(self) -> None:
        mast = self.m.mast_protect_comment
        self.assertEqual(mast("Mast 2L", "Brick"), "Brick | Switch 1")
        self.assertEqual(mast("Mast 8LA", "Barn"), "Barn | Switch 7")
        self.assertEqual(mast("Mast 26L", "South Yard"), "South Yard | Switch 21")
        self.assertEqual(mast("Mast 2035", "Princess"), "Princess")
        self.assertEqual(mast("Mast 2L", "Brick | Switch 1"), "Brick | Switch 1")

    def test_block_prose_keeps_occupancy_and_stop(self) -> None:
        refresh = self.m.refresh_block_prose
        self.assertEqual(
            refresh("Lead 117 to 116; occupancy Block 13-1 / M2S1300; stop"),
            "Lead Switch 7 to Switch 13; occupancy Block 13-1 / M2S1300; stop",
        )
        self.assertEqual(
            refresh("Run-through east of 103; occupancy Block 2-8 / M2S207; stop"),
            "Run-through east of Switch 15; occupancy Block 2-8 / M2S207; stop",
        )
        self.assertEqual(
            self.m.BLOCK_COMMENTS["Track Barn"],
            "Lead Switch 7 to Switch 13; occupancy Block 13-1 / M2S1300; stop",
        )
        self.assertEqual(
            self.m.BLOCK_COMMENTS["Track Scale"],
            "Plane diverging lead to Track Barn; occupancy Block 4-8 / M2S407; stop",
        )


if __name__ == "__main__":
    unittest.main()
