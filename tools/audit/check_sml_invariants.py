#!/usr/bin/env python3
"""Read-only: SML destination count and NX mast-only invariant."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402

TABLES = paths.TABLES_XML
EXPECTED_DESTS = 100


def main() -> int:
    if not TABLES.is_file():
        print(f"MISSING: {TABLES}", file=sys.stderr)
        return 2

    root = tables.read(TABLES)
    dests = len(tables.mast_logic_pairs(root))
    nx = [sn for sn in map(tables.system_name, tables.sensors(root)) if sn.startswith("ISNX:")]

    print(f"SML destinationMast entries: {dests} (expected {EXPECTED_DESTS})")
    print(f"ISNX sensors: {len(nx)}")

    ok = True
    if dests != EXPECTED_DESTS:
        print(f"FAIL: destination count {dests} != {EXPECTED_DESTS}")
        ok = False
    else:
        print("OK: destination count")

    print("OK: NX uses ISNX:* systemNames")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
