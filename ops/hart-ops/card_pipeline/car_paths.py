"""Shared paths for car card + waybill print pipeline."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402


from card_errors import CardPipelineError  # noqa: E402,F401  re-exported: callers that already import car_paths


PIPELINE = Path(__file__).resolve().parent
HART_OPS_ROOT = PIPELINE.parent
PUBLICATIONS = HART_OPS_ROOT / "publications"
# The card scripts import the OOXML helpers (hart_ooxml.py) and the crew master's colours (crew_master.py) from
# publications/. Appended, so a card_pipeline module of the same name would still win.
if str(PUBLICATIONS) not in sys.path:
    sys.path.append(str(PUBLICATIONS))


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
# HART_CAR_IMAGES_FINAL; else ROOT / "CarImagesFinal" when HART_CAR_CARDS_ROOT moves the image trees, so they stay
# together; else the repo copy (hartlib.paths). The old default, ROOT / "CarImagesFinal" with HART_CAR_CARDS_ROOT
# unset, named ops/hart-ops/CarImagesFinal, which does not exist.
if os.environ.get("HART_CAR_IMAGES_FINAL", "").strip() or not os.environ.get("HART_CAR_CARDS_ROOT", "").strip():
    FINAL_DIR = paths.car_images_final()
else:
    FINAL_DIR = (ROOT / "CarImagesFinal").resolve()
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
        raise CardPipelineError(
            f"Missing the sticker sheet template {STICKER_SHEET}.\n"
            f"Download the poker-size Word template (US Letter) from {STICKER_SHEET_URL}\n"
            f"and save it there under that name."
        )
    return STICKER_SHEET
EQUIPMENT_TEMPLATE = OUTPUT_DIR / "HART_Equipment_Card_Template.docx"
SPOT_WAYBILLS = OUTPUT_DIR / "HART_Spot_Waybills.docx"
ALL_CAR_CARDS = OUTPUT_DIR / "HART_All_Car_Cards.docx"

PRINT_ARCHIVE = HART_OPS_ROOT.parents[1] / "docs/ops" / "print"
