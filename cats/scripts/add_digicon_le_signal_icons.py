#!/usr/bin/env python3
"""Place HART JMRI signal masts as Layout Editor SignalMastIcons.

Targets tables/new_tables.xml (writable SoR). Synchronization is opt-in because
output/tables.xml also contains CTC data that must never be replaced by the
working file. The reviewed coordinates put horizontal masts on the engineer's
right side of the governed track.

Mac/Pi/Windows-safe when cats-virtual appearances include imagelinks.
Digicon also binds by userName (LE icons optional for Digicon itself).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANEL = ROOT / "tables/new_tables.xml"
OUTPUT_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
STANDALONE_PANEL = ROOT / "jmri/layouts/hart/output/hart_prod.xml"
PREF_TABLES = Path.home() / "Library/Preferences/JMRI/My_JMRI_Railroad.jmri/tables.xml"

# Digicon PANELSIGNAL SIGORIENT → LE SignalMastIcon degrees (AAR schematic GIFs):
#   RIGHT → 90  (horizontal, heads east / post west)
#   LEFT  → 270 (horizontal, heads west / post east)
#   TOP   → 0   (vertical upright)
#   BOTTOM→ 180
# Positions are the reviewed LE standard. Digicon cell facing remains the SoR
# for route direction, while the LE x/y puts each mast trackside.
PLACEMENTS: list[tuple[str, int, int, int]] = [
    ("100L", 378, 222, 270),
    ("101RA", 185, 258, 90),
    ("101RB", 185, 321, 90),
    ("102LA", 360, 297, 270),
    ("102LB", 365, 345, 270),
    ("117RA", 435, 321, 90),
    ("117LB", 534, 297, 270),
    ("117RB", 425, 368, 90),
    ("117LA", 534, 344, 270),
    ("111RA", 1095, 258, 90),
    ("111L", 1225, 222, 270),
    ("111RB", 1135, 321, 90),
    ("112L", 1392, 285, 270),
    ("110R", 1248, 350, 60),
    ("112R", 1320, 348, 60),
    ("115LB", 1608, 185, 225),
    ("113RA", 1465, 258, 90),
    ("113RB", 1465, 321, 90),
    ("114LB", 1628, 322, 310),
    ("115R", 1810, 276, 180),
    ("114R", 1855, 276, 0),
    ("115LA", 1665, 239, 270),
    ("114LA", 1665, 302, 270),
]

ICON_ATTRS = (
    'level="9" forcecontroloff="false" hidden="no" positionable="true" '
    'showtooltip="true" editable="false" clickmode="0" litmode="false" '
    'scale="1.0" imageset="default" '
    'class="jmri.jmrit.display.configurexml.SignalMastIconXml"'
)


def _icon_xml(name: str, x: int, y: int, degrees: int) -> str:
    return (
        f'    <signalmasticon signalmast="{name}" x="{x}" y="{y}" '
        f'{ICON_ATTRS} degrees="{degrees}" />\n'
    )


def strip_icons(text: str) -> str:
    # Remove prior Digicon-managed icons (known mast set from this script)
    names = {p[0] for p in PLACEMENTS}
    name_re = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.sub(
        rf"\n?\s*<signalmasticon signalmast=\"(?:{name_re})\"[^>]*/>\s*",
        "\n",
        text,
    )


def inject_icons(text: str) -> str:
    text = strip_icons(text)
    block = "".join(_icon_xml(*p) for p in PLACEMENTS)
    # Insert before LayoutEditor closing tag
    m = re.search(r"(</LayoutEditor>)", text)
    if not m:
        raise SystemExit("no </LayoutEditor> in panel")
    return text[: m.start()] + block + text[m.start() :]


def patch_file(path: Path, *, dry_run: bool = False) -> None:
    if not path.is_file():
        print(f"SKIP missing {path}")
        return
    text = path.read_text(encoding="utf-8")
    if "<LayoutEditor" not in text:
        print(f"SKIP no LayoutEditor: {path}")
        return
    out = inject_icons(text)
    n = sum(1 for name, *_ in PLACEMENTS if f'signalmasticon signalmast="{name}"' in out)
    if dry_run:
        print(f"DRY {path}: would write {n} icons")
        return
    path.write_text(out, encoding="utf-8")
    print(f"patched {path} ({n} icons)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    ap.add_argument(
        "--sync-output",
        action="store_true",
        help="Patch output/tables.xml and hart_prod.xml independently",
    )
    ap.add_argument(
        "--sync-pref",
        action="store_true",
        help="Patch the Mac preference tables independently",
    )
    ap.add_argument(
        "--no-sync",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    patch_file(args.panel, dry_run=args.dry_run)
    if args.dry_run:
        return
    if args.sync_output:
        for dest in (OUTPUT_TABLES, STANDALONE_PANEL):
            if not dest.is_file():
                print(f"SKIP sync missing {dest}")
                continue
            patch_file(dest)
    if args.sync_pref and PREF_TABLES.is_file():
        patch_file(PREF_TABLES)


if __name__ == "__main__":
    main()
