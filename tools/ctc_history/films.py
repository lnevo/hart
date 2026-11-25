#!/usr/bin/env python3
"""Build the panel evolution films in docs/ctc/history (docs/ctc/history/README.md).

    python3 tools/ctc_history/films.py ctc    CTC_Panel_Evolution.mp4 and .gif (film_ctc.py)
    python3 tools/ctc_history/films.py cats   CATS_Panel_Evolution.mp4 and cats-poster.jpg (film_cats.py)
    python3 tools/ctc_history/films.py le     LE_Panel_Evolution.mp4 and le-poster.jpg (film_le.py)

Each film takes its pace from tools/hartlib/src/hartlib/film_pace.py and needs Pillow and ffmpeg. The CATS film reads
media/screenshots (or HART_SCREENSHOTS); the other two read the screenshots in docs/ctc/history.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

FILMS = {
    "ctc": "film_ctc",
    "cats": "film_cats",
    "le": "film_le",
}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("film", choices=sorted(FILMS), help="which film to build")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    importlib.import_module(FILMS[args.film]).main()  # imported here, so --help needs neither Pillow nor ffmpeg
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
