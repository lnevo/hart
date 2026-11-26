"""Font paths and the font loader of the drawn publications (station maps SM-01 to SM-05).

The maps are drawn on the Mac with its system fonts. For SM-01 a missing font raises
FontMissing: the PIL bitmap default would change every label, so the drawing stops instead.
The local maps (SM-02 to SM-05) load through local_station_maps.kit._font, which falls back
to the PIL default with a warning, and hand that loader to the compass too.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import ImageFont

GEORGIA = "/System/Library/Fonts/Supplemental/Georgia.ttf"
GEORGIA_BOLD = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
ARIAL_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"


class FontMissing(RuntimeError):
    """A font a publication draws with cannot be loaded."""


@lru_cache(maxsize=None)
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """The TrueType font at ``path`` in ``size`` px, loaded once per path and size."""
    try:
        return ImageFont.truetype(path, size)
    except OSError as exc:
        raise FontMissing(f"cannot load font {path} at {size} px: {exc}") from exc
