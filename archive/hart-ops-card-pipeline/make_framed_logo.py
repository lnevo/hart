#!/usr/bin/env python3
"""Bake a rounded-rectangle frame into the card logo.

Reads the pristine badge (Logo_source.png) and writes Logo.png with a white
rounded-rectangle (subtle gray border) around it, so the Word template needs no
shape of its own -- it just embeds the framed PNG.

A 25px white edge buffer sits outside the border stroke so cell clipping does
not eat into the rounded frame.

Re-runnable: always starts from Logo_source.png, never from the framed output.
"""

from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)
ASSETS = Path(__file__).resolve().parent / "assets"
SRC = ASSETS / "Logo_source.png"
DST = ASSETS / "Logo.png"

N = 1024                       # output size (square)
SS = 3                         # supersample factor for crisp edges
BORDER_CLR = (191, 191, 191, 255)   # matches DIVIDER_CLR (#BFBFBF)
FILL_CLR = (255, 255, 255, 255)     # white interior (blends with the card)
BUFFER = 25                    # white margin (output px) before the border stroke
STROKE = 14                    # frame line thickness (output px) — ~1pt at card scale
GAP = 10                       # padding between the frame and the badge (output px)
RADIUS_FRAC = 0.14             # corner rounding (fraction of the side)


def main() -> None:
    logo = Image.open(SRC).convert("RGBA")

    n = N * SS
    buffer = BUFFER * SS
    stroke = STROKE * SS
    gap = GAP * SS
    radius = int(RADIUS_FRAC * (n - 2 * buffer))

    # Solid white canvas so the 5px edge buffer is white before the border stroke.
    canvas = Image.new("RGBA", (n, n), FILL_CLR)
    draw = ImageDraw.Draw(canvas)
    frame = [buffer, buffer, n - buffer - 1, n - buffer - 1]
    draw.rounded_rectangle(
        frame,
        radius=radius,
        fill=FILL_CLR,
        outline=BORDER_CLR,
        width=stroke,
    )

    inner = (frame[2] - frame[0] + 1) - 2 * (stroke + gap)
    scaled = logo.resize((inner, inner), Image.LANCZOS)
    off = (n - inner) // 2
    canvas.alpha_composite(scaled, (off, off))

    out = canvas.resize((N, N), Image.LANCZOS)
    out.save(DST)
    print(f"Wrote {DST}  ({N}x{N}, framed from {SRC.name})")


if __name__ == "__main__":
    main()
