#!/usr/bin/env python3
"""Print-ready sharpened copies of CarImagesCardFill/ in a separate folder."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

BASE = Path(__file__).resolve().parent.parent  # Car Cards project root (scripts live in card_pipeline/)
SRC_DIR = BASE / "CarImagesCardFill"
OUT_DIR = BASE / "CarImagesCardFillPrint"

# Print prep — originals stay in CarImagesCardFill/.
BRIGHTNESS = 1.14
CONTRAST = 1.04
SHARPNESS = 1.12
UNSHARP = dict(radius=0.9, percent=115, threshold=2)


def sharpen_for_print(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(BRIGHTNESS)
    rgb = ImageEnhance.Contrast(rgb).enhance(CONTRAST)
    rgb = ImageEnhance.Sharpness(rgb).enhance(SHARPNESS)
    return rgb.filter(ImageFilter.UnsharpMask(**UNSHARP))


def sharpen_one(stem: str, verbose: bool = True) -> bool:
    src = SRC_DIR / f"{stem}.png"
    if not src.exists():
        if verbose:
            print(f"missing {src}")
        return False
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / src.name
    sharpen_for_print(Image.open(src)).save(out)
    if verbose:
        print(f"{src.name}: {src.stat().st_size // 1024}KB -> {out.stat().st_size // 1024}KB")
    return True


def sharpen_all(verbose: bool = True) -> int:
    stems = sorted(p.stem for p in SRC_DIR.glob("IMG_*.png"))
    if not stems:
        print(f"No images in {SRC_DIR}")
        return 1
    ok = sum(1 for s in stems if sharpen_one(s, verbose=verbose))
    print(f"Wrote {ok} images to {OUT_DIR}/")
    return 0


def main() -> int:
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--all":
            return sharpen_all()
        return 0 if sharpen_one(Path(arg).stem) else 1
    return sharpen_all()


if __name__ == "__main__":
    raise SystemExit(main())
