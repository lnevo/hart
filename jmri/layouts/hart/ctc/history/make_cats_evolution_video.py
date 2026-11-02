#!/usr/bin/env python3
"""Build a stop-motion video of the CATS Dispatcher Panel evolution (Aug 8-26 2026).

Sources are dated screenshots in media/screenshots (gitignored). Each frame is
cropped to the panel itself, so browser and editor windows that happened to be
on the desktop stay out of the picture. Every frame uses the same scale and is
anchored top-left, so growth of the diagram is visible rather than rescaled.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("HART_SCREENSHOTS", str(Path(__file__).resolve().parents[5] / "media" / "screenshots")))
OUT_MP4 = HERE / "CATS_Panel_Evolution.mp4"
CANVAS = (1280, 380)
BG = (0, 0, 0)
CAPTION_H = 44
SCALE = 0.88
FRAME_MS = 2200
FINAL_HOLD_MS = 4000

# (file, crop box in source pixels, caption). Crops drop other windows.
FRAMES: list[tuple[str, tuple[int, int, int, int], str]] = [
    ("cats_HART_ctc_20260808_230606.png", (0, 0, 1100, 240), "First draft: station names and bare track"),
    ("cats_HART_ctc_20260808_232006.png", (0, 0, 1300, 390), "Yard ladder grows; Barn and Main East appear"),
    ("cats_HART_ctc_20260808_234941.png", (0, 0, 1200, 300), "Some labels renamed as control points (CP Brick, CP Plane, CP 112)"),
    ("cats_HART_ctc_20260808_235941_crop.png", (0, 32, 1450, 300), "Main runs through to Shenango; yard ladder redrawn"),
    ("cats_HART_ctc_20260809_001200.png", (0, 0, 1450, 300), "Route labels added along the diagram"),
    # Later frames come from the desktop; box None means fit the whole image to the canvas.
    ("cats_dispatcher_20260810_104619.png", None, "Live: West Yard, Brick and the yard tracks S-1 to S-5"),
    ("cats_dispatcher_20260810_122329.png", None, "Yard tracks T9 to T11 and the West Lead added"),
    ("cats_dispatcher_20260823_204325.png", None, "Redrawn on straight mains; engine house tracks EH-1 to EH-3"),
    ("cats_dispatcher_20260825_015115.png", None, "Title block: Neville Island Operations, CTC Digicon"),
    ("cats_dispatcher_20260825_075630.png", None, "Retitled ABS Digicon; Brick-Plane, Scale and Barn labelled"),
    ("cats_dispatcher_20260826_184626.png", None, "Rev A, effective 26 August"),
]


def load_font(size: int):
    for name in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        if Path(name).exists():
            try:
                return ImageFont.truetype(name, size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def compose(src: Path, box, caption: str, font) -> Image.Image:
    img = Image.open(src).convert("RGB")
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
    d.text(((CANVAS[0] - tw) / 2, CANVAS[1] - CAPTION_H + 6), caption, fill=(220, 200, 140), font=font)
    return canvas


def main() -> None:
    font = load_font(22)
    with tempfile.TemporaryDirectory(prefix="cats_evo_") as tmp:
        work = Path(tmp)
        lines = []
        for i, (name, box, cap) in enumerate(FRAMES):
            p = work / f"f{i:02d}.png"
            compose(SRC / name, box, cap, font).save(p)
            dur = (FINAL_HOLD_MS if i == len(FRAMES) - 1 else FRAME_MS) / 1000
            lines += [f"file '{p}'", f"duration {dur:.3f}"]
        lines.append(f"file '{work / f'f{len(FRAMES) - 1:02d}.png'}'")
        lst = work / "concat.txt"
        lst.write_text("\n".join(lines) + "\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", "fps=30,format=yuv420p",
             "-c:v", "libx264", "-crf", "26", "-movflags", "+faststart", str(OUT_MP4)],
            check=True, capture_output=True, text=True,
        )
    print(f"Wrote {OUT_MP4}")


if __name__ == "__main__":
    main()
