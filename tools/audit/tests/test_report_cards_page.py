"""tools/agent/report_cards_page.py: the scores master's rules, dashboard times and the page build."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/agent"))

import report_cards_page as rc  # noqa: E402

EST = timezone(timedelta(hours=-5))


def master(**over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "page": "https://example.invalid/page",
        "categories": [{"id": "code", "title": "Code", "scale": 4, "what": "w", "wiki": "wiki/x.md",
                        "scores": [{"date": "2026-11-26", "value": 3.0, "label": "a"},
                                   {"date": "2026-11-27", "value": 3.2, "label": "b"}],
                        "table": {"columns": ["A", "B"], "rows": [["x", 1]]}}],
        "unscored": [{"date": "2026-11-02", "title": "Old card", "text": "t"}],
        "dashboards": [{"id": "w", "title": "Wave", "start": "2026-11-27T22:00", "store": "data/w",
                        "link": "https://example.invalid/d", "wiki": "wiki/w.md", "summary": "s"}],
    }
    data.update(over)
    return data


class Case(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def write(self, rel: str, obj: Any) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj))
        return path


class ValidateTest(Case):
    def test_repo_master_is_valid(self) -> None:
        data = rc.load_scores()
        self.assertTrue(data["categories"])
        self.assertTrue(data["page"].startswith("https://claude.ai/artifact/"))

    def test_score_off_scale_is_refused(self) -> None:
        data = master()
        data["categories"][0]["scores"][1]["value"] = 4.5
        with self.assertRaisesRegex(rc.CardsError, "not on 0..4"):
            rc.validate(data)

    def test_scores_out_of_date_order_are_refused(self) -> None:
        data = master()
        data["categories"][0]["scores"].reverse()
        with self.assertRaisesRegex(rc.CardsError, "out of date order"):
            rc.validate(data)

    def test_table_row_must_match_columns(self) -> None:
        data = master()
        data["categories"][0]["table"]["rows"].append(["only one"])
        with self.assertRaisesRegex(rc.CardsError, "does not match"):
            rc.validate(data)

    def test_duplicate_dashboard_and_bad_start_are_refused(self) -> None:
        data = master()
        data["dashboards"].append(dict(data["dashboards"][0]))
        with self.assertRaisesRegex(rc.CardsError, "used twice"):
            rc.validate(data)
        data = master()
        data["dashboards"][0]["start"] = "27 Nov 22:00"
        with self.assertRaisesRegex(rc.CardsError, "not YYYY-MM-DDTHH:MM"):
            rc.validate(data)

    def test_bad_unscored_date_names_the_item(self) -> None:
        with self.assertRaisesRegex(rc.CardsError, "unscored Old card"):
            rc.validate(master(unscored=[{"date": "Nov 2", "title": "Old card"}]))


class StampTest(unittest.TestCase):
    def test_time_before_start_is_next_day(self) -> None:
        self.assertEqual(rc.stamp("2026-11-27T22:22", "23:10"), "2026-11-27T23:10")
        self.assertEqual(rc.stamp("2026-11-27T22:22", "00:14"), "2026-11-28T00:14")
        self.assertEqual(rc.stamp("2026-11-30T23:00", "01:00"), "2026-12-01T01:00")

    def test_bad_time_is_none(self) -> None:
        self.assertIsNone(rc.stamp("2026-11-27T22:22", "25:00"))
        self.assertIsNone(rc.stamp("2026-11-27T22:22", None))


class SlippageTest(unittest.TestCase):
    def test_drop_is_marked(self) -> None:
        data = master()
        data["categories"][0]["scores"][1]["value"] = 2.9
        lines = rc.slippage(data)
        self.assertTrue(lines[0].startswith("SLIP Code: 2.9"), lines)
        self.assertIn("(-0.1)", lines[0])

    def test_rise_and_first_score(self) -> None:
        data = master()
        data["categories"].append({"id": "ux", "title": "UX", "scale": 10, "what": "w", "wiki": "w",
                                   "scores": [{"date": "2026-11-28", "value": 6.8, "label": "x"}]})
        lines = rc.slippage(data)
        self.assertEqual(lines[0], "Code: 3.2 on 2026-11-27, 3.0 on 2026-11-26 (+0.2)")
        self.assertEqual(lines[1], "UX: 6.8 on 2026-11-28 (first score)")


class BuildTest(Case):
    def test_build_writes_page_and_counts_merges_in_window(self) -> None:
        scores = self.write("scores.json", master())
        self.write("dumps/data/w/lanes/w-L1.json", {"lane": "L1", "status": "merged", "order": 1, "pr": 7})
        self.write("dumps/data/w/events/e1.json", {"at": "22:05", "text": "Merged #1001"})
        self.write("dumps/data/w/events/e2.json", {"at": "00:30", "text": "Wave done"})
        self.write("dumps/data/w/samples/s1.json", {"at": "23:00", "mac_load1": 3.5, "mac_cpus": 8,
                                                    "sessions": 2, "subagents": 4, "claude_total": 6})
        merged = self.write("merged.json", [
            {"number": 1000, "mergedAt": "2026-11-28T02:59:00Z"},
            {"number": 1001, "mergedAt": "2026-11-28T03:05:00Z"},
            {"number": 1002, "mergedAt": "2026-11-28T05:30:00Z"},
            {"number": 1003, "mergedAt": "2026-11-28T05:31:00Z"},
        ])
        template = self.tmp / "index.html"
        template.write_text("<title>t</title>")
        out = self.tmp / "out"
        dashes = rc.build(self.tmp / "dumps", merged, out, scores=scores, template=template, tz=EST)
        self.assertEqual([d.prs for d in dashes], [[1001, 1002]])
        self.assertEqual(dashes[0].end, "2026-11-28T00:30")
        self.assertEqual((out / "index.html").read_text(), "<title>t</title>")
        dash = json.loads((out / "dash.json").read_text())[0]
        self.assertEqual(dash["samples"][0]["sessions"], 2)
        self.assertEqual(dash["lanes"][0]["id"], "w-L1")
        self.assertEqual(json.loads((out / "cards.json").read_text())["page"], "https://example.invalid/page")

    def test_wave_ids_and_missing_store(self) -> None:
        self.assertEqual(rc.wave_of("3-L1", True), 3)
        self.assertEqual(rc.wave_of("e5-0307", True), 5)
        self.assertEqual(rc.wave_of("A2", True), 2)
        self.assertIsNone(rc.wave_of("3-L1", False))
        scores = self.write("scores.json", master())
        merged = self.write("merged.json", [])
        with self.assertRaisesRegex(rc.CardsError, "no store copy"):
            rc.build(self.tmp / "dumps", merged, self.tmp / "out", scores=scores, template=scores, tz=EST)

    def test_main_check_and_slippage_exit_codes(self) -> None:
        self.assertEqual(rc.main(["check"]), 0)
        self.assertIn(rc.main(["slippage"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
