"""Text widths as JMRI draws them on the Pi: the Dialog font of a Layout Editor label under Raspberry Pi OS, where
Dialog is DejaVu Sans.

    pi_dialog.width("Track Power", 12)        # 76 px, as FontMetrics.stringWidth on the Pi
    pi_dialog.height(12)                      # 15 px, FontMetrics.getHeight

The plugin's jmri_text holds the larger of the Mac's and the Pi's widths, so a label sized by it never covers its
neighbours on either host. A label that must line up with something on the Pi's panel (the status cluster's
captions beside their lamps, panel_items.py) needs the Pi's own widths, which this table holds.

Measured on the Pi 2026-11-21 with OpenJDK 17.0.21, headless: FontMetrics.charWidth of each printable ASCII
character (chr(32)..chr(126)) and getHeight, for new Font("Dialog", style, size); /usr/share/fonts/truetype/dejavu/
DejaVuSans.ttf (sha256 abdc775b...2322). stringWidth was checked to equal the sum of charWidth for the four status
captions. Java's hinted integer advances differ from a font library's rounded ones (PIL's for 21 of 95 characters
at 12 px), so measure again in Java, not from the font file, to add a size.
"""
from __future__ import annotations

FIRST = 32
# (style, size): (line height, [advance of chr(32) .. chr(126)]); style 0 plain, 1 bold
DIALOG = {
    (0, 10): (13, [3, 4, 5, 8, 6, 10, 9, 3, 4, 4, 5, 8, 3, 4, 3, 3, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 3, 3, 8, 8, 8, 5,
                   11, 7, 7, 8, 8, 7, 6, 8, 8, 3, 3, 7, 6, 9, 8, 8, 7, 8, 7, 7, 5, 8, 7, 9, 6, 7, 6, 4, 3, 4, 8, 5, 5,
                   6, 6, 5, 6, 6, 4, 6, 6, 2, 2, 5, 2, 10, 6, 6, 6, 6, 4, 5, 4, 6, 6, 8, 6, 6, 5, 6, 3, 6, 8]),
    (0, 12): (15, [4, 5, 5, 10, 8, 11, 10, 3, 5, 5, 6, 10, 4, 4, 4, 4, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 4, 4, 10, 10, 10,
                   6, 13, 8, 8, 8, 9, 8, 7, 9, 9, 3, 3, 7, 6, 10, 9, 9, 8, 9, 8, 8, 7, 9, 8, 11, 7, 7, 9, 5, 4, 5, 10,
                   6, 6, 8, 8, 7, 8, 8, 4, 8, 8, 3, 3, 7, 3, 11, 8, 8, 8, 8, 5, 7, 5, 8, 6, 9, 6, 6, 5, 8, 4, 8, 10]),
    (0, 14): (17, [4, 5, 5, 12, 9, 13, 12, 3, 5, 5, 7, 12, 4, 5, 4, 5, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 5, 5, 12, 12, 12,
                   7, 14, 9, 10, 10, 11, 9, 8, 11, 10, 3, 3, 9, 7, 12, 10, 11, 9, 11, 10, 9, 9, 10, 9, 13, 9, 9, 10, 5,
                   5, 5, 12, 7, 7, 8, 9, 8, 9, 9, 4, 9, 9, 3, 3, 8, 3, 13, 9, 9, 9, 9, 5, 8, 5, 9, 7, 11, 7, 7, 8, 9,
                   5, 9, 12]),
    (1, 10): (13, [3, 5, 5, 8, 7, 10, 9, 3, 5, 5, 5, 8, 4, 4, 4, 4, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 4, 4, 8, 8, 8, 6,
                   10, 9, 7, 7, 8, 6, 6, 8, 8, 3, 3, 7, 6, 9, 8, 8, 7, 8, 8, 7, 7, 8, 9, 11, 8, 7, 7, 5, 4, 5, 8, 5, 5,
                   7, 7, 6, 7, 7, 4, 7, 7, 3, 3, 7, 3, 11, 7, 7, 7, 7, 5, 6, 5, 7, 7, 9, 7, 7, 5, 7, 4, 7, 8]),
    (1, 12): (15, [4, 5, 6, 10, 8, 12, 10, 4, 5, 5, 6, 10, 5, 5, 5, 4, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 5, 5, 10, 10, 10,
                   7, 12, 9, 9, 9, 10, 8, 8, 10, 10, 4, 4, 9, 8, 12, 10, 11, 9, 10, 9, 9, 8, 10, 9, 14, 9, 8, 10, 5, 4,
                   5, 10, 6, 6, 9, 9, 7, 9, 9, 5, 9, 9, 4, 4, 8, 4, 12, 9, 9, 9, 9, 6, 8, 6, 9, 7, 12, 7, 8, 8, 9, 4,
                   9, 10]),
    (1, 14): (17, [5, 6, 7, 12, 10, 14, 13, 4, 6, 6, 7, 12, 5, 6, 5, 5, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 6, 6,
                   12, 12, 12, 8, 14, 11, 10, 11, 11, 9, 9, 12, 11, 4, 4, 11, 9, 13, 11, 12, 10, 12, 10, 10, 10, 11, 11,
                   15, 10, 10, 11, 6, 5, 6, 12, 7, 7, 9, 10, 9, 10, 10, 6, 10, 10, 4, 4, 9, 4, 14, 10, 10, 10, 10, 7, 9,
                   6, 10, 9, 14, 9, 9, 9, 10, 5, 10, 12]),
}


class PiTextError(ValueError):
    pass


def _table(size, bold):
    key = (1 if bold else 0, size)
    if key not in DIALOG:
        have = ", ".join(f"{s}{' bold' if b else ''}" for b, s in sorted(DIALOG))
        raise PiTextError(f"no Pi Dialog widths for size {size}{' bold' if bold else ''} (measured: {have}); "
                          "measure them on the Pi in Java (module text)")
    return DIALOG[key]


def width(text: str, size: int, bold: bool = False) -> int:
    """px JMRI on the Pi gives `text` (FontMetrics.stringWidth: the sum of its characters' advances)."""
    adv = _table(size, bold)[1]
    out = 0
    for c in text:
        i = ord(c) - FIRST
        if not 0 <= i < len(adv):
            raise PiTextError(f"{text!r}: {c!r} is not printable ASCII, which the Pi Dialog table holds")
        out += adv[i]
    return out


def height(size: int, bold: bool = False) -> int:
    """px JMRI on the Pi gives a line (FontMetrics.getHeight)."""
    return _table(size, bold)[0]
