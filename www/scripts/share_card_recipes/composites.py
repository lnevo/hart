"""Share cards composed from, or cropped out of, pictures and documents already in the repo.

A recipe module of make_share_cards.py, which lists the cards (CARDS) and runs them."""

from __future__ import annotations

import re
import subprocess

import make_share_cards as kit
from make_share_cards import H, PAPER, PORTAL, REPO, SOURCES, STS_URL, W
from share_card_recipes.page_figures import _page_style


# ---- Composites and crops of pictures already in the repo -------------------------------------

def panel_evolution():
    """behind-panel-evolution: diagonal slices of the Layout Editor, CATS and USS panels, west to east."""
    from PIL import Image

    def layer(name, box, zoom, cx):
        crop = Image.open(PORTAL / "assets/behind/panel-evolution" / name).convert("RGB").crop(box)
        ground = crop.getpixel((6, 6))
        s = W / crop.width * zoom
        crop = crop.resize((round(crop.width * s), round(crop.height * s)), Image.LANCZOS)
        out = Image.new("RGB", (W, H), ground)
        out.paste(crop, (round(W * cx - crop.width * cx), (H - crop.height) // 2))  # keep fraction cx in place
        return out

    layers = [layer("le-poster.jpg", (24, 14, 1258, 460), 1.42, 0.10),
              layer("cats-poster.jpg", (0, 22, 1280, 335), 1.45, 0.50),
              layer("uss-poster.jpg", (0, 62, 1200, 712), 1.0, 1.0)]
    return kit._slices(layers, [(470, 330), (870, 730)])


def ai_construction():
    """ai-construction: the top of sheet 1 of the main level framing plan (macOS: uses qlmanage to render the PDF)."""
    from PIL import Image

    pdf = REPO / "docs/benchwork/main_level/main_level_joist_construction.pdf"
    subprocess.run(["qlmanage", "-t", "-s", "2400", "-o", str(kit._tmp), str(pdf)], check=True, capture_output=True)
    im = Image.open(kit._tmp / (pdf.name + ".png")).convert("RGB")
    w, h = im.size
    x0, x1, y0 = int(w * 0.035), int(w * 0.965), int(h * 0.02)
    return kit.card(im.crop((x0, y0, x1, y0 + round((x1 - x0) * H / W))))


def link_build_main_level():
    """link-build-main-level: the "Where the pieces go" drawings on the main level plywood cut plan (hub card for build/#main-level)."""
    im = kit.shot(kit._site + "build/files/main-level-plywood-cut-plan.html", (W, 2 * H))
    w, h = im.size
    ch = round(w * H / W)
    top = round(h * 0.42)  # the drawings sit just below the middle of the first two screens
    return kit.card(im.crop((0, top, w, top + ch)))


def _title_canvas(name: str, rel: str):
    """Shoot the pixel-art title canvas (#xwTitleCv) of the game page REL so it fills the card, the rest of the page hidden under it."""
    page = (PORTAL / rel).read_text(encoding="utf-8")
    if "<head>" not in page or "</head>" not in page:  # without them the style and base are skipped and the wrong picture is written
        raise SystemExit(f"{name}: {rel} has no plain <head> ... </head>; fix the patch in _title_canvas")
    # the canvas fills the frame, cropped evenly at the sides so the whole title stays in
    fill = (f"<style>#xwTitleCv{{position:fixed!important;left:0!important;top:0!important;width:{W}px!important;height:{H}px!important;"
            "object-fit:cover;object-position:center;z-index:9999}</style>")
    out = kit._tmp / f"{name}.html"
    base = f'<base href="{(PORTAL / rel).parent.as_uri()}/">'  # the copy sits in a temp folder: load the scripts and CSS from www/
    out.write_text(page.replace("<head>", "<head>" + base, 1).replace("</head>", fill + "</head>", 1), encoding="utf-8")
    # with reduced motion the title art draws one still frame, the train standing mid-picture
    return kit.card(kit.shot(out.as_uri(), flags=("--force-prefers-reduced-motion",)))


def link_exam_run_title():
    """link-exam-run-title: the game's own pixel-art title screen with the train standing in it, the canvas at the top of Extra East (hub card for exam/run.html#xw)."""
    return _title_canvas("link-exam-run-title", "exam/run.html")


def link_play_title():
    """link-play-title: the pixel-art title screen of Extra East: HART Railroad, the canvas at the top of play/ (hub card for play/index.html)."""
    return _title_canvas("link-play-title", "play/index.html")


def build_track_plan():
    """build-track-plan: the three level drawings of the track plan article side by side, the helix ramps dotted in orange."""
    text = (PORTAL / "build/track-plan.html").read_text(encoding="utf-8")
    figs = re.findall(r'<div class="plan"><svg viewBox="([^"]+)" role="img" aria-label="([^"]+)">(.*?)</svg></div>', text, re.S)
    css = re.search(r"</style>", text) and _page_style("build/track-plan.html")
    parts = []
    for (vb, _label, inner), name in zip(figs, ("Staging", "Main level", "Upper level")):
        inner = re.sub(r'<line class="scale".*$', "", inner, flags=re.S)  # the 100 cm bar is too small to read at card size
        _x, _y, vw, vh = map(float, vb.split())
        parts.append(f'<figure><svg viewBox="{vb}" style="width:{vw / vh * 440:.0f}px">{inner}</svg><figcaption>{name}</figcaption></figure>')
    style = (css + "svg text{display:none}body{background:" + PAPER + ";display:flex;justify-content:center;gap:40px;"
             "align-items:center;box-sizing:border-box;padding:0 30px}figure{margin:0;text-align:center}"
             "svg{height:440px;display:block}figure{flex:none}"
             "figcaption{font:700 40px var(--font-display);letter-spacing:.04em;color:var(--brand);margin-top:16px}")
    return kit.card(kit.draw("track-plan", "".join(parts), style))


def ai_operations():
    """ai-operations: the weighed car on the STS Track Scale, from the owner's screenshot."""
    from PIL import Image

    im = Image.open(SOURCES / "track-scale-weighed.png").convert("RGB")
    w = im.width
    y0 = round(78 * w / 1085)  # below the green title bar
    return kit.card(im.crop((0, y0, w, y0 + round(w * H / W))))


def sts_home():
    """library-sts-operations-article: the STS main menu. Needs STS running locally."""
    return kit.card(kit.shot(STS_URL))


def _clipboard(box):
    """A crop of the clipboards photo (assets/behind/sts/crew-sheets.jpg, 1600 x 1200)."""
    from PIL import Image

    return kit.card(Image.open(PORTAL / "assets/behind/sts/crew-sheets.jpg").convert("RGB").crop(box))


def crew_nvl():
    """crew-nvl: the NVL Neville Island Local clipboard."""
    return _clipboard((605, 470, 1165, 764))


def crew_dispatcher():
    """crew-dispatcher: all the crew clipboards laid out along the layout edge (also used by CK1 and D749)."""
    return _clipboard((60, 150, 1540, 927))


def tt23():
    """crew-tt23: the timetable page of the Route 23 employee timetable (macOS: uses qlmanage, which
    draws only a document's first page, so a scratch copy with the two pages swapped is rendered)."""
    import zipfile
    from PIL import Image

    doc = REPO / "docs/ops/TT-23_Route23_NevilleQueen_RevisionB.pptx"
    copy = kit._tmp / "tt23-page2.pptx"
    with zipfile.ZipFile(doc) as src, zipfile.ZipFile(copy, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "ppt/presentation.xml":
                text = data.decode("utf-8")
                first, second = re.findall(r"<p:sldId [^>]*/>", text)[:2]
                data = text.replace(first + second, second + first).encode("utf-8")
            out.writestr(item, data)
    subprocess.run(["qlmanage", "-t", "-s", "2400", "-o", str(kit._tmp), str(copy)], check=True, capture_output=True)
    im = Image.open(kit._tmp / (copy.name + ".png")).convert("RGB")
    top = round(im.width * 30 / 2400)
    return kit.card(im.crop((0, top, im.width, top + round(im.width * H / W))))


def station_maps():
    """crew-maps: the full station map, whole, on white (used by the station maps index
    and every map page). The source is a copy of ops/hart-ops/publications/assets/station_map_full.png;
    copy it again to refresh."""
    from PIL import Image

    im = Image.open(SOURCES / "station-map-full.png").convert("RGB")
    w = W - 24
    h = round(im.height * w / im.width)
    out = Image.new("RGB", (W, H), "white")
    out.paste(im.resize((w, h), Image.LANCZOS), (12, (H - h) // 2))
    return out


def _crop_drawing(im, window, src, pad=24, edge=8):
    """The drawing inside WINDOW (left, top, right, bottom) of IM, trimmed to its ink plus PAD.

    The window is set by hand against a generated sheet, so it stops (SystemExit) when the sheet has moved:
    ink within EDGE pixels of the window's top or bottom means a heading or bracket has leaked in or the
    drawing is cut off. Nothing is published from a crop that fails."""
    from PIL import Image, ImageChops

    inner = im.crop(window)
    ink = ImageChops.difference(inner, Image.new("RGB", inner.size, "white")).convert("L").point(
        lambda v: 255 if v > 40 else 0)
    box = ink.getbbox()
    if box is None:
        raise SystemExit(f"{src}: rendered blank")
    if box[1] < edge or box[3] > inner.height - edge:
        raise SystemExit(f"{src}: drawing touches the crop window's top or bottom edge; the sheet has moved, "
                         f"re-measure the window")
    return inner.crop((max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, inner.width),
                       min(box[3] + pad, inner.height)))      # clamped: PIL pads past the edge with black


def station_map_east_end():
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
    out = Image.new("RGB", (W, H), "white")
    out.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
    return out


def ai_mmr():
    """ai-mmr: the twelve-certificate dashboard on the NMRA Achievement Program page, on the page background."""
    from PIL import Image

    im = kit.shot(f"{kit._site}ap/index.html", (1400, 1100))
    grid = im.crop((464, 975, 2338, 1835))  # the three card rows (device px, x2); recheck the crop if the dashboard changes
    w, h = grid.size[0] + 80, round((grid.size[0] + 80) * H / W)
    out = Image.new("RGB", (w, h), im.getpixel((300, 1300)))  # the page background beside the grid
    out.paste(grid, (40, (h - grid.size[1]) // 2))
    return kit.card(out)


def ap_opsig():
    """ap-opsig: the Toward Ninja dashboard on the OPSIG Achievement Program page, on the page background."""
    from PIL import Image

    im = kit.shot(f"{kit._site}ap/opsig.html", (1400, 1100))
    grid = im.crop((464, 910, 2338, 1760))  # the three card rows (device px, x2); recheck the crop if the dashboard changes
    w, h = grid.size[0] + 80, round((grid.size[0] + 80) * H / W)
    out = Image.new("RGB", (w, h), im.getpixel((300, 1300)))  # the page background beside the grid
    out.paste(grid, (40, (h - grid.size[1]) // 2))
    return kit.card(out)
