#!/usr/bin/env python3
"""Print-ready sharpened copies of the card-fill images (car_paths.CARD_FILL_DIR) in CARD_FILL_PRINT_DIR.

    sharpen_card_fill_images.py            every IMG_*.png in CARD_FILL_DIR
    sharpen_card_fill_images.py --all      the same
    sharpen_card_fill_images.py IMG_1234   one image, by stem or file name

Both folders sit under HART_CAR_CARDS_ROOT (car_paths). The originals are not changed.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageEnhance, ImageFilter

import car_paths

BRIGHTNESS = 1.14
CONTRAST = 1.04
SHARPNESS = 1.12


class Unsharp(NamedTuple):
    """The unsharp mask applied last (PIL ImageFilter.UnsharpMask arguments)."""

    radius: float
    percent: int
    threshold: int


UNSHARP = Unsharp(radius=0.9, percent=115, threshold=2)


def sharpen_for_print(img: Image.Image) -> Image.Image:
    """An RGB copy of ``img``, brightened, given more contrast and sharpened for printing."""
    rgb = img.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(BRIGHTNESS)
    rgb = ImageEnhance.Contrast(rgb).enhance(CONTRAST)
    rgb = ImageEnhance.Sharpness(rgb).enhance(SHARPNESS)
    return rgb.filter(ImageFilter.UnsharpMask(*UNSHARP))


def _folders(src_dir: Path | None, out_dir: Path | None) -> tuple[Path, Path]:
    """The given folders, or car_paths' card-fill folders, read when called."""
    return (car_paths.CARD_FILL_DIR if src_dir is None else src_dir,
            car_paths.CARD_FILL_PRINT_DIR if out_dir is None else out_dir)


def sharpen_one(stem: str, src_dir: Path | None = None, out_dir: Path | None = None, verbose: bool = True) -> bool:
    """Write out_dir/<stem>.png from src_dir/<stem>.png. False, with a message, when the source is missing."""
    src_dir, out_dir = _folders(src_dir, out_dir)
    src = src_dir / f"{stem}.png"
    if not src.exists():
        if verbose:
            print(f"missing {src}")
        return False
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / src.name
    with Image.open(src) as img:
        sharpen_for_print(img).save(out)
    if verbose:
        print(f"{src.name}: {src.stat().st_size // 1024}KB -> {out.stat().st_size // 1024}KB")
    return True


def sharpen_all(src_dir: Path | None = None, out_dir: Path | None = None, verbose: bool = True) -> int:
    """Sharpen every IMG_*.png in src_dir into out_dir. Exit code 1 when src_dir holds none."""
    src_dir, out_dir = _folders(src_dir, out_dir)
    stems = sorted(p.stem for p in src_dir.glob("IMG_*.png"))
    if not stems:
        print(f"No images in {src_dir}")
        return 1
    ok = sum(1 for s in stems if sharpen_one(s, src_dir, out_dir, verbose=verbose))
    print(f"Wrote {ok} images to {out_dir}/")
    return 0


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Print-ready sharpened copies of the card-fill images.")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("image", nargs="?", help="one image, by stem or file name (IMG_1234 or IMG_1234.png)")
    group.add_argument("--all", action="store_true", help="every IMG_*.png in the card-fill folder (the default)")
    return ap


def main(argv: list[str] | None = None, src_dir: Path | None = None, out_dir: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.image:
        return 0 if sharpen_one(Path(args.image).stem, src_dir, out_dir) else 1
    return sharpen_all(src_dir, out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
