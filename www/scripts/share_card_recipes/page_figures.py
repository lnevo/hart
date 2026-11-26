"""Share cards drawn from figures and views of the site's own pages, rendered at card size.

A recipe module of make_share_cards.py, which lists the cards (CARDS) and runs them."""

from __future__ import annotations

import importlib.util
import json
import re

import make_share_cards as kit
from make_share_cards import H, PAPER, PORTAL, REPO, W
from share_card_recipes import CardError


# ---- Page figures, rendered at card size ----------------------------------------------------

def _page_style(page: str) -> str:
    return "".join(re.findall(r"<style>(.*?)</style>", (PORTAL / page).read_text(encoding="utf-8"), re.S))


def ai_locomotives():
    """ai-locomotives: the speed-match chart, which lives in the speed-matching article."""
    page = "ai/speed-runs.html"
    style = (_page_style(page) + f"body{{background:var(--card)}}.w{{display:flex;align-items:center;justify-content:center;"
             f"width:{W}px;height:{H}px}}.speed-svg{{max-width:none!important;width:auto!important;height:600px!important}}")
    return kit.card(kit.draw("speed", f"<div class=w>{kit._svg(page, 'speed-svg')}</div>", style, ("css/ops.css", "css/ai.css")))


def speed_runs():
    """ai-speed-runs: the run viewer on the 8-step 2738 forward run, its loco, readings and track strip (needs the ops/car-cards mirror)."""
    rid = "steprun_CSX_2738_forward_20261113_165713"  # the alt text in share-cards.json quotes this run
    runs = json.loads((PORTAL / "data/speedmatch/index.json").read_text(encoding="utf-8"))["runs"]
    if not any(r["id"] == rid for r in runs):  # the viewer would quietly show the newest run instead
        raise CardError(f"ai-speed-runs: {rid} is no longer in data/speedmatch/index.json; pick a run and fix the alt text")
    if not (REPO / "ops/car-cards/car-images/CarImagesFinal/loco_CSX_2738_right.png").is_file():
        raise CardError("ai-speed-runs: the ops/car-cards mirror is missing, so the loco photo would be blank")
    im = kit.shot(f"{kit._site}ai/speed-runs.html#run={rid}", (1400, 1200))
    return kit.card(im.crop((150 * 2, 550 * 2, 1251 * 2, 1128 * 2)))  # the hero and Track cards (CSS px, x2), 1200:630


def repo_guide():
    """library-repository-guide: the overview figure from the page, the repository between its submodules and the places it deploys to."""
    page = "library/repository-guide.html"
    style = (_page_style(page) + f"body{{background:{PAPER}}}.w{{display:flex;align-items:center;justify-content:center;"
             f"width:{W}px;height:{H}px}}.repo-svg{{max-width:none!important;width:auto!important;height:600px!important}}")
    return kit.card(kit.draw("repo", f"<div class=w>{kit._svg(page, 'repo-svg')}</div>", style, ("css/ops.css", "css/article.css")))


def pipeline_map():
    """library-pipeline-map: the map's own filtered view of run_sml_discover.sh, one step each side (#focus=jmri/layouts/hart/scripts/run_sml_discover.sh&up=1&down=1&compact=0, full boxes), drawn by the page with its toolbar and panels hidden."""
    # the page as the site build draws it now (it is not committed, ADR-036), so the card shows the current chain
    spec = importlib.util.spec_from_file_location("build_pipeline_map", REPO / "tools/ops/build_pipeline_map.py")
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    try:
        page = pipeline.site_page()
    except pipeline.GraphError as err:
        raise CardError(f"library-pipeline-map: the map page does not build:\n{err}") from err
    # the site header goes too, and the page ground is forced back to #fafafa so _fill_band finds the band
    hide = "<style>.site-header,#bar,#tour,#legend,#nav,#info{display:none!important}#stage{background:#fafafa!important}</style>"
    out = kit._tmp / "pipeline-map-view.html"
    base = f'<base href="{(PORTAL / "library").as_uri()}/">'  # the copy sits in a temp folder: load ../css/ops.css from www/
    out.write_text(page.replace("<head>", "<head>" + base, 1).replace("</head>", hide + "</head>", 1), encoding="utf-8")
    im = kit.shot(out.as_uri() + "#focus=jmri/layouts/hart/scripts/run_sml_discover.sh&up=1&down=1&compact=0")  # 2400 x 1260
    return kit.card(_fill_band(im))


def _fill_band(im):
    """The pipeline map's one lane band, centred on a card filled with the band's own colour: the drawing is wider
    than a card, so Fit leaves page background above and below it."""
    from PIL import Image

    bg = (250, 250, 250)  # the page background, #fafafa (forced by the hide style above)
    rows = [y for y in range(im.height) if im.getpixel((8, y)) != bg]
    if not rows or rows[0] == 0 and rows[-1] == im.height - 1:
        return im  # the band already fills the height
    rule = im.height // 630 + 2  # the band's 1 CSS px top rule, at the shot's scale, and a pixel of anti-aliasing
    top, bottom = rows[0] + rule, rows[-1] + 1
    band = im.crop((0, top, im.width, bottom))
    out = Image.new("RGB", im.size, band.getpixel((8, band.height // 2)))
    out.paste(band, (0, (im.height - band.height) // 2))
    return out


def build_story():
    """library-how-it-was-built-article: the homepage's island photo with the Diverging Route drawing over it."""
    island = kit._published("assets/media/birdseye-neville-island.jpg").as_uri()
    style = (
        f".bg{{position:absolute;inset:0;background:url('{island}') center/cover}}"
        ".veil{position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,61,74,.10),rgba(10,61,74,.38))}"
        ".hub-banner{position:absolute;left:50px;right:50px;top:170px;margin:0;padding:26px 30px 22px;"
        "background:rgba(243,246,248,.8);border:1px solid rgba(183,196,207,.9);border-radius:14px;"
        "box-shadow:0 14px 40px rgba(8,20,28,.45)}.hub-banner svg.route-wide{display:block!important;width:100%;height:auto}"
    )
    body = f'<div class=bg></div><div class=veil></div><figure class="hub-banner">{kit._svg("ai/index.html", "route-wide")}</figure>'
    return kit.card(kit.draw("journey", body, style, ("css/ops.css", "css/ai.css")))


def wiring_node():
    """behind-wiring: node C4's card from the wiring viewer. The box is the card's place on a
    1440 px wide page; move it if the page's layout or node order changes."""
    from PIL import Image

    k = 3
    page = kit.shot(f"{kit._site}behind/wiring.html", (1440, 1200), k)
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
    return kit.card(kit.shot(f"{kit._site}{page}", (1440, 1400), k).crop((170 * k, 640 * k, 1270 * k, 1217 * k)))


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
    return kit.card(im.crop((0, 0, im.width, round(im.width * H / W))))
