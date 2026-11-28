"""tools/agent/dash_rows.py: dashboard writes stamped from the clock, run as a script on a temp dir."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/agent/dash_rows.py"


class DashRowsCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.out = self.tmp / "out"

    def run_script(self, *args: str, now: str | None = "23:30") -> subprocess.CompletedProcess[str]:
        clock = ["--now", now] if now else []
        return subprocess.run([sys.executable, str(SCRIPT), str(self.out), "--wave", "3", *clock, *args],
                              capture_output=True, text=True, timeout=30)

    def writes(self, *args: str, now: str | None = "23:30") -> list[dict[str, object]]:
        result = self.run_script(*args, now=now)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def refused(self, *args: str) -> str:
        result = self.run_script(*args)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(result.stdout, "")
        return result.stderr

    @staticmethod
    def data(entry: dict[str, object]) -> Any:
        return json.loads(Path(str(entry["file_path"])).read_text(encoding="utf-8"))


class TestRows(DashRowsCase):
    def test_row_update_keeps_typed_values_and_stamps_updated(self) -> None:
        [entry] = self.writes("--if-version", "3-L7=4", "row", "3-L7", "status=ci", "pr=[1271,1280]",
                              "order=7", "eta=23:45", "stage=head abc123 green")
        self.assertEqual(entry, {"op": "update", "collection": "data/3/lanes", "doc_id": "3-L7",
                                 "file_path": str((self.out / "lanes/3-L7.json").resolve()), "if_version": 4})
        self.assertEqual(self.data(entry), {"status": "ci", "pr": [1271, 1280], "order": 7, "eta": "23:45",
                                            "stage": "head abc123 green", "updated": "23:30"})

    def test_new_row_is_a_set_without_if_version(self) -> None:
        [entry] = self.writes("new-row", "3-P1290", "lane=Other session", "status=queued", "stage=plan sent",
                              "eta=00:10", "order=90", "pr=1290")
        self.assertEqual((entry["op"], "if_version" in entry), ("set", False))
        self.assertEqual(self.data(entry)["pr"], 1290)
        self.assertEqual(self.data(entry)["updated"], "23:30")

    def test_clock_stamp_without_now_is_hhmm(self) -> None:
        [entry] = self.writes("--if-version", "3-RC=1", "row", "3-RC", "status=running", now=None)
        self.assertRegex(str(self.data(entry)["updated"]), r"^\d\d:\d\d$")


class TestRefusals(DashRowsCase):
    def test_row_without_if_version_names_the_doc(self) -> None:
        self.assertIn("3-L7", self.refused("row", "3-L7", "status=ci"))

    def test_caller_supplied_times(self) -> None:
        self.assertIn("'updated'", self.refused("--if-version", "3-L7=1", "row", "3-L7", "updated=23:00"))
        self.assertIn("'at'", self.refused("--if-version", "3-L7=1", "row", "3-L7", "at=23:00"))

    def test_bad_status_and_eta(self) -> None:
        self.assertIn("status", self.refused("--if-version", "3-L7=1", "row", "3-L7", "status=green"))
        self.assertIn("eta", self.refused("--if-version", "3-L7=1", "row", "3-L7", "eta=soon"))
        self.assertIn("eta", self.refused("--if-version", "3-L7=1", "row", "3-L7", "eta=24:10"))

    def test_new_row_missing_keys(self) -> None:
        self.assertIn("stage, eta, order", self.refused("new-row", "3-L9", "lane=L9", "status=queued"))

    def test_nothing_written_on_refusal(self) -> None:
        self.refused("event", "ok", "row", "3-L7", "status=ci")
        self.assertFalse(self.out.exists())


class TestEventsAndSamples(DashRowsCase):
    def test_event_ids_get_letters_in_one_run(self) -> None:
        entries = self.writes("event", "Merged #1271", "event", "Deploy pi exit 0", "event", "Wave end")
        self.assertEqual([e["doc_id"] for e in entries], ["e3-2330", "e3-2330b", "e3-2330c"])
        self.assertEqual(self.data(entries[1]), {"at": "23:30", "text": "Deploy pi exit 0"})
        self.assertNotIn("if_version", entries[0])

    def test_samples_since_takes_lines_after_the_mark(self) -> None:
        lines = [{"at": t, "sessions": n} for n, t in enumerate(["23:56", "23:58", "00:00", "00:02"])]
        path = self.tmp / "samples.jsonl"
        path.write_text("".join(json.dumps(rec) + "\n" for rec in lines), encoding="utf-8")
        entries = self.writes("samples", str(path), "--since", "23:58")
        self.assertEqual([e["doc_id"] for e in entries], ["s0000", "s0002"])
        self.assertEqual(self.data(entries[1]), {"at": "00:02", "sessions": 3})
        self.assertEqual(len(self.writes("samples", str(path))), 4)
        self.assertIn("23:59", self.refused("samples", str(path), "--since", "23:59"))


if __name__ == "__main__":
    unittest.main()
