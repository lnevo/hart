#!/usr/bin/env python3
"""Guard: the discovered Signal Mast Logic (data/schematic/discovered_sml.xml) was discovered from the tables the
sources give now.

run_sml_discover.sh discovers on the discovery base (build_tables.py --discovery-base: every generated bean, no Signal
Mast Logic) and writes discovered_sml.stamp beside the result: the digest of that base (build_tables.discovery_digest:
the base without what discovery cannot see, such as comments, sensor user names and panel labels). This builds the
base in memory (build_tables.py --base-hash does the same) and compares. A mismatch means a mast, turnout, block or
track changed since the last discovery, so the file may name a pair that is gone or miss one that is new.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_layout_le as ble  # noqa: E402
import build_tables as bt  # noqa: E402
import publish_draft as pd  # noqa: E402
from hartlib import paths  # noqa: E402
from hartlib import tables_sml as sml  # noqa: E402

STAMP = sml.DISCOVERED.with_suffix(".stamp")
STALE = ("SML discovery is stale: make panels on the Mac discovers itself; elsewhere run "
         "jmri/layouts/hart/scripts/run_sml_discover.sh on the Mac (PanelPro), then make panels")
# The exit code for stale, apart from 1 (an uncaught exception) and 2 (a build error): make panels on the Mac discovers
# only on this one (build_panels.sh, discover_sml).
EXIT_STALE = 4


def verdict(stamp: Path, current: str) -> str | None:
    """None when `stamp` holds `current`; else the message that says what to run."""
    if not stamp.is_file():
        return f"{STALE} ({paths.rel(stamp)} is missing)"
    if stamp.read_text(encoding="utf-8").strip() != current:
        return STALE
    return None


def base_digest() -> str:
    with pd.cache_on():
        data, _counts = bt.generate(with_logic=False)
    return bt.discovery_digest(data)


def main() -> int:
    try:
        ble.plugin()
    except ble.BuildError as exc:
        if os.environ.get("SCHEMATIC_REQUIRED") != "1":
            print(f"SKIPPED sml-current: {exc}")
            return 0
        print(f"check_sml_current.py: the schematic-maps plugin: {exc}", file=sys.stderr)
        return bt.EXIT_NO_PLUGIN
    try:
        current = base_digest()
    except (sml.TablesBuildError, ble.BuildError) as exc:
        print(f"check_sml_current.py: {exc}", file=sys.stderr)
        return 2
    message = verdict(STAMP, current)
    if message:
        print(message, file=sys.stderr)
        return EXIT_STALE
    print(f"ok: {paths.rel(STAMP)} matches the discovery base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
