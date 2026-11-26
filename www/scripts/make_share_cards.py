#!/usr/bin/env python3
"""Rebuild the share thumbnails that are drawn or composed, not plain photo crops.

Plain crops are made with `share_cards.py make`. The cards here are drawings, page
snapshots and composites. Each recipe is one function in share_card_recipes/, the whole recipe for one card;
CARDS below names them in the order they run, and this file keeps what they share (the page server, Chrome
shots, the card size).

  make_share_cards.py --list                 names and what each needs
  make_share_cards.py [NAME ...] [--out DIR]  rebuild some or all (default: all, into assets/share/)

Needs Pillow and Google Chrome (headless). Pages are served from this checkout, so the
site's own styles and fonts are used. Some cards read a picture captured or copied from
elsewhere, kept in share-card-sources/:
  station-map-full.png     a copy of ops/hart-ops/publications/assets/station_map_full.png
  panel-frame.png          the HART Railroad panel from JMRI's web server
                           (GET http://<jmri host>:12080/frame/HART%20Railroad.png)
  track-scale-weighed.png  the owner's screenshot of the STS Track Scale after a weigh
Replace those files to refresh the cards that use them. `sts-home` needs STS running locally.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import unquote, urlsplit

PORTAL = Path(__file__).resolve().parents[1]
REPO = PORTAL.parent
SOURCES = Path(__file__).resolve().parent / "share-card-sources"
W, H = 1200, 630
PUBLISHED = json.loads((PORTAL / "scripts/published-files.json").read_text(encoding="utf-8"))
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
STS_URL = "http://localhost:8980/sts/"  # the Mac working copy, never the live Pi
PAPER = "linear-gradient(180deg,#edf2f5,var(--paper) 45%,var(--paper-2))"

_site = ""  # http://127.0.0.1:<port>/ while serving()
_tmp = Path()
sys.path.insert(0, str(PORTAL / "scripts"))
import site_views  # noqa: E402  (the files the site build makes instead of committing, ADR-036)

_views: dict[str, str] = {}  # site path -> the copy this run built; a view that did not build is in _view_errors
_view_errors: list[str] = []
_view_lock = threading.Lock()


def _view(rel: str) -> str:
    """Where this run serves view `rel` from: built once into the scratch folder, as the site build makes it (ADR-036),
    so a page never reads a missing or stale www/ copy. One that cannot be built is a 404 and an error in shot()."""
    with _view_lock:
        if rel not in _views:
            _views[rel] = str(_tmp / "views" / rel)
            try:
                site_views.write(Path(_views[rel]), site_views.build(rel))
            except site_views.ViewError as err:
                _view_errors.append(str(err))
        return _views[rel]


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def translate_path(self, path: str) -> str:
        """Serve published files from their one source, as serve_portal.py does, and the gitignored
        car-card photos a page names as ../ops/car-cards/ from the checkout's mirror."""
        rel = unquote(urlsplit(path).path).removeprefix("/www/")
        if rel in site_views.VIEWS:
            return _view(rel)
        if source := PUBLISHED.get(rel):
            return str(REPO / source)
        if rel.startswith("ops/car-cards/"):
            target = (REPO / rel).resolve()
            if target.is_relative_to((REPO / "ops/car-cards").resolve()):
                return str(target)
        return super().translate_path(path)


@contextlib.contextmanager
def serving():
    """Serve the repo on a free port (pages reach logos in ../external/) and give drawings a scratch folder."""
    global _site, _tmp
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(REPO)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        _site, _tmp = f"http://127.0.0.1:{server.server_address[1]}/www/", Path(tmp)
        _views.clear(), _view_errors.clear()  # the views of an earlier serving() went with its scratch folder
        try:
            yield
        finally:
            server.shutdown()


class ShareCardError(Exception):
    """A card cannot be drawn (no Chrome, or a page view that does not build); the message says which."""


def _chrome() -> str:
    for name in (MAC_CHROME, "google-chrome", "chromium"):
        if found := shutil.which(name):
            return found
    raise ShareCardError("Google Chrome not found")


def shot(url: str, size: tuple[int, int] = (W, H), scale: int = 2, flags: tuple[str, ...] = ()):
    """A headless Chrome screenshot of URL as a Pillow image, `scale` device pixels per CSS pixel; `flags` go to Chrome."""
    from PIL import Image

    out = _tmp / f"shot-{abs(hash((url, size, scale, flags)))}.png"
    subprocess.run(
        [_chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
         f"--force-device-scale-factor={scale}", f"--window-size={size[0]},{size[1]}",
         "--virtual-time-budget=8000", *flags, f"--screenshot={out}", url],
        check=True, capture_output=True,
    )
    if _view_errors:  # the page read a view that did not build: its picture shows the load error
        raise ShareCardError(f"{url}: a file the page reads does not build:\n" + "\n".join(_view_errors))
    return Image.open(out).convert("RGB")


def draw(name: str, body: str, style: str, sheets: tuple[str, ...] = ("css/ops.css",)):
    """Render an HTML body at card size with the site's stylesheets, and return the image."""
    links = "".join(f'<link rel=stylesheet href="{_site}{s}">' for s in sheets)
    page = _tmp / f"{name}.html"
    page.write_text(
        f"<!doctype html><meta charset=utf-8>{links}<style>html,body{{margin:0;width:{W}px;height:{H}px;"
        f"overflow:hidden}}{style}</style>{body}",
        encoding="utf-8",
    )
    return shot(page.as_uri())


def card(im):
    """Any image, scaled to the card size."""
    from PIL import Image

    return im.convert("RGB").resize((W, H), Image.LANCZOS)


def _published(rel: str) -> Path:
    """A site file on disk: in www/, or where published-files.json says its one source is."""
    source = PUBLISHED.get(rel)
    return REPO / source if source else PORTAL / rel


def _svg(page: str, cls: str) -> str:
    text = (PORTAL / page).read_text(encoding="utf-8")
    return re.search(rf'<svg class="{cls}".*?</svg>', text, re.S).group(0)


def _slices(layers, cuts, line=7):
    """Lay images side by side, cut on diagonals. cuts: (x at top, x at bottom) per boundary."""
    from PIL import Image, ImageDraw

    ss = 2
    out = layers[0].copy()
    edges = [(0, 0)] + list(cuts) + [(W, W)]
    for i, layer in enumerate(layers[1:], start=1):
        (t0, b0), (t1, b1) = edges[i], edges[i + 1]
        mask = Image.new("L", (W * ss, H * ss), 0)
        ImageDraw.Draw(mask).polygon([(x * ss, y * ss) for x, y in ((t0, 0), (t1, 0), (b1, H), (b0, H))], fill=255)
        out.paste(layer, (0, 0), mask.resize((W, H), Image.LANCZOS))
    big = out.resize((W * ss, H * ss), Image.LANCZOS)
    pen = ImageDraw.Draw(big)
    for top, bottom in cuts:
        pen.line([(top * ss, -10), (bottom * ss, H * ss + 10)], fill=(243, 246, 248), width=line * ss)
    return big.resize((W, H), Image.LANCZOS)


# The recipes call the helpers above through this module (kit.shot, kit._tmp), at run time. Run as a script, this
# file is __main__: register it under its own name first, so they get this copy and not a second one whose
# serving() never ran.
sys.modules.setdefault("make_share_cards", sys.modules[__name__])
# The drawing helpers the tests call (_jfn_svg, _highlight, _crop_drawing) are re-exported here with the recipes.
from share_card_recipes.composites import (  # noqa: E402
    _crop_drawing, ai_construction, ai_mmr, ai_operations, ap_opsig, build_track_plan, crew_dispatcher, crew_nvl,  # noqa: F401
    link_build_main_level, link_exam_run_title, link_play_title, panel_evolution, station_map_east_end, station_maps,
    sts_home, tt23,
)
from share_card_recipes.editor_view import _highlight, ai_electronics  # noqa: E402,F401
from share_card_recipes.forms import ap_exam, ap_exam_run, play_neville  # noqa: E402
from share_card_recipes.opspro import _jfn_svg, opspro_article, opspro_walkthrough  # noqa: E402,F401
from share_card_recipes.page_figures import (  # noqa: E402
    ai_locomotives, build_story, coraopolis_record, pipeline_map, plants, railroads, repo_guide, speed_runs,
    wiring_node,
)
from share_card_recipes.panel_image import jmri_additions, roster  # noqa: E402
from share_card_recipes import CardError  # noqa: E402


CARDS = {
    "library-operations-pro-article": opspro_article,
    "library-opspro-showcase-guide": opspro_walkthrough,
    "library-how-it-was-built-article": build_story,
    "library-repository-guide": repo_guide,
    "library-pipeline-map": pipeline_map,
    "library-sts-operations-article": sts_home,
    "ai-locomotives": ai_locomotives,
    "ai-speed-runs": speed_runs,
    "ai-electronics": ai_electronics,
    "ai-construction": ai_construction,
    "ai-operations": ai_operations,
    "ai-mmr": ai_mmr,
    "ap-opsig": ap_opsig,
    "ap-exam": ap_exam,
    "ap-exam-run": ap_exam_run,
    "play-neville": play_neville,
    "link-play-title": link_play_title,
    "behind-wiring": wiring_node,
    "behind-jmri-additions": jmri_additions,
    "behind-panel-evolution": panel_evolution,
    "roster-index": roster,
    "plants-index": plants,
    "railroads-index": railroads,
    "library-coraopolis-record-opinion": coraopolis_record,
    "crew-maps": station_maps,
    "crew-maps-east-end": station_map_east_end,
    "crew-tt23": tt23,
    "link-build-main-level": link_build_main_level,
    "link-exam-run-title": link_exam_run_title,
    "build-track-plan": build_track_plan,
    "crew-nvl": crew_nvl,
    "crew-dispatcher": crew_dispatcher,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("names", nargs="*", help="cards to rebuild (default: all)")
    parser.add_argument("--list", action="store_true", help="list the cards and stop")
    parser.add_argument("--out", type=Path, default=PORTAL / "assets/share", help="output folder (default %(default)s)")
    args = parser.parse_args()
    if args.list:
        for name, fn in CARDS.items():
            print(f"{name}: {' '.join(fn.__doc__.split(': ', 1)[1].split())}")
        return 0
    if unknown := [n for n in args.names if n not in CARDS]:
        parser.error(f"unknown card(s): {', '.join(unknown)}; see --list")
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        _make(args.names or list(CARDS), args.out)
    except (CardError, ShareCardError) as err:
        print(f"make_share_cards: {err}", file=sys.stderr)
        return 1
    return 0


def _make(names: list[str], out: Path) -> None:
    with serving():
        for name in names:
            CARDS[name]().save(out / f"{name}.jpg", "JPEG", quality=88, optimize=True, progressive=True)
            print(f"Wrote {out / (name + '.jpg')}")


if __name__ == "__main__":
    raise SystemExit(main())
