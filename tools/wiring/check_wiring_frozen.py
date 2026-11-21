#!/usr/bin/env python3
"""wiring.csv changes only through freeze_wiring.py (make wiring-freeze): main and upper wiring is a proposal in the
generated device rows until a control point is frozen, and the freeze is the one writer into wiring.csv.

Fails on a main or upper row wired with no freeze note, a frozen control point with a row that is not wired, or text
not in the form freeze_wiring.py writes (hartlib.wiring.audit). Staging's rows are kept by hand, as built.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hartlib" / "src"))
from hartlib import wiring  # noqa: E402
from hartlib.railroad_facts import FactsError  # noqa: E402


def main() -> int:
    try:
        found = wiring.audit()
    except (FactsError, OSError) as exc:
        print(f"FAIL: {exc}")
        return 1
    if found:
        print(f"FAIL: wiring.csv was changed other than by freeze_wiring.py ({len(found)})")
        for line in found:
            print(f"  - {line}")
        return 1
    print("OK: wiring.csv holds only what freeze_wiring.py writes on main and upper")
    return 0


if __name__ == "__main__":
    sys.exit(main())
