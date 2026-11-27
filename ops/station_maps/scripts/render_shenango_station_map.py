#!/usr/bin/env python3
"""Shenango station map (SM-05), normal and rotated.

Princess switches 35 / 37 / 39, Track Helix Outer / Track Helix Inner (mainline up the
helix), and the K-1 / K-2 loop that serves Shenango Coke Works. Same sheet
language as the Barn / South Yard maps: 8 in x 5 in (1600x1000 at 200 dpi).

The rotated sheet is the same plan turned 180 degrees about the diagram, with
text kept upright.

    python3 ops/station_maps/scripts/render_shenango_station_map.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal, NamedTuple, TypeAlias

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sheet_kit  # noqa: E402
from sheet_kit import Point  # noqa: E402

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

ROOT = paths.REPO_ROOT
sys.path.insert(0, str(ROOT / sheet_kit.PUBLICATIONS_REL))
import station_compass  # noqa: E402

MAPS = ROOT / "ops/station_maps/maps"
OUT = MAPS / "Neville_Island_Station_Map_Shenango_0.png"
OUT_ROT = MAPS / "Neville_Island_Station_Map_Shenango_Rotated_0.png"
DOCS = ROOT / "docs/ops"

W, H = sheet_kit.W, sheet_kit.H
TRACK, INK, BADGE, BADGE_INK = sheet_kit.TRACK, sheet_kit.INK, sheet_kit.BADGE, sheet_kit.BADGE_INK
DOCX_TEMPLATE = ROOT / sheet_kit.SM_DOCX_TEMPLATE_REL
HOPS = ROOT / sheet_kit.HOPS_REL
DOT_R = 19

Font: TypeAlias = ImageFont.FreeTypeFont | ImageFont.ImageFont
FontKey = Literal["princess", "track", "dest"]

# Plan geometry (pixels, normal orientation).
Y_W, Y_E = 405, 512          # Main West (upper), Main East (lower)
X_ARROW = 222                # west end of the mains
X_SW115 = 728                # switches 39 / 37
X_END = 1142                 # east end of the two straight tracks
X_113 = [(578, Y_W), (525, 459), (472, Y_E)]
LOOP_TOP, LOOP_BOT = 305, 611
LOOP = [(838, 305), (1293, 305), (1382, 396), (1382, 522), (1293, 611), (838, 611)]
# 180-degree turn: x -> 1600 - x, y -> 917 - y (centre of the plan).
CY = Y_W + Y_E  # y' = CY - y


class Label(NamedTuple):
    """Text placed by its ink box at (x, y) in plan coordinates."""

    x: float
    y: float
    text: str
    font: FontKey
    anchor: str = "mm"


# Switch pills: centre in plan coordinates and number.
BADGES = ((680, 378, "39"), (570, 463, "35"), (680, 540, "37"))
LABELS = (
    Label(525, 358, "Princess", "princess"),
    Label(274, 388, "Main West", "track", "lm"),
    Label(274, 530, "Main East", "track", "lm"),
    Label(274, 459, "to East End", "dest", "lm"),
    Label(885, 388, "Track Helix Outer", "track", "lm"),
    Label(885, 530, "Track Helix Inner", "track", "lm"),
    Label(X_END - 6, 430, "to Scully Yard (helix)", "dest", "rm"),
    Label(X_END - 6, 487, "to Demmler Yard (helix)", "dest", "rm"),
    Label(1065, LOOP_TOP - 20, "Track K-1", "track"),
    Label(1065, LOOP_BOT + 22, "Track K-2", "track"),
)
# Coke Works sits inside the loop's east end, served from K-1 and K-2: a square and two
# lines of text, one unit; turned 180 degrees the square swaps sides.
INDUSTRY_LINES = ("Shenango", "Coke Works")
INDUSTRY_SQUARE, INDUSTRY_GAP = 22, 12
INDUSTRY_Y = 459
INDUSTRY_LINE_OFFSET = 17  # each line's centre above / below the square's centre
COMPASS_X, COMPASS_X_ROT, COMPASS_Y, COMPASS_R = 172, 1429, 815, 74


class Sheet:
    """One Shenango drawing, upright or turned 180 degrees; plan points go through ``at``."""

    def __init__(self, d: ImageDraw.ImageDraw, rotated: bool) -> None:
        self.d = d
        self.rotated = rotated
        self.f_num = sheet_kit.arial(20, bold=True)
        self.fonts: dict[FontKey, Font] = {
            "princess": sheet_kit.arial(38, bold=True),
            "track": sheet_kit.arial(22, bold=True),
            "dest": sheet_kit.georgia(20),
        }

    def at(self, p: Point) -> Point:
        """The sheet point of plan point ``p``."""
        return (W - p[0], CY - p[1]) if self.rotated else p

    def line(self, a: Point, b: Point, w: int = 4) -> None:
        sheet_kit.capped_line(self.d, self.at(a), self.at(b), w, TRACK)

    def text(self, label: Label) -> None:
        """Place text by its ink box in plan coordinates; keep it upright."""
        font = self.fonts[label.font]
        bx = self.d.textbbox((label.x, label.y), label.text, font=font, anchor=label.anchor)
        c = self.at(((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2))
        ob = self.d.textbbox((0, 0), label.text, font=font, anchor="mm")
        self.d.text((c[0] - (ob[0] + ob[2]) / 2, c[1] - (ob[1] + ob[3]) / 2), label.text,
                    font=font, fill=INK, anchor="mm")

    def badge(self, cx: float, cy: float, s: str) -> None:
        box = self.d.textbbox((0, 0), s, font=self.f_num)
        w, h = box[2] - box[0] + 22, box[3] - box[1] + 16
        x, y = self.at((cx, cy))
        self.d.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], radius=8, fill=BADGE)
        self.d.text((x, y - 1), s, font=self.f_num, fill=BADGE_INK, anchor="mm")

    def track(self) -> None:
        """Mains, Princess crossover, straight tracks, loop, arrows and frogs."""
        self.line((X_ARROW, Y_W), (X_END, Y_W))
        self.line((X_ARROW, Y_E), (X_END, Y_E))
        self.line(X_113[0], X_113[2])
        pts = [(X_SW115, Y_W)] + LOOP + [(X_SW115, Y_E)]
        for a, b in zip(pts, pts[1:]):
            self.line(a, b)
        for y in (Y_W, Y_E):
            sheet_kit.arrow(self.d, self.at((X_ARROW, y)), "right" if self.rotated else "left", size=17)
        for p in X_113 + [(X_SW115, Y_W), (X_SW115, Y_E)]:
            sheet_kit.dot(self.d, self.at(p), DOT_R, TRACK)

    def industry(self) -> None:
        """The Coke Works square and its two lines, centred between the track ends and the loop."""
        f_ind = sheet_kit.georgia(27, bold=True)
        l1, l2 = INDUSTRY_LINES
        tw = max(self.d.textlength(l1, font=f_ind), self.d.textlength(l2, font=f_ind))
        sqs, gap = INDUSTRY_SQUARE, INDUSTRY_GAP
        unit_w = sqs + gap + tw
        ux = (X_END + 1382) / 2 - unit_w / 2          # plan-space left edge of the unit
        mx, my = self.at((ux + unit_w / 2, INDUSTRY_Y))
        left = mx - unit_w / 2                         # upright left edge
        if self.rotated:
            sq_x, tx, anchor = left + unit_w - sqs, left + tw, "rm"
        else:
            sq_x, tx, anchor = left, left + sqs + gap, "lm"
        self.d.rectangle([sq_x, my - sqs / 2, sq_x + sqs, my + sqs / 2], fill=(0, 0, 0))
        self.d.text((tx, my - INDUSTRY_LINE_OFFSET), l1, font=f_ind, fill=INK, anchor=anchor)
        self.d.text((tx, my + INDUSTRY_LINE_OFFSET), l2, font=f_ind, fill=INK, anchor=anchor)

    def draw(self) -> None:
        """The whole sheet: title, track, pills, labels, industry and compass."""
        self.d.text((W / 2, 37), "SHENANGO", font=sheet_kit.arial(56, bold=True), fill=INK, anchor="mm")
        self.track()
        for cx, cy, s in BADGES:
            self.badge(cx, cy, s)
        for label in LABELS:
            self.text(label)
        self.industry()
        # Turned with the plan; the letters stay upright, so S is on top.
        station_compass.draw_sheet_compass(
            self.d, COMPASS_X_ROT if self.rotated else COMPASS_X, COMPASS_Y, COMPASS_R,
            style="split", turned=self.rotated, load_font=sheet_kit.load_font,
        )


def render(out: Path, rotated: bool) -> None:
    """Draw the sheet, turned 180 degrees when ``rotated``, and write it to ``out`` as PNG."""
    img = Image.new("RGB", (W, H), (255, 255, 255))
    Sheet(ImageDraw.Draw(img), rotated).draw()
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out} ({W}x{H})")


def _write_docx(png: Path, dest: Path, media_name: str) -> None:
    """The SM-series landscape docx with the Shenango map in it."""
    title = "Neville Island Station Map — Shenango"
    if "Rotated" in dest.name:
        title += " (rotated)"
    sheet_kit.write_sheet_docx(DOCX_TEMPLATE, png, dest,
                               media_names=("station_map_west_yard.png", media_name), title=title)
    print(f"wrote {dest}")


def main() -> None:
    render(OUT, False)
    render(OUT_ROT, True)
    if HOPS.is_dir():
        try:
            _write_docx(OUT, DOCS / "Neville_Island_Station_Map_Shenango.docx",
                        "station_map_shenango.png")
            _write_docx(OUT_ROT, DOCS / "Neville_Island_Station_Map_Shenango_Rotated.docx",
                        "station_map_shenango_rotated.png")
        except sheet_kit.SheetTemplateMissing as exc:
            raise SystemExit(f"render_shenango_station_map: {exc}") from exc


if __name__ == "__main__":
    main()
