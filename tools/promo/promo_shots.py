"""What the promo cuts in tiktok_promo.py show: the site pages captured, the layout photos and the page regions,
and the headless Chrome captures of those pages. PromoError is the promo scripts' one error.

The page regions are pixel offsets into the 1080 px wide phone captures in media/promo/shots/. After the site
changes, delete the old capture, let tiktok_promo.py take a new one, and check these offsets against it.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple

SITE_URL = "https://www.hartrailroad.com/"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class PromoError(Exception):
    """A promo cannot be rendered: a missing input, a tool that failed, or voice timings that do not fit."""


# Site pages captured live at phone width: path under the site -> file stem in media/promo/shots/.
PAGES: dict[str, str] = {
    "": "home",
    "history/": "history",
    "plants/": "plants",
    "railroads/": "railroads",
    "photos/": "photos",
    "operators/cards/": "cards",
    "operators/room/": "room",
    "crew/": "crew",
    "build/": "build",
    "behind/": "behind",
    "behind/signals.html": "signals",
    "behind/wiring.html": "wiring",
    "behind/panel-evolution.html": "panels",
    "ai/": "ai",
    "ai/control.html": "ai-control",
    "ai/speed-runs.html": "speed-runs",
    "ai/research.html": "ai-research",
    "ai/construction.html": "ai-construction",
    "ai/electronics.html": "ai-electronics",
}

# The captures each cut reads.
CUT_PAGES: dict[str, set[str]] = {
    "build": {"home"},
    "site": set(PAGES.values()) - {"ai-research", "ai-construction", "ai-electronics"},
    "diverging": {"ai", "photos", "signals", "cards", "speed-runs", "ai-research", "ai-electronics"},
}


class Focus(NamedTuple):
    """Where a cover crop centres, as a share of the photo's width and height."""
    x: float
    y: float


class QuickPhoto(NamedTuple):
    name: str           # file in media/photos-layout
    focus: Focus


# The build cut's quick run of photos from the empty room to the railroad.
BUILD_QUICK: tuple[QuickPhoto, ...] = (
    QuickPhoto("IMG_5280.jpg", Focus(0.5, 0.5)),
    QuickPhoto("IMG_6653.jpg", Focus(0.45, 0.5)),
    QuickPhoto("IMG_6844.jpg", Focus(0.5, 0.5)),
    QuickPhoto("IMG_0691.jpg", Focus(0.5, 0.5)),
    QuickPhoto("IMG_7813.jpg", Focus(0.5, 0.5)),
    QuickPhoto("IMG_7915.jpg", Focus(0.5, 0.5)),
    QuickPhoto("IMG_8070.jpg", Focus(0.5, 0.5)),
)


class Region(NamedTuple):
    """A region of a page capture, in capture pixels, shown as a card tilted by `tilt` degrees."""
    page: str           # capture stem, a value of PAGES
    y0: int
    y1: int
    x0: int
    x1: int
    tilt: float


class Section(NamedTuple):
    """One section of the site cut: its title slam, the caption over its shots, the blurred backdrop photo and
    the page regions shown."""
    name: str
    caption: str
    backdrop: str       # file in media/photos-layout
    regions: tuple[Region, ...]


SITE_SECTIONS: tuple[Section, ...] = (
    Section("Prototype", "Real Neville Island history", "IMG_9231.jpg", (
        Region("history", 120, 1400, 0, 1080, 0),
        Region("photos", 1900, 3000, 0, 1080, -3),
        Region("plants", 4300, 5700, 0, 1080, 0),
        Region("photos", 2900, 4000, 0, 1080, 3),
        Region("railroads", 2700, 3700, 0, 1080, 0),
        Region("photos", 5800, 6950, 0, 1080, -2.5),
    )),
    Section("Operations", "Car cards, waybills and crew sheets", "IMG_8904.jpg", (
        Region("cards", 330, 1650, 60, 1020, 0),
        Region("cards", 3360, 4440, 150, 930, -3),
        Region("cards", 4500, 5560, 150, 930, 3),
        Region("crew", 560, 2300, 0, 1080, 0),
        Region("room", 1150, 2500, 0, 1080, -2),
        Region("cards", 6560, 7160, 20, 780, 0),
    )),
    Section("Behind the Scenes", "How it's built, wired and signalled", "IMG_7813.jpg", (
        Region("behind", 280, 660, 20, 560, 0),
        Region("behind", 2230, 2960, 0, 1080, 3),
        Region("signals", 1600, 2550, 0, 1080, 0),
        Region("wiring", 1350, 2750, 0, 1080, -3),
        Region("build", 5550, 6800, 0, 1080, 0),
        Region("panels", 5400, 6000, 380, 700, 2.5),
        Region("build", 4250, 5500, 0, 1080, 0),
    )),
    Section("The Diverging Route", "How AI helps build and run it", "IMG_9288.jpg", (
        Region("ai", 600, 2150, 0, 1080, 0),
        Region("speed-runs", 2600, 3450, 0, 1080, -3),
        Region("speed-runs", 6100, 6950, 0, 1080, 0),
        Region("ai-control", 0, 1650, 0, 1080, 3),
        Region("ai", 4300, 5450, 0, 1080, 0),
        Region("ai", 7150, 7700, 0, 1080, -2),
    )),
)


def find_chrome() -> str:
    """Google Chrome or Chromium on this machine; PromoError when there is neither."""
    for name in (CHROME, "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    raise PromoError("Google Chrome not found")


def capture_pages(out: Path, stems: set[str]) -> dict[str, Path]:
    """Phone-width captures of the live pages in PAGES, reusing files in out.

    Headless Chrome on macOS lays out no narrower than about 500 CSS px, so a
    390 px window clips the page; 500 px at 2.16x gives a clean 1080 px image.
    """
    out.mkdir(parents=True, exist_ok=True)
    shots = {}
    for path, stem in PAGES.items():
        if stem not in stems:
            continue
        shot = out / f"{stem}.png"
        if not shot.exists():
            with tempfile.TemporaryDirectory() as profile:  # never touch the owner's Chrome
                subprocess.run([find_chrome(), "--headless=new", "--disable-gpu",
                                "--hide-scrollbars", f"--user-data-dir={profile}",
                                "--virtual-time-budget=6000", "--force-device-scale-factor=2.16",
                                "--window-size=500,3600", f"--screenshot={shot}",
                                SITE_URL + path],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shots[stem] = shot
    return shots
