"""Clean a locomotive lightbox photo for a card: loose crop, neutral backdrop, soft shadow.

The pipeline's own crop is made for freight cars. On the CSX 2121 and 2738 photos it
cropped too tight, rotated a level photo and blew out the exposure. This keeps the pixels
of the loco and the track untouched (no rotation, no exposure change) and rebuilds
everything else:

* the backdrop (creases, tape, corner wedges) is replaced by a smooth grey gradient fitted
  to the backdrop itself, forced neutral;
* the loco and track are the one big region that is not backdrop-coloured (a dark corner
  wedge that does not touch them is dropped);
* a soft contact shadow is added under the track.

Run on an upright photo (loco wheels down, EXIF already applied)::

    python loco_backdrop.py PHOTO OUT.png --box 135,445,1235,825

``--box`` is x0,y0,x1,y1 on the photo scaled to 1400 px wide. Choose it by eye: loco and
track with a margin. ``--target`` is the grey the backdrop is balanced to (default 175);
use the same value for photos that must match. Check the result by eye before using it.
"""
from __future__ import annotations

import argparse

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

REF_WIDTH = 1400
SMALL = 3  # the mask and the backdrop fit run at 1/3 size


def loco_mask(small: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """True for the loco and track: the largest region not coloured like the backdrop."""
    lum = small.mean(2)
    r = small[..., 0] / (small[..., 1] + 1)
    b = small[..., 2] / (small[..., 1] + 1)
    near = (
        (lum > 0.62 * bg.mean())
        & (abs(r - bg[0] / bg[1]) < 0.045)
        & (abs(b - bg[2] / bg[1]) < 0.07)
    )
    near = ndi.binary_opening(near, iterations=1)
    labels, _ = ndi.label(near)
    edge = (set(np.unique(labels[0, :])) | set(np.unique(labels[-1, :]))) - {0}
    backdrop = np.isin(labels, list(edge))
    parts, count = ndi.label(~backdrop)
    sizes = ndi.sum(~backdrop, parts, range(1, count + 1))
    return parts == 1 + int(np.argmax(sizes)), backdrop


def _basis(x: np.ndarray, y: np.ndarray, degree: int = 3) -> np.ndarray:
    return np.stack([x**i * y**j for i in range(degree + 1) for j in range(degree + 1 - i)], -1)


def smooth_backdrop(small: np.ndarray, backdrop: np.ndarray, keep: np.ndarray, gain: np.ndarray):
    """Neutral grey polynomial surface fitted to the backdrop pixels (creases ignored)."""
    h, w, _ = small.shape
    yy, xx = np.mgrid[0:h, 0:w]
    x, y = xx / w * 2 - 1, yy / h * 2 - 1
    use = backdrop & (ndi.distance_transform_edt(~keep) > 6)
    idx = np.argwhere(use)[::7]
    basis = _basis(x[idx[:, 0], idx[:, 1]], y[idx[:, 0], idx[:, 1]])
    value = (small[idx[:, 0], idx[:, 1]] * gain).mean(1)
    weight = np.ones(len(value))
    for _ in range(4):  # creases are darker than the fit: give them almost no weight
        coef = np.linalg.lstsq(basis * weight[:, None], value * weight, rcond=None)[0]
        weight = np.where(value - basis @ coef < -6, 0.05, 1.0)
    return _basis(x, y) @ coef


def clean(photo: Image.Image, box: tuple[int, int, int, int], target: float = 175.0,
          shadow: float = 0.55, lift: float = 10.0) -> Image.Image:
    scale = photo.width / REF_WIDTH
    img = photo.convert("RGB").crop(tuple(int(v * scale) for v in box))
    w, h = img.size
    small = np.asarray(img.resize((w // SMALL, h // SMALL), Image.LANCZOS), float)
    sh, sw, _ = small.shape
    bg = np.median(small[: int(sh * 0.07), int(sw * 0.35): int(sw * 0.65)].reshape(-1, 3), 0)
    gain = np.clip(target / bg, 0.8, 1.25)
    keep, backdrop = loco_mask(small, bg)
    surface = smooth_backdrop(small, backdrop, keep, gain)
    surface = np.asarray(Image.fromarray(np.float32(surface)).resize(img.size, Image.BICUBIC))
    back = np.clip(surface + lift, 0, 255)[..., None].repeat(3, 2)

    alpha = Image.fromarray(np.uint8(keep * 255)).resize(img.size, Image.BICUBIC)
    alpha = np.asarray(alpha.filter(ImageFilter.GaussianBlur(1.2)), float)[..., None] / 255
    drop = int(w * 0.014)
    moved = np.zeros_like(alpha[..., 0])
    moved[drop:] = alpha[:-drop, :, 0]
    soft = Image.fromarray(np.uint8(moved * 255)).filter(ImageFilter.GaussianBlur(w * 0.009))
    shade = 1 - shadow * (np.asarray(soft, float) / 255) * (1 - alpha[..., 0])
    body = np.clip(np.asarray(img, float) * gain, 0, 255)
    out = alpha * body + (1 - alpha) * back * shade[..., None]
    return Image.fromarray(np.uint8(np.clip(out, 0, 255)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("out")
    ap.add_argument("--box", required=True, help="x0,y0,x1,y1 on the photo scaled to 1400 wide")
    ap.add_argument("--target", type=float, default=175.0)
    ap.add_argument("--shadow", type=float, default=0.55)
    ap.add_argument("--lift", type=float, default=10.0)
    a = ap.parse_args()
    box = tuple(int(v) for v in a.box.split(","))
    clean(Image.open(a.photo), box, a.target, a.shadow, a.lift).save(a.out)


if __name__ == "__main__":
    main()
