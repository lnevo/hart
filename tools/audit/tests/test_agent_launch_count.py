"""agent_launch_count.py: what counts as a launch, dates, de-duplication and the error paths, on a fake projects tree."""
from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("agent_launch_count", ROOT / "tools/ops/agent_launch_count.py")
ALC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ALC)

D = dt.date


def call(tool_id: str, kind: str | None = None, stamp: str = "2026-11-25T15:00:00Z", name: str = "Agent") -> str:
    inp = {"prompt": "x"} if kind is None else {"prompt": "x", "subagent_type": kind}
    return json.dumps({"timestamp": stamp, "message": {"content": [
        {"type": "tool_use", "id": tool_id, "name": name, "input": inp}]}})


class Tree:
    def __init__(self, base: Path):
        self.checkout = base / "u" / "repo"
        for entry in (".claude", "external", "ops"):
            (self.checkout / entry).mkdir(parents=True)
        self.key = ALC.project_key(self.checkout)
        self.projects = base / "projects"
        (self.projects / self.key).mkdir(parents=True)

    def folder(self, suffix: str = "") -> str:
        return self.key + suffix

    def transcript(self, folder: str, name: str, *lines: str) -> Path:
        p = self.projects / folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def subagent(self, folder: str, agent: str, kind, stamp: str = "2026-11-25T15:00:00Z") -> None:
        sub = self.projects / folder / "sess" / "subagents"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / f"{agent}.meta.json").write_text(json.dumps({} if kind is None else {"agentType": kind}))
        (sub / f"{agent}.jsonl").write_text(json.dumps({"timestamp": stamp, "type": "user"}) + "\n")

    def run(self, *args: str) -> tuple[int, dict | str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(ALC, "main_checkout", return_value=self.checkout), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ALC.main(["--projects", str(self.projects), *args])
        text = out.getvalue()
        return rc, (json.loads(text) if "--json" in args and rc == 0 else text + err.getvalue())


class CountTest(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.t = Tree(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_types_default_and_dedup(self) -> None:
        self.t.transcript(self.t.key, "a.jsonl", call("t1", "site-builder"), call("t2"), call("t3", "Explore"))
        # a resumed session repeats t1 and t2: each id counts once
        self.t.transcript(self.t.key, "b.jsonl", call("t1", "site-builder"), call("t2"), call("t4", name="Task"))
        rc, out = self.t.run("--since", "2026-11-22", "--until", "2026-12-05", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(out["chosen"]["total"], 4)
        self.assertEqual(out["chosen"]["by_type"], {"general-purpose": 2, "site-builder": 1, "Explore": 1})
        self.assertEqual(out["chosen"]["general_purpose_pct"], 50.0)

    def test_dates_are_inclusive_and_local(self) -> None:
        self.t.transcript(self.t.key, "a.jsonl", call("in1", stamp="2026-11-22T12:00:00Z"),
                          call("in2", stamp="2026-12-05T12:00:00Z"), call("out", stamp="2026-12-07T12:00:00Z"))
        with mock.patch.object(ALC, "_local_date", side_effect=lambda s: dt.date.fromisoformat(s[:10]) if s else None):
            rc, out = self.t.run("--since", "2026-11-22", "--until", "2026-12-05", "--json")
        self.assertEqual(out["chosen"]["total"], 2)

    def test_only_this_repos_folders_count(self) -> None:
        k = self.t.key
        self.t.transcript(k + "--claude-worktrees-x", "w.jsonl", call("w1"))
        self.t.transcript(k + "-external-sts", "e.jsonl", call("e1"))
        self.t.transcript("-private-tmp-claude-501-" + k + "-0123abcd-0000-4000-8000-0123456789ab-scratchpad-x",
                          "s.jsonl", call("s1"))
        for sibling in (k + "2", k + "-old", k + "-other-thing", "-private-tmp-" + k + "-scratchpad"):
            self.t.transcript(sibling, "o.jsonl", call("o-" + sibling))
        rc, out = self.t.run("--since", "2026-11-22", "--until", "2026-12-05", "--json")
        self.assertEqual(out["chosen"]["total"], 3)
        self.assertEqual(out["project_dirs"], 4)

    def test_every_launch_counts_forks_and_reads_meta(self) -> None:
        self.t.subagent(self.t.key, "agent-a1", "general-purpose")
        self.t.subagent(self.t.key, "agent-a2", "schematic-builder")
        self.t.subagent(self.t.key, "agent-a3", None)                      # no agentType: the default
        self.t.subagent(self.t.key, "agent-a4", "panel-tracer", stamp="2026-10-01T12:00:00Z")
        rc, out = self.t.run("--since", "2026-11-22", "--until", "2026-12-05", "--json")
        self.assertEqual(out["every"]["total"], 3)
        self.assertEqual(out["every"]["by_type"], {"general-purpose": 2, "schematic-builder": 1})
        self.assertEqual(out["chosen"]["total"], 0)

    def test_unreadable_lines_and_subagents_are_reported_not_hidden(self) -> None:
        self.t.transcript(self.t.key, "a.jsonl", call("t1"), '{"tool_use", "name": "Agent" broken', call("t2", stamp=None))
        sub = self.t.projects / self.t.key / "sess" / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-b.meta.json").write_text("{not json")
        (sub / "agent-c.meta.json").write_text(json.dumps({"agentType": "Explore"}))   # no transcript: undated
        rc, out = self.t.run("--since", "2026-11-22", "--until", "2026-12-05", "--json")
        self.assertEqual(out["chosen"]["total"], 1)
        self.assertEqual(out["unreadable_lines"], 2)
        self.assertEqual(out["unreadable_subagents"], 2)
        rc, text = self.t.run("--since", "2026-11-22", "--until", "2026-12-05")
        self.assertIn("not counted: 2 transcript line(s) and 2 subagent(s)", text)

    def test_text_report_names_both_counts_and_the_baseline(self) -> None:
        self.t.transcript(self.t.key, "a.jsonl", call("t1", "repo-auditor"))
        rc, text = self.t.run("--since", "2026-11-22", "--until", "2026-12-05")
        self.assertEqual(rc, 0)
        self.assertIn("launches a session chose (Agent calls; compare with the baseline): 1", text)
        self.assertIn("every launch (skill forks and their reviewers included): 0", text)
        self.assertIn("404 general-purpose, 68%", text)

    def test_errors(self) -> None:
        rc, text = self.t.run("--since", "2026-12-05", "--until", "2026-11-22")
        self.assertEqual(rc, 2)
        self.assertIn("is before --since", text)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(ALC, "main_checkout", return_value=self.t.checkout), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ALC.main(["--projects", str(self.t.projects / "nowhere"), "--since", "2026-11-22",
                           "--until", "2026-12-05"])
        self.assertEqual(rc, 2)
        self.assertIn("no Claude Code projects folder", err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ALC.main(["--since", "22 Nov", "--until", "2026-12-05"])

    def test_main_checkout_failure_is_a_count_error(self) -> None:
        with mock.patch.object(ALC.subprocess, "run", side_effect=OSError("no git")):
            with self.assertRaises(ALC.CountError):
                ALC.main_checkout(Path("/nowhere"))

    def test_project_key(self) -> None:
        self.assertEqual(ALC.project_key(Path("/Users/x/my.repo")), "-Users-x-my-repo")
        self.assertEqual(ALC.project_key(Path("/Users/x/My Repo_2")), "-Users-x-My-Repo-2")

    def test_no_matching_folder_is_an_error_not_zero(self) -> None:
        (self.t.projects / self.t.key).rmdir()
        self.t.transcript("-home-u-other", "o.jsonl", call("o1"))
        rc, text = self.t.run("--since", "2026-11-22", "--until", "2026-12-05")
        self.assertEqual(rc, 2)
        self.assertIn("no project folder", text)

    def test_a_resumed_copy_keeps_the_earliest_date(self) -> None:
        self.t.transcript(self.t.key, "a.jsonl", call("t1", stamp="2026-11-21T12:00:00Z"))
        self.t.transcript(self.t.key, "b.jsonl", call("t1", stamp="2026-11-23T12:00:00Z"),
                          call("t2", stamp="2026-11-23T12:00:00Z"))
        with mock.patch.object(ALC, "_local_date", side_effect=lambda s: dt.date.fromisoformat(s[:10]) if s else None):
            rc, out = self.t.run("--since", "2026-11-22", "--until", "2026-12-05", "--json")
        self.assertEqual(out["chosen"]["total"], 1)

    def test_only_broken_launch_lines_count_as_unreadable(self) -> None:
        idless = json.dumps({"timestamp": "2026-11-25T15:00:00Z", "message": {"content": [
            {"type": "tool_use", "name": "Agent", "input": {}}]}})
        self.t.transcript(self.t.key, "a.jsonl", '{"type": "tool_use", "name": "Read" broken',
                          '{"type": "tool_use", "name": "Agent" broken', idless)
        rc, out = self.t.run("--since", "2026-11-22", "--until", "2026-12-05", "--json")
        self.assertEqual(out["unreadable_lines"], 2)


if __name__ == "__main__":
    unittest.main()
