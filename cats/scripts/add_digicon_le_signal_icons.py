#!/usr/bin/env python3
"""Place Digicon West Yard JMRI signal masts as Layout Editor SignalMastIcons.

Targets tables/new_tables.xml (writable SoR) and syncs hart output + Mac preference
tables when present. Brick East Main West (MQTT $432) sits east of Brick / switch 100;
Plane East OS 102 takes the former icon spot near switch 102.

Mac/Pi/Windows-safe when cats-virtual appearances include imagelinks.
Digicon also binds by userName (LE icons optional for Digicon itself).
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANEL = ROOT / "tables/new_tables.xml"
SYNC_COPIES = [
    ROOT / "jmri/layouts/hart/output/tables.xml",
    ROOT / "jmri/layouts/hart/output/hart_prod.xml",
]
PREF_TABLES = Path.home() / "Library/Preferences/JMRI/My_JMRI_Railroad.jmri/tables.xml"

# Digicon PANELSIGNAL SIGORIENT → LE SignalMastIcon degrees (AAR schematic GIFs):
#   RIGHT → 90  (horizontal, heads east / post west)
#   LEFT  → 270 (horizontal, heads west / post east)
#   TOP   → 0   (vertical upright)
#   BOTTOM→ 180
# Positions are first-pass; Digicon cell facing is SoR for rotation.
PLACEMENTS: list[tuple[str, int, int, int]] = [
    # Brick — east face SIGORIENT LEFT; W-1/W-2 west stubs RIGHT (dwarf masts)
    ("Brick East Main West", 372, 228, 270),
    ("Brick West Yard 1", 170, 228, 90),
    ("Brick West Yard 2", 170, 298, 90),
    # Plane — upper (OS 102) even with East Lead; Main Ext even with barn main-east
    ("Plane East OS 102", 335, 322, 270),
    ("Plane East East Main Ext", 335, 370, 270),
    # Barn — uppers even with East Lead (322); main-east row at 370
    ("West Yard West OS 117", 420, 322, 90),
    ("West Yard East Yard T6", 520, 322, 270),
    ("West Yard West East Main Ext", 420, 370, 90),
    ("West Yard East OS 117b", 538, 370, 270),
    # East End — East Lead west under track; OS 112 further down clear of 110
    ("East End West Main West", 1135, 228, 90),
    ("East End East OS 111a", 1225, 228, 270),
    ("East End West Yard Track 1", 1135, 298, 90),
    ("East End East Lead", 1375, 322, 270),
    ("East End South OS 110", 1315, 305, 0),
    ("East End South OS 112", 1325, 358, 90),
    # Princess
    ("Princess North McKees Rocks", 1620, 198, 270),
    ("Princess West OS 113b", 1465, 228, 90),
    ("Princess West OS 113a", 1465, 322, 90),
    ("Princess South McKeesport", 1620, 348, 270),
]

ICON_ATTRS = (
    'level="9" forcecontroloff="false" hidden="no" positionable="true" '
    'showtooltip="true" editable="false" clickmode="0" litmode="false" '
    'scale="1.5" imageset="default" '
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
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--no-pref", action="store_true", help="Do not update Mac preference tables")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    patch_file(args.panel, dry_run=args.dry_run)
    if args.no_sync or args.dry_run:
        return
    for dest in SYNC_COPIES:
        if not dest.is_file():
            print(f"SKIP sync missing {dest}")
            continue
        # hart_prod may lack some masts — still place icons; JMRI ignores unknown quietly
        if dest.name == "hart_prod.xml":
            patch_file(dest)
        else:
            shutil.copy2(args.panel, dest)
            print(f"synced {dest.relative_to(ROOT)}")
    if not args.no_pref and PREF_TABLES.is_file():
        shutil.copy2(args.panel, PREF_TABLES)
        print(f"synced preference {PREF_TABLES}")


if __name__ == "__main__":
    main()
