#!/usr/bin/env python3
"""Every track, OS block and mast name typed in a hand-kept file must be a current name.

    python3 tools/audit/check_name_copies.py          # the checkout's tracked files
    python3 tools/audit/check_name_copies.py --list   # also print every file that holds a name

A name is current when its row in jmri/layouts/hart/data/public_name_map.csv has
current = proposed (the identity row), or, for a block, when tables.xml holds a block
with that user name (the hidden yard throat blocks such as Track S-R West have only
alias rows in the map; JMRI holds them). A rename adds a row with the old name as
`current` and the new one as `proposed` (ADR-005), so after a rename the old name
is no longer current, and every hand-kept copy of it fails here with its file and line.
A `proposed` name that neither an identity row nor tables.xml holds is not current.

What counts as a name:
  - `Mast <digits><letters>` (Mast 16R, Mast 2035) and `OS Switch <digits><a|b>`:
    any such text that is not current fails, renamed or never existed;
  - `Track ...`: a track name has free words, so only the names the map knows are
    matched, longest first (`Track Scale East` is not `Track Scale`); one that is
    not current fails.

Data files that key on a name (mast_cells.csv, switch_legs.csv, block_lengths.csv ...)
are read: a rename has to change them too. Left out: the name map and tables.xml (the
sources), files a generator writes and a `--check` holds (SKIP_PREFIXES), tests, and the
dated records in ALLOW, each with its reason.
Markdown is prose (the wiki and docs may keep a name; a record is not a copy) and is
not read. The rename checklist is in wiki/pipelines/switch-facts.md.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402

NAME_MAP_REL = "jmri/layouts/hart/data/public_name_map.csv"
TABLES_REL = "jmri/layouts/hart/output/tables.xml"
LAYERS = ("block", "mast")

# Files and folders not read. Each is a source, a file a generator writes under a
# --check in tools/check.sh, or not ours.
SKIP_PREFIXES = (
    "archive/",                                   # retired material
    "reference/", "external/",                    # vendor and submodule source
    NAME_MAP_REL,                                 # the source of the names, old ones included
    TABLES_REL,                                   # JMRI's file; held to the map by the baselines
    "jmri/layouts/hart/data/baselines/",          # capture_public_name_baseline.py --check
    # the generated files of the schematic data; its hand-kept files (staging_le/, the overrides) are read
    "jmri/layouts/hart/data/schematic/staging.signals.json",          # build_signals.py --check
    "jmri/layouts/hart/data/schematic/hands.csv",                     # build_hands.py --check
    "jmri/layouts/hart/data/schematic/device_map_main_upper.csv",     # build_device_map.py --check
    "jmri/layouts/hart/data/schematic/main_upper_masts.csv",          # build_main_upper_masts.py --check
    "jmri/layouts/hart/data/schematic/inputs/",                       # plan graphs read from the AnyRail export
    "www/data/",                                  # build_tables_browser / build_layout_index --check
    "jmri/layouts/hart/scripts/speedmatch/routes.json",  # build_routes.py --check
    "cats/panels/HART_CTC.xml", "cats/panels/HART_ABS.xml",  # test_desks_match_source.py
    "cats/panels/generated/",                     # build_cats_panel.py --check (main and upper names from the device map)
    "tools/audit/check_name_copies.py",           # this file
)
# Tests are not read. A test that asserts the real data fails by itself after a rename;
# the rest hold fixture names (Mast 99X) or old names on purpose, to test the rename
# and alias handling (apply_public_names, rename_extension_tracks).
SKIP_PARTS = ("/tests/",)
TEXT_SUFFIXES = (".py", ".sh", ".js", ".mjs", ".csv", ".json", ".xml", ".html", ".svg", ".txt", ".cmd", ".yml", ".yaml")

# Dated records that keep a name that is no longer current: file -> (names, reason);
# names None allows any. Keep this short: a copy still in use belongs on the data.
ALLOW: dict[str, tuple[frozenset[str] | None, str]] = {
    "jmri/layouts/hart/scripts/speedmatch/rename_extension_tracks.py": (
        frozenset({"Track West Main Ext"}),
        "rewrites logs recorded before the 2026-11-13 rename, so it holds the old names",
    ),
}


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    name: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.name!r} is not a current name"


def load_names(name_map: Path) -> tuple[set[str], set[str]]:
    """(identity-row names, every name the map has ever held) for blocks and masts."""
    current: set[str] = set()
    known: set[str] = set()
    with name_map.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["layer"] not in LAYERS:
                continue
            cur, new = row["current"].strip(), row["proposed"].strip()
            known.update(n for n in (cur, new) if n)
            if cur and cur == new:
                current.add(cur)
    return current, known


def table_blocks(tables_xml: Path) -> set[str]:
    """Block user names in tables.xml (none when the file is absent, as in a test root)."""
    if not tables_xml.is_file():
        return set()
    return {n for n in (tables.user_name(b) for b in tables.blocks(tables.read(tables_xml), full=False)) if n}


# `Signal Mast 1` is a JMRI default user name (AnyRail-era hart.xml), not one of ours.
_SHAPED = re.compile(r"(?<![\w-])(?<!Signal )(?:Mast \d+[A-Z]*|OS Switch \d+[a-z]?)(?![\w-])")
# Track 1, Track 2 ... are old aliases of OS blocks (Track 7 -> OS Switch 7) but also the
# yard and sheet track numbers of old publications and drawings (`Yard Track 1`), so a
# Track name that is only a number is not matched. Track names today are lettered.
_NUMBERED_TRACK = re.compile(r"Track \d+[a-z]?")


def _track_pattern(known: set[str]) -> re.Pattern[str] | None:
    tracks = sorted((n for n in known if n.startswith("Track ") and not _NUMBERED_TRACK.fullmatch(n)),
                    key=len, reverse=True)
    if not tracks:
        return None
    return re.compile(r"(?<![\w-])(?:%s)(?![\w-])" % "|".join(re.escape(t) for t in tracks))


def scan_text(path: str, text: str, current: set[str], track_re: re.Pattern[str] | None) -> list[Hit]:
    hits = []
    for no, line in enumerate(text.splitlines(), 1):
        for m in _SHAPED.finditer(line):
            if m.group(0) not in current:
                hits.append(Hit(path, no, m.group(0)))
        if track_re is not None:
            for m in track_re.finditer(line):
                if m.group(0) not in current:
                    hits.append(Hit(path, no, m.group(0)))
    return hits


def tracked_files(root: Path) -> list[str]:
    """The checkout's tracked files. Needs git: walking the folder would also read untracked
    and gitignored files (media mirrors, local runs), so there is no fallback."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        detail = e.stderr.decode("utf-8", "replace").strip() if isinstance(e, subprocess.CalledProcessError) else e
        raise SystemExit(f"check_name_copies.py needs git to list the tracked files of {root}: {detail}")
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def readable(rel: str) -> bool:
    return (rel.endswith(TEXT_SUFFIXES) and not rel.startswith(SKIP_PREFIXES)
            and not any(part in f"/{rel}" for part in SKIP_PARTS))


def run(root: Path, files: list[str] | None = None, allow=None, name_map: Path | None = None,
        tables_xml: Path | None = None):
    """(stale hits not in ALLOW, name copies per file read, the (file, name) ALLOW pairs used).

    name_map and tables_xml default to the ones under root; a test passes edited copies.
    """
    allow = ALLOW if allow is None else allow
    current, known = load_names(name_map or root / NAME_MAP_REL)
    blocks = table_blocks(tables_xml or root / TABLES_REL)
    current |= blocks
    known |= blocks
    track_re = _track_pattern(known)  # known holds every current name too
    hits: list[Hit] = []
    counts: dict[str, int] = {}
    used: set[tuple[str, str]] = set()
    for rel in files if files is not None else tracked_files(root):
        if not readable(rel):
            continue
        p = root / rel
        if p.is_symlink() or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        n = len(_SHAPED.findall(text)) + (len(track_re.findall(text)) if track_re else 0)
        if n:
            counts[rel] = n
        names, _reason = allow.get(rel, (frozenset(), ""))
        for h in scan_text(rel, text, current, track_re):
            if names is None or h.name in names:
                used.add((rel, h.name))
            else:
                hits.append(h)
    return hits, counts, used


def unused_allow(allow, used: set[tuple[str, str]]) -> list[str]:
    """An ALLOW entry (or one of its names) that no longer matches anything must go."""
    out = []
    for rel, (names, _reason) in allow.items():
        if names is None:
            if not any(r == rel for r, _ in used):
                out.append(f"ALLOW {rel}: no stale name left there; remove the entry")
            continue
        for name in sorted(names - {n for r, n in used if r == rel}):
            out.append(f"ALLOW {rel}: {name!r} is no longer there; remove it")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--root", type=Path, default=paths.REPO_ROOT, help="checkout to read (default: this one)")
    ap.add_argument("--list", action="store_true", help="also print each file holding a name, with its count")
    args = ap.parse_args(argv)
    hits, counts, used = run(args.root)
    if args.list:
        for rel, n in sorted(counts.items()):
            print(f"{n:5d} {rel}")
    for h in hits:
        print(h)
    unused = unused_allow(ALLOW, used)
    for msg in unused:
        print(msg)
    if hits or unused:
        print(f"FAIL: {len(hits)} stale name copies. Change each to the current name, look it up from "
              "the data, or (dated records only) add it to ALLOW with its reason.")
        return 1
    print(f"OK: every track, OS block and mast name in {len(counts)} hand-kept files is current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
