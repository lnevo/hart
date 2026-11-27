"""Share cards made from the captured panel image (share-card-sources/panel-frame.png).

A recipe module of make_share_cards.py, which lists the cards (CARDS) and runs them."""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING, NamedTuple

import make_share_cards as kit
import share_cards
from make_share_cards import H, PAPER, SOURCES, W, site_views
from share_card_recipes import CardError

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


# ---- Cards that use the captured panel image ------------------------------------------------

# Places in panel-frame.png (1500 x 750), in its pixels: boxes are (left, top, right, bottom).
LAMP_ROWS_Y = (569, 597, 625, 653)    # the centre lines of the LCOS, Turnouts, Signals and Track Power lamp rows
LAMP_ROW_X, LAMP_ROW_HALF = (18, 146), 14  # each lamp row's left and right edge, and half its height
LAMP_ZOOM = 1.9                       # how much the lamps are enlarged in front of the panel
BRICK_TO_EAST_END = (250, 70, 1450, 700)  # the panel from Brick to East End, the jmri-additions card's ground
PANEL_BLUE_AT = (300, 600)            # a pixel of plain panel background, for the lamps' box
TITLE_EDGE = (560, 0, 900, 14)        # on the card: the bottom edge of the panel's title, painted over
BRICK_CORNER = (228, 165, 528, 345)   # the Brick corner, for the roster card
ROSTER_PAGE = "roster/index.html"     # the roster card's entry in share-cards.json; its "rows" are the rows it shows


class RosterRow(NamedTuple):
    """A device viewer row the roster card shows, as share-cards.json names it."""
    kind: str
    name: str             # the public name, the layout index's publicName


def _panel() -> PILImage:
    from PIL import Image

    return Image.open(SOURCES / "panel-frame.png").convert("RGB")


def jmri_additions() -> PILImage:
    """behind-jmri-additions: the panel from Brick to East End with its four status lamps enlarged in front."""
    from PIL import Image, ImageDraw, ImageFilter

    im = _panel()
    (left, right), half, k = LAMP_ROW_X, LAMP_ROW_HALF, LAMP_ZOOM
    rows = [im.crop((left, c - half, right, c + half)) for c in LAMP_ROWS_Y]
    rows = [r.resize((round(r.width * k), round(r.height * k)), Image.LANCZOS) for r in rows]
    rw, rh = rows[0].size
    pad, gx, gy = 20, 26, 14
    w, h = 2 * rw + gx + 2 * pad, 2 * rh + gy + 2 * pad
    x, y = 24, H - h - 22
    out = im.crop(BRICK_TO_EAST_END).convert("RGBA")
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x + 3, y + 7, x + w + 3, y + h + 7), 14, fill=(18, 26, 34, 110))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    pen = ImageDraw.Draw(out)
    panel_blue = im.getpixel(PANEL_BLUE_AT)
    pen.rounded_rectangle((x, y, x + w, y + h), 14, fill=panel_blue, outline=(10, 61, 74), width=4)
    for i, row in enumerate(rows):
        out.paste(row, (x + pad + (i % 2) * (rw + gx), y + pad + (i // 2) * (rh + gy)))
    pen.rectangle(TITLE_EDGE, fill=panel_blue)
    return out.convert("RGB")


def roster_picks(cards: dict[str, dict] | None = None) -> list[RosterRow]:
    """The rows the roster card shows: the "rows" of its share-cards.json entry ({"kind", "name"} each), in order.
    `cards` is share_cards.load()'s result, None the repo's. CardError when the entry or its rows are missing, a row
    is not a kind and a name, or a row is given twice."""
    cards = share_cards.load() if cards is None else cards
    where = f"roster-index: share-cards.json {ROSTER_PAGE}"
    if ROSTER_PAGE not in cards:
        raise CardError(f"{where}: no such card")
    rows = cards[ROSTER_PAGE].get("rows")
    if not isinstance(rows, list) or not rows:
        raise CardError(f'{where}: no "rows" list of the device viewer rows to show')
    out: list[RosterRow] = []
    for n, row in enumerate(rows, 1):
        if not (isinstance(row, dict) and set(row) == {"kind", "name"}
                and all(isinstance(v, str) and v.strip() for v in row.values())):
            raise CardError(f"{where}: row {n} is {row!r}, not a kind and a name")
        pick = RosterRow(row["kind"], row["name"])
        if pick in out:
            raise CardError(f"{where}: row {n} gives {pick.kind} {pick.name} twice")
        out.append(pick)
    return out


def roster_rows(items: list[dict[str, str]], picks: list[RosterRow]) -> str:
    """The table rows of `picks` (roster_picks) from the layout index's items (JSON: kind, publicName, cp, hardware).
    Raises CardError naming every row the index no longer has."""
    by_name = {(i["kind"], i.get("publicName")): i for i in items}
    gone = [f"{kind} {name}" for kind, name in picks if (kind, name) not in by_name]
    if gone:
        raise CardError(f"roster-index: the layout index has no {', '.join(gone)}; pick other rows for the card")
    return "".join(
        f"<tr><td>{kind}</td><td><b>{html.escape(name)}</b></td><td>{html.escape(by_name[kind, name].get('cp') or '')}</td>"
        f"<td>{html.escape(by_name[kind, name].get('hardware') or '')}</td></tr>"
        for kind, name in picks
    )


def roster() -> PILImage:
    """roster-index: the Brick corner of the panel beside six Brick rows of the device viewer."""
    from PIL import Image

    picks = roster_picks()
    brick = _panel().crop(BRICK_CORNER)
    brick.resize((brick.width * 3, brick.height * 3), Image.LANCZOS).save(kit._tmp / "brick.png")
    try:  # the published index is built, not committed (ADR-036): build it as the site does
        items = json.loads(site_views.build("data/layout-index.json"))["items"]
    except site_views.ViewError as err:
        raise CardError(f"roster-index: {err}") from err
    tr = roster_rows(items, picks)
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
