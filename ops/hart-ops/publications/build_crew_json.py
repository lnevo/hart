#!/usr/bin/env python3
"""Write www/data/crew.json from the crew master ops/hart-ops/data/crew.json (ADR-039, lane L5).

    python3 ops/hart-ops/publications/build_crew_json.py           write www/data/crew.json
    python3 ops/hart-ops/publications/build_crew_json.py --check   write nothing; exit 1 when it differs from a build

The text is crew_master.build(), the one writer of www/data/crew.json (hartlib.map_revision calls it too, when a
title block change reaches the station maps in make panels): the master less its docx-only fields, the spot sheet's industry names and
anchors from ops/hart-ops/data/industries.csv, and the schematic's revision and date from the title block
(hartlib.map_revision.fields). It first runs crew_schema.problems() and
stops on any. Edit the master, never www/data/crew.json.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "tools/hartlib/src"))
import crew_master  # noqa: E402
from hartlib.map_revision import fields  # noqa: E402

OUT = crew_master.SITE


def build() -> str:
    try:
        return crew_master.build(fields())
    except ValueError as e:
        raise SystemExit(f"build_crew_json: {e}") from None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 when www/data/crew.json is stale")
    args = ap.parse_args(argv)
    text = build()
    rel = OUT.relative_to(crew_master.REPO)
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"build_crew_json: {rel} differs from a build of the crew master; "
                  "run python3 ops/hart-ops/publications/build_crew_json.py")
            return 1
        print(f"build_crew_json: {rel} is current")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"build_crew_json: wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
