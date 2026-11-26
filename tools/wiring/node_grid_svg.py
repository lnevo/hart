#!/usr/bin/env python3
"""Draw the LCOS node grid for the website from the owner's workbook.

    python3 tools/wiring/node_grid_svg.py [GRID.xlsx]

Reads media/hart-research/wiring-drafts/lcos-node-grid-2025-10-06c.xlsx (the owner's floor grid of the room:
benchwork cells filled orange, nodes in service yellow, each node's radio address in its cell; local media mirror,
not in git) and writes www/assets/behind/lcos-node-grid.svg, used by www/behind/bridge.html. Cell text other than
radio addresses (the owner's working notes) is left out, as is the "*" mark on 01. Rerun after the owner edits
the grid.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402
ROOT = paths.REPO_ROOT
GRID = ROOT / "media/hart-research/wiring-drafts/lcos-node-grid-2025-10-06c.xlsx"
OUT = ROOT / "www/assets/behind/lcos-node-grid.svg"
ADDRESS = re.compile(r"^0[0-7]{1,2}\*?$")
CELL = 30
FILL = {"orange": "#cc4a1b", "yellow": "#fff200"}


def kind(cell) -> str | None:
    if not (cell.fill and cell.fill.fill_type):
        return None
    rgb = str(cell.fill.fgColor.rgb or "").upper()[-6:]
    return {"CC4A1B": "orange", "FFF200": "yellow"}.get(rgb)


def svg(path: Path) -> str:
    ws = load_workbook(path).active
    rows, cols = ws.max_row, ws.max_column
    w, h = cols * CELL, rows * CELL
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w + 2} {h + 2}" width="{w + 2}" height="{h + 2}" '
           f'role="img" aria-label="LCOS radio node addresses on a floor plan of the layout room">',
           f'<rect x="0" y="0" width="{w + 2}" height="{h + 2}" fill="#ffffff"/>',
           '<g transform="translate(1,1)" font-family="Helvetica, Arial, sans-serif" font-size="11" font-weight="700">']
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            cell = ws.cell(r, c)
            x, y = (c - 1) * CELL, (r - 1) * CELL
            k = kind(cell)
            out.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" fill="{FILL.get(k, "#ffffff")}" '
                       f'stroke="#d6d6d6" stroke-width="0.6"/>')
            text = str(cell.value).strip() if cell.value is not None else ""
            if ADDRESS.match(text):
                colour = "#ffffff" if k == "orange" else "#111111"
                out.append(f'<text x="{x + CELL / 2}" y="{y + CELL / 2 + 4}" text-anchor="middle" '
                           f'fill="{colour}">{text.rstrip("*")}</text>')
    out += ["</g>", "</svg>"]
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    src = Path(argv[1]) if len(argv) > 1 else GRID
    if not src.exists():
        print(f"no grid workbook at {src} (it lives in the local media mirror)", file=sys.stderr)
        return 1
    OUT.write_text(svg(src), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
