#!/usr/bin/env python3
"""agent_launch_count.py

Count the subagents Claude Code sessions launched for this repo, by agent type, from the session transcripts.

    python3 tools/ops/agent_launch_count.py --since 2026-11-22 --until 2026-12-05
    python3 tools/ops/agent_launch_count.py --since 2026-10-31 --until 2026-11-21 --json

It reads every transcript (*.jsonl, subagent transcripts included) under the Claude Code projects folder
(~/.claude/projects, or --projects) whose project folder belongs to this repo: the main checkout, its worktrees and
subfolders, and session scratchpads named after it, and gives two counts:

- chosen: every Agent (or older Task) tool call, whoever made it (a main session or a subagent). A call with no
  subagent_type is the default, general-purpose. A resumed session repeats earlier calls in its transcript, so each
  tool call id counts once. This is the count the 2026-11-21 baseline used (it gives 426 for that window).
- every: every subagent Claude Code started, one subagents/agent-*.meta.json each, with its agentType. It adds the
  agents no session picks a type for: skill forks such as /code-review and the reviewers they start.

Dates are local, and both ends are included. A subagent is dated by the first timestamp in its transcript. The health round 2 target (wiki/projects/health-round2-handoff.md, item 3) is general-purpose
under 50% of launches; the 2026-11-21 baseline was 404 general-purpose launches, 68%.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TYPE = "general-purpose"
LAUNCH_TOOLS = ("Agent", "Task")


class CountError(Exception):
    """A problem the caller can fix: a missing folder, a bad date range, no repo checkout."""


def main_checkout(root: Path = ROOT) -> Path:
    """The main checkout of the repo `root` belongs to (a worktree resolves to its main checkout)."""
    try:
        common = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        raise CountError(f"cannot find the main checkout of {root}: git rev-parse failed ({e})") from None
    return Path(common).parent


def project_key(checkout: Path) -> str:
    """Claude Code's folder name for a project: the absolute path with every / and . made a -."""
    return str(checkout).replace("/", "-").replace(".", "-")


def repo_project_dirs(projects: Path, key: str) -> list[Path]:
    if not projects.is_dir():
        raise CountError(f"no Claude Code projects folder at {projects}")
    return sorted(d for d in projects.iterdir() if d.is_dir() and key in d.name)


def _local_date(stamp) -> dt.date | None:
    if not isinstance(stamp, str):
        return None
    try:
        return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone().date()
    except (TypeError, ValueError):
        return None


def launches(files, since: dt.date, until: dt.date) -> tuple[dict[str, str], int]:
    """tool call id -> agent type for the launches dated since..until; also how many lines could not be read."""
    if until < since:
        raise CountError(f"--until {until} is before --since {since}")
    found: dict[str, str] = {}
    unreadable = 0
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    unreadable += 1
                    continue
                day = _local_date(rec.get("timestamp"))
                content = (rec.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not (isinstance(part, dict) and part.get("type") == "tool_use"
                            and part.get("name") in LAUNCH_TOOLS):
                        continue
                    if day is None:
                        unreadable += 1
                        continue
                    if since <= day <= until and part.get("id"):
                        found[part["id"]] = (part.get("input") or {}).get("subagent_type") or DEFAULT_TYPE
    return found, unreadable


def every_launch(files, since: dt.date, until: dt.date) -> tuple[list[str], int]:
    """The agentType of every subagent (one *.meta.json each) started since..until; also how many could not be read."""
    if until < since:
        raise CountError(f"--until {until} is before --since {since}")
    types: list[str] = []
    unreadable = 0
    for meta in files:
        try:
            kind = json.loads(meta.read_text(encoding="utf-8")).get("agentType") or DEFAULT_TYPE
        except (OSError, ValueError, AttributeError):
            unreadable += 1
            continue
        day = _first_day(meta.with_name(meta.name[: -len(".meta.json")] + ".jsonl"))
        if day is None:
            unreadable += 1
        elif since <= day <= until:
            types.append(kind)
    return types, unreadable


def _first_day(transcript: Path) -> dt.date | None:
    try:
        with open(transcript, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    day = _local_date(json.loads(line).get("timestamp"))
                except (ValueError, AttributeError):
                    continue
                if day is not None:
                    return day
    except OSError:
        return None
    return None


def summary(found) -> dict:
    by_type = Counter(found.values() if isinstance(found, dict) else found)
    total = sum(by_type.values())
    gp = by_type.get(DEFAULT_TYPE, 0)
    return {"total": total, "general_purpose": gp,
            "general_purpose_pct": round(100 * gp / total, 1) if total else None,
            "by_type": dict(by_type.most_common())}


def _date(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a date (YYYY-MM-DD)") from None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", type=_date, required=True, help="first day counted (YYYY-MM-DD, local)")
    ap.add_argument("--until", type=_date, required=True, help="last day counted (YYYY-MM-DD, local)")
    ap.add_argument("--projects", type=Path, default=Path.home() / ".claude/projects")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        dirs = repo_project_dirs(args.projects, project_key(main_checkout()))
        files = [f for d in dirs for f in sorted(d.rglob("*.jsonl"))]
        metas = [f for d in dirs for f in sorted(d.rglob("*.meta.json")) if f.parent.name == "subagents"]
        found, bad_lines = launches(files, args.since, args.until)
        every, bad_metas = every_launch(metas, args.since, args.until)
    except CountError as e:
        print(f"agent_launch_count: {e}", file=sys.stderr)
        return 2
    out = {"since": str(args.since), "until": str(args.until), "project_dirs": len(dirs), "transcripts": len(files),
           "chosen": summary(found), "every": summary(every),
           "unreadable_lines": bad_lines, "unreadable_subagents": bad_metas,
           "baseline": {"window": "2026-10-31 to 2026-11-21", "general_purpose": 404, "general_purpose_pct": 68}}
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"{out['since']} to {out['until']}, from {len(files)} transcripts in {len(dirs)} project folders")
    for key, label in (("chosen", "launches a session chose (Agent calls; compare with the baseline)"),
                       ("every", "every launch (skill forks and their reviewers included)")):
        s = out[key]
        print(f"\n{label}: {s['total']}")
        if s["total"]:
            print(f"general-purpose: {s['general_purpose']} ({s['general_purpose_pct']}%), target under 50%")
            for name, n in s["by_type"].items():
                print(f"  {n:5d}  {name}")
    print("\nbaseline (2026-10-31 to 2026-11-21): 404 general-purpose, 68%")
    if bad_lines or bad_metas:
        print(f"not counted: {bad_lines} transcript line(s) and {bad_metas} subagent(s) that could not be read or dated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
