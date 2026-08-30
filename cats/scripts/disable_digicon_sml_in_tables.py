#!/usr/bin/env python3
"""Store Digicon SignalMastLogic destination pairs as disabled in tables.

Digicon field masts (cats/data/signal_wiring.csv) boot with SML Enabled=no so
JMRI does not run ABS until mqtt_signalhead_publisher.py takes Digicon control.
Non-Digicon SML sources (yard / approach without LCOS IH heads) are left alone.

Edits tables/new_tables.xml then copies to jmri/layouts/hart/output/tables.xml.
Re-run after cats/scripts/run_sml_discover.sh (Discover writes enabled=yes).
Deploy (`sync_hart_package.sh`) calls this with `--panel` on the shipped tables
and `--no-sync` so Digicon dests are Disabled without replacing the other file.

Usage:
  python3 cats/scripts/disable_digicon_sml_in_tables.py
  python3 cats/scripts/disable_digicon_sml_in_tables.py --dry-run
  python3 cats/scripts/disable_digicon_sml_in_tables.py --check --panel path/to/tables.xml
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIRING = ROOT / "cats/data/signal_wiring.csv"
NEW_TABLES = ROOT / "tables/new_tables.xml"
SYNC_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"

_LOGIC_RE = re.compile(
    r'<signalmastlogic source="([^"]+)">.*?</signalmastlogic>',
    re.DOTALL,
)
_DEST_ENABLED_RE = re.compile(
    r'<destinationMast destination="([^"]+)">.*?<enabled>(yes|no)</enabled>',
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


def enabled_digicon_pairs(text: str, digicon: set[str]) -> list[tuple[str, str]]:
    """Digicon source -> dest pairs still stored Enabled=yes."""
    pairs: list[tuple[str, str]] = []
    for m in _LOGIC_RE.finditer(text):
        src = m.group(1)
        if src not in digicon:
            continue
        for dm in _DEST_ENABLED_RE.finditer(m.group(0)):
            if dm.group(2) == "yes":
                pairs.append((src, dm.group(1)))
    return pairs


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
    ap.add_argument(
        "--check",
        action="store_true",
        help="Fail if any Digicon (MQTT) SML dest is still Enabled=yes; do not write",
    )
    args = ap.parse_args()

    if not args.panel.is_file():
        print("missing tables file: %s" % args.panel, file=sys.stderr)
        raise SystemExit(1)

    digicon = digicon_mast_names()
    text = args.panel.read_text(encoding="utf-8")
    if args.check:
        pairs = enabled_digicon_pairs(text, digicon)
        rel = args.panel
        try:
            rel = args.panel.relative_to(ROOT)
        except ValueError:
            pass
        if pairs:
            print(
                "ERROR: %s has %d Digicon SML dest(s) Enabled=yes "
                "(MQTT masts must boot Disabled):"
                % (rel, len(pairs)),
                file=sys.stderr,
            )
            for src, dest in pairs[:24]:
                print("  %s -> %s" % (src, dest), file=sys.stderr)
            if len(pairs) > 24:
                print("  ... (%d more)" % (len(pairs) - 24), file=sys.stderr)
            print(
                "Fix: python3 cats/scripts/disable_digicon_sml_in_tables.py",
                file=sys.stderr,
            )
            raise SystemExit(1)
        print(
            "ok: %s Digicon SML dests Enabled=no (masts=%d)"
            % (rel, len(digicon))
        )
        return
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
