"""Shared paths for car card + waybill print pipeline."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

PIPELINE = Path(__file__).resolve().parent
HART_OPS_ROOT = PIPELINE.parent


def cards_root() -> Path:
    """Operational car-cards tree (images); defaults to hart-ops root."""
    env = os.environ.get("HART_CAR_CARDS_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return HART_OPS_ROOT


ROOT = cards_root()
ASSETS = PIPELINE / "assets"
OUTPUT_DIR = PIPELINE / "output"
DATA = HART_OPS_ROOT / "data"

# Image trees (symlinks under HART_CAR_CARDS_ROOT)
IMAGES_DIR = ROOT / "Images"
CAR_IMAGES_DIR = ROOT / "CarImages"
# HART_CAR_IMAGES_FINAL, else the repo's ops/car-cards/car-images/CarImagesFinal. The old default,
# ROOT / "CarImagesFinal", named ops/hart-ops/CarImagesFinal when HART_CAR_CARDS_ROOT was unset, which does not exist.
FINAL_DIR = paths.car_images_final()
OCR_DIR = ROOT / "OcrZoom"
CARD_FILL_DIR = ROOT / "CarImagesCardFill"
CARD_FILL_PRINT_DIR = ROOT / "CarImagesCardFillPrint"

STICKER_SHEET = ASSETS / "Poker Size Sticker Sheet Template.docx"  # local only, not in git
STICKER_SHEET_URL = "https://www.apostrophegames.com/pages/blank-sticker-templates"


def require_sticker_sheet() -> Path:
    """The Apostrophe Games poker-size sticker template every card sheet starts from.

    It is their file, so it is not kept in the repo: download the Word version once.
    """
    if not STICKER_SHEET.is_file():
        raise SystemExit(
            f"Missing the sticker sheet template {STICKER_SHEET}.\n"
            f"Download the poker-size Word template (US Letter) from {STICKER_SHEET_URL}\n"
            f"and save it there under that name."
        )
    return STICKER_SHEET
EQUIPMENT_TEMPLATE = OUTPUT_DIR / "HART_Equipment_Card_Template.docx"
SPOT_WAYBILLS = OUTPUT_DIR / "HART_Spot_Waybills.docx"
ALL_CAR_CARDS = OUTPUT_DIR / "HART_All_Car_Cards.docx"

PRINT_ARCHIVE = HART_OPS_ROOT.parents[1] / "docs/ops" / "print"
