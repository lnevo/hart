#!/usr/bin/env python3
"""The archive catalogue: one row per archive item and per logo file (ADR-039, lane L6).

``www/scripts/archive_catalogue.csv`` is the master for what a historical item is and where it came from:
its id, the file, its title and caption, the credit, the source link, how sure the credit is, the rights and
where the copy was found. It is also the one place for logo credits: every file under
``ops/hart-ops/operator_logos/`` and the site's own logos has a row of collection ``logo`` (owner, 2026-11-25). Its columns are described in ``archive_catalogue.columns.csv``. It sits in ``www/scripts/`` because
the build never publishes that folder: its paths name the gitignored ``media/`` mirrors.

Two files copy it, and this check holds them to it:

- ``www/data/archive.json``: each item is a catalogue row of collection ``archive``, under the same id,
  with the same ``src`` (the row's ``path``), ``pdf``, ``title``, ``caption``, ``credit``, ``source_url``,
  ``credit_confidence``, ``rights`` and ``origin``, and each such row is an item. Date, tags, kind, bucket and
  reason are the page's own and stay in archive.json only.
- the lineage charts (``www/data/*-lineage.json``, read by ``www/js/lineage.js``): each card with a logo
  cites a catalogue row of collection ``logo`` in ``logo_id``, and its ``logo`` is that row's ``path``.

``serve_portal.py`` edits through ``sync_item`` and ``drop_item``, so a title, caption or credit fixed on the
local Photos page changes the catalogue too.

    python3 www/scripts/archive_catalogue.py           # check; exit 1 on a difference
    python3 www/scripts/archive_catalogue.py --write   # set each lineage card's logo from its logo_id
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WWW = ROOT / "www"
CATALOGUE = Path(__file__).resolve().parent / "archive_catalogue.csv"
ARCHIVE = WWW / "data" / "archive.json"
LINEAGE_GLOB = "*-lineage.json"

COLUMNS = ("id", "collection", "path", "pdf", "title", "caption", "credit", "source_url", "credit_confidence",
           "rights", "origin", "derived_from")
# catalogue column -> archive.json item key, for the columns archive.json copies
ARCHIVE_FIELDS = {"id": "id", "path": "src", "pdf": "pdf", "title": "title", "caption": "caption", "credit": "credit",
                  "source_url": "source_url", "credit_confidence": "credit_confidence", "rights": "rights",
                  "origin": "origin"}


def read(path: Path = CATALOGUE) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write(rows: list[dict], path: Path = CATALOGUE) -> None:
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        out = csv.DictWriter(fh, COLUMNS, lineterminator="\n")
        out.writeheader()
        out.writerows({c: row.get(c, "") for c in COLUMNS} for row in rows)
    os.replace(tmp, path)


def _text(value) -> str:
    """archive.json leaves some fields out or null; the catalogue holds them as empty cells."""
    return "" if value is None else str(value)


def row_for(item: dict, collection: str = "archive") -> dict:
    """The catalogue row an archive.json item copies."""
    row = {col: _text(item.get(key)) for col, key in ARCHIVE_FIELDS.items()}
    return {**{c: "" for c in COLUMNS}, **row, "collection": collection}


def sync_item(item: dict, path: Path = CATALOGUE) -> None:
    """Write an archive item's catalogue fields into its row, adding the row when it is new."""
    rows = read(path)
    new = row_for(item)
    for row in rows:
        if row["id"] == new["id"]:
            row.update({c: new[c] for c in ARCHIVE_FIELDS})
            break
    else:
        rows.append(new)
    write(rows, path)


def drop_item(item_id: str, path: Path = CATALOGUE) -> None:
    """Remove an archive item's row (it left the archive, as when it moves to the layout photos)."""
    rows = read(path)
    write([r for r in rows if not (r["id"] == item_id and r["collection"] == "archive")], path)


def _cards(node):
    """Every dict under a lineage chart that shows a logo or cites one."""
    if isinstance(node, dict):
        if "logo" in node or "logo_id" in node:
            yield node
        for value in node.values():
            yield from _cards(value)
    elif isinstance(node, list):
        for value in node:
            yield from _cards(value)


def check_archive(rows: list[dict], data: dict) -> list[str]:
    problems = []
    by_id = {r["id"]: r for r in rows if r["collection"] == "archive"}
    seen = set()
    for item in data.get("items", []):
        item_id = item.get("id", "")
        row = by_id.get(item_id)
        if row is None:
            problems.append(f"archive.json item {item_id!r} is not an archive row of the catalogue")
            continue
        seen.add(item_id)
        for col, key in ARCHIVE_FIELDS.items():
            if _text(item.get(key)) != row[col]:
                problems.append(f"archive.json item {item_id!r} {key} is {_text(item.get(key))!r}; "
                                f"the catalogue's {col} is {row[col]!r}")
    for item_id in by_id.keys() - seen:
        problems.append(f"catalogue archive row {item_id!r} is not an item of archive.json")
    return problems


def check_lineage(rows: list[dict], name: str, data: dict) -> list[str]:
    problems = []
    logos = {r["id"]: r for r in rows if r["collection"] == "logo"}
    for card in _cards(data):
        label = card.get("name") or card.get("title") or "?"
        logo_id = card.get("logo_id", "")
        row = logos.get(logo_id)
        if row is None:
            problems.append(f"{name}: card {label!r} logo_id {logo_id!r} is not a logo row of the catalogue")
        elif card.get("logo") != row["path"]:
            problems.append(f"{name}: card {label!r} logo is {card.get('logo')!r}; its catalogue row "
                            f"{logo_id!r} has {row['path']!r} (run with --write)")
    return problems


def check_rows(rows: list[dict]) -> list[str]:
    """What the sidecar cannot say: a logo is a file of the site or the repo, cited from www/."""
    problems = []
    for row in rows:
        if row["collection"] == "logo" and not (WWW / row["path"]).resolve().is_file():
            problems.append(f"catalogue logo row {row['id']!r}: {row['path']} (from www/) is not a file")
    return problems


def lineage_files() -> list[Path]:
    return sorted((WWW / "data").glob(LINEAGE_GLOB))


def check() -> list[str]:
    rows = read()
    problems = check_rows(rows) + check_archive(rows, json.loads(ARCHIVE.read_text(encoding="utf-8")))
    for path in lineage_files():
        problems += check_lineage(rows, path.name, json.loads(path.read_text(encoding="utf-8")))
    return problems


def write_lineage() -> int:
    """Set each lineage card's logo from its logo_id; returns the number of files changed."""
    logos = {r["id"]: r["path"] for r in read() if r["collection"] == "logo"}
    changed = 0
    for path in lineage_files():
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        for card in _cards(data):
            if card.get("logo_id") in logos:
                card["logo"] = logos[card["logo_id"]]
        new = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--write", action="store_true", help="set each lineage card's logo from its logo_id")
    args = parser.parse_args(argv)
    if args.write:
        print(f"archive_catalogue: wrote {write_lineage()} lineage file(s)")
    problems = check()
    for p in problems:
        print(f"archive_catalogue: {p}", file=sys.stderr)
    if problems:
        print(f"archive_catalogue: {len(problems)} difference(s) from {CATALOGUE.relative_to(ROOT)}", file=sys.stderr)
        return 1
    rows = read()
    n = sum(r["collection"] == "archive" for r in rows)
    print(f"archive_catalogue: ok ({n} archive items, {len(rows) - n} logos, {len(lineage_files())} lineage charts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
