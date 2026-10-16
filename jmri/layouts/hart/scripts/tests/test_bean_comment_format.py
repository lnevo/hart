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
            "Node: 4 | DCC: 100 | OU: 1 Ports: 1,2",
        )
        self.assertEqual(
            fmt("Node 1 / OU-2 / Ports 8 / OU-3 / Ports 1"),
            "Node: 1 | OU: 2 Ports: 8 | OU: 3 Ports: 1",
        )
        self.assertEqual(fmt("Node 1 / IN-1 / Ports 1"), "Node: 1 | IN: 1 Ports: 1")
        self.assertEqual(
            fmt("Node: 4 | OU-1: Port: 1,2 | DCC: 100"),
            "Node: 4 | DCC: 100 | OU: 1 Ports: 1,2",
        )
        self.assertEqual(
            fmt("Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2"),
            "Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2",
        )
        self.assertEqual(
            fmt("Node: 4 Sensor: 3 | IN: 1 Ports: 1"),
            "Node: 4 Sensor: 3 | IN: 1 Ports: 1",
        )
        self.assertEqual(
            fmt("Node: 4 Signal: 6 | OU: 3 Ports: 1,2,3"),
            "Node: 4 Signal: 6 | OU: 3 Ports: 1,2,3",
        )
        self.assertEqual(fmt("Block 4-2"), "Node: 4 Block: 2")
        self.assertEqual(fmt("Node: 4 Block: 1"), "Node: 4 Block: 1")

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

    def test_comment_from_port_ids_groups_and_spills(self) -> None:
        from_ports = self.m.comment_from_port_ids
        self.assertEqual(
            from_ports(["C4-OU2-1", "C4-OU2-2", "C4-OU2-3"]),
            "Node: 4 | OU: 2 Ports: 1,2,3",
        )
        self.assertEqual(
            from_ports(["C4-OU2-7", "C4-OU3-8", "C4-OU3-7"]),
            "Node: 4 | OU: 2 Ports: 7 | OU: 3 Ports: 8,7",
        )
        self.assertEqual(
            from_ports(["C11-OU3-7", "C11-OU3-8", "C11-OU2-7"]),
            "Node: 11 | OU: 3 Ports: 7,8 | OU: 2 Ports: 7",
        )
        self.assertEqual(
            from_ports(
                ["C4-OU1-1", "C4-OU1-2"],
                dcc="100",
                label="Turnout",
                index=0,
            ),
            "Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2",
        )

    def test_wiring_head_comments_match_live_user_names(self) -> None:
        comments = self.m.load_wiring_head_comments()
        self.assertEqual(comments["Head 6LB Top"], "Node: 4 Signal: 0 | OU: 2 Ports: 1,2,3")
        self.assertEqual(comments["Head 6LB Bottom"], "Node: 4 Signal: 1 | OU: 2 Ports: 4,5,6")
        self.assertEqual(
            comments["Head 6LA"], "Node: 4 Signal: 2 | OU: 2 Ports: 7 | OU: 3 Ports: 8,7"
        )
        self.assertEqual(comments["Head 40LB Top"], "Node: 11 Signal: 0 | OU: 2 Ports: 1,2,3")
        self.assertEqual(comments["Head 24RA Top"], "Node: 2 Signal: 0 | OU: 1 Ports: 1,2,3")
        self.assertEqual(comments["Head 34L Top"], "Node: 12 Signal: 0 | OU: 2 Ports: 1,2,3")
        self.assertEqual(
            comments["Head 38LA"], "Node: 1 Signal: 11 | OU: 3 Ports: 7,8 | OU: 2 Ports: 7"
        )
        self.assertEqual(
            comments["Head 2035"], "Node: 11 Signal: 2 | OU: 3 Ports: 7,8 | OU: 2 Ports: 7"
        )
        self.assertEqual(
            self.m.comment_for(
                "signalhead", "IH432", "Head 6LB Top", "Node: 4 | OU-2: Port: 1,2"
            ),
            "Node: 4 Signal: 0 | OU: 2 Ports: 1,2,3",
        )

    def test_lcc_aliases_use_device_map_names(self) -> None:
        self.assertEqual(self.m.user_name_for("turnout", "MTT100"), "DCC Switch 1")
        self.assertEqual(self.m.user_name_for("turnout", "MTT102"), "DCC Switch 5")
        self.assertEqual(self.m.user_name_for("turnout", "MTT119"), "DCC Switch 9")
        self.assertEqual(
            self.m.comment_for("turnout", "MTT100", "DCC Switch 1", ""),
            "Node: 4 Turnout: 0 | OU: 1 Ports: 1,2",
        )
        leftover = self.m.comment_for("turnout", "MTT102", "DCC Switch 5", "")
        self.assertEqual(leftover, "Node: 4 Turnout: 2 | OU: 1 Ports: 5,6")
        self.assertNotIn("leftover", leftover.lower())
        self.assertNotIn("alias", leftover.lower())


if __name__ == "__main__":
    unittest.main()
