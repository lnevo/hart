"""Build a stop-motion video of the Layout Editor panel evolution (May-Nov 2026).

Sources are the le_panel_*.png screenshots in this folder (Desktop captures of
the "HART Railroad" Layout Editor panel; the November frames are PanelPro painting the whole panel to a file). Each frame is fitted to the same
canvas on the panel's light-blue background, with a caption under it.

Run it with `python3 tools/ctc_history/films.py le`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import NamedTuple

from film_common import CAPTION_INK, HISTORY, Font, load_font, mp4_command, open_frame, run_ffmpeg, write_concat_list
from PIL import Image, ImageDraw

HERE = HISTORY
OUT_MP4 = HERE / "LE_Panel_Evolution.mp4"
OUT_POSTER = HERE / "le-poster.jpg"
CANVAS = (1280, 720)    # 16:9 so the three-level panel of November is not tiny
BG = (186, 205, 230)  # the panel's own light blue, so letterboxing is invisible
CAPTION_H = 48
CAPTION_BG = (32, 32, 36)


class Frame(NamedTuple):
    name: str     # screenshot file in docs/ctc/history
    caption: str


FRAMES: list[Frame] = [
    Frame("le_panel_20260520_092004.png", "20 May: first panel, one long schematic with switch numbers 100 to 115"),
    Frame("le_panel_20260607_020155.png", "7 June: redrawn with named tracks, the loop, and Brick, Plane, East End, Princess"),
    Frame("le_panel_20260820_080629.png", "20 August: signals and occupancy on the panel; Barn and Switches 116 to 119"),
    Frame("le_panel_20260831_215346.png", "31 August: SW numbers, block labels and status lamps"),
    Frame("le_panel_20261115_hand_drawn.png", "15 November: the last hand-drawn panel"),
    Frame("le_panel_20261116_generated.png", "16 November: generated from the schematic, staging, main and upper level"),
]


def compose(src: Path, caption: str, font: Font) -> Image.Image:
    img = open_frame(src)
    inner_w, inner_h = CANVAS[0] - 24, CANVAS[1] - CAPTION_H - 16
    scale = min(inner_w / img.width, inner_h / img.height)
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", CANVAS, BG)
    canvas.paste(img, ((CANVAS[0] - img.width) // 2, 8 + (inner_h - img.height) // 2))
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, CANVAS[1] - CAPTION_H, CANVAS[0], CANVAS[1]), fill=CAPTION_BG)
    tw = d.textlength(caption, font=font)
    d.text(((CANVAS[0] - tw) / 2, CANVAS[1] - CAPTION_H + 12), caption, fill=CAPTION_INK, font=font)
    return canvas


def main() -> None:
    font = load_font(22)
    with tempfile.TemporaryDirectory(prefix="le_evo_") as tmp:
        work = Path(tmp)
        frame_paths: list[Path] = []
        for i, frame_spec in enumerate(FRAMES):
            p = work / f"f{i:02d}.png"
            frame = compose(HERE / frame_spec.name, frame_spec.caption, font)
            frame.save(p)
            if i == len(FRAMES) - 1:
                frame.save(OUT_POSTER, quality=88)
            frame_paths.append(p)
        lst = work / "concat.txt"
        write_concat_list(frame_paths, lst)
        run_ffmpeg(mp4_command(lst, len(frame_paths), ["-c:v", "libx264", "-crf", "26", "-movflags", "+faststart"], OUT_MP4))
    print(f"Wrote {OUT_MP4} and {OUT_POSTER}")
