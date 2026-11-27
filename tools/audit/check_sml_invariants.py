#!/usr/bin/env python3
"""Read-only: SML destination count and NX mast-only invariant."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import parked, paths, tables  # noqa: E402

TABLES = paths.TABLES_XML


def expected_dests(root: ET.Element) -> int:
    """The SML destination count of the generated three-level panel: audit_panel_contracts.expected_sml (one place).
    ValueError when the main panel is not a generated one or the panel counts file cannot be read."""
    import importlib.util
    tables.require_generated_panel(root, paths.rel(TABLES))
    spec = importlib.util.spec_from_file_location("audit_panel_contracts",
                                                  paths.LAYOUT_SCRIPTS / "audit_panel_contracts.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {paths.LAYOUT_SCRIPTS / 'audit_panel_contracts.py'}")
    audit = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("audit_panel_contracts", audit)
    spec.loader.exec_module(audit)
    expected: int = audit.expected_sml(True)
    return expected


def main() -> int:
    if not TABLES.is_file():
        print(f"MISSING: {TABLES}", file=sys.stderr)
        return 2

    root = tables.read(TABLES)
    dests = len(tables.mast_logic_pairs(root))
    try:
        EXPECTED_DESTS = expected_dests(root)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    nx = [sn for sn in map(tables.system_name, tables.sensors(root)) if sn.startswith("ISNX:")]

    print(f"SML destinationMast entries: {dests} (expected {EXPECTED_DESTS})")
    print(f"ISNX sensors: {len(nx)}")

    ok = True
    if dests != EXPECTED_DESTS:
        print(f"FAIL: destination count {dests} != {EXPECTED_DESTS}")
        ok = False
    else:
        print("OK: destination count")

    if "nx" in parked.PARKED:           # Entry/Exit parked (hartlib.parked): its sensors are in the parked file
        if nx:
            print(f"FAIL: Entry/Exit is parked, but tables.xml holds {len(nx)} ISNX sensors")
            ok = False
        else:
            print("OK: Entry/Exit parked, no ISNX sensor in tables.xml")
    else:
        print("OK: NX uses ISNX:* systemNames")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
