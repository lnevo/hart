#!/usr/bin/env python3
"""Insert or remove a JMRI profile Start Up script perform tag.

Preserves the attribute order of the neighbouring PerformScript tag.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def _perform_for(sample: str, script_path: str) -> str:
    if "xmlns=" in sample:
        return (
            '        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" '
            f'enabled="yes" name="{script_path}" type="ScriptFile"/>'
        )
    return (
        f'        <perform name="{script_path}" type="ScriptFile" enabled="yes" '
        'class="jmri.util.startup.configurexml.PerformScriptModelXml"/>'
    )


def _script_basename(path: str) -> str:
    return Path(path).name


def insert_after(profile: Path, script_path: str, after: str) -> str:
    txt = profile.read_text(encoding="utf-8")
    needle = _script_basename(script_path)
    if needle in txt:
        return "already"
    idx = txt.find(after)
    if idx < 0:
        raise SystemExit(f"{profile}: no Start Up entry containing {after!r}")
    end = txt.find("/>", idx)
    if end < 0:
        raise SystemExit(f"{profile}: malformed perform tag at {after!r}")
    end += 2
    sample = txt[txt.rfind("<perform", 0, idx) : end]
    insert = "\n" + _perform_for(sample, script_path)
    profile.write_text(txt[:end] + insert + txt[end:], encoding="utf-8")
    return "inserted"


def remove_script(profile: Path, script_path: str) -> str:
    txt = profile.read_text(encoding="utf-8")
    needle = _script_basename(script_path)
    if needle not in txt:
        return "absent"
    new, n = re.subn(
        rf"\n?[ \t]*<perform\b[^>]*{re.escape(needle)}[^>]*/>",
        "",
        txt,
        count=1,
    )
    if n != 1:
        raise SystemExit(f"{profile}: could not remove {needle}")
    profile.write_text(new, encoding="utf-8")
    return "removed"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("insert", "remove"))
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument("--script", required=True, help="Absolute path stored in the perform name")
    ap.add_argument("--after", help="Existing perform filename to insert after (insert only)")
    args = ap.parse_args()
    if args.action == "insert":
        if not args.after:
            raise SystemExit("insert requires --after")
        print(insert_after(args.profile, args.script, args.after))
    else:
        print(remove_script(args.profile, args.script))


if __name__ == "__main__":
    main()
