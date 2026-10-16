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


def retarget_to_preference_jython(profile: Path, scripts: list[str]) -> list[str]:
    """Rewrite PerformScript name= to preference:jython/<basename>.

    Leaves ScriptButton / XmlFile / Action tags alone. Idempotent when the
    name is already preference:jython/.
    Also renames known retired basenames (e.g. sync_yard_ladder_buttons →
    sync_layout_button) before retargeting.
    """
    txt = profile.read_text(encoding="utf-8")
    orig = txt
    notes: list[str] = []
    wanted = {_script_basename(s) for s in scripts}

    # Retired → current startup script basenames (must run after package rename).
    renames = {
        "sync_yard_ladder_buttons.py": "sync_layout_button.py",
        "sync_turnout_buttons.py": "sync_layout_button.py",
    }
    for old, new in renames.items():
        if old in txt and new in wanted:
            txt2, n = re.subn(
                rf'(name="[^"]*){re.escape(old)}(")',
                rf"\1{new}\2",
                txt,
            )
            if n:
                notes.append(f"{old} -> {new} ({n} Start Up entr{'y' if n == 1 else 'ies'})")
                txt = txt2

    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        if "PerformScriptModelXml" not in tag:
            return tag
        name_m = re.search(r'\bname="([^"]*)"', tag)
        if name_m is None:
            return tag
        old = name_m.group(1)
        base = _script_basename(old)
        if base not in wanted:
            return tag
        target = f"preference:jython/{base}"
        if old == target:
            return tag
        notes.append(f"{old} -> {target}")
        return tag[: name_m.start()] + f'name="{target}"' + tag[name_m.end() :]

    txt = re.sub(r"<perform\b[^>]*/>", repl, txt)
    if txt != orig:
        profile.write_text(txt, encoding="utf-8")
    return notes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("insert", "remove", "retarget-jython"))
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument(
        "--script",
        action="append",
        default=[],
        help="Script path or basename (repeatable for retarget-jython)",
    )
    ap.add_argument("--after", help="Existing perform filename to insert after (insert only)")
    args = ap.parse_args()
    if not args.script:
        raise SystemExit("--script is required")
    if args.action == "insert":
        if not args.after:
            raise SystemExit("insert requires --after")
        print(insert_after(args.profile, args.script[0], args.after))
    elif args.action == "remove":
        print(remove_script(args.profile, args.script[0]))
    else:
        notes = retarget_to_preference_jython(args.profile, args.script)
        print("\n".join(notes) if notes else "already")


if __name__ == "__main__":
    main()
