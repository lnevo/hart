#!/usr/bin/env python3
"""Dashboard writes for the ArtifactData tool, with every time taken from this Mac's clock.

    dash_rows.py OUT_DIR --wave W [--if-version DOC=N ...] OP ...

OPs, any number, in order:
  row DOC key=value ...        an `update` of data/W/lanes/DOC; needs --if-version DOC=N
  new-row DOC key=value ...    a `set` of data/W/lanes/DOC; needs lane, status, stage, eta and order
  event "TEXT"                 a `set` in data/W/events, id eW-HHMM (then eW-HHMMb, eW-HHMMc, ... in one run)
  samples FILE [--since HH:MM] one `set` per JSON line of FILE in data/W/samples, id sHHMM from the line's `at`;
                               --since keeps only the lines after the last one stamped HH:MM

`updated` (rows) and `at` (events) are stamped HH:MM from the local clock, and a caller-supplied
`updated` or `at` key is refused. A value that parses as JSON (a number, a list such as pr=[1271,1280])
is kept typed; any other value is a string. `status` must be one of STATUSES and `eta` HH:MM.

Each document is written as OUT_DIR/<collection name>/<doc id>.json. stdout is the JSON array for the
ArtifactData `batch` call's `writes`: {op, collection, doc_id, file_path} plus if_version where given.
`--now HH:MM` replaces the clock and is for the tests only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

STATUSES = ("queued", "running", "remote", "review", "ci", "merged", "done", "blocked", "failed")
NEW_ROW_KEYS = ("lane", "status", "stage", "eta", "order")
CLOCK_KEYS = ("updated", "at")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
OP_WORDS = ("row", "new-row", "event", "samples")
WriteOp = Literal["set", "update"]


class DashError(Exception):
    """An op or its values are refused; the message names the doc and the reason."""


@dataclass(frozen=True)
class Write:
    op: WriteOp
    collection: str
    doc_id: str
    data: dict[str, object]
    if_version: int | None = None


def parse_value(text: str) -> object:
    """JSON numbers, lists, objects, true/false/null stay typed; anything else is the string itself."""
    try:
        value = json.loads(text)
    except ValueError:
        return text
    return value if not isinstance(value, str) else text


def parse_fields(doc_id: str, pairs: list[str]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep or not key:
            raise DashError(f"{doc_id}: {pair!r} is not key=value")
        if key in CLOCK_KEYS:
            raise DashError(f"{doc_id}: {key!r} is stamped from the clock; do not pass it")
        fields[key] = parse_value(raw)
    if "status" in fields and fields["status"] not in STATUSES:
        raise DashError(f"{doc_id}: status {fields['status']!r} is not one of {', '.join(STATUSES)}")
    if "eta" in fields and not (isinstance(fields["eta"], str) and HHMM.match(fields["eta"])):
        raise DashError(f"{doc_id}: eta {fields['eta']!r} is not HH:MM")
    return fields


def check_hhmm(text: str, what: str) -> str:
    if not HHMM.match(text):
        raise DashError(f"{what} {text!r} is not HH:MM")
    return text


class Builder:
    """Turns ops into writes for one wave. An event id already made in this run, or already written by an earlier
    run into the same OUT_DIR (`taken`), gets a letter suffix, so an earlier event is never replaced."""

    def __init__(self, wave: str, now: str, versions: dict[str, int],
                 taken: set[tuple[str, str]] | None = None) -> None:
        self.wave = wave
        self.now = now
        self.versions = versions
        self.writes: list[Write] = []
        self._ids: set[tuple[str, str]] = set(taken or ())

    def collection(self, name: str) -> str:
        return f"data/{self.wave}/{name}"

    def _unique(self, collection: str, base: str) -> str:
        doc_id, letter = base, ord("b")
        while (collection, doc_id) in self._ids:
            if letter > ord("z"):
                raise DashError(f"{base}: more than 25 ids made from it in one run")
            doc_id, letter = base + chr(letter), letter + 1
        self._ids.add((collection, doc_id))
        return doc_id

    def row(self, doc_id: str, pairs: list[str]) -> None:
        if doc_id not in self.versions:
            raise DashError(f"{doc_id}: a row update needs --if-version {doc_id}=N from the row's last read")
        fields = parse_fields(doc_id, pairs)
        fields["updated"] = self.now
        self.writes.append(Write("update", self.collection("lanes"), doc_id, fields, self.versions[doc_id]))

    def new_row(self, doc_id: str, pairs: list[str]) -> None:
        fields = parse_fields(doc_id, pairs)
        missing = [key for key in NEW_ROW_KEYS if key not in fields]
        if missing:
            raise DashError(f"{doc_id}: a new row needs {', '.join(missing)}")
        fields["updated"] = self.now
        self.writes.append(Write("set", self.collection("lanes"), doc_id, fields, self.versions.get(doc_id)))

    def event(self, text: str) -> None:
        collection = self.collection("events")
        doc_id = self._unique(collection, f"e{self.wave}-{self.now.replace(':', '')}")
        self.writes.append(Write("set", collection, doc_id, {"at": self.now, "text": text},
                                 self.versions.get(doc_id)))

    def samples(self, path: Path, since: str | None) -> None:
        try:
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except OSError as exc:
            raise DashError(f"samples {path}: cannot read it") from exc
        try:
            records = [json.loads(line) for line in lines]
        except ValueError as exc:
            raise DashError(f"samples {path}: a line is not JSON") from exc
        if since is not None:
            marks = [i for i, rec in enumerate(records) if rec.get("at") == since]
            if not marks:
                raise DashError(f"samples {path}: no line has at {since!r}")
            records = records[marks[-1] + 1:]
        collection = self.collection("samples")
        for rec in records:
            at = rec.get("at")
            if not isinstance(at, str) or not HHMM.match(at):
                raise DashError(f"samples {path}: a line has at {at!r}, not HH:MM")
            doc_id = self._unique(collection, "s" + at.replace(":", ""))
            self.writes.append(Write("set", collection, doc_id, rec, self.versions.get(doc_id)))


def split_ops(tokens: list[str]) -> list[list[str]]:
    """Cut the op tokens at each op word; the first token must be one."""
    ops: list[list[str]] = []
    for token in tokens:
        if token in OP_WORDS:
            ops.append([token])
        elif not ops:
            raise DashError(f"{token!r}: expected one of {', '.join(OP_WORDS)}")
        else:
            ops[-1].append(token)
    if not ops:
        raise DashError("no ops given")
    return ops


def build(builder: Builder, ops: list[list[str]]) -> None:
    for word, *args in ops:
        if word in ("row", "new-row"):
            if not args:
                raise DashError(f"{word}: needs a doc id")
            (builder.row if word == "row" else builder.new_row)(args[0], args[1:])
        elif word == "event":
            if len(args) != 1:
                raise DashError("event: needs one quoted text")
            builder.event(args[0])
        else:
            since = None
            if len(args) == 3 and args[1] == "--since":
                since = check_hhmm(args[2], "--since")
            elif len(args) != 1:
                raise DashError("samples: needs FILE [--since HH:MM]")
            builder.samples(Path(args[0]), since)


def emit(writes: list[Write], out_dir: Path) -> list[dict[str, object]]:
    """Write each document's data to OUT_DIR and return the batch entries."""
    entries: list[dict[str, object]] = []
    for w in writes:
        path = (out_dir / w.collection.rsplit("/", 1)[-1] / f"{w.doc_id}.json").resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(w.data, indent=1) + "\n", encoding="utf-8")
        entry: dict[str, object] = {"op": w.op, "collection": w.collection, "doc_id": w.doc_id,
                                    "file_path": str(path)}
        if w.if_version is not None:
            entry["if_version"] = w.if_version
        entries.append(entry)
    return entries


def written_ids(out_dir: Path, wave: str) -> set[tuple[str, str]]:
    """The (collection, id) of every event document an earlier run wrote into OUT_DIR."""
    folder = out_dir / "events"
    return {(f"data/{wave}/events", p.stem) for p in folder.glob("*.json")} if folder.is_dir() else set()


def parse_versions(items: list[str]) -> dict[str, int]:
    versions: dict[str, int] = {}
    for item in items:
        doc_id, sep, raw = item.partition("=")
        if not sep or not doc_id or not raw.isdigit():
            raise DashError(f"--if-version {item!r} is not DOC=N")
        versions[doc_id] = int(raw)
    return versions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(usage="%(prog)s OUT_DIR --wave W [--if-version DOC=N ...] OP ...",
                                     description=__doc__.split("\n", 1)[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--wave", required=True)
    parser.add_argument("--if-version", action="append", default=[], metavar="DOC=N")
    parser.add_argument("--now", help="test only: use this HH:MM instead of the clock")
    argv = sys.argv[1:] if argv is None else argv
    first_op = next((i for i, token in enumerate(argv) if token in OP_WORDS), len(argv))
    args = parser.parse_args(argv[:first_op])
    try:
        now = check_hhmm(args.now, "--now") if args.now else datetime.now().strftime("%H:%M")
        builder = Builder(args.wave, now, parse_versions(args.if_version), written_ids(args.out_dir, args.wave))
        build(builder, split_ops(argv[first_op:]))
    except DashError as exc:
        print(f"dash_rows: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(emit(builder.writes, args.out_dir), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
