"""Card layout and style constants for the HART card templates (twips unless noted).

The helpers and builders in the card_template_* modules read these from this module,
so a test that wants to change one patches it here.
"""

from docx.shared import RGBColor

# ── sticker-slot dimensions (twips) ─────────────────────────────────────────
# Page 4 of the sticker template (the 3×3 table): prints closer to the sticker
# edge — best for card fronts with text per Apostrophe's instructions.
SLOT_W = 3686   # ≈ 2.56"
SLOT_H = 5098   # ≈ 3.54"

CARD_SLOTS = [
    (0, 0), (0, 1), (0, 2),
    (1, 0), (1, 1), (1, 2),
    (2, 0), (2, 1), (2, 2),
]

# Page margins from the template's sectPr (page 4 grid).
PAGE_MAR_TOP = 202
PAGE_MAR_BOTTOM = 101
PAGE_MAR_LEFT = 418
PAGE_MAR_RIGHT = 360

# Column widths for the 3-column card grid (consistent across all rows)
COL_A = 900    # logo / icon
COL_B = 1000   # railroad name / label
COL_C = SLOT_W - COL_A - COL_B   # 1501 – badge / value

# Row heights (twips) – sized so the card fills the sticker top to bottom.
H_HEADER = 860     # tall enough for the logo + title
H_IMAGE  = 2004    # image row (taller for square/tall crops like IMG_9137)
H_DATA_SECTION = 1450  # data block; tuned with revision gap below data table
# Visual gap between image bordered box and data table (c_img bottom + c_data top).
DATA_TABLE_TOP_PAD = 140   # c_data top margin (gap below image box)
IMG_OUTER_PAD_TOP = 50
IMG_OUTER_PAD_BOTTOM = 80  # kept small so the image box can be taller
IMG_INNER_PAD = 20
WORK_FLOW_COMMODITY_GAP = 36  # space below INBOUND/OUTBOUND, before commodity
H_FOOTER = 110     # exact height for one 5.5pt revision line
H_FOOTER_LINE_TWIPS = 110  # 5.5pt exact line in revision cell

# ── style constants ─────────────────────────────────────────────────────────
FONT        = "Arial"
GRAY_FILL   = "D9D9D9"
DIVIDER_CLR = "BFBFBF"
LABEL_CLR   = RGBColor(0, 0, 0)
VALUE_CLR   = RGBColor(70, 70, 70)
ICON        = "\u2630"   # consistent line-style icon

# Inner section boxes (image + data); the main container itself is borderless.
# Inner lines: heavier than before, still lighter than the outer card frame (2.25pt).
INNER_BORDER = 8         # 1pt in Word (sz is 1/8-pt units)
IMAGE_BORDER = INNER_BORDER

# Card art sized on the page-2 gutter grid; centered as a unit in page-4 slots.
PAGE2_SLOT_W = 3401
CONTENT_MARGIN = 110
FRAME_MARGIN = 140
TARGET_CARD_W = PAGE2_SLOT_W - 2 * CONTENT_MARGIN    # 3181 twips
TARGET_FRAME_W = PAGE2_SLOT_W - 2 * FRAME_MARGIN     # 3121 twips
CENTER_OFFSET = (SLOT_W - PAGE2_SLOT_W) // 2         # shift block into wider slot
CARD_DROP_TWIPS = 180                                # 1/8" — nudge card art down in each slot
CARD_TOP_PAD = 166 + CARD_DROP_TWIPS                 # frame origin below slot top

CARD_W = TARGET_CARD_W
SIDE_PAD = 160           # horizontal pad inside header / image / data sections
FRAME_STROKE_PT = 2.25   # heavier rounded frame
FRAME_GROW_TWIPS = 45      # 1/32" — expand outer rounded frame per side / downward
FRAME_GROW_PT = 72.0 / 32  # same in points
FRAME_ARCSIZE = 0.07     # corner rounding (fraction of shorter side)
