"""Share cards for the Operations Pro articles: the invented Juniper Falls & Northern's route map and a switch list.

A recipe module of make_share_cards.py, which lists the cards (CARDS) and runs them."""

from __future__ import annotations

import make_share_cards as kit
from make_share_cards import H, PAPER, W


# ---- Juniper Falls & Northern (Operations Pro showcase) ---------------------------------------

_JFN_STYLE = (
    ".ln{fill:none;stroke:var(--brand);stroke-width:7;stroke-linecap:round;stroke-linejoin:round}.thin{stroke-width:4}"
    ".st{fill:#f0c055;stroke:var(--brand);stroke-width:4}.stg{fill:var(--card);stroke:var(--brand);stroke-width:4}"
    ".job{fill:var(--brand)}.lb{font:600 25px var(--font-body);fill:var(--ink)}.lb.b{font-weight:700;font-size:28px}"
    ".lb.s{font-size:21px;fill:var(--ink-soft)}.ttl{font:700 46px var(--font-display);fill:var(--brand);"
    "letter-spacing:.01em}.sub{font:500 22px var(--font-body);fill:var(--muted)}"
)


def _jfn_svg() -> str:
    """Route map from the Map paragraph of external/model-railroad-skills/plugins/operations-pro/examples/showcase/PLAN.md."""
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
    (external/model-railroad-skills/plugins/operations-pro/examples/showcase/operations/buildstatus/train (SAWYER SWITCHER).txt)."""
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
    return kit.card(kit.draw("jfn", _jfn_svg(), f"body{{background:{PAPER}}}" + _JFN_STYLE))


def opspro_walkthrough():
    """library-opspro-showcase-guide: a smaller switch list over the route map."""
    body, style = _switch_list("left:500px;top:265px;width:900px;height:440px;transform-origin:0 0;transform:scale(.72) rotate(-2deg);")
    return kit.card(kit.draw("walk", _jfn_svg() + body, f"body{{background:{PAPER}}}svg{{position:absolute;left:0;top:0}}" + _JFN_STYLE + style))
