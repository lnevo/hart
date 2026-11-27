#!/usr/bin/env python3
"""Check the DecoderPro roster master and its link to the loco master (ADR-039 amendment 2026-11-26, lane N8).

``jmri/layouts/hart/roster/`` holds the DecoderPro roster as the hosts keep it under ``JMRI_UserFiles``: the index
``roster.xml`` and one entry file per loco in ``roster/``, named by the index's ``fileName``. The deploy installs it
on every host and ``make roster-pull`` brings a Pi session back. ``ops/hart-ops/data/locos.csv`` is the loco master;
its ``dcc_address`` and ``long_address`` columns, for a loco the roster has, are the roster's, written by this
script (``--write``) and never typed by hand. A loco not yet in the roster (an intake loco that ``bin/cars locos
publish`` will send to DecoderPro) keeps the address typed for it.

The check fails, naming the file and the loco, when:

- the index or an entry file does not parse, or an index ``<locomotive>`` lacks ``id``, ``fileName`` or
  ``dccAddress``, or its ``dccAddress`` is not a whole number;
- two index entries share an ``id`` or a ``fileName``;
- an entry file the index names is missing, or names another ``id`` or ``dccAddress`` than its index entry, or its
  ``<dcclocoaddress>`` names another number;
- the folder holds a file the index does not name (a JMRI ``.bak`` or an old entry file: the master holds no
  backups);
- a roster ``id`` is not a ``locos.csv`` ``roster_id`` (both are "road name, space, road number": ``BO 2235``);
- a ``locos.csv`` row the roster has gives another ``dcc_address`` or ``long_address`` than the roster.

    python3 tools/ops/check_roster.py            check, write nothing
    python3 tools/ops/check_roster.py --write    fill locos.csv's two address columns from the roster, then check
"""
from __future__ import annotations

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal, NamedTuple

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

ROOT = paths.REPO_ROOT
sys.path.insert(0, str(ROOT / "ops/hart-ops/card_pipeline"))
import locos  # noqa: E402  (write_table: the one writer of locos.csv)

ROSTER = ROOT / "jmri/layouts/hart/roster"
MASTER = ROOT / "ops/hart-ops/data/locos.csv"


class RosterError(Exception):
    """The roster master cannot be read: the message names the file and what is wrong."""


class Entry(NamedTuple):
    roster_id: str
    file_name: str
    dcc_address: str
    long_address: Literal["yes", "no"]   # from the entry file's <dcclocoaddress longaddress>


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def parse(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except FileNotFoundError:
        raise RosterError(f"{rel(path)}: missing") from None
    except (ET.ParseError, OSError) as exc:
        raise RosterError(f"{rel(path)}: does not parse ({exc})") from exc


def read_roster(folder: Path = ROSTER) -> tuple[list[Entry], list[str]]:
    """The roster's entries and every problem found in the folder itself (not against locos.csv)."""
    index = folder / "roster.xml"
    root = parse(index)
    problems: list[str] = []
    entries: list[Entry] = []
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    named_files: set[str] = set()
    for loco in root.iter("locomotive"):
        rid, fname, addr = (loco.get(k, "").strip() for k in ("id", "fileName", "dccAddress"))
        if fname:
            named_files.add(fname)   # named, even when the entry fails a check below: the file is not a stray
        if not rid or not fname:
            problems.append(f"{rel(index)}: a <locomotive> without id or fileName ({rid or fname or 'neither'})")
            continue
        if not addr:
            problems.append(f"{rel(index)}: {rid}: no dccAddress")
            continue
        if not addr.isdigit():
            problems.append(f"{rel(index)}: {rid}: dccAddress {addr!r} is not a whole number")
            continue
        if rid in seen_ids:
            problems.append(f"{rel(index)}: {rid}: the id is given twice")
        if fname in seen_files:
            problems.append(f"{rel(index)}: {rid}: fileName {fname} is given twice")
        seen_ids.add(rid)
        seen_files.add(fname)
        if "/" in fname or fname.startswith(".") or not fname.endswith(".xml"):
            problems.append(f"{rel(index)}: {rid}: fileName {fname!r} is not a plain roster/*.xml name")
            continue
        entry_path = folder / "roster" / fname
        try:
            eroot = parse(entry_path)
        except RosterError as exc:
            problems.append(f"{exc} (named by {rid} in roster.xml)")
            continue
        eloco = eroot.find("locomotive")
        if eloco is None:
            problems.append(f"{rel(entry_path)}: no <locomotive>")
            continue
        if eloco.get("id") != rid:
            problems.append(f"{rel(entry_path)}: id {eloco.get('id')!r}, but roster.xml names it for {rid}")
        if eloco.get("dccAddress") != addr:
            problems.append(f"{rel(entry_path)}: dccAddress {eloco.get('dccAddress')!r}, roster.xml {addr!r} ({rid})")
        dcc = eloco.find("locoaddress/dcclocoaddress")
        long_address = None if dcc is None else dcc.get("longaddress")
        if dcc is None or dcc.get("number") != addr or long_address not in ("yes", "no"):
            got = "none" if dcc is None else f"number {dcc.get('number')!r}, longaddress {dcc.get('longaddress')!r}"
            problems.append(f"{rel(entry_path)}: <dcclocoaddress> {got}, want number {addr!r} and longaddress yes or no")
            continue
        entries.append(Entry(rid, fname, addr, "yes" if long_address == "yes" else "no"))
    named = {"roster.xml"} | {f"roster/{f}" for f in named_files}
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        if path.relative_to(folder).as_posix() not in named:
            problems.append(f"{rel(path)}: not named by roster.xml (the master holds no JMRI backups or old entry "
                            "files; make roster-pull copies only what roster.xml names)")
    if not entries and not problems:
        problems.append(f"{rel(index)}: no <locomotive> entries")
    return entries, problems


def read_master(path: Path = MASTER) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        header = list(reader.fieldnames or [])
    for col in ("roster_id", "dcc_address", "long_address"):
        if col not in header:
            raise RosterError(f"{rel(path)}: no {col} column")
    return header, rows


def link_problems(entries: list[Entry], rows: list[dict]) -> list[str]:
    """Each roster id must be a locos.csv roster_id, and that row's two address columns the roster's."""
    by_id = {r["roster_id"]: r for r in rows}
    found = []
    for e in entries:
        row = by_id.get(e.roster_id)
        if row is None:
            found.append(f"{rel(ROSTER / 'roster.xml')}: {e.roster_id}: no locos.csv row has this roster_id "
                         "(add the loco to the master: bin/cars locos add)")
            continue
        if row["dcc_address"] != e.dcc_address:
            found.append(f"{rel(MASTER)}: {e.roster_id}: dcc_address {row['dcc_address']!r}, the roster's is "
                         f"{e.dcc_address!r} (python3 tools/ops/check_roster.py --write)")
        if row["long_address"] != e.long_address:
            found.append(f"{rel(MASTER)}: {e.roster_id}: long_address {row['long_address']!r}, the roster's is "
                         f"{e.long_address!r} (python3 tools/ops/check_roster.py --write)")
    return found


def fill(entries: list[Entry], rows: list[dict]) -> int:
    """Set the two address columns of each locos.csv row the roster has; the number of rows changed."""
    by_id = {e.roster_id: e for e in entries}
    changed = 0
    for row in rows:
        e = by_id.get(row["roster_id"])
        if e is None:
            continue
        if (row["dcc_address"], row["long_address"]) != (e.dcc_address, e.long_address):
            row["dcc_address"], row["long_address"] = e.dcc_address, e.long_address
            changed += 1
    return changed


def run(write: bool, roster: Path = ROSTER, master: Path = MASTER) -> int:
    try:
        entries, problems = read_roster(roster)
        header, rows = read_master(master)
    except (RosterError, OSError) as exc:
        print(f"FAIL     check_roster: {exc}")
        return 1
    if write:
        if problems:
            print("check_roster --write: the roster has problems, so locos.csv was not written:")
        else:
            changed = fill(entries, rows)
            if changed:
                locos.write_table(master, header, rows)
                _, rows = read_master(master)   # the file as written, so the check below reads what is on disk
            print(f"check_roster --write: {changed} locos.csv row(s) took the roster's address")
    problems += link_problems(entries, rows)
    for p in problems:
        print(f"FAIL     {p}")
    print(f"check_roster: {len(entries)} roster locos; {len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="fill locos.csv's dcc_address and long_address from the roster")
    args = ap.parse_args(argv)
    return run(args.write)


if __name__ == "__main__":
    sys.exit(main())
