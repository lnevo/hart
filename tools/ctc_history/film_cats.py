"""Build a stop-motion video of the CATS Dispatcher Panel evolution (Aug 8-26 2026).

Sources are dated screenshots in media/screenshots (gitignored). Each frame is
cropped to the panel itself, so browser and editor windows that happened to be
on the desktop stay out of the picture. Every frame uses the same scale and is
anchored top-left, so growth of the diagram is visible rather than rescaled.

Run it with `python3 tools/ctc_history/films.py cats`.
"""

from __future__ import annotations

import os
from functools import partial
from pathlib import Path
from typing import NamedTuple

from film_common import CAPTION_INK, HISTORY, REPO, Box, Font, build_film, load_font, open_frame
from PIL import Image, ImageDraw

HERE = HISTORY
SRC = Path(os.environ.get("HART_SCREENSHOTS", str(REPO / "media" / "screenshots")))
OUT_MP4 = HERE / "CATS_Panel_Evolution.mp4"
OUT_POSTER = HERE / "cats-poster.jpg"
CANVAS = (1280, 720)    # 16:9 so the three-level desk of November is readable
BG = (0, 0, 0)
CAPTION_H = 44
SCALE = 0.88


class Frame(NamedTuple):
    name: str          # screenshot file in SRC
    box: Box | None    # crop box in source pixels, dropping other windows; None fits the whole image
    caption: str


FRAMES: list[Frame] = [
    Frame("cats_HART_ctc_20260808_230606.png", (0, 0, 1100, 240), "First draft: station names and bare track"),
    Frame("cats_HART_ctc_20260808_232006.png", (0, 0, 1300, 390), "Yard ladder grows; Barn and Main East appear"),
    Frame("cats_HART_ctc_20260808_234941.png", (0, 0, 1200, 300), "Some labels renamed as control points (CP Brick, CP Plane, CP 112)"),
    Frame("cats_HART_ctc_20260808_235941_crop.png", (0, 32, 1450, 300), "Main runs through to Shenango; yard ladder redrawn"),
    Frame("cats_HART_ctc_20260809_001200.png", (0, 0, 1450, 300), "Route labels added along the diagram"),
    # Later frames come from the desktop and are fitted whole.
    Frame("cats_dispatcher_20260810_104619.png", None, "Live: West Yard, Brick and the yard tracks S-1 to S-5"),
    Frame("cats_dispatcher_20260810_122329.png", None, "Yard tracks T9 to T11 and the West Lead added"),
    Frame("cats_dispatcher_20260823_204325.png", None, "Redrawn on straight mains; engine house tracks EH-1 to EH-3"),
    Frame("cats_dispatcher_20260825_015115.png", None, "Title block: Neville Island Operations, CTC Digicon"),
    Frame("cats_dispatcher_20260825_075630.png", None, "Retitled ABS Digicon; Brick-Plane, Scale and Barn labelled"),
    Frame("cats_dispatcher_20260826_123325.png", None, "Routes lined in green on the CTC Digicon"),
    Frame("cats_dispatcher_20260826_184626.png", None, "Rev A, effective 26 August"),
    Frame("cats_dispatcher_20261116_225112.png", None, "16 November: generated from the schematic, staging, main and upper level (ABS)"),
]


def compose(src: Path, box: Box | None, caption: str, font: Font) -> Image.Image:
    """The screenshot at ``src``, cropped to ``box`` at SCALE (or fitted whole, never enlarged, when ``box`` is None),
    anchored top-left with ``caption`` centred along the bottom; the caption strip hides what reaches it."""
    img = open_frame(src)
    if box is None:
        scale = min(CANVAS[0] / img.width, (CANVAS[1] - CAPTION_H) / img.height, 1.0)
    else:
        img = img.crop(box)
        scale = SCALE
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", CANVAS, BG)
    canvas.paste(img.crop((0, 0, CANVAS[0], CANVAS[1] - CAPTION_H)), (0, 0))
    d = ImageDraw.Draw(canvas)
    tw = d.textlength(caption, font=font)
    d.text(((CANVAS[0] - tw) / 2, CANVAS[1] - CAPTION_H + 6), caption, fill=CAPTION_INK, font=font)
    return canvas


def main() -> None:
    font = load_font(22)
    build_film([partial(compose, SRC / f.name, f.box, f.caption, font) for f in FRAMES], OUT_MP4, OUT_POSTER,
               "cats_evo_")
    print(f"Wrote {OUT_MP4} and {OUT_POSTER}")
