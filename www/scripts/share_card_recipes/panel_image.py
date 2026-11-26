"""Share cards made from the captured panel image (share-card-sources/panel-frame.png).

A recipe module of make_share_cards.py, which lists the cards (CARDS) and runs them."""

from __future__ import annotations

import html
import json

import make_share_cards as kit
from make_share_cards import H, PAPER, SOURCES, W, site_views


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
    """roster-index: the Brick corner of the panel beside six Brick rows of the device viewer."""
    from PIL import Image

    brick = _panel().crop((228, 165, 528, 345))
    brick.resize((brick.width * 3, brick.height * 3), Image.LANCZOS).save(kit._tmp / "brick.png")
    try:  # the published index is built, not committed (ADR-036): build it as the site does
        items = json.loads(site_views.build("data/layout-index.json"))["items"]
    except site_views.ViewError as err:
        raise SystemExit(f"roster-index: {err}") from None
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
    return kit.card(kit.draw("roster", body, style))
