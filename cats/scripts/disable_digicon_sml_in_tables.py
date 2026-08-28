#!/usr/bin/env python3
"""Store Digicon SignalMastLogic destination pairs as disabled in tables.

Digicon field masts (cats/data/signal_wiring.csv) boot with SML Enabled=no so
JMRI does not run ABS until mqtt_signalhead_publisher.py takes Digicon control.
Non-Digicon SML sources (yard / approach without LCOS IH heads) are left alone.

Edits tables/new_tables.xml then copies to jmri/layouts/hart/output/tables.xml.
Re-run after cats/scripts/run_sml_discover.sh (Discover writes enabled=yes).

Usage:
  python3 cats/scripts/disable_digicon_sml_in_tables.py
  python3 cats/scripts/disable_digicon_sml_in_tables.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIRING = ROOT / "cats/data/signal_wiring.csv"
NEW_TABLES = ROOT / "tables/new_tables.xml"
SYNC_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"

_LOGIC_RE = re.compile(
    r'<signalmastlogic source="([^"]+)">.*?</signalmastlogic>',
    re.DOTALL,
)


def digicon_mast_names(path: Path = WIRING) -> set[str]:
    names: set[str] = set()
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = (row.get("mast_user_name") or "").strip()
            if m:
                names.add(m)
    return names


def disable_digicon_destinations(text: str, digicon: set[str]) -> tuple[str, int, int]:
    """Return (new_text, flipped_yes_to_no, already_no)."""
    flipped = 0
    already = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal flipped, already
        src = m.group(1)
        block = m.group(0)
        if src not in digicon:
            return block

        def en_repl(em: re.Match[str]) -> str:
            nonlocal flipped, already
            if em.group(1) == "yes":
                flipped += 1
                return "<enabled>no</enabled>"
            already += 1
            return em.group(0)

        return re.sub(r"<enabled>(yes|no)</enabled>", en_repl, block)

    out = _LOGIC_RE.sub(repl, text)
    return out, flipped, already


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--panel",
        type=Path,
        default=NEW_TABLES,
        help="tables XML to patch (default: tables/new_tables.xml)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts only; do not write",
    )
    ap.add_argument(
        "--no-sync",
        action="store_true",
        help="Do not copy to jmri/layouts/hart/output/tables.xml",
    )
    args = ap.parse_args()

    digicon = digicon_mast_names()
    text = args.panel.read_text(encoding="utf-8")
    out, flipped, already = disable_digicon_destinations(text, digicon)
    print(
        "digicon masts=%d  flipped yes->no=%d  already no=%d"
        % (len(digicon), flipped, already)
    )
    if args.dry_run:
        return
    if flipped == 0 and out == text:
        print("no changes")
    else:
        args.panel.write_text(out, encoding="utf-8")
        print("wrote %s" % args.panel.relative_to(ROOT))
    if not args.no_sync:
        shutil.copy2(args.panel, SYNC_TABLES)
        print("synced %s" % SYNC_TABLES.relative_to(ROOT))


if __name__ == "__main__":
    main()
