#!/usr/bin/env python3
"""Rebuild the share thumbnails that are drawn or composed, not plain photo crops.

Plain crops are made with `share_cards.py make`. The cards here are drawings, page
snapshots and composites; each function below is the whole recipe for one of them.

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
import html
import http.server
import json
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
REPO = PORTAL.parent
SOURCES = Path(__file__).resolve().parent / "share-card-sources"
W, H = 1200, 630
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
STS_URL = "http://10.0.0.150:8980/sts/"
PAPER = "linear-gradient(180deg,#edf2f5,var(--paper) 45%,var(--paper-2))"

_site = ""  # http://127.0.0.1:<port>/ while serving()
_tmp = Path()


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


@contextlib.contextmanager
def serving():
    """Serve the repo on a free port (pages reach logos in ../external/) and give drawings a scratch folder."""
    global _site, _tmp
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(REPO)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        _site, _tmp = f"http://127.0.0.1:{server.server_address[1]}/www/", Path(tmp)
        try:
            yield
        finally:
            server.shutdown()


def _chrome() -> str:
    for name in (MAC_CHROME, "google-chrome", "chromium"):
        if found := shutil.which(name):
            return found
    raise SystemExit("Google Chrome not found")


def shot(url: str, size: tuple[int, int] = (W, H), scale: int = 2):
    """A headless Chrome screenshot of URL as a Pillow image, `scale` device pixels per CSS pixel."""
    from PIL import Image

    out = _tmp / f"shot-{abs(hash((url, size, scale)))}.png"
    subprocess.run(
        [_chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
         f"--force-device-scale-factor={scale}", f"--window-size={size[0]},{size[1]}",
         "--virtual-time-budget=8000", f"--screenshot={out}", url],
        check=True, capture_output=True,
    )
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
    source = json.loads((PORTAL / "scripts/published-files.json").read_text(encoding="utf-8")).get(rel)
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


# ---- Juniper Falls & Northern (Operations Pro showcase) ---------------------------------------

_JFN_STYLE = (
    ".ln{fill:none;stroke:var(--brand);stroke-width:7;stroke-linecap:round;stroke-linejoin:round}.thin{stroke-width:4}"
    ".st{fill:#f0c055;stroke:var(--brand);stroke-width:4}.stg{fill:var(--card);stroke:var(--brand);stroke-width:4}"
    ".job{fill:var(--brand)}.lb{font:600 25px var(--font-body);fill:var(--ink)}.lb.b{font-weight:700;font-size:28px}"
    ".lb.s{font-size:21px;fill:var(--ink-soft)}.ttl{font:700 46px var(--font-display);fill:var(--brand);"
    "letter-spacing:.01em}.sub{font:500 22px var(--font-body);fill:var(--muted)}"
)


def _jfn_svg() -> str:
    """Route map from the Map paragraph of docs/ops/opspro-showcase/railroad/PLAN.md."""
    y = 330
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
         f'<path class="ln" d="M110 {y} H1090"/>',
         f'<path class="ln" d="M300 {y} L400 470 H640"/>',  # south branch from Carrow
         f'<path class="ln" d="M780 {y} L860 200 H1080"/>',  # north branch from Ferris Junction
         f'<path class="ln thin" d="M300 {y} L240 215 M300 {y} L300 195 M300 {y} L360 215"/>']  # Carrow jobs
    main = [("West Staging", 110), ("Carrow", 300), ("Brae", 460), ("Dunmere", 610),
            ("Ferris Junction", 780), ("Linden", 940), ("East Staging", 1090)]
    for name, x in main:
        big, staging = name in ("Carrow", "Ferris Junction"), "Staging" in name
        s.append(f'<circle class="{"stg" if staging else "st"}" cx="{x}" cy="{y}" r="{14 if big else 11}"/>')
        if name == "Carrow":  # the branch leaves under the dot, so the name sits to its left
            s.append(f'<text class="lb b" x="282" y="{y + 44}" text-anchor="end">Carrow</text>')
        elif name == "West Staging":
            s.append(f'<text class="lb" x="{x}" y="{y - 30}" text-anchor="middle">{name}</text>')
        else:
            s.append(f'<text class="lb{" b" if big else ""}" x="{x}" y="{y + 44}" text-anchor="middle">{name}</text>')
    for name, x, yy, ly in (("Hollis Mill", 500, 470, 514), ("Oakhaven", 640, 470, 514),
                            ("Pell Creek", 950, 200, 174), ("Northwood", 1080, 200, 174)):
        s.append(f'<circle class="st" cx="{x}" cy="{yy}" r="11"/><text class="lb" x="{x}" y="{ly}" text-anchor="middle">{name}</text>')
    for name, x, yy, anchor in (("Sawyer", 240, 215, "end"), ("Kessock", 300, 195, "middle"), ("Fiddle", 360, 215, "start")):
        lx = x + {"end": -14, "start": 14, "middle": 0}[anchor]
        ly = yy - 14 if anchor == "middle" else yy + 5
        s.append(f'<circle class="job" cx="{x}" cy="{yy}" r="8"/><text class="lb s" x="{lx}" y="{ly}" text-anchor="{anchor}">{name}</text>')
    s.append('<text class="ttl" x="70" y="92">Juniper Falls &amp; Northern</text>'
             '<text class="sub" x="72" y="126">15 locations · 18 trains · about 110 cars</text></svg>')
    return "".join(s)


def _switch_list(box: str) -> tuple[str, str]:
    """A switch list for SAWYER SWITCHER; the three moves are from its build report
    (docs/ops/opspro-showcase/railroad/operations/buildstatus/train (SAWYER SWITCHER).txt)."""
    rows = [("SWYX 2", "Hopper", "E", "Sawyer Yard 1", "Sawyer Yard 2"),
            ("SWYX 1", "Reefer", "E", "Sawyer Team", "Sawyer Warehouse"),
            ("JFN 401", "Boxcar", "Semolina", "Sawyer Yard", "Sawyer Pasta Plant")]
    tr = "".join(f"<tr><td class=c>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td><td class=to>{e}</td></tr>" for a, b, c, d, e in rows)
    body = ("<div class=p><h1>SAWYER SWITCHER</h1><div class=r>Juniper Falls &amp; Northern · Switch list · Sawyer · 11:30</div>"
            f"<table><tr><th>Car</th><th>Type</th><th>Load</th><th>From</th><th>Set out at</th></tr>{tr}</table></div>")
    style = (
        f".p{{position:absolute;{box}background:#fffdf7;border:1px solid var(--rule);box-shadow:0 10px 30px rgba(18,26,34,.18);"
        "padding:38px 48px;box-sizing:border-box;font-family:var(--font-body);color:var(--ink)}"
        "h1{font:700 44px var(--font-display);margin:0;color:var(--brand);letter-spacing:.02em}"
        ".r{font:600 21px var(--font-body);color:var(--muted);margin:2px 0 22px;border-bottom:3px solid var(--ink);padding-bottom:14px}"
        "table{border-collapse:collapse;width:100%;font-size:25px}th{text-align:left;font:700 17px var(--font-body);"
        "letter-spacing:.08em;text-transform:uppercase;color:var(--muted);padding:0 0 8px}"
        "td{padding:14px 0;border-top:1px solid var(--rule)}.c{font-weight:700}.to{font-weight:700;color:var(--brand)}"
    )
    return body, style


def opspro_article():
    """library-operations-pro-article: the invented railroad's route map."""
    return card(draw("jfn", _jfn_svg(), f"body{{background:{PAPER}}}" + _JFN_STYLE))


def opspro_walkthrough():
    """library-opspro-showcase-guide: a smaller switch list over the route map."""
    body, style = _switch_list("left:500px;top:265px;width:900px;height:440px;transform-origin:0 0;transform:scale(.72) rotate(-2deg);")
    return card(draw("walk", _jfn_svg() + body, f"body{{background:{PAPER}}}svg{{position:absolute;left:0;top:0}}" + _JFN_STYLE + style))


# ---- Page figures, rendered at card size ----------------------------------------------------

def _page_style(page: str) -> str:
    return "".join(re.findall(r"<style>(.*?)</style>", (PORTAL / page).read_text(encoding="utf-8"), re.S))


def ai_locomotives():
    """ai-locomotives: the speed-match chart from the page."""
    page = "ai/locomotives.html"
    style = (_page_style(page) + f"body{{background:var(--card)}}.w{{display:flex;align-items:center;justify-content:center;"
             f"width:{W}px;height:{H}px}}.speed-svg{{max-width:none!important;width:auto!important;height:600px!important}}")
    return card(draw("speed", f"<div class=w>{_svg(page, 'speed-svg')}</div>", style, ("css/ops.css", "css/ai.css")))


def build_story():
    """library-how-it-was-built-article: the homepage's island photo with the Diverging Route drawing over it."""
    island = _published("assets/media/birdseye-neville-island.jpg").as_uri()
    style = (
        f".bg{{position:absolute;inset:0;background:url('{island}') center/cover}}"
        ".veil{position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,61,74,.10),rgba(10,61,74,.38))}"
        ".hub-banner{position:absolute;left:50px;right:50px;top:170px;margin:0;padding:26px 30px 22px;"
        "background:rgba(243,246,248,.8);border:1px solid rgba(183,196,207,.9);border-radius:14px;"
        "box-shadow:0 14px 40px rgba(8,20,28,.45)}.hub-banner svg.route-wide{display:block!important;width:100%;height:auto}"
    )
    body = f'<div class=bg></div><div class=veil></div><figure class="hub-banner">{_svg("ai/index.html", "route-wide")}</figure>'
    return card(draw("journey", body, style, ("css/ops.css", "css/ai.css")))


def wiring_node():
    """behind-wiring: node C4's card from the wiring viewer. The box is the card's place on a
    1440 px wide page; move it if the page's layout or node order changes."""
    from PIL import Image

    k = 3
    page = shot(f"{_site}behind/wiring.html", (1440, 1200), k)
    node = page.crop((546 * k, 749 * k, 895 * k, 1066 * k))
    h = 570
    w = round(node.width * h / node.height)
    out = Image.new("RGB", (W, H), (228, 235, 240))
    out.paste(node.resize((w, h), Image.LANCZOS), ((W - w) // 2, 30))
    return out


def _lineage(page: str):
    """The top of a "who became who" chart: the first companies and what they became.
    The box is the chart's place on a 1440 px wide page; move it if the page's text above it changes length."""
    k = 2
    return card(shot(f"{_site}{page}", (1440, 1400), k).crop((170 * k, 640 * k, 1270 * k, 1217 * k)))


def plants():
    """plants-index: the Neville Island plant lineage, from American Steel & Wire to the 1960s break-up."""
    return _lineage("plants/index.html")


def railroads():
    """railroads-index: the Chartiers Valley railroads lineage, line by line."""
    return _lineage("railroads/index.html")


def coraopolis_record():
    """library-coraopolis-record-opinion: the top of the Bring Back The Trolleys column, with its Route 23 car."""
    from PIL import Image

    im = Image.open(PORTAL / "assets/history/coraopolis-record_bring-back-the-trolleys.jpg").convert("RGB")
    return card(im.crop((0, 0, im.width, round(im.width * H / W))))


# ---- Editor view of the bridge code -----------------------------------------------------------

_KEYWORDS = r"\b(static|bool|const|char|byte|if|return|true|false|NULL|void|uint16_t)\b"
_TOKEN = re.compile(r'"[^"]*"|\'[^\']*\'|\b[A-Z][A-Z0-9_]{3,}\b|\b[A-Za-z_]\w*(?=\()|' + _KEYWORDS + r"|\b\d+\b")


def _highlight(line: str) -> str:
    if re.match(r"\s*(/\*\*|\*/)|^ \*( |$)", line):  # doc comment lines; "  *aspect_out = …" is code
        return f"<span class=c>{html.escape(line)}</span>"
    out, i = [], 0
    for m in _TOKEN.finditer(line):
        token = m.group(0)
        cls = ("s" if token[0] in "\"'" else "k" if re.fullmatch(_KEYWORDS, token)
               else "n" if token.isdigit() else "K" if token.isupper() else "f")
        out += [html.escape(line[i:m.start()]), f"<span class={cls}>{html.escape(token)}</span>"]
        i = m.end()
    return "".join(out) + html.escape(line[i:])


def ai_electronics(first: int = 136, last: int = 160):
    """ai-electronics: lines of external/lcos-bridge/lcos_mqtt_bridge.cpp (the signal colour to
    aspect function) drawn as an editor view. Needs the lcos-bridge submodule."""
    src = (REPO / "external/lcos-bridge/lcos_mqtt_bridge.cpp").read_text(encoding="utf-8").splitlines()
    rows = "".join(f"<div class=l><span class=g>{n}</span>{_highlight(src[n - 1]) or ' '}</div>" for n in range(first, last + 1))
    files = ["lcos-bridge.ino", "lcos_mqtt_bridge.cpp", "lcos_mqtt_bridge.h", "mqtt_serial.cpp", "mqtt_serial.h",
             "gateways.h", "serial_to_mqtt.py", "README.md"]
    side = "".join(f'<div class="fi{" on" if f == "lcos_mqtt_bridge.cpp" else ""}">{f}</div>' for f in files)
    style = (
        'body{background:#1e1e1e;color:#d4d4d4;font:13px -apple-system,"Segoe UI",sans-serif}'
        ".side{position:absolute;left:0;top:0;width:205px;height:630px;background:#252526;border-right:1px solid #111}"
        ".side h4{margin:0;padding:13px 16px 9px;font-size:11px;letter-spacing:.09em;color:#bbb;font-weight:600}"
        ".rp{padding:4px 16px 8px;font-weight:700;font-size:12px;color:#ccc}"
        ".fi{padding:5px 16px 5px 28px;color:#c5c5c5;font-size:13.5px}.fi.on{background:#094771;color:#fff}"
        ".tabs{position:absolute;left:206px;top:0;right:0;height:38px;background:#2d2d2d}"
        ".tab{display:inline-block;height:38px;line-height:38px;padding:0 18px;background:#1e1e1e;"
        "border-top:2px solid #0a84c1;box-sizing:border-box;color:#fff;font-size:13.5px}"
        ".code{position:absolute;left:206px;top:46px;right:0;bottom:24px;font:16px/22px Menlo,Monaco,Consolas,monospace;white-space:pre}"
        ".l{height:22px}.g{display:inline-block;width:52px;padding-right:18px;text-align:right;color:#858585}"
        ".c{color:#6a9955}.s{color:#ce9178}.k{color:#569cd6}.K{color:#4fc1ff}.f{color:#dcdcaa}.n{color:#b5cea8}"
        ".st{position:absolute;left:0;right:0;bottom:0;height:24px;background:#0a6aa1;color:#fff;font-size:12px;line-height:24px;padding:0 14px}"
    )
    body = (f"<div class=side><h4>EXPLORER</h4><div class=rp>LCOS-BRIDGE</div>{side}</div>"
            f"<div class=tabs><span class=tab>lcos_mqtt_bridge.cpp</span></div><div class=code>{rows}</div>"
            f"<div class=st>C++ &nbsp;·&nbsp; UTF-8 &nbsp;·&nbsp; Ln {first + 4}, Col 1</div>")
    return card(draw("ide", body, style, ()))


# ---- Cards that use the captured panel image ------------------------------------------------

def _panel():
    from PIL import Image

    return Image.open(SOURCES / "panel-frame.png").convert("RGB")


def jmri_additions():
    """behind-jmri-additions: the panel from Brick to East End with its four status lamps enlarged in front."""
    from PIL import Image, ImageDraw, ImageFilter

    im = _panel()
    k = 1.9
    rows = [im.crop((18, c - 14, 146, c + 14)) for c in (569, 597, 625, 653)]  # LCOS, Turnouts, Signals, Track Power
    rows = [r.resize((round(r.width * k), round(r.height * k)), Image.LANCZOS) for r in rows]
    rw, rh = rows[0].size
    pad, gx, gy = 20, 26, 14
    w, h = 2 * rw + gx + 2 * pad, 2 * rh + gy + 2 * pad
    x, y = 24, H - h - 22
    out = im.crop((250, 70, 1450, 700)).convert("RGBA")
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x + 3, y + 7, x + w + 3, y + h + 7), 14, fill=(18, 26, 34, 110))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    pen = ImageDraw.Draw(out)
    panel_blue = im.getpixel((300, 600))
    pen.rounded_rectangle((x, y, x + w, y + h), 14, fill=panel_blue, outline=(10, 61, 74), width=4)
    for i, row in enumerate(rows):
        out.paste(row, (x + pad + (i % 2) * (rw + gx), y + pad + (i // 2) * (rh + gy)))
    pen.rectangle((560, 0, 900, 14), fill=panel_blue)  # the bottom edge of the panel's title
    return out.convert("RGB")


def roster():
    """roster-index: the Brick corner of the panel beside six Brick rows of the device roster."""
    from PIL import Image

    brick = _panel().crop((228, 165, 528, 345))
    brick.resize((brick.width * 3, brick.height * 3), Image.LANCZOS).save(_tmp / "brick.png")
    items = json.loads((PORTAL / "data/layout-index.json").read_text(encoding="utf-8"))["items"]
    wanted = [("turnout", "Switch 1"), ("turnout", "Switch 3"), ("signal", "Mast 2L"), ("signal", "Mast 4RA"),
              ("occupancy", "OS Switch 1"), ("occupancy", "OS Switch 3")]
    by_name = {(i["kind"], i.get("publicName")): i for i in items}
    tr = "".join(
        f"<tr><td>{kind}</td><td><b>{html.escape(name)}</b></td><td>{html.escape(by_name[kind, name].get('cp') or '')}</td>"
        f"<td>{html.escape(by_name[kind, name].get('hardware') or '')}</td></tr>"
        for kind, name in wanted
    )
    style = (
        f"body{{background:{PAPER}}}"
        ".pn{position:absolute;left:36px;top:150px;width:500px;height:300px;border:4px solid var(--brand);border-radius:12px;"
        "overflow:hidden;box-shadow:0 10px 26px rgba(18,26,34,.22)}.pn img{width:100%;height:100%;object-fit:cover}"
        ".tb{position:absolute;left:500px;top:70px;width:664px;background:var(--card);border:1px solid var(--rule);"
        "box-shadow:0 10px 26px rgba(18,26,34,.18);font-family:var(--font-body);color:var(--ink)}"
        "table{border-collapse:collapse;width:100%;font-size:25px}th{text-align:left;background:var(--paper-2);"
        "padding:14px 18px;font-size:21px}td{padding:17px 18px;border-top:1px solid var(--rule)}"
    )
    body = ('<div class=pn><img src="brick.png"></div><div class=tb><table>'
            f"<tr><th>Kind</th><th>Public name</th><th>CP</th><th>Hardware</th></tr>{tr}</table></div>")
    return card(draw("roster", body, style))


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
    return _slices(layers, [(470, 330), (870, 730)])


def ai_construction():
    """ai-construction: the top of sheet 1 of the main level framing plan (macOS: uses qlmanage to render the PDF)."""
    from PIL import Image

    pdf = REPO / "docs/benchwork/main_level/main_level_joist_construction.pdf"
    subprocess.run(["qlmanage", "-t", "-s", "2400", "-o", str(_tmp), str(pdf)], check=True, capture_output=True)
    im = Image.open(_tmp / (pdf.name + ".png")).convert("RGB")
    w, h = im.size
    x0, x1, y0 = int(w * 0.035), int(w * 0.965), int(h * 0.02)
    return card(im.crop((x0, y0, x1, y0 + round((x1 - x0) * H / W))))


def link_build_main_level():
    """link-build-main-level: the "Where the pieces go" drawings on the main level plywood cut plan (hub card for build/#main-level)."""
    im = shot(_site + "build/files/main-level-plywood-cut-plan.html", (W, 2 * H))
    w, h = im.size
    ch = round(w * H / W)
    top = round(h * 0.42)  # the drawings sit just below the middle of the first two screens
    return card(im.crop((0, top, w, top + ch)))


def ai_operations():
    """ai-operations: the weighed car on the STS Track Scale, from the owner's screenshot."""
    from PIL import Image

    im = Image.open(SOURCES / "track-scale-weighed.png").convert("RGB")
    w = im.width
    y0 = round(78 * w / 1085)  # below the green title bar
    return card(im.crop((0, y0, w, y0 + round(w * H / W))))


def sts_home():
    """library-sts-operations-article: the STS main menu. Needs STS running locally."""
    return card(shot(STS_URL))


def _clipboard(box):
    """A crop of the clipboards photo (assets/behind/sts/crew-sheets.jpg, 1600 x 1200)."""
    from PIL import Image

    return card(Image.open(PORTAL / "assets/behind/sts/crew-sheets.jpg").convert("RGB").crop(box))


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

    doc = REPO / "docs/ops/TT-23_Route23_NevilleQueen_RevisionA_v6.pptx"
    copy = _tmp / "tt23-page2.pptx"
    with zipfile.ZipFile(doc) as src, zipfile.ZipFile(copy, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "ppt/presentation.xml":
                text = data.decode("utf-8")
                first, second = re.findall(r"<p:sldId [^>]*/>", text)[:2]
                data = text.replace(first + second, second + first).encode("utf-8")
            out.writestr(item, data)
    subprocess.run(["qlmanage", "-t", "-s", "2400", "-o", str(_tmp), str(copy)], check=True, capture_output=True)
    im = Image.open(_tmp / (copy.name + ".png")).convert("RGB")
    top = round(im.width * 30 / 2400)
    return card(im.crop((0, top, im.width, top + round(im.width * H / W))))


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


CARDS = {
    "library-operations-pro-article": opspro_article,
    "library-opspro-showcase-guide": opspro_walkthrough,
    "library-how-it-was-built-article": build_story,
    "library-sts-operations-article": sts_home,
    "ai-locomotives": ai_locomotives,
    "ai-electronics": ai_electronics,
    "ai-construction": ai_construction,
    "ai-operations": ai_operations,
    "behind-wiring": wiring_node,
    "behind-jmri-additions": jmri_additions,
    "behind-panel-evolution": panel_evolution,
    "roster-index": roster,
    "plants-index": plants,
    "railroads-index": railroads,
    "library-coraopolis-record-opinion": coraopolis_record,
    "crew-maps": station_maps,
    "crew-tt23": tt23,
    "link-build-main-level": link_build_main_level,
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
    with serving():
        for name in args.names or CARDS:
            CARDS[name]().save(args.out / f"{name}.jpg", "JPEG", quality=88, optimize=True, progressive=True)
            print(f"Wrote {args.out / (name + '.jpg')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
