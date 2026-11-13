#!/usr/bin/env python3
"""Rewrite the old extension-track names in speed-match logs and data to the new ones.

On 2026-11-13 "East Main Ext" and "West Main Ext" became "East Ext" and "West Ext".
Logs and data recorded before that (steprun, pass and stoptest logs, block_events.csv,
block_summary.csv and the like) still carry the old names, in every form:
"BS East Main Ext", "Track West Main Ext", "BS_East_Main_Ext" (inside BLOCK and MEASURE
lines), "East Main Ext" alone. Each keeps its case style and separator.

    rename_extension_tracks.py FILE...           # dry run: counts per file, changes nothing
    rename_extension_tracks.py --apply FILE...   # rewrite the files in place

Only the exact names change; a file with none is left untouched. Run it on a log only
when no job is writing to it.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# "Main" is dropped and the rest is kept as written, so every case style survives
# (west_main_ext -> west_ext, EAST MAIN EXT -> EAST EXT). The legacy composite names
# "Plane East East Main Ext" and "West Yard West East Main Ext" are a different thing
# and stay as they are: a name preceded by East or West is not touched.
OLD = re.compile(r"(?<![A-Za-z])(?<!East[ _-])(?<!West[ _-])(East|West)([ _-])Main\2(Ext)(?![A-Za-z])",
                 re.IGNORECASE)


def rename(text: str) -> tuple[str, int]:
    """(text with the new names, how many names changed)."""
    return OLD.subn(lambda m: m.group(1) + m.group(2) + m.group(3), text)


def convert_file(path: Path, apply: bool = False) -> int:
    """Number of names in the file; rewrites it only when apply is true and there are any."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return 0
    new, n = rename(text)
    if n and apply:
        path.write_bytes(new.encode("utf-8"))
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--apply", action="store_true", help="rewrite the files (default: dry run)")
    a = ap.parse_args(argv)
    total = 0
    for p in a.files:
        if not p.is_file():
            print("skip (not a file): %s" % p, file=sys.stderr)
            continue
        n = convert_file(p, a.apply)
        total += n
        print("%s %s: %d name(s)" % ("changed" if a.apply and n else "would change" if n else "no change", p, n))
    if not a.apply and total:
        print("dry run: pass --apply to rewrite")
    return 0


if __name__ == "__main__":
    sys.exit(main())
