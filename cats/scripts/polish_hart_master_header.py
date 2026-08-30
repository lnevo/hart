#!/usr/bin/env python3
"""Polish Digicon Master panels with a HART publication-style title block.

Follows Desktop/HART/Car Cards/docs/HART_Railroad_Publication_Standards_v1.0.docx:
  HART Railroad · Pittsburgh & Chartiers Valley Division · Neville Island Operations
  Publication block: ID · Effective date · Revision letter

Adds SEC_NAME header cells on row Y=1 (track plan starts at Y=2). Does not move track.
"""

from __future__ import annotations

import argparse
import shutil
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANELS_DIR = ROOT / "cats/panels"

# Digicon Java RGB ints (opaque ARGB without alpha in CATS COLOR/FONTCOLOR).
WHITE = "-1"
YELLOW = "-256"  # same as FONT_CP

PANELS = {
    "ctc": {
        "path": PANELS_DIR / "HART_Master.xml",
        "pub_id": "DS-CTC",
        "mode": "CTC DIGICON",
    },
    "abs": {
        "path": PANELS_DIR / "HART_Master_ABS.xml",
        "pub_id": "DS-ABS",
        "mode": "ABS DIGICON",
    },
    "abs_hold": {
        "path": PANELS_DIR / "HART_Master_ABS_hold.xml",
        "pub_id": "DS-ABS",
        "mode": "ABS DIGICON",
    },
    "ctc_hold": {
        "path": PANELS_DIR / "HART_Master_CTC_hold.xml",
        "pub_id": "DS-CTC",
        "mode": "CTC DIGICON",
    },
}

# Header cells on Y=1 (left → right). NAME is what Digicon paints.
HEADER_LAYOUT = (
    # x, name, font_key, loc
    (3, "HART RAILROAD", "FONT_TITLE", "LOWLEFT"),
    (10, "NEVILLE ISLAND OPERATIONS", "FONT_SUBTITLE", "LOWLEFT"),
    (22, "P&CV DIVISION", "FONT_LABEL", "LOWCENT"),
)


def _ensure_fonts(root: ET.Element) -> None:
    """Insert title/subtitle fonts after FONT_LABEL if missing."""
    keys = {el.get("FONTKEY") for el in root.findall("FONTDEFINITION")}
    insert_after = None
    for el in root.findall("FONTDEFINITION"):
        if el.get("FONTKEY") == "FONT_LABEL":
            insert_after = el
            break
    specs = [
        ("FONT_TITLE", "Panel Title", WHITE, "16", "BOLD"),
        ("FONT_SUBTITLE", "Panel Subtitle", YELLOW, "12", "PLAIN"),
    ]
    parent = root
    idx = list(parent).index(insert_after) + 1 if insert_after is not None else 0
    for key, name, color, size, style in specs:
        if key in keys:
            # refresh size/color
            for el in root.findall("FONTDEFINITION"):
                if el.get("FONTKEY") == key:
                    el.set("FONTNAME", name)
                    el.set("FONTCOLOR", color)
                    el.set("FONTSIZE", size)
                    el.set("FONTSTYLE", style)
            continue
        el = ET.Element(
            "FONTDEFINITION",
            {
                "FONTKEY": key,
                "FONTNAME": name,
                "FONTCOLOR": color,
                "FONTSIZE": size,
                "FONTSTYLE": style,
            },
        )
        parent.insert(idx, el)
        idx += 1


def _trackplan(root: ET.Element) -> ET.Element:
    tp = root.find("TRACKPLAN")
    if tp is None:
        raise SystemExit("No TRACKPLAN in panel")
    return tp


def _upsert_section_name(
    tp: ET.Element, x: int, y: int, name: str, font: str, loc: str
) -> None:
    """Create or replace a label-only SECTION at (x,y)."""
    target = None
    for s in tp.findall("SECTION"):
        if int(s.get("X", "-1")) == x and int(s.get("Y", "-1")) == y:
            target = s
            break
    if target is None:
        target = ET.Element("SECTION", {"X": str(x), "Y": str(y)})
        # Insert near other low-Y sections (after first SECTION is fine).
        tp.insert(0, target)
    # Label-only: drop tracks if somehow present on header row (shouldn't be).
    if y == 1 and (target.find("TRACKGROUP") is not None or target.find("BLOCK") is not None):
        raise SystemExit(f"Refusing to overwrite track cell at ({x},{y})")
    for child in list(target):
        target.remove(child)
    ET.SubElement(
        target,
        "SEC_NAME",
        {"LOC_NAME": loc, "NAME": name, "FONT_NAME": font},
    )


def polish(
    path: Path,
    pub_id: str,
    mode: str,
    rev: str,
    effective: str | None,
) -> None:
    if not effective:
        effective = date.today().isoformat()
    tree = ET.parse(path)
    root = tree.getroot()
    _ensure_fonts(root)
    tp = _trackplan(root)

    # Clear prior header row Y=1 label-only cells we own (any X on Y=1 without track).
    for s in list(tp.findall("SECTION")):
        if int(s.get("Y", "-1")) != 1:
            continue
        if s.find("TRACKGROUP") is None and s.find("BLOCK") is None:
            tp.remove(s)

    for x, name, font, loc in HEADER_LAYOUT:
        _upsert_section_name(tp, x, 1, name, font, loc)

    # Mode + publication block (right side)
    _upsert_section_name(tp, 30, 1, mode, "FONT_SUBTITLE", "LOWCENT")
    pub = f"{pub_id}  Rev {rev}  Eff {effective}"
    _upsert_section_name(tp, 38, 1, pub, "FONT_LABEL", "LOWLEFT")

    # Slightly taller window so Y=1 header has air (grid paint uses HEIGHT as window hint).
    h = int(root.get("HEIGHT", "910"))
    if h < 940:
        root.set("HEIGHT", "940")

    tree.write(path, encoding="UTF-8", xml_declaration=True)
    print(f"polished {path.relative_to(ROOT)}  [{pub}]")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--panel",
        choices=("ctc", "abs", "abs_hold", "ctc_hold", "all"),
        default="ctc",
        help="Which Digicon Master to polish (default: ctc for Mac test)",
    )
    ap.add_argument("--rev", default="A", help="Revision letter (default A)")
    ap.add_argument(
        "--effective",
        default=date.today().isoformat(),
        help="Effective date YYYY-MM-DD (default today)",
    )
    ap.add_argument(
        "--checkpoint",
        action="store_true",
        help="Copy each target to cats/panels/checkpoints/ before writing",
    )
    args = ap.parse_args()

    keys = list(PANELS) if args.panel == "all" else [args.panel]
    for key in keys:
        meta = PANELS[key]
        path: Path = meta["path"]
        if not path.is_file():
            raise SystemExit(f"Missing {path}")
        if args.checkpoint:
            ck = ROOT / "cats/panels/checkpoints" / f"{path.stem}_pre_header.xml"
            shutil.copy2(path, ck)
            print(f"checkpoint {ck.relative_to(ROOT)}")
        polish(path, meta["pub_id"], meta["mode"], args.rev, args.effective)


if __name__ == "__main__":
    main()
