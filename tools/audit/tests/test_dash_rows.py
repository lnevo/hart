"""tools/agent/dash_rows.py: dashboard writes stamped from the clock, run as a script on a temp dir."""
from __future__ import annotations

import json
import os
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

    def test_a_second_run_in_the_same_minute_does_not_replace_the_first_event(self) -> None:
        first = self.writes("event", "Merged #1371")
        second = self.writes("event", "Merged #1372")
        third = self.writes("event", "Merged #1373", now="23:31")
        self.assertEqual([first[0]["doc_id"], second[0]["doc_id"], third[0]["doc_id"]],
                         ["e3-2330", "e3-2330b", "e3-2331"])
        self.assertEqual(self.data(first[0])["text"], "Merged #1371")
        self.assertEqual(self.data(second[0])["text"], "Merged #1372")

    def test_samples_since_takes_lines_after_the_mark(self) -> None:
        lines = [{"at": t, "sessions": n} for n, t in enumerate(["23:56", "23:58", "00:00", "00:02"])]
        path = self.tmp / "samples.jsonl"
        path.write_text("".join(json.dumps(rec) + "\n" for rec in lines), encoding="utf-8")
        entries = self.writes("samples", str(path), "--since", "23:58")
        self.assertEqual([e["doc_id"] for e in entries], ["s0000", "s0002"])
        self.assertEqual(self.data(entries[1]), {"at": "00:02", "sessions": 3})
        self.assertEqual(len(self.writes("samples", str(path))), 4)
        self.assertIn("23:59", self.refused("samples", str(path), "--since", "23:59"))


class TestLedger(DashRowsCase):
    """OUT_DIR/versions.json: the version each document has after the emitted writes, and the pins read from it."""

    def ledger(self) -> Any:
        return json.loads((self.out / "versions.json").read_text(encoding="utf-8"))

    def sync_file(self, versions: dict[str, object]) -> str:
        path = self.tmp / "listed.json"
        path.write_text(json.dumps(versions), encoding="utf-8")
        return str(path)

    def test_each_op_records_the_version_after_its_write(self) -> None:
        self.writes("new-row", "3-L1", "lane=a", "status=queued", "stage=s", "eta=00:10", "order=1",
                    "event", "started")
        self.assertEqual(self.ledger(), {"data/3/events/e3-2330": 1})
        self.writes("ledger-sync", self.sync_file({"3-L1": 1}))
        [entry] = self.writes("row", "3-L1", "status=running")
        self.assertEqual((entry["op"], entry["if_version"]), ("update", 1))
        self.assertEqual(self.ledger()["data/3/lanes/3-L1"], 2)
        first, second = self.writes("row", "3-L1", "status=ci", "row", "3-L1", "status=review")
        self.assertEqual((first["if_version"], second["if_version"]), (2, 3), "one run pins each write in turn")
        self.assertEqual(self.ledger()["data/3/lanes/3-L1"], 4)
        [gone] = self.writes("delete", "3-L1")
        self.assertEqual(gone, {"op": "delete", "collection": "data/3/lanes", "doc_id": "3-L1", "if_version": 4})
        self.assertNotIn("data/3/lanes/3-L1", self.ledger())

    def test_an_explicit_if_version_wins_once(self) -> None:
        self.writes("ledger-sync", self.sync_file({"3-L2": 5}))
        first, second = self.writes("--if-version", "3-L2=9", "row", "3-L2", "stage=a", "row", "3-L2", "stage=b")
        self.assertEqual((first["if_version"], second["if_version"]), (9, 10))
        self.assertEqual(self.ledger()["data/3/lanes/3-L2"], 11)

    def test_ledger_sync_seeds_corrects_and_removes(self) -> None:
        self.assertEqual([], self.writes("ledger-sync", self.sync_file({"3-L1": 4, "3-L2": 2,
                                                                      "data/3/events/e3-0100": 1})))
        self.assertEqual(self.ledger(), {"data/3/events/e3-0100": 1, "data/3/lanes/3-L1": 4,
                                         "data/3/lanes/3-L2": 2})
        self.writes("ledger-sync", self.sync_file({"3-L1": 7, "3-L2": None}))
        self.assertEqual(self.ledger(), {"data/3/events/e3-0100": 1, "data/3/lanes/3-L1": 7})
        [entry] = self.writes("row", "3-L1", "status=ci")
        self.assertEqual(entry["if_version"], 7)
        self.assertIn("not a version", self.refused("ledger-sync", self.sync_file({"3-L1": "seven"})))
        self.assertEqual(self.ledger()["data/3/lanes/3-L1"], 8, "a refused run leaves the ledger as it was")

    def test_ledger_sync_without_a_wave_takes_full_ids_only(self) -> None:
        def run(path: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, str(SCRIPT), str(self.out), "ledger-sync", path],
                                  capture_output=True, text=True, timeout=30)

        self.assertEqual(0, run(self.sync_file({"data/3/lanes/3-L1": 3})).returncode)
        self.assertEqual(self.ledger(), {"data/3/lanes/3-L1": 3})
        refused = run(self.sync_file({"3-L1": 3}))
        self.assertEqual(2, refused.returncode)
        self.assertIn("--wave", refused.stderr)

    def test_a_row_the_ledger_does_not_hold_names_ledger_sync(self) -> None:
        self.assertIn("ledger-sync", self.refused("row", "3-L9", "status=ci"))

    def test_new_row_over_an_existing_row_leaves_its_version_unknown(self) -> None:
        [entry] = self.writes("new-row", "3-L1", "lane=a", "status=queued", "stage=s", "eta=00:10", "order=1")
        self.assertNotIn("if_version", entry)
        self.assertNotIn("data/3/lanes/3-L1", self.ledger(), "an unpinned set does not guess version 1")
        self.assertIn("ledger-sync", self.refused("row", "3-L1", "status=running"))
        [entry] = self.writes("--if-version", "3-L1=7", "new-row", "3-L1", "lane=a", "status=queued",
                              "stage=s", "eta=00:10", "order=1")
        self.assertEqual(entry["if_version"], 7)
        self.assertEqual(self.ledger()["data/3/lanes/3-L1"], 8, "a pinned set records the pin plus 1")


FAKE_GH = """#!{python}
import json, os, sys
from pathlib import Path
d = Path(os.environ["FAKE_GH_DIR"])
with open(d / "calls.log", "a") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if (d / "fail").exists():
    sys.stderr.write("HTTP 502 from the fake\\n")
    sys.exit(1)
if sys.argv[1:3] == ["pr", "list"]:
    sys.stdout.write((d / "list.json").read_text())
elif sys.argv[1:3] == ["pr", "view"]:
    sys.stdout.write((d / ("view-" + sys.argv[3] + ".json")).read_text())
else:
    sys.exit(3)
"""


def pr(number: int, state: str, merged_at: str | None = None, oid: str | None = None) -> dict[str, object]:
    return {"number": number, "state": state, "mergedAt": merged_at or "",
            "mergeCommit": {"oid": oid} if oid else None}


class TestSyncPrs(DashRowsCase):
    """sync-prs against a fake gh on PATH; TZ=UTC so the merge times read as given."""

    def setUp(self) -> None:
        super().setUp()
        self.gh_dir = self.tmp / "gh"
        self.gh_dir.mkdir()
        fake = self.gh_dir / "gh"
        fake.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
        fake.chmod(0o755)
        self.rows = self.tmp / "rows/data/3/lanes"
        self.rows.mkdir(parents=True)

    def gh_says(self, prs: list[dict[str, object]], **views: dict[str, object]) -> None:
        (self.gh_dir / "list.json").write_text(json.dumps(prs), encoding="utf-8")
        for number, item in views.items():
            (self.gh_dir / f"view-{number.lstrip('n')}.json").write_text(json.dumps(item), encoding="utf-8")

    def row_file(self, doc_id: str, data: dict[str, object]) -> None:
        (self.rows / f"{doc_id}.json").write_text(json.dumps(data), encoding="utf-8")

    def sync(self, *extra: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PATH": f"{self.gh_dir}{os.pathsep}{os.environ['PATH']}",
               "FAKE_GH_DIR": str(self.gh_dir), "TZ": "UTC"}
        return subprocess.run([sys.executable, str(SCRIPT), str(self.out), "--wave", "3", "--now", "02:20",
                               "sync-prs", str(self.rows), *extra], capture_output=True, text=True, timeout=30,
                              env=env)

    def calls(self) -> list[str]:
        path = self.gh_dir / "calls.log"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def test_merged_closed_open_two_prs_and_no_pr(self) -> None:
        self.row_file("3-L1", {"lane": "merged", "status": "ci", "pr": 1301})
        self.row_file("3-L2", {"lane": "closed", "status": "review", "pr": 1302})
        self.row_file("3-L3", {"lane": "open", "status": "ci", "pr": 1303})
        self.row_file("3-L4", {"lane": "split", "status": "ci", "pr": [1301, 1304]})
        self.row_file("3-L5", {"lane": "half merged", "status": "ci", "pr": [1301, 1303]})
        self.row_file("3-L6", {"lane": "no pr", "status": "running"})
        self.row_file("3-L7", {"lane": "already merged", "status": "done", "pr": 1301})
        self.row_file("3-L8", {"lane": "closed then redone", "status": "ci", "pr": [1302, 1304]})
        self.row_file("3-L9", {"lane": "done, old closed PR", "status": "done", "pr": 1302})
        versions = self.tmp / "versions.json"
        versions.write_text(json.dumps({f"3-L{n}": n + 10 for n in range(1, 10)}), encoding="utf-8")
        self.gh_says([pr(1301, "MERGED", "2026-11-28T01:05:00Z", "a" * 40), pr(1302, "CLOSED"),
                      pr(1303, "OPEN")], n1304=pr(1304, "MERGED", "2026-11-28T01:40:00Z", "b" * 40))
        result = self.sync("--versions", str(versions))
        self.assertEqual(result.returncode, 0, result.stderr)
        entries = json.loads(result.stdout)
        self.assertEqual([(e["doc_id"], e["op"], e["if_version"]) for e in entries],
                         [("3-L1", "update", 11), ("3-L2", "update", 12), ("3-L4", "update", 14),
                          ("3-L8", "update", 18)])
        self.assertEqual(self.data(entries[0]),
                         {"status": "merged", "stage": "merged #1301 as aaaaaaa at 01:05", "updated": "02:20"})
        self.assertEqual(self.data(entries[1]),
                         {"status": "failed", "stage": "closed unmerged: #1302", "updated": "02:20"})
        self.assertEqual(self.data(entries[2])["stage"],
                         "merged #1301 as aaaaaaa at 01:05, #1304 as bbbbbbb at 01:40")
        self.assertEqual(self.data(entries[3])["status"], "merged")
        self.assertEqual(self.data(entries[3])["stage"], "merged #1304 as bbbbbbb at 01:40")
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.calls(), ["pr list --state all --limit 200 --json number,state,mergedAt,mergeCommit",
                                        "pr view 1304 --json number,state,mergedAt,mergeCommit"])

    def test_version_read_from_a_wrapped_row_file(self) -> None:
        self.row_file("3-L1", {"data": {"status": "ci", "pr": "1301"}, "version": 6})
        self.gh_says([pr(1301, "MERGED", "2026-11-28T01:05:00Z", "c" * 40)])
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        [entry] = json.loads(result.stdout)
        self.assertEqual((entry["doc_id"], entry["if_version"]), ("3-L1", 6))

    def test_versions_come_from_the_ledger_without_versions_file(self) -> None:
        self.row_file("3-L1", {"status": "ci", "pr": 1301})
        self.row_file("3-L2", {"data": {"status": "ci", "pr": 1301}, "version": 9})
        self.out.mkdir()
        (self.out / "versions.json").write_text(json.dumps({"data/3/lanes/3-L1": 4, "data/3/lanes/3-L2": 6}),
                                                encoding="utf-8")
        self.gh_says([pr(1301, "MERGED", "2026-11-28T01:05:00Z", "c" * 40)])
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([(e["doc_id"], e["if_version"]) for e in json.loads(result.stdout)],
                         [("3-L1", 4), ("3-L2", 9)], "the file's version, else the ledger's")
        ledger = json.loads((self.out / "versions.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger, {"data/3/lanes/3-L1": 5, "data/3/lanes/3-L2": 10})

    def test_a_listed_version_corrects_a_stale_high_ledger(self) -> None:
        self.row_file("3-L1", {"data": {"status": "ci", "pr": 1301}, "version": 5})
        self.row_file("3-L2", {"data": {"status": "running"}, "version": 3})
        self.out.mkdir()
        (self.out / "versions.json").write_text(json.dumps({"data/3/lanes/3-L1": 9, "data/3/lanes/3-L2": 8}),
                                                encoding="utf-8")
        self.gh_says([pr(1301, "MERGED", "2026-11-28T01:05:00Z", "c" * 40)])
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        [entry] = json.loads(result.stdout)
        self.assertEqual((entry["doc_id"], entry["if_version"]), ("3-L1", 5), "the listed version, not the ledger's")
        ledger = json.loads((self.out / "versions.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger, {"data/3/lanes/3-L1": 6, "data/3/lanes/3-L2": 3},
                         "the ledger takes each listed version, rows without a pr too")

    def test_a_versions_file_wins_over_the_row_file_and_the_ledger(self) -> None:
        self.row_file("3-L1", {"data": {"status": "ci", "pr": 1301}, "version": 5})
        self.out.mkdir()
        (self.out / "versions.json").write_text(json.dumps({"data/3/lanes/3-L1": 9}), encoding="utf-8")
        versions = self.tmp / "given.json"
        versions.write_text(json.dumps({"3-L1": 7}), encoding="utf-8")
        self.gh_says([pr(1301, "MERGED", "2026-11-28T01:05:00Z", "c" * 40)])
        result = self.sync("--versions", str(versions))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]["if_version"], 7)

    def test_a_row_with_no_version_is_refused(self) -> None:
        self.row_file("3-L1", {"status": "ci", "pr": 1301})
        self.gh_says([pr(1301, "MERGED", "2026-11-28T01:05:00Z", "c" * 40)])
        result = self.sync()
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("3-L1: no version", result.stderr)

    def test_gh_failing_writes_nothing_and_says_so(self) -> None:
        self.row_file("3-L1", {"status": "ci", "pr": 1301, "version": 2})
        (self.gh_dir / "fail").write_text("", encoding="utf-8")
        result = self.sync()
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("nothing written", result.stderr)
        self.assertIn("HTTP 502", result.stderr)
        self.assertFalse(self.out.exists())

    def test_unreadable_pr_bad_pr_and_non_row_file_are_skipped_with_warnings(self) -> None:
        self.row_file("3-L1", {"status": "ci", "pr": 1301, "version": 3})
        self.row_file("3-L2", {"status": "ci", "pr": 1399, "version": 3})
        self.row_file("3-L3", {"status": "ci", "pr": "soon", "version": 3})
        (self.rows / "3-L4.json").write_text("[1, 2]", encoding="utf-8")
        self.gh_says([pr(1301, "MERGED", "2026-11-28T01:05:00Z", "c" * 40)])
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([e["doc_id"] for e in json.loads(result.stdout)], ["3-L1"])
        for doc_id in ("#1399", "3-L2", "3-L3", "3-L4"):
            self.assertIn(doc_id, result.stderr)

    def test_rows_without_pr_make_no_gh_call(self) -> None:
        self.row_file("3-RC", {"status": "running"})
        result = self.sync()
        self.assertEqual((result.returncode, json.loads(result.stdout)), (0, []))
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
