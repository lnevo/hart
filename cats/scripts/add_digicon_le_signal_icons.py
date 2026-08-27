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
    ("Mast 2L", 378, 222, 270),
    ("Mast 4RA", 185, 258, 90),
    ("Mast 4RB", 185, 321, 90),
    ("Mast 6LA", 366, 290, 270),
    ("Mast 6LB", 366, 338, 270),
    ("Mast 8RA", 445, 327, 90),
    ("Mast 8LB", 552, 290, 270),
    ("Mast 8RB", 445, 374, 90),
    ("Mast 8LA", 529, 341, 270),
    ("Mast 24RA", 1095, 263, 90),
    ("Mast 24L", 1248, 218, 270),
    ("Mast 24RB", 1095, 326, 90),
    ("Mast 34L", 1392, 289, 270),
    ("Mast 32R", 1265, 349, 60),
    ("Mast 34R", 1320, 348, 60),
    ("Mast 40LB", 1608, 185, 225),
    ("Mast 36RA", 1465, 264, 90),
    ("Mast 36RB", 1465, 325, 90),
    ("Mast 38LB", 1628, 322, 310),
    ("Mast 2035", 1848, 245, 0),
    ("Mast 2036", 1804, 291, 180),
    ("Mast 40LA", 1665, 222, 270),
    ("Mast 38LA", 1665, 285, 270),
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
