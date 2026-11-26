#!/usr/bin/env python3
"""Every track, OS block and mast name typed in a hand-kept file must be a current name.

    python3 tools/audit/check_name_copies.py          # the checkout's tracked files
    python3 tools/audit/check_name_copies.py --list   # also print every file that holds a name

A name is current when it is the user name of a staging block or mast row of the device master,
or, for a block, when tables.xml holds a block with that user name (a block JMRI holds that the master has no row for
yet; the hidden South Yard throat blocks were such blocks until 2026-11-17). A rename changes the row's user name
(ADR-005), so after a rename the old name is no longer current, and every hand-kept copy of it fails here with its
file and line. The master keeps no alias rows (ADR-029), so a track name that is no longer anything's is not matched
at all: only a Mast, an OS Switch or a name the master or tables.xml still holds is checked. The rename checklist therefore greps for the old name itself.

What counts as a name:
  - `Mast <digits><letters>` (Mast 16R, Mast 2035) and `OS Switch <digits><a|b>`:
    any such text that is not current fails, renamed or never existed;
  - `Track ...`: a track name has free words, so only the names the master knows are
    matched, longest first (`Track Scale East` is not `Track Scale`); one that is
    not current fails.

Data files that key on a name (mast_cells.csv, switches.csv, block_lengths.csv ...)
are read: a rename has to change them too. Left out: the device master and tables.xml (the
sources), files a generator writes and a `--check` holds (SKIP_PREFIXES), tests, and the
dated records in ALLOW, each with its reason (a key ending in "/" covers every file under that folder).
Markdown is prose (the wiki and docs may keep a name; a record is not a copy) and is
not read. The rename checklist is in wiki/pipelines/switch-facts.md.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, files, paths, railroad, tables  # noqa: E402

DEVICES_REL = devices.MASTER.relative_to(paths.REPO_ROOT).as_posix()
FIELD_REL = devices.FIELD.relative_to(paths.REPO_ROOT).as_posix()
TABLES_REL = "jmri/layouts/hart/output/tables.xml"
LAYERS = ("block", "mast")

# Files and folders not read. Each is a source, a file a generator writes under a
# --check in tools/check.sh, or not ours.
SKIP_PREFIXES = (
    "archive/",                                   # retired material
    "reference/", "external/",                    # vendor and submodule source
    DEVICES_REL, FIELD_REL,                       # the source of the names (the master's two files)
    TABLES_REL,                                   # JMRI's file; build_tables.py --check holds it to the master
    # stock discovery's output, written only by run_sml_discover.sh; build_tables.py stops on a mast it names that
    # the tables do not hold (hartlib.tables_build.merge_discovered)
    "jmri/layouts/hart/data/schematic/discovered_sml.xml",
    # the generated files of the schematic data; its hand-kept files (the overrides) are read
    "jmri/layouts/hart/data/schematic/signals.json",                  # both sections generated from masts.csv:
                                                                      # build_signals.py --check
    "jmri/layouts/hart/data/schematic/masts.csv",                     # build_masts.py --check (every level)
    "jmri/layouts/hart/data/schematic/inputs/",                       # plan graphs read from the AnyRail export
    "www/data/",                                  # build_tables_browser / build_layout_index --check
    "jmri/layouts/hart/scripts/speedmatch/routes.json",  # build_routes.py --check
    "cats/panels/HART_CTC.xml", "cats/panels/HART_ABS.xml",  # build_cats_panel.py --check (the CATS cut-over)
    "cats/panels/HART_CTC.bindings.json",         # build_cats_panel.py --check
    "tools/audit/check_name_copies.py",           # this file
)
# Tests are not read. A test that asserts the real data fails by itself after a rename;
# the rest hold fixture names (Mast 99X) or old names on purpose, to test the rename
# and old-name handling (rename_extension_tracks).
SKIP_PARTS = ("/tests/",)
TEXT_SUFFIXES = (".py", ".sh", ".js", ".mjs", ".csv", ".json", ".xml", ".html", ".svg", ".txt", ".cmd", ".yml", ".yaml")
# The tracked files it lists, as git globs: one per suffix (readable() then leaves out SKIP_PREFIXES and tests). The
# step's quiet_inputs in tools/pipeline/checks.toml are these (tools/audit/tests/test_manifest_scans.py).
SCAN_GLOBS = tuple(f"**/*{s}" for s in TEXT_SUFFIXES)

# Dated records that keep a name that is no longer current: file -> (names, reason);
# names None allows any. Keep this short: a copy still in use belongs on the data.
ALLOW: dict[str, tuple[frozenset[str] | None, str]] = {
    "jmri/layouts/hart/parked/tables_parked.xml": (
        None,
        "frozen snapshot of the live tables at 3bd3ac64 (NX, Dispatcher, USS CTC parked 2026-11-17); it keeps the names "
        "of that day until it is unparked and refreshed",
    ),
    "jmri/layouts/hart/dispatcher/traininfo/": (
        None,
        "the Dispatcher System's train files, parked with it (2026-11-17); their mast names are refreshed when it is "
        "unparked and Stage 1 runs on the rule-built masts (ADR-024)",
    ),
    "jmri/layouts/hart/ctc/GUIObjects.xml": (
        None,
        "the USS CTC machine, parked (2026-11-17); its signal levers name the masts of that day until it is unparked",
    ),
    "jmri/layouts/hart/data/mast_cells.csv": (
        None,
        "the USS board's mast cells, parked with the machine (owner, 2026-11-19); updated on unpark",
    ),
    "jmri/layouts/hart/scripts/discover_nx.py": (None, "Entry/Exit, parked (2026-11-17); updated on unpark"),
    "jmri/layouts/hart/scripts/nx_contract.py": (None, "Entry/Exit, parked (2026-11-17); updated on unpark"),
    "jmri/layouts/hart/parked/apply_nx_layer.py": (None, "Entry/Exit, parked (2026-11-17); updated on unpark"),
    "jmri/layouts/hart/data/schematic/block_numbering.csv": (
        frozenset({"OS Switch 225"}),
        "numbered_as gives corner block OS Switch 225a the system number of the block it replaced, so it keeps that "
        "block's old name (the helix-join release, 2026-11-17). The same text is also the CATS desk's name for the "
        "middle of 225's X, a desk-only block with no Layout Editor block; it is not corner a",
    ),
    "jmri/layouts/hart/data/schematic/retired_virtual_masts.csv": (
        None,
        "the hidden staging masts dropped on 2026-11-20 with the system names they held, so no new mast reuses one "
        "and a Dispatcher unpark can restore them; a dated record of names that are gone",
    ),
    "jmri/layouts/hart/scripts/ctc_logic_smoke.py": (None, "the USS CTC machine, parked (2026-11-17); updated on unpark"),
    "jmri/layouts/hart/scripts/build_ctc_full_15col.py": (
        None, "the USS CTC machine, parked (2026-11-17); updated on unpark"),
}


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    name: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.name!r} is not a current name"


def load_names(devices_csv: Path) -> tuple[set[str], set[str]]:
    """(current names, every name the master holds: the same set, as it keeps no alias rows) of staging's blocks and
    masts, the user names of their rows in the device master. DevicesError when it cannot be read."""
    names = {row["user_name"].strip() for row in devices.load(devices_csv)
             if row["level"] == railroad.STAGING_LEVEL and row["layer"] in LAYERS}
    return names, set(names)


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


class NameCopiesError(Exception):
    """The check cannot read what it checks (the checkout's file list)."""


def tracked_files(root: Path) -> list[str]:
    """The checkout's tracked files. Needs git: walking the folder would also read untracked
    and gitignored files (media mirrors, local runs), so there is no fallback. NameCopiesError when git cannot."""
    try:
        return files.tracked_files(root, *(f":(glob){g}" for g in SCAN_GLOBS))
    except files.GitError as e:
        raise NameCopiesError(f"needs git to list the tracked files of {root}: {e}") from e


def readable(rel: str) -> bool:
    return (rel.endswith(TEXT_SUFFIXES) and not rel.startswith(SKIP_PREFIXES)
            and not any(part in f"/{rel}" for part in SKIP_PARTS))


def run(root: Path, files: list[str] | None = None, allow=None, devices_csv: Path | None = None,
        tables_xml: Path | None = None):
    """(stale hits not in ALLOW, name copies per file read, the (file, name) ALLOW pairs used).

    devices_csv and tables_xml default to the ones under root; a test passes edited copies.
    """
    allow = ALLOW if allow is None else allow
    current, known = load_names(devices_csv or root / DEVICES_REL)
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
        key = rel if rel in allow else next((k for k in allow if k.endswith("/") and rel.startswith(k)), rel)
        names, _reason = allow.get(key, (frozenset(), ""))
        for h in scan_text(rel, text, current, track_re):
            if names is None or h.name in names:
                used.add((key, h.name))
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
    try:
        hits, counts, used = run(args.root)
    except (devices.DevicesError, NameCopiesError) as exc:
        print(f"check_name_copies.py: {exc}", file=sys.stderr)
        return 2
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
