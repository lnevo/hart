#!/usr/bin/env python3
"""Build the report-cards history page from the scores master and copies of the dashboard stores.

    report_cards_page.py check
    report_cards_page.py build --dumps DIR --merged FILE --out DIR
    report_cards_page.py slippage

`check` validates docs/report-cards/scores.json. `slippage` prints each category's latest score
against the one before it and exits 1 when any category went down.

`build` writes OUT/index.html (the report-cards skill's template), OUT/cards.json (the scores master)
and OUT/dash.json (one record per dashboard in the master). DIR holds the ArtifactData `out_dir`
copies of each dashboard's store, DIR/<store>/{lanes,events,samples}/<doc>.json, where <store> is the
dashboard's `store` value (data/ax, ...). FILE is `gh pr list --state merged --json number,mergedAt`.

Dashboard times are HH:MM on this Mac's clock with no date. A time earlier than the dashboard's
`start` time falls on the next day; a dashboard runs for under 24 hours.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SCORES = REPO / "docs/report-cards/scores.json"
TEMPLATE = REPO / ".claude/skills/report-cards/index.html"
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT([01]\d|2[0-3]):[0-5]\d$")
WAVE_ID = re.compile(r"^e?(\d)-")
CATEGORY_KEYS = {"id", "title", "scale", "what", "wiki", "scores"}
DASHBOARD_KEYS = {"id", "title", "start", "store", "link", "wiki", "summary"}


class CardsError(Exception):
    """The scores master or a store copy is refused; the message names the record and the reason."""


@dataclass(frozen=True)
class Sample:
    t: str
    mac: float | None
    cpus: int | None
    sessions: int | None
    subagents: int | None
    total: int | None


@dataclass
class Dashboard:
    id: str
    title: str
    start: str
    end: str
    link: str
    wiki: str
    summary: str
    lanes: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    samples: list[Sample] = field(default_factory=list)
    prs: list[int] = field(default_factory=list)


def load_scores(path: Path = SCORES) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise CardsError(f"{path}: {exc}") from exc
    validate(data)
    return data


def validate(data: dict[str, Any]) -> None:
    """Refuse a master the page cannot draw: missing keys, bad dates, duplicate ids, scores off scale."""
    seen: set[str] = set()
    for cat in data.get("categories", []):
        missing = CATEGORY_KEYS - cat.keys()
        if missing:
            raise CardsError(f"category {cat.get('id', '?')}: missing {sorted(missing)}")
        if cat["id"] in seen:
            raise CardsError(f"category {cat['id']}: id used twice")
        seen.add(cat["id"])
        if not cat["scores"]:
            raise CardsError(f"category {cat['id']}: no scores")
        last = ""
        for s in cat["scores"]:
            day = s.get("date", "")
            try:
                date.fromisoformat(day)
            except ValueError as exc:
                raise CardsError(f"category {cat['id']}: bad date {day!r}") from exc
            if day < last:
                raise CardsError(f"category {cat['id']}: scores out of date order at {day}")
            last = day
            value = s.get("value")
            if not isinstance(value, (int, float)) or not 0 <= value <= cat["scale"]:
                raise CardsError(f"category {cat['id']} {day}: value {value!r} not on 0..{cat['scale']}")
        table = cat.get("table")
        if table and any(len(row) != len(table["columns"]) for row in table["rows"]):
            raise CardsError(f"category {cat['id']}: a table row does not match its columns")
    for item in data.get("unscored", []):
        try:
            date.fromisoformat(item.get("date", ""))
        except ValueError as exc:
            raise CardsError(f"unscored {item.get('title', '?')}: bad date {item.get('date')!r}") from exc
    ids: set[str] = set()
    for dash in data.get("dashboards", []):
        missing = DASHBOARD_KEYS - dash.keys()
        if missing:
            raise CardsError(f"dashboard {dash.get('id', '?')}: missing {sorted(missing)}")
        if dash["id"] in ids:
            raise CardsError(f"dashboard {dash['id']}: id used twice")
        ids.add(dash["id"])
        if not STAMP.match(dash["start"]):
            raise CardsError(f"dashboard {dash['id']}: start {dash['start']!r} is not YYYY-MM-DDTHH:MM")


def stamp(start: str, hhmm: str | None) -> str | None:
    """The full local time of an HH:MM seen after `start`: same day, or the next when it is earlier."""
    if not hhmm or not HHMM.match(hhmm):
        return None
    day = date.fromisoformat(start[:10])
    if hhmm < start[11:16]:
        day += timedelta(days=1)
    return f"{day.isoformat()}T{hhmm}"


def read_docs(folder: Path) -> list[tuple[str, dict[str, Any]]]:
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.glob("*.json")):
        try:
            out.append((path.stem, json.loads(path.read_text())))
        except ValueError as exc:
            raise CardsError(f"{path}: {exc}") from exc
    return out


def wave_of(doc_id: str, waves: bool) -> int | None:
    """Wave number from a code-quality doc id (3-L1, e4-0015); ids without one are wave 2."""
    if not waves:
        return None
    m = WAVE_ID.match(doc_id)
    return int(m.group(1)) if m else 2


def num(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def count(value: object) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def build_dashboard(entry: dict[str, Any], dumps: Path, merged: list[dict[str, Any]], tz: tzinfo) -> Dashboard:
    base = dumps / entry["store"]
    start, waves = entry["start"], bool(entry.get("waves"))
    if not base.is_dir():
        raise CardsError(f"dashboard {entry['id']}: no store copy at {base}")
    dash = Dashboard(id=entry["id"], title=entry["title"], start=start, end=start, link=entry["link"],
                     wiki=entry["wiki"], summary=entry["summary"])
    for doc_id, doc in read_docs(base / "lanes"):
        row = {k: doc.get(k) for k in ("lane", "scope", "status", "stage", "pr", "order")}
        dash.lanes.append(row | {"id": doc_id, "wave": wave_of(doc_id, waves)})
    dash.lanes.sort(key=lambda r: (r["wave"] or 0, r["order"] if isinstance(r["order"], (int, float)) else 999, r["id"]))
    for doc_id, doc in read_docs(base / "events"):
        dash.events.append({"t": stamp(start, doc.get("at")), "text": str(doc.get("text", "")),
                            "wave": wave_of(doc_id, waves)})
    dash.events.sort(key=lambda e: e["t"] or "")
    for _, doc in read_docs(base / "samples"):
        t = stamp(start, doc.get("at"))
        if t:
            dash.samples.append(Sample(t=t, mac=num(doc.get("mac_load1")), cpus=count(doc.get("mac_cpus")),
                                       sessions=count(doc.get("sessions")), subagents=count(doc.get("subagents")),
                                       total=count(doc.get("claude_total"))))
    dash.samples.sort(key=lambda s: s.t)
    times = [e["t"] for e in dash.events if e["t"]] + [s.t for s in dash.samples]
    dash.end = max(times, default=start)
    lo = datetime.fromisoformat(start).replace(tzinfo=tz)
    hi = datetime.fromisoformat(dash.end).replace(tzinfo=tz) + timedelta(minutes=1)
    for pr in merged:
        at = datetime.fromisoformat(str(pr["mergedAt"]).replace("Z", "+00:00"))
        if lo <= at < hi:
            dash.prs.append(int(pr["number"]))
    dash.prs.sort()
    return dash


def slippage(data: dict[str, Any]) -> list[str]:
    """One line per category: latest score, the one before and the change; a drop starts with SLIP."""
    lines = []
    for cat in data["categories"]:
        scores = cat["scores"]
        now = scores[-1]
        if len(scores) == 1:
            lines.append(f"{cat['title']}: {now['value']} on {now['date']} (first score)")
            continue
        before = scores[-2]
        delta = round(now["value"] - before["value"], 3)
        mark = "SLIP " if delta < 0 else ""
        lines.append(f"{mark}{cat['title']}: {now['value']} on {now['date']}, "
                     f"{before['value']} on {before['date']} ({delta:+g})")
    return lines


def build(dumps: Path, merged_file: Path, out: Path, scores: Path = SCORES, template: Path = TEMPLATE,
          tz: tzinfo | None = None) -> list[Dashboard]:
    data = load_scores(scores)
    try:
        merged = json.loads(merged_file.read_text())
    except (OSError, ValueError) as exc:
        raise CardsError(f"{merged_file}: {exc}") from exc
    zone = tz or datetime.now(timezone.utc).astimezone().tzinfo or timezone.utc
    dashes = [build_dashboard(entry, dumps, merged, zone) for entry in data.get("dashboards", [])]
    dashes.sort(key=lambda d: d.start)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, out / "index.html")
    (out / "cards.json").write_text(json.dumps(data, separators=(",", ":")))
    (out / "dash.json").write_text(json.dumps([asdict(d) for d in dashes], separators=(",", ":")))
    return dashes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("slippage")
    b = sub.add_parser("build")
    b.add_argument("--dumps", type=Path, required=True)
    b.add_argument("--merged", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "check":
            data = load_scores()
            print(f"scores.json: {len(data['categories'])} categories, {len(data.get('dashboards', []))} dashboards")
            return 0
        if args.cmd == "slippage":
            lines = slippage(load_scores())
            print("\n".join(lines))
            return 1 if any(line.startswith("SLIP") for line in lines) else 0
        for d in build(args.dumps, args.merged, args.out):
            print(f"{d.id}: {d.start} to {d.end}, {len(d.lanes)} rows, {len(d.events)} events, "
                  f"{len(d.samples)} samples, {len(d.prs)} PRs merged")
        print(f"wrote {args.out}/index.html, cards.json, dash.json")
        return 0
    except CardsError as exc:
        print(f"report_cards_page: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
