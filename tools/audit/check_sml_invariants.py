#!/usr/bin/env python3
"""Read-only: the SML destination count of tables.xml, and no ISNX sensor in it while Entry/Exit (NX) is parked."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


class SmlInvariantsError(Exception):
    """The check cannot run: no tools/hartlib/src above this script."""


_HARTLIB = next((p / "tools/hartlib/src" for p in Path(__file__).resolve().parents
                 if (p / "tools/hartlib/src").is_dir()), None)
if _HARTLIB is None:
    if __name__ == "__main__":
        print(f"FAIL: no tools/hartlib/src above {__file__}", file=sys.stderr)
        raise SystemExit(2)
    raise SmlInvariantsError(f"no tools/hartlib/src above {__file__}")
sys.path.insert(0, str(_HARTLIB))
from hartlib import parked, paths, tables  # noqa: E402

TABLES = paths.TABLES_XML


def expected_dests(root: ET.Element, tables_xml: Path = TABLES) -> int:
    """The SML destination count of the generated three-level panel: audit_panel_contracts.expected_sml (one place).
    ValueError when the main panel is not a generated one or the panel counts are wrong, OSError when that file
    cannot be read."""
    import importlib.util
    tables.require_generated_panel(root, paths.rel(tables_xml))
    spec = importlib.util.spec_from_file_location("audit_panel_contracts",
                                                  paths.LAYOUT_SCRIPTS / "audit_panel_contracts.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {paths.LAYOUT_SCRIPTS / 'audit_panel_contracts.py'}")
    audit = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("audit_panel_contracts", audit)
    spec.loader.exec_module(audit)
    expected: int = audit.expected_sml(True)
    return expected


def run(tables_xml: Path) -> int:
    """Check `tables_xml`: 0 when every invariant holds, 1 when one fails, 2 when the file or the panel counts cannot
    be read (a one-line message on stderr)."""
    if not tables_xml.is_file():
        print(f"MISSING: {tables_xml}", file=sys.stderr)
        return 2
    try:
        root = tables.read(tables_xml)
    except (OSError, ET.ParseError, ValueError) as exc:
        print(f"FAIL: cannot read {paths.rel(tables_xml)}: {exc}", file=sys.stderr)
        return 2
    try:
        dests = len(tables.mast_logic_pairs(root))
        expected = expected_dests(root, tables_xml)
        nx = [sn for sn in map(tables.system_name, tables.sensors(root)) if sn.startswith("ISNX:")]
    except (OSError, ValueError) as exc:  # the tables' sections or the panel counts file
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    print(f"SML destinationMast entries: {dests} (expected {expected})")
    print(f"ISNX sensors: {len(nx)}")

    ok = True
    if dests != expected:
        print(f"FAIL: destination count {dests} != {expected}")
        ok = False
    else:
        print("OK: destination count")

    # Entry/Exit (NX) is parked (hartlib.parked): its pairs and ISNX sensors live in the parked file, so the live
    # tables must hold no ISNX sensor and the NX mast-only check has nothing to read. Unparking NX brings that
    # check back as the feature's own (docs/parked/UNPARK.md); until it is written the unparked case fails.
    if "nx" in parked.PARKED:
        if nx:
            print(f"FAIL: Entry/Exit is parked, but tables.xml holds {len(nx)} ISNX sensors")
            ok = False
        else:
            print("OK: Entry/Exit parked, no ISNX sensor in tables.xml")
        print("skipped: NX mast-only check, NX is parked (hartlib.parked)")
    else:
        print("FAIL: NX is not parked, and this script has no NX mast-only check yet (docs/parked/UNPARK.md)")
        ok = False
    return 0 if ok else 1


def main() -> int:
    return run(TABLES)


if __name__ == "__main__":
    raise SystemExit(main())
