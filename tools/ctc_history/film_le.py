"""Build a stop-motion video of the Layout Editor panel evolution (May-Nov 2026).

Sources are the le_panel_*.png screenshots in this folder (Desktop captures of
the "HART Railroad" Layout Editor panel; the November frames are PanelPro painting the whole panel to a file). Each frame is fitted to the same
canvas on the panel's light-blue background, with a caption under it.

Run it with `python3 tools/ctc_history/films.py le`.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import film_pace  # noqa: E402

HERE = Path(__file__).resolve().parents[2] / "docs/ctc/history"
OUT_MP4 = HERE / "LE_Panel_Evolution.mp4"
OUT_POSTER = HERE / "le-poster.jpg"
CANVAS = (1280, 720)    # 16:9 so the three-level panel of November is not tiny
BG = (186, 205, 230)  # the panel's own light blue, so letterboxing is invisible
CAPTION_H = 48
CAPTION_BG = (32, 32, 36)

FRAMES: list[tuple[str, str]] = [
    ("le_panel_20260520_092004.png", "20 May: first panel, one long schematic with switch numbers 100 to 115"),
    ("le_panel_20260607_020155.png", "7 June: redrawn with named tracks, the loop, and Brick, Plane, East End, Princess"),
    ("le_panel_20260820_080629.png", "20 August: signals and occupancy on the panel; Barn and Switches 116 to 119"),
    ("le_panel_20260831_215346.png", "31 August: SW numbers, block labels and status lamps"),
    ("le_panel_20261115_hand_drawn.png", "15 November: the last hand-drawn panel"),
    ("le_panel_20261116_generated.png", "16 November: generated from the schematic, staging, main and upper level"),
]


def load_font(size: int):
    for name in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        if Path(name).exists():
            try:
                return ImageFont.truetype(name, size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def compose(src: Path, caption: str, font) -> Image.Image:
    img = Image.open(src).convert("RGB")
    inner_w, inner_h = CANVAS[0] - 24, CANVAS[1] - CAPTION_H - 16
    scale = min(inner_w / img.width, inner_h / img.height)
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", CANVAS, BG)
    canvas.paste(img, ((CANVAS[0] - img.width) // 2, 8 + (inner_h - img.height) // 2))
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, CANVAS[1] - CAPTION_H, CANVAS[0], CANVAS[1]), fill=CAPTION_BG)
    tw = d.textlength(caption, font=font)
    d.text(((CANVAS[0] - tw) / 2, CANVAS[1] - CAPTION_H + 12), caption, fill=(220, 200, 140), font=font)
    return canvas


def main() -> None:
    font = load_font(22)
    with tempfile.TemporaryDirectory(prefix="le_evo_") as tmp:
        work = Path(tmp)
        lines = []
        for i, (name, cap) in enumerate(FRAMES):
            p = work / f"f{i:02d}.png"
            frame = compose(HERE / name, cap, font)
            frame.save(p)
            if i == len(FRAMES) - 1:
                frame.save(OUT_POSTER, quality=88)
            dur = film_pace.durations(len(FRAMES))[i]
            lines += [f"file '{p}'", f"duration {dur:.3f}"]
        lines.append(f"file '{work / f'f{len(FRAMES) - 1:02d}.png'}'")
        lst = work / "concat.txt"
        lst.write_text("\n".join(lines) + "\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", "fps=30,format=yuv420p", "-t", str(film_pace.film_length(len(FRAMES))),
             "-c:v", "libx264", "-crf", "26", "-movflags", "+faststart", str(OUT_MP4)],
            check=True, capture_output=True, text=True,
        )
    print(f"Wrote {OUT_MP4} and {OUT_POSTER}")

