#!/usr/bin/env python3
"""Per-page share thumbnails (the image a link preview shows), 1200 x 630 JPEG.

A page named in share-cards.json gets its own picture in the Open Graph tags the build adds;
every other page keeps the site card (assets/icons/share-card.jpg). Pages in Operations,
Behind the Scenes and The Diverging Route are expected to have one, about the page's own
subject rather than its section. Paperwork pages and hubs without a subject picture share the
Operations card ("shared": true), by the owner's choice.

The build also shows these pictures on hub cards: in a card grid marked data-card-thumbs,
each card linking to a page with its own picture gets a small copy on top, unless that picture
would appear twice in the grid.

  share_cards.py make SOURCE assets/share/NAME.jpg [--focus X,Y] [--zoom Z]   crop a picture to a card
  share_cards.py check                                                        list gaps and faults
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
CARDS = PORTAL / "scripts" / "share-cards.json"
SIZE = (1200, 630)
DEFAULT = {"image": "assets/icons/share-card.jpg", "alt": "Neville Island from above"}
# Sections whose pages should each carry their own card (site.json nav ids).
SECTIONS = ("operators", "behind", "ai")
# Folders whose pages do not name a page id in their own HTML (a script mounts the header).
FOLDER_SECTION = {"crew": "operators", "layout": "operators", "roster": "behind"}
# Pages the owner has said keep the site card.
NO_CARD_PAGES: set[str] = set()
_PAGE_ID = re.compile(r'data-page="([^"]+)"|mountChrome\("([^"{]+)"\)')
_TITLE = re.compile(r"<title>(.*?)</title>", re.S)


def load(path: Path = CARDS) -> dict[str, dict]:
    """Cards by site-relative page path ("guides/cats-ctc.html")."""
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("cards") or {}


def card_for(rel: Path | str, cards: dict[str, dict] | None = None) -> dict:
    """The card for a page: its own entry, or the site card."""
    cards = load() if cards is None else cards
    return cards.get(Path(rel).as_posix()) or DEFAULT


def section_of(rel: Path, text: str, site: dict) -> str | None:
    """The nav section id a page belongs to, from its page id or, failing that, its folder."""
    m = _PAGE_ID.search(text)
    page_id = (m.group(1) or m.group(2)) if m else None
    for item in site.get("nav") or []:
        if page_id in (item.get("pages") or [item["id"]]):
            return item["id"]
    return FOLDER_SECTION.get(rel.parts[0]) if len(rel.parts) > 1 else None


def _is_stub(text: str) -> bool:
    """Redirect pages ("Moved — …") and pages without a title are not shared."""
    m = _TITLE.search(text)
    return not m or "moved" in m.group(1).lower() or 'http-equiv="refresh"' in text.lower()


def expected_pages(pages: list[Path], portal: Path = PORTAL) -> list[Path]:
    """Published pages in SECTIONS that should have their own card."""
    site = json.loads((portal / "data" / "site.json").read_text(encoding="utf-8"))
    out = []
    for rel in pages:
        if rel.suffix != ".html" or "files" in rel.parts or rel.parts[:2] == ("docs", "html") or rel.as_posix() in NO_CARD_PAGES:
            continue
        text = (portal / rel).read_text(encoding="utf-8", errors="replace")
        if not _is_stub(text) and section_of(rel, text, site) in SECTIONS:
            out.append(rel)
    return out


THUMB_DIR = "assets/share/thumbs"
THUMB_PX = 560  # long side; the card shows it at about 260 px wide, so this covers 2x screens
_GRID = re.compile(r"<div\b[^>]*\bdata-card-thumbs\b[^>]*>")
_DIV = re.compile(r"<(/?)div\b[^>]*>")
_CARD = re.compile(r'<a class="card"( href="([^"#?]+)")>')


def card_target(page: Path | str, href: str) -> str | None:
    """The site-relative page a card links to ("ai/research.html"), or None for links off the site."""
    if href.startswith(("http:", "https:", "mailto:", "/")):
        return None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(Path(page).as_posix()), href))
    if target.startswith("../"):
        return None
    if href.endswith("/") or target == ".":
        target = posixpath.join("" if target == "." else target, "index.html")
    return target


def add_card_thumbs(text: str, page: Path | str, cards: dict[str, dict] | None = None) -> tuple[str, dict[str, str]]:
    """Put the linked page's share picture at the top of each card in a grid marked data-card-thumbs.

    Returns (new text, {thumb path: share image path}) so the build can write the small copies.
    Cards whose page has no picture of its own stay text-only, and so do cards whose picture would
    appear twice in the grid (pages marked "shared" in share-cards.json).
    """
    cards = load() if cards is None else cards
    thumbs: dict[str, str] = {}
    out, pos = [], 0
    for grid in _GRID.finditer(text):
        if grid.start() < pos:
            continue
        depth, end = 1, len(text)  # find the grid's closing </div>
        for d in _DIV.finditer(text, grid.end()):
            depth += -1 if d.group(1) else 1
            if depth == 0:
                end = d.start()
                break

        body = text[grid.end() : end]
        images = {m.start(): (cards.get(card_target(page, m.group(2)) or "") or {}).get("image") for m in _CARD.finditer(body)}
        repeated = {i for i in images.values() if i and list(images.values()).count(i) > 1}

        def add(m: re.Match) -> str:
            image = images.get(m.start())
            if not image or image in repeated:
                return m.group(0)
            thumb = f"{THUMB_DIR}/{Path(image).stem}.jpg"
            thumbs[thumb] = image
            up = "../" * (len(Path(page).parts) - 1)
            return f'<a class="card has-thumb"{m.group(1)}><img class="card-thumb" src="{up}{thumb}" alt="" loading="lazy">'

        out.append(text[pos : grid.end()])
        out.append(_CARD.sub(add, body))
        pos = end
    out.append(text[pos:])
    return "".join(out), thumbs


def _image_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    with Image.open(path) as im:
        return im.size


def review(pages: list[Path], cards: dict[str, dict], portal: Path = PORTAL) -> tuple[list[str], list[str]]:
    """(pages that still show the site card, faults in the cards that exist)."""
    missing = [p.as_posix() for p in expected_pages(pages, portal) if p.as_posix() not in cards]
    faults, seen_image, seen_from = [], {}, {}
    for page, card in cards.items():
        image, alt = card.get("image", ""), card.get("alt", "")
        if not (portal / page).is_file():
            faults.append(f"{page}: no such page")
        if not alt.strip():
            faults.append(f"{page}: no alt text")
        path = portal / image
        if not image.startswith("assets/share/") or not path.is_file():
            faults.append(f"{page}: image {image or '(none)'} is not a file under assets/share/")
        elif (size := _image_size(path)) not in (None, SIZE):
            faults.append(f"{page}: {image} is {size[0]} x {size[1]}, not {SIZE[0]} x {SIZE[1]}")
        for seen, value, what in ((seen_image, image, "image"), (seen_from, card.get("from", ""), "source picture")):
            if value and value in seen and not card.get("shared"):  # "shared": the owner chose one picture for several pages
                faults.append(f"{page}: same {what} as {seen[value]} ({value})")
            seen.setdefault(value, page)
    return missing, faults


def tracked_pages(portal: Path = PORTAL) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(portal), "ls-files", "-z", "--", "*.html"], check=True, capture_output=True
    ).stdout.decode("utf-8")
    import prepare_github_pages as build  # the build's own list of what stays off the site

    pages = [Path(n) for n in filter(None, out.split("\0"))]
    return [p for p in pages if p not in build.SKIP_FILES and not any(d in p.parents for d in build.SKIP_DIRS)]


def report(portal: Path = PORTAL) -> int:
    """Print gaps (a suggestion) and faults (an error). Returns 1 only for faults."""
    cards = load(portal / "scripts" / "share-cards.json")
    missing, faults = review(tracked_pages(portal), cards, portal)
    if missing:
        print(f"Share thumbnails: {len(missing)} page(s) still show the site card. Suggest one for each:")
        print("\n".join("  " + m for m in missing))
    else:
        print(f"Share thumbnails OK: {len(cards)} page card(s), none missing.")
    if faults:
        print(f"{len(faults)} share thumbnail fault(s):", file=sys.stderr)
        print("\n".join("  " + f for f in faults), file=sys.stderr)
    return 1 if faults else 0


def make(source: Path, dest: Path, focus: tuple[float, float] = (50, 50), zoom: float = 1.0) -> None:
    """Crop SOURCE to the card shape around FOCUS (percent from left, top) and save a JPEG."""
    from PIL import Image, ImageOps

    with Image.open(source) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):  # flatten transparency onto white
            im = im.convert("RGBA")
            flat = Image.new("RGB", im.size, "white")
            flat.paste(im, mask=im.getchannel("A"))
            im = flat
        im = im.convert("RGB")
        ratio = SIZE[0] / SIZE[1]
        w, h = im.size
        cw, ch = (w, w / ratio) if w / h < ratio else (h * ratio, h)
        cw, ch = cw / max(zoom, 1.0), ch / max(zoom, 1.0)
        left = min(max(w * focus[0] / 100 - cw / 2, 0), w - cw)
        top = min(max(h * focus[1] / 100 - ch / 2, 0), h - ch)
        card = im.crop((round(left), round(top), round(left + cw), round(top + ch))).resize(SIZE, Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    card.save(dest, "JPEG", quality=84, optimize=True, progressive=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="crop a picture to a 1200 x 630 card")
    m.add_argument("source", type=Path)
    m.add_argument("dest", type=Path, help="site-relative, e.g. assets/share/cats-ctc.jpg")
    m.add_argument("--focus", default="50,50", help="centre of the crop, percent from left,top (default %(default)s)")
    m.add_argument("--zoom", type=float, default=1.0, help="crop tighter than the widest fit (default %(default)s)")
    sub.add_parser("check", help="list pages without a card and faults in the cards")
    args = parser.parse_args()
    if args.cmd == "check":
        return report()
    x, y = (float(v) for v in args.focus.split(","))
    dest = args.dest if args.dest.is_absolute() else PORTAL / args.dest
    make(args.source, dest, (x, y), args.zoom)
    print(f"Wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
