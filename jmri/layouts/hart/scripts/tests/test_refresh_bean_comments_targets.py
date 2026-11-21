"""refresh_bean_comments.py no longer edits tables.xml (R9c, ADR-029) nor devices.csv: the command checks that the
staging heads' wiring in devices.csv is wiring.csv's (build_masts.py writes it); the tables' comments are
generated (tools/schematic/build_tables.py)."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import refresh_bean_comments  # noqa: E402

devices = refresh_bean_comments.devices


class RefreshWritesNothingTest(unittest.TestCase):
    def test_main_writes_no_file(self) -> None:
        with mock.patch.object(refresh_bean_comments, "stale_head_comments", return_value=[]) as stale, \
                mock.patch.object(Path, "write_text") as write_text, \
                mock.patch.object(Path, "write_bytes") as write_bytes:
            self.assertEqual(0, refresh_bean_comments.main())
        stale.assert_called_once_with()
        write_text.assert_not_called()
        write_bytes.assert_not_called()
        self.assertFalse(hasattr(refresh_bean_comments, "TARGETS"))

    def test_a_bad_master_stops_with_its_message(self) -> None:
        err = devices.DevicesError("devices.csv: line 3 broken")
        with mock.patch.object(refresh_bean_comments, "stale_head_comments", side_effect=err):
            self.assertEqual(2, refresh_bean_comments.main())

    def test_a_stale_head_names_the_builder(self) -> None:
        with mock.patch.object(refresh_bean_comments, "stale_head_comments", return_value=["Head 6LB: x"]):
            self.assertEqual(1, refresh_bean_comments.main())


class StaleHeadCommentsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.files = devices.Files.under(self.tmp).but(master=self.tmp / devices.ONE_FILE, field=None)   # one file
        real = devices.Files.here()
        devices.one_file_copy(self.files.master)
        shutil.copyfile(real.dictionary, self.files.dictionary)

    def test_the_committed_heads_are_wiring_csvs(self) -> None:
        self.assertEqual(refresh_bean_comments.stale_head_comments(), [])

    def test_a_head_whose_wiring_differs_is_named(self) -> None:
        rows = [dict(r) for r in devices.load(self.files)]
        head = next(r for r in rows if r["level"] == "1" and r["user_name"] == "Head 6LB")
        want = head["wiring"]
        head["wiring"] = "Node: 4 Signal: 9"
        devices.write_one_file(rows, self.files)
        self.assertEqual(refresh_bean_comments.stale_head_comments(self.files),
                         [f"Head 6LB: wiring.csv gives {want!r}, devices.csv has 'Node: 4 Signal: 9'"])


if __name__ == "__main__":
    unittest.main()
