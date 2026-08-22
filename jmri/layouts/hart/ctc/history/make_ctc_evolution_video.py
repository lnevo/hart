#!/usr/bin/env python3
"""Build stop-motion video of HART JMRI USS CTC panel evolution from history screenshots."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HISTORY = Path(__file__).resolve().parent
DESKTOP = HISTORY
OUT_MP4 = HISTORY / "CTC_Panel_Evolution.mp4"
OUT_GIF = HISTORY / "CTC_Panel_Evolution.gif"
CANVAS = (1200, 820)
BG = (32, 32, 36)
CAPTION_H = 44
FRAME_MS = 1400
FINAL_HOLD_MS = 3200

# Full-panel crops: anchor the track schematic top-left to a fixed point so
# frames don't jitter during stop-motion. Pilot / partial-width frames are
# centered instead (see is_full_panel).
FULL_PANEL_W = 1120
FULL_PANEL_H = 700
TRACK_ANCHOR_X = 8
TRACK_ANCHOR_Y = 20
FULL_PANEL_MIN_W = 980
PAD_COLOR = (180, 155, 95)  # tan panel background

# Chronological evolution (Desktop captures, Aug 19–20 2026)
FRAMES: list[tuple[str, str]] = [
    ("66e68918-4180-46f9-938b-cc55f4fa56a2.png", "Pilot — Brick + Plane (3 columns)"),
    ("Screenshot 2026-08-19 at 5.44.55\u202fPM.png", "Wireframe track + lever machine"),
    ("Screenshot 2026-08-19 at 8.37.11\u202fPM.png", "Station labels — Brick through Princess"),
    ("Screenshot 2026-08-19 at 8.44.31\u202fPM.png", "Main West / South Yard routing"),
    ("Screenshot 2026-08-19 at 9.36.05\u202fPM.png", "Engine Terminal + yard ladders"),
    ("Screenshot 2026-08-19 at 9.48.51\u202fPM.png", "West Yard W-1 / W-2 stubs"),
    ("Screenshot 2026-08-19 at 10.06.35\u202fPM.png", "Full plant geometry"),
    ("Screenshot 2026-08-19 at 10.41.20\u202fPM.png", "Engine House + McKees stubs"),
    ("Screenshot 2026-08-19 at 11.33.05\u202fPM.png", "Title banner + live lever art"),
    ("Screenshot 2026-08-19 at 11.35.49\u202fPM.png", "Connected — occupancy + aspects"),
    ("Screenshot 2026-08-20 at 1.34.22\u202fAM.png", "HART RAILROAD — NEVILLE ISLAND"),
    ("Screenshot 2026-08-20 at 7.42.19\u202fAM.png", "Final USS panel"),
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ):
        p = Path(name)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def is_dark(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r < 55 and g < 55 and b < 55


def is_gold(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r > 95 and g > 80 and b < 135 and r >= g >= b and (r - b) > 25


def is_desktop_purple(rgb: tuple[int, int, int]) -> bool:
    """Raspberry Pi / JMRI desktop background — not part of the panel."""
    r, g, b = rgb
    return 72 <= r <= 96 and 42 <= g <= 58 and 108 <= b <= 138 and (b - r) >= 22


def is_white_bg(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r > 240 and g > 240 and b > 240


def is_panel_pixel(rgb: tuple[int, int, int], y: int) -> bool:
    if is_desktop_purple(rgb) or is_white_bg(rgb):
        return False
    if is_gold(rgb) or is_dark(rgb):
        return True
    # Menu bar inside the Panel window
    if y < 26 and rgb[0] > 200 and rgb[1] > 200 and rgb[2] > 200:
        return True
    return False


def panel_trim(img: Image.Image) -> Image.Image:
    """Remove Pi purple desktop and outer white margins; keep only Panel window."""
    img = img.convert("RGB")
    w, h = img.size
    px = img.load()
    col_count = [
        sum(1 for y in range(h) if is_panel_pixel(px[x, y], y)) for x in range(w)
    ]
    thresh = max(8, h // 30)
    panel_cols = [i for i, n in enumerate(col_count) if n >= thresh]
    if not panel_cols:
        return img

    x0, x1 = panel_cols[0], panel_cols[-1]
    ys = [
        y
        for y in range(h)
        for x in range(x0, x1 + 1)
        if is_panel_pixel(px[x, y], y)
    ]
    y0, y1 = min(ys), max(ys)
    for y in range(h - 1, -1, -1):
        if sum(1 for x in range(x0, x1 + 1) if is_gold(px[x, y])) > 10:
            y1 = y
            break
    return img.crop((x0, y0, x1 + 1, y1 + 1))


def track_bbox(img: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box of the dark track-schematic band (ignores stray dark pixels)."""
    img = img.convert("RGB")
    w, h = img.size
    px = img.load()

    row_dark_x: list[list[int]] = []
    for y in range(h):
        xs = [x for x in range(w) if is_dark(px[x, y])]
        if len(xs) >= max(40, w // 20):
            row_dark_x.append(xs)

    if not row_dark_x:
        return None

    xs = [x for row in row_dark_x for x in row]
    ys = [y for y in range(h) if len([x for x in range(w) if is_dark(px[x, y])]) >= max(40, w // 20)]
    tx0, tx1 = min(xs), max(xs)
    ty0, ty1 = min(ys), max(ys)

    # Wide panels share the same schematic left edge once the plant is full width.
    if w >= FULL_PANEL_MIN_W and (tx1 - tx0) >= FULL_PANEL_MIN_W - 120:
        tx0 = 7

    return tx0, ty0, tx1, ty1


def is_full_panel(img: Image.Image) -> bool:
    trimmed = panel_trim(img)
    return trimmed.size[0] >= FULL_PANEL_MIN_W and track_bbox(trimmed) is not None


def extract_aligned(img: Image.Image, x0: int, y0: int, width: int, height: int) -> Image.Image:
    """Crop a fixed window, padding with tan when the source window is smaller."""
    src = img.convert("RGB")
    sw, sh = src.size
    out = Image.new("RGB", (width, height), PAD_COLOR)
    dx0 = max(0, -x0)
    dy0 = max(0, -y0)
    sx0 = max(0, x0)
    sy0 = max(0, y0)
    sx1 = min(sw, x0 + width)
    sy1 = min(sh, y0 + height)
    if sx1 > sx0 and sy1 > sy0:
        patch = src.crop((sx0, sy0, sx1, sy1))
        out.paste(patch, (dx0, dy0))
    return out


def aligned_full_panel_crop(img: Image.Image) -> Image.Image:
    """Crop full-panel shots; trim desktop first, then anchor on track schematic."""
    trimmed = panel_trim(img)
    box = track_bbox(trimmed)
    if box is None:
        return trimmed

    tx0, ty0, _, _ = box
    x0 = tx0 - TRACK_ANCHOR_X
    y0 = ty0 - TRACK_ANCHOR_Y
    return extract_aligned(trimmed, x0, y0, FULL_PANEL_W, FULL_PANEL_H)


def panel_crop(img: Image.Image) -> Image.Image:
    """Pilot / partial-width frame — tan panel only (no white canvas at right)."""
    return panel_trim(img)


def compose_frame(img: Image.Image, caption: str, font) -> Image.Image:
    canvas = Image.new("RGB", CANVAS, BG)
    draw = ImageDraw.Draw(canvas)

    inner_w, inner_h = CANVAS[0], CANVAS[1] - CAPTION_H - 16
    src = img.convert("RGB")
    cropped = aligned_full_panel_crop(src) if is_full_panel(src) else panel_crop(src)
    cw, ch = cropped.size
    scale = min(inner_w / cw, inner_h / ch)
    nw, nh = max(1, int(cw * scale)), max(1, int(ch * scale))
    resized = cropped.resize((nw, nh), Image.Resampling.LANCZOS)
    x = (CANVAS[0] - nw) // 2
    y = (inner_h - nh) // 2 + 8
    canvas.paste(resized, (x, y))

    tw = draw.textlength(caption, font=font)
    draw.text(
        ((CANVAS[0] - tw) / 2, CANVAS[1] - CAPTION_H),
        caption,
        fill=(220, 200, 140),
        font=font,
    )
    return canvas


def build_frames(work: Path, font) -> list[Path]:
    paths: list[Path] = []
    for i, (name, caption) in enumerate(FRAMES):
        src = DESKTOP / name
        if not src.exists():
            raise FileNotFoundError(src)
        frame = compose_frame(Image.open(src), caption, font)
        out = work / f"frame_{i:03d}.png"
        frame.save(out, optimize=True)
        paths.append(out)
    return paths


def write_concat_list(frame_paths: list[Path], list_path: Path) -> None:
    lines = []
    for i, p in enumerate(frame_paths):
        dur = FINAL_HOLD_MS / 1000 if i == len(frame_paths) - 1 else FRAME_MS / 1000
        lines.append(f"file '{p}'")
        lines.append(f"duration {dur:.3f}")
    lines.append(f"file '{frame_paths[-1]}'")
    list_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    font = load_font(22)
    with tempfile.TemporaryDirectory(prefix="ctc_evo_") as tmp:
        work = Path(tmp)
        frame_paths = build_frames(work, font)
        list_path = work / "concat.txt"
        write_concat_list(frame_paths, list_path)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-vf",
                "fps=30,format=yuv420p",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(OUT_MP4),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        # GIF — shorter loop-friendly version
        palette = work / "palette.png"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-vf",
                f"fps=2,scale={CANVAS[0]}:{CANVAS[1]}:flags=lanczos,palettegen",
                str(palette),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-i",
                str(palette),
                "-lavfi",
                f"fps=2,scale={CANVAS[0]}:{CANVAS[1]}:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer",
                str(OUT_GIF),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    print(f"Wrote {OUT_MP4}")
    print(f"Wrote {OUT_GIF}")
    print(f"Frames: {len(FRAMES)}")


if __name__ == "__main__":
    main()
