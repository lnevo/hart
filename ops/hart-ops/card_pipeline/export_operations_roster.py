#!/usr/bin/env python3
"""Export HART_MergedCarRoster.xml → OperationsCarRoster.xml for JMRI Operations Pro.

Operations Pro receives the full fleet (freight + passenger + caboose + MOW).
Edit inventory in ``data/image_metadata.csv`` and rebuild via ``build_car_roster_sor.py``.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
MERGED = DATA / "HART_MergedCarRoster.xml"
OPERATIONS = DATA / "OperationsCarRoster.xml"


def main() -> None:
    if not MERGED.is_file():
        raise SystemExit(f"Missing {MERGED} — run build_car_roster_sor.py first")

    text = MERGED.read_text(encoding="utf-8")
    stamp = datetime.now().strftime("%a %b %d %H:%M:%S %Y")
    if "<!--Merged HART" in text:
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("<!--Merged HART"):
                lines[i] = (
                    f"  <!--Exported to Operations Pro — {stamp} "
                    f"(source: HART_MergedCarRoster.xml)-->"
                )
                break
        text = "\n".join(lines) + "\n"

    OPERATIONS.write_text(text, encoding="utf-8")
    print(f"Wrote {OPERATIONS.name} from {MERGED.name}")


if __name__ == "__main__":
    main()
