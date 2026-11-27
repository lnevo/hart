#!/usr/bin/env python3
"""Insert or remove a JMRI profile Start Up script perform tag (hartlib.jmri_profile does the edit).

Preserves the attribute order of the neighbouring PerformScript tag. The deploy ships this script with the part of
hartlib it needs (tools/hosts/deploy/stage.sh); the host apply scripts and ship_mac.sh run it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib.jmri_profile import (  # noqa: E402
    StartupPatchError,
    insert_after,
    load_tables_from,
    remove_script,
    retarget_to_preference_jython,
)

__all__ = ["StartupPatchError", "insert_after", "load_tables_from", "remove_script", "retarget_to_preference_jython"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("insert", "remove", "retarget-jython", "load-tables"))
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument(
        "--script",
        action="append",
        default=[],
        help="Script path or basename (repeatable for retarget-jython)",
    )
    ap.add_argument("--after", help="Existing perform filename to insert after (insert only)")
    ap.add_argument("--tables", help="Tables path for load-tables")
    args = ap.parse_args()
    if args.action == "load-tables" and not args.tables:
        sys.exit("load-tables requires --tables")
    if args.action != "load-tables" and not args.script:
        sys.exit("--script is required")
    if args.action == "insert" and not args.after:
        sys.exit("insert requires --after")
    try:
        if args.action == "load-tables":
            print(load_tables_from(args.profile, args.tables))
        elif args.action == "insert":
            print(insert_after(args.profile, args.script[0], args.after))
        elif args.action == "remove":
            print(remove_script(args.profile, args.script[0]))
        else:
            notes = retarget_to_preference_jython(args.profile, args.script)
            print("\n".join(notes) if notes else "already")
    except StartupPatchError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
