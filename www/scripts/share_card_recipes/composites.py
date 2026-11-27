"""Share cards composed from, or cropped out of, pictures and documents already in the repo.

A recipe module of make_share_cards.py, which lists the cards (CARDS) and runs them."""

from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import make_share_cards as kit
from make_share_cards import H, PAPER, PORTAL, REPO, SOURCES, STS_URL, W
from share_card_recipes import CardError
from share_card_recipes.page_figures import _page_style

if TYPE_CHECKING:  # Pillow is imported inside each recipe, so --list runs without it
    from PIL import Image

Box = tuple[int, int, int, int]  # left, top, right, bottom in pixels, as PIL's crop takes it


class _Layer(NamedTuple):
    """One panel picture of behind-panel-evolution: the crop of the poster, its zoom over the card width, and the
    fraction cx of its width that stays at the same fraction of the card's width."""
    name: str
    box: Box
    zoom: float
    cx: float


PANEL_LAYERS = (_Layer("le-poster.jpg", (24, 14, 1258, 460), 1.42, 0.10),
                _Layer("cats-poster.jpg", (0, 22, 1280, 335), 1.45, 0.50),
                _Layer("uss-poster.jpg", (0, 62, 1200, 712), 1.0, 1.0))
PANEL_CUTS = ((470, 330), (870, 730))  # (x at top, x at bottom) of each diagonal between the layers
TRACK_PLAN_LEVELS = ("Staging", "Main level", "Upper level")  # the order of the plan figures on the page


# ---- Shared steps ------------------------------------------------------------------------------

def _quicklook(card: str, doc: Path) -> Image.Image:
    """The first page of DOC drawn 2400 px wide by macOS Quick Look (qlmanage), as an RGB image."""
    from PIL import Image

    try:
        subprocess.run(["qlmanage", "-t", "-s", "2400", "-o", str(kit._tmp), str(doc)], check=True, capture_output=True)
    except FileNotFoundError as exc:
        raise CardError(f"{card}: qlmanage not found; this card is drawn on macOS") from exc
    except subprocess.CalledProcessError as exc:
        raise CardError(f"{card}: qlmanage could not draw {doc}: {exc.stderr.decode(errors='replace').strip()}") from exc
    return Image.open(kit._tmp / (doc.name + ".png")).convert("RGB")


def _top_band(im: Image.Image, top: int, x0: int = 0, x1: int | None = None) -> Image.Image:
    """The card-shaped band of IM from row TOP down, between columns X0 and X1 (default: the full width)."""
    x1 = im.width if x1 is None else x1
    return im.crop((x0, top, x1, top + round((x1 - x0) * H / W)))


def _on_ground(im: Image.Image, ground: float | tuple[int, ...] | str | None, size: tuple[int, int], left: int) -> Image.Image:
    """IM pasted on a SIZE canvas of colour GROUND (a name, or a pixel as getpixel reads it), LEFT px from the left edge and centred top to bottom."""
    from PIL import Image

    out = Image.new("RGB", size, ground)
    out.paste(im, (left, (size[1] - im.height) // 2))
    return out


# ---- Composites and crops of pictures already in the repo -------------------------------------

def _panel_layer(layer: _Layer) -> Image.Image:
    """One poster crop, scaled to ZOOM card widths and placed on a card of its own top-left colour."""
    from PIL import Image

    crop = Image.open(PORTAL / "assets/behind/panel-evolution" / layer.name).convert("RGB").crop(layer.box)
    ground = crop.getpixel((6, 6))
    s = W / crop.width * layer.zoom
    crop = crop.resize((round(crop.width * s), round(crop.height * s)), Image.LANCZOS)
    out = Image.new("RGB", (W, H), ground)
    out.paste(crop, (round(W * layer.cx - crop.width * layer.cx), (H - crop.height) // 2))  # keep fraction cx in place
    return out


def panel_evolution() -> Image.Image:
    """behind-panel-evolution: diagonal slices of the Layout Editor, CATS and USS panels, west to east."""
    return kit._slices([_panel_layer(layer) for layer in PANEL_LAYERS], PANEL_CUTS)


def ai_construction() -> Image.Image:
    """ai-construction: the top of sheet 1 of the main level framing plan (macOS: uses qlmanage to render the PDF)."""
    im = _quicklook("ai-construction", REPO / "docs/benchwork/main_level/main_level_joist_construction.pdf")
    w, h = im.size
    return kit.card(_top_band(im, int(h * 0.02), int(w * 0.035), int(w * 0.965)))


def link_build_main_level() -> Image.Image:
    """link-build-main-level: the "Where the pieces go" drawings on the main level plywood cut plan (hub card for build/#main-level)."""
    im = kit.shot(kit._site + "build/files/main-level-plywood-cut-plan.html", (W, 2 * H))
    return kit.card(_top_band(im, round(im.height * 0.42)))  # the drawings sit just below the middle of the first two screens


def _title_canvas(name: str, rel: str) -> Image.Image:
    """Shoot the pixel-art title canvas (#xwTitleCv) of the game page REL so it fills the card, the rest of the page hidden under it."""
    page = (PORTAL / rel).read_text(encoding="utf-8")
    if "<head>" not in page or "</head>" not in page:  # without them the style and base are skipped and the wrong picture is written
        raise CardError(f"{name}: {rel} has no plain <head> ... </head>; fix the patch in _title_canvas")
    # the canvas fills the frame, cropped evenly at the sides so the whole title stays in
    fill = (f"<style>#xwTitleCv{{position:fixed!important;left:0!important;top:0!important;width:{W}px!important;height:{H}px!important;"
            "object-fit:cover;object-position:center;z-index:9999}</style>")
    out = kit._tmp / f"{name}.html"
    base = f'<base href="{(PORTAL / rel).parent.as_uri()}/">'  # the copy sits in a temp folder: load the scripts and CSS from www/
    out.write_text(page.replace("<head>", "<head>" + base, 1).replace("</head>", fill + "</head>", 1), encoding="utf-8")
    # with reduced motion the title art draws one still frame, the train standing mid-picture
    return kit.card(kit.shot(out.as_uri(), flags=("--force-prefers-reduced-motion",)))


def link_exam_run_title() -> Image.Image:
    """link-exam-run-title: the game's own pixel-art title screen with the train standing in it, the canvas at the top of Extra East (hub card for exam/run.html#xw)."""
    return _title_canvas("link-exam-run-title", "exam/run.html")


def link_play_title() -> Image.Image:
    """link-play-title: the pixel-art title screen of Extra East: HART Railroad, the canvas at the top of play/ (hub card for play/index.html)."""
    return _title_canvas("link-play-title", "play/index.html")


def _plan_figures(text: str) -> str:
    """The three level drawings of the track plan page TEXT as figures 440 px tall, captioned, the scale bar dropped."""
    figs = re.findall(r'<div class="plan"><svg viewBox="([^"]+)" role="img" aria-label="([^"]+)">(.*?)</svg></div>', text, re.S)
    if len(figs) != len(TRACK_PLAN_LEVELS):
        raise CardError(f"build-track-plan: build/track-plan.html has {len(figs)} plan drawings, the card captions "
                        f"{len(TRACK_PLAN_LEVELS)}; fix TRACK_PLAN_LEVELS or the pattern in _plan_figures")
    parts = []
    for (vb, _label, inner), name in zip(figs, TRACK_PLAN_LEVELS):
        inner = re.sub(r'<line class="scale".*$', "", inner, flags=re.S)  # the 100 cm bar is too small to read at card size
        _x, _y, vw, vh = map(float, vb.split())
        parts.append(f'<figure><svg viewBox="{vb}" style="width:{vw / vh * 440:.0f}px">{inner}</svg><figcaption>{name}</figcaption></figure>')
    return "".join(parts)


def build_track_plan() -> Image.Image:
    """build-track-plan: the three level drawings of the track plan article side by side, the helix ramps dotted in orange."""
    page = "build/track-plan.html"
    text = (PORTAL / page).read_text(encoding="utf-8")
    if "</style>" not in text:  # the drawings take their track colours from the page's own style
        raise CardError(f"build-track-plan: {page} has no <style>; the drawings would lose their colours")
    style = (_page_style(page) + "svg text{display:none}body{background:" + PAPER + ";display:flex;justify-content:center;gap:40px;"
             "align-items:center;box-sizing:border-box;padding:0 30px}figure{margin:0;text-align:center}"
             "svg{height:440px;display:block}figure{flex:none}"
             "figcaption{font:700 40px var(--font-display);letter-spacing:.04em;color:var(--brand);margin-top:16px}")
    return kit.card(kit.draw("track-plan", _plan_figures(text), style))


def ai_operations() -> Image.Image:
    """ai-operations: the weighed car on the STS Track Scale, from the owner's screenshot."""
    from PIL import Image

    im = Image.open(SOURCES / "track-scale-weighed.png").convert("RGB")
    return kit.card(_top_band(im, round(78 * im.width / 1085)))  # below the green title bar


def sts_home() -> Image.Image:
    """library-sts-operations-article: the STS main menu. Needs STS running locally."""
    return kit.card(kit.shot(STS_URL))


def _clipboard(box: Box) -> Image.Image:
    """A crop of the clipboards photo (assets/behind/sts/crew-sheets.jpg, 1600 x 1200)."""
    from PIL import Image

    return kit.card(Image.open(PORTAL / "assets/behind/sts/crew-sheets.jpg").convert("RGB").crop(box))


def crew_nvl() -> Image.Image:
    """crew-nvl: the NVL Neville Island Local clipboard."""
    return _clipboard((605, 470, 1165, 764))


def crew_dispatcher() -> Image.Image:
    """crew-dispatcher: all the crew clipboards laid out along the layout edge (also used by CK1 and D749)."""
    return _clipboard((60, 150, 1540, 927))


def _swap_first_slides(doc: Path, copy: Path) -> None:
    """Write COPY: the deck DOC with its first two slides in the other order, so Quick Look draws the second."""
    with zipfile.ZipFile(doc) as src, zipfile.ZipFile(copy, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "ppt/presentation.xml":
                text = data.decode("utf-8")
                slides = re.findall(r"<p:sldId [^>]*/>", text)
                if len(slides) < 2 or slides[0] + slides[1] not in text:  # the swap below would leave the deck as it is
                    raise CardError(f"crew-tt23: {doc.name} has no first two slides side by side in "
                                    f"ppt/presentation.xml ({len(slides)} slide ids); fix _swap_first_slides")
                data = text.replace(slides[0] + slides[1], slides[1] + slides[0]).encode("utf-8")
            out.writestr(item, data)


def tt23() -> Image.Image:
    """crew-tt23: the timetable page of the Route 23 employee timetable (macOS: uses qlmanage, which
    draws only a document's first page, so a scratch copy with the two pages swapped is rendered)."""
    copy = kit._tmp / "tt23-page2.pptx"
    _swap_first_slides(REPO / "docs/ops/TT-23_Route23_NevilleQueen_RevisionB.pptx", copy)
    im = _quicklook("crew-tt23", copy)
    return kit.card(_top_band(im, round(im.width * 30 / 2400)))


def station_maps() -> Image.Image:
    """crew-maps: the full station map, whole, on white (used by the station maps index
    and every map page). The source is a copy of ops/hart-ops/publications/assets/station_map_full.png;
    copy it again to refresh."""
    from PIL import Image

    im = Image.open(SOURCES / "station-map-full.png").convert("RGB")
    w = W - 24
    return _on_ground(im.resize((w, round(im.height * w / im.width)), Image.LANCZOS), "white", (W, H), 12)


def _crop_drawing(im: Image.Image, window: Box, src: Path | str, pad: int = 24, edge: int = 8) -> Image.Image:
    """The drawing inside WINDOW (left, top, right, bottom) of IM, trimmed to its ink plus PAD.

    The window is set by hand against a generated sheet, so it stops (CardError) when the sheet has moved:
    ink within EDGE pixels of the window's top or bottom means a heading or bracket has leaked in or the
    drawing is cut off. Nothing is published from a crop that fails."""
    from PIL import Image, ImageChops

    inner = im.crop(window)
    ink = ImageChops.difference(inner, Image.new("RGB", inner.size, "white")).convert("L").point(
        lambda v: 255 if v > 40 else 0)
    box = ink.getbbox()
    if box is None:
        raise CardError(f"{src}: rendered blank")
    if box[1] < edge or box[3] > inner.height - edge:
        raise CardError(f"{src}: drawing touches the crop window's top or bottom edge; the sheet has moved, "
                        f"re-measure the window")
    return inner.crop((max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, inner.width),
                       min(box[3] + pad, inner.height)))      # clamped: PIL pads past the edge with black


def station_map_east_end() -> Image.Image:
    """crew-maps-east-end: the track drawing of the generated East End station sheet
    (docs/ops/stations/east-end.svg), on white (used by the station maps index and the live map pages; the
    archive keeps crew-maps)."""
    from PIL import Image

    src = REPO / "docs/ops/stations/east-end.svg"
    im = kit.shot(src.as_uri(), (1056, 816))            # the sheet's own size (its viewBox), at 2x
    # The track drawing only: below the STAGING LEVEL heading, above the EAST END bracket and the title block,
    # inside the border (sheet units 1056 x 816, rendered at 2x).
    im = _crop_drawing(im, (60, 2 * 215, im.width - 60, 2 * 580), src)
    scale = min((W - 48) / im.width, (H - 48) / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    return _on_ground(im, "white", (W, H), (W - im.width) // 2)


def _dashboard(page: str, grid_box: Box) -> Image.Image:
    """The card rows of an Achievement Program dashboard: GRID_BOX of PAGE shot at 1400 x 1100 (device px, x2),
    on the page background beside the grid."""
    im = kit.shot(f"{kit._site}{page}", (1400, 1100))
    grid = im.crop(grid_box)
    w = grid.width + 80
    return kit.card(_on_ground(grid, im.getpixel((300, 1300)), (w, round(w * H / W)), 40))


def ai_mmr() -> Image.Image:
    """ai-mmr: the twelve-certificate dashboard on the NMRA Achievement Program page, on the page background."""
    return _dashboard("ap/index.html", (464, 975, 2338, 1835))  # the three card rows; recheck if the dashboard changes


def ap_opsig() -> Image.Image:
    """ap-opsig: the Toward Ninja dashboard on the OPSIG Achievement Program page, on the page background."""
    return _dashboard("ap/opsig.html", (464, 910, 2338, 1760))  # the three card rows; recheck if the dashboard changes
