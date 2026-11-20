"""refresh_bean_comments.py no longer edits tables.xml (R9c, ADR-029): the command writes the head wiring comments onto
devices.csv and nothing else; the tables' comments are generated (tools/schematic/build_tables.py)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import refresh_bean_comments


class RefreshWritesNoTablesTest(unittest.TestCase):
    def test_main_writes_only_through_the_master(self) -> None:
        with mock.patch.object(refresh_bean_comments, "sync_map_head_comments", return_value=0) as sync, \
                mock.patch.object(Path, "write_text") as write_text, \
                mock.patch.object(Path, "write_bytes") as write_bytes:
            self.assertEqual(0, refresh_bean_comments.main())
        sync.assert_called_once_with()
        write_text.assert_not_called()
        write_bytes.assert_not_called()
        self.assertFalse(hasattr(refresh_bean_comments, "TARGETS"))

    def test_a_bad_master_stops_with_its_message(self) -> None:
        err = refresh_bean_comments.devices.DevicesError("devices.csv: line 3 broken")
        with mock.patch.object(refresh_bean_comments, "sync_map_head_comments", side_effect=err):
            self.assertEqual(2, refresh_bean_comments.main())


if __name__ == "__main__":
    unittest.main()
