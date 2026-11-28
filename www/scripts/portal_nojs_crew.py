"""Stage 7b, crew pages and the publications shelf: their content as plain HTML for visitors without JavaScript.

js/crew.js draws each crew page (crew sheets, YM-01, DS-01, station maps, TT-23, colors, EQ-01, spot sheets) from
data/crew.json, and docs/index.html draws the shelf from data/publications.json. The built copy carries the same
content in #crew-root (and #sheet-head) and #pub-shelf, in the markup and classes the page scripts write, so a page
reads the same with JavaScript off. With JavaScript the scripts replace it as before; the root carries data-static,
and crew.js keeps the static copy when crew.json fails to load.

Left out of the static copy: the controls that need JavaScript (Print, Clear ticks, the map zoom and the
orientation toggle; a map links its drawing instead) and the source docx buttons (never on the public site).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

# The page's HARTCrew.page(kind, id) call, as crew_pages_test.js finds it.
_PAGE_CALL = re.compile(r'HARTCrew\.page\("([\w-]+)", "([\w-]*)"\)')
_NAV_SRC = re.compile(r"""<script\b[^>]*\bsrc=["']((?:\.\./)*|/)js/nav\.js(?:\?[^"']*)?["']""")
# The "needs JavaScript" note before the root, and the root with its Loading line.
_CREW_NOTE = re.compile(r"\s*<noscript><style>#crew-root > p\.muted \{ display: none; \}</style>.*?</noscript>", re.S)
_CREW_ROOT = re.compile(r'<div id="crew-root"><p class="muted">Loading…</p></div>')
_SHEET_HEAD = re.compile(r'(<div class="sheet-head" id="sheet-head">).*?(</div>)', re.S)
_PUB_NOTE = re.compile(r"\s*<noscript><style>#pub-shelf > p\.muted \{ display: none; \}</style>.*?</noscript>", re.S)
_PUB_ROOT = re.compile(r'<div id="pub-shelf"><p class="muted">Loading…</p></div>')
DOCS_REL = Path("docs/index.html")

ROTATE_HINT = '<span class="rotate-hint">Turn your phone sideways for a bigger view.</span>'


def esc(s: object) -> str:
    """HARTOps.esc: &, <, > and the double quote."""
    return (("" if s is None else str(s)).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def encode_uri(s: str) -> str:
    """JavaScript's encodeURI."""
    return quote(s, safe=";,/?:@&=+$-_.!~*'()#")


def join(items, fn, sep: str = "") -> str:
    return sep.join(fn(x) for x in items or [])


class Crew:
    """crew.js's page drawing for one page's base (the ../ in front of the site root)."""

    def __init__(self, data: dict, base: str, archive: bool = False):
        self.d = data
        self.base = base
        self.archive = archive

    def u(self, rel: str) -> str:
        return self.base + rel

    # —— lookups and links ——
    def color(self, cid):
        return next((c for c in self.d.get("colors") or [] if c.get("id") == cid), None)

    def map_by(self, mid):
        return next((m for m in self.d.get("maps") or [] if m.get("id") == mid), None)

    def map_href(self, mid: str) -> str:
        return self.u(f"crew/maps/{'archive/' if self.archive else ''}{mid}/index.html")

    def sheet_src(self, f: str) -> str:
        return self.u(f"crew/maps/generated-sheets/{f}.svg")

    def map_thumb(self, m: dict) -> str:
        return self.u(m["img"]) if self.archive or not m.get("sheets") else self.sheet_src(m["sheets"][0])

    def spot_href(self, sid: str) -> str:
        return f'{self.u("crew/industries/index.html")}#{sid}'

    def spot_name(self, sid: str) -> str:
        sh = self.d.get("spotsheet") or {}
        hit = next((i for i in (sh.get("industries") or []) + (sh.get("offline") or []) if i.get("id") == sid), None)
        return hit["name"] if hit else sid

    # —— shared pieces ——
    @staticmethod
    def chip(c, dim: bool = False, small: bool = False, swatch_only: bool = False) -> str:
        if not c:
            return ""
        cls = f"cchip{' is-dim' if dim else ''}{' is-small' if small else ''}"
        label = f' role="img" aria-label="{esc(c.get("label"))}"' if swatch_only else ""
        return (f'<span class="{cls}" style="--chip:{esc(c.get("hex"))};--chip-ink:{esc(c.get("ink"))}"{label}>'
                f'{"" if swatch_only else esc(c.get("label"))}</span>')

    def chips(self, ids, small: bool = False) -> str:
        return join(ids, lambda i: self.chip(self.color(i), small=small), " ")

    @staticmethod
    def table(cls: str, heads, rows, row_html) -> str:
        return (f'<div class="table-wrap"><table class="{cls}"><thead><tr>{join(heads, lambda h: f"<th>{h}</th>")}'
                f"</tr></thead><tbody>{join(rows, row_html)}</tbody></table></div>")

    def color_table(self) -> str:
        return self.table("data-table color-table", ["Color", "Destination", "Train"], self.d.get("colors"),
                          lambda c: f'<tr><td>{self.chip(c)}</td><td><a href="{self.spot_href(c["spot"])}">'
                                    f'{esc(c["dest"])}</a></td><td>{esc(c["train"])}</td></tr>')

    def tt_table(self) -> str:
        tt = self.d["timetable"]
        return (self.table("data-table tt-table", [esc(c) for c in tt["columns"]], tt["rows"],
                           lambda r: f'<tr><td>{esc(r[0])}</td><th scope="row">{esc(r[1])}</th><td>{esc(r[2])}</td></tr>')
                + f'<p class="tt-note">{esc(tt.get("note"))}</p>')

    def ghost(self, rel: str, label: str) -> str:
        return f'<a class="btn btn-ghost" href="{self.u(rel)}">{label}</a>'

    @staticmethod
    def actions(inner: str) -> str:
        return f'<div class="sheet-actions no-print">{inner}</div>'

    def map_card(self, m) -> str:
        if not m:
            return ""
        return (f'<a class="map-card" href="{self.map_href(m["id"])}"><img src="{esc(self.map_thumb(m))}" alt="" '
                f'loading="lazy"><span><strong>{esc(m["title"])}</strong><small>{esc(m["pub"])}</small></span></a>')

    # —— crew sheet, YM-01, DS-01 ——
    def sheet_head(self, job: dict) -> str:
        engine = ""
        eng = job.get("engine")
        if eng:
            pic = (f'<img src="{esc(self.u(eng["img"]))}" alt="{esc(eng["label"])}" width="160" height="45">'
                   if eng.get("img") else '<span class="engine-none" aria-hidden="true">?</span>')
            engine = f'<div class="sheet-engine">{pic}<span><small>Engine</small>{esc(eng["label"])}</span></div>'
        return (f'<div class="sheet-id"><p class="sheet-code">{esc(job["code"])}</p>'
                f'<div><h1>{esc(job["name"])}</h1><p class="sheet-pub">{esc(job.get("pub"))} · Rev {esc(job.get("revision"))}'
                f' <span class="sheet-eff">· Effective {esc(job.get("effective"))}</span></p></div></div>' + engine)

    @staticmethod
    def jump(job: dict) -> str:
        links = [(k, h, label) for k, h, label in (
            ("priority", "prio-h", "Priority"), ("steps", "steps-h", "Steps"), ("sequence", "sequence-h", "Sequence"),
            ("lineup", "lineup-h", "Train lineup"), ("", "colors-h", "Colors"), ("maps", "where-h", "Maps"),
            ("talk", "talk-h", "Talk")) if not k or job.get(k)]
        if len(links) < 3:
            return ""
        return ('<nav class="jump no-print" aria-label="On this page"><ul>'
                + join(links, lambda l: f'<li><a href="#{l[1]}">{l[2]}</a></li>') + "</ul></nav>")

    @staticmethod
    def steps(job: dict) -> str:
        # The tick boxes work without JavaScript; only keeping them per job (and Clear ticks) needs it.
        return ('<section class="sheet-sec" aria-labelledby="steps-h"><div class="sec-head"><h2 id="steps-h">Crew steps</h2>'
                '</div><ol class="steps">'
                + "".join(f'<li><label><input type="checkbox" class="no-print" data-step="{i}"><span>{esc(s)}</span>'
                          "</label></li>" for i, s in enumerate(job["steps"]))
                + "</ol></section>")

    def rows(self, title: str, rows, hid: str) -> str:
        return (f'<section class="sheet-sec"><h2 id="{hid}">{esc(title)}</h2><ol class="seq">'
                + join(rows, lambda r: f'<li><span class="seq-n">{esc(r.get("n"))}</span><div><p class="seq-train">'
                                       f'{esc(r.get("train"))}</p><p class="seq-action">{esc(r.get("action"))}</p>'
                                       + (f'<p class="seq-chips">{self.chips(r["colors"], small=True)}</p>'
                                          if r.get("colors") else "") + "</div></li>")
                + "</ol></section>")

    def colors(self, job: dict) -> str:
        mine = job.get("colors") or []
        every = self.d.get("colors") or []
        all_ = len(mine) >= len(every)
        shown = [self.color(i) for i in mine] + (job.get("legend_extra") or []) if all_ else every

        def item(c):
            on = not c.get("id") or c["id"] in mine
            dest = (f'<a href="{self.spot_href(c["spot"])}">{esc(c["dest"])}</a>' if c.get("spot")
                    else f'<strong>{esc(c["dest"])}</strong>')
            return f'<li class="{"is-mine" if on else "is-other"}">{self.chip(c, dim=not on)}{dest}<small>{esc(c.get("train"))}</small></li>'

        return (f'<section class="sheet-sec sheet-colors" aria-labelledby="colors-h"><h2 id="colors-h">'
                f'{"Destination colors" if all_ else "Your colors"}</h2>'
                + ("" if all_ else '<p class="muted small">Your blocks are bright; the rest are dimmed.</p>')
                + '<ul class="cc-list">' + join([c for c in shown if c], item) + "</ul></section>")

    def talk(self, job: dict) -> str:
        return ('<section class="sheet-sec no-print" aria-labelledby="talk-h"><h2 id="talk-h">Who you talk to</h2><dl class="talk">'
                + join(job["talk"], lambda t: f'<dt>{esc(t["who"])}</dt><dd>{esc(t["why"])}</dd>') + "</dl>"
                + join(job.get("links"), lambda l: f'<p class="small"><a href="{self.u(l["href"])}">{esc(l["label"])}</a></p>')
                + "</section>")

    @staticmethod
    def priority(job: dict) -> str:
        return ('<section class="sheet-sec" aria-labelledby="prio-h"><h2 id="prio-h">Priority</h2><ol class="prio-strip">'
                + join(job["priority"], lambda p: f"<li><span>{esc(p)}</span></li>")
                + '</ol><p class="muted small">When moves conflict, the train further left goes first.</p></section>')

    def where(self, job: dict) -> str:
        return ('<section class="sheet-sec no-print" aria-labelledby="where-h"><h2 id="where-h">Where you work</h2>'
                '<div class="map-cards">' + join(job["maps"], lambda i: self.map_card(self.map_by(i)))
                + f'</div><p class="small"><a href="{self.u("crew/maps/index.html")}">All station maps</a></p></section>')

    def timetable_back(self, job: dict) -> str:
        return (f'<details class="sheet-more print-back" data-print-open{" open" if job.get("ttOpen") else ""}>'
                "<summary>Route 23 timetable (TT-23)</summary>"
                f'<div class="back-page"><figure class="back-map print-only"><img src="{esc(self.u("assets/maps/station_map_diagram_only.png"))}"'
                f' alt="Subdivision diagram"></figure><div>{self.tt_table()}'
                f'<p class="small no-print"><a href="{self.u("crew/tt23/index.html")}">Full timetable page</a></p></div></div></details>')

    def sheet_body(self, job: dict) -> str:
        return (f'<p class="sheet-summary">{esc(job.get("summary"))}</p>' + self.jump(job)
                + (self.priority(job) if job.get("priority") else "")
                + (self.steps(job) if job.get("steps") else "")
                + (self.rows("Sequence", job["sequence"], "sequence-h") if job.get("sequence") else "")
                + (self.rows("Train lineup", job["lineup"], "lineup-h") if job.get("lineup") else "")
                + self.colors(job)
                + (self.where(job) if job.get("maps") else "")
                + (self.talk(job) if job.get("talk") else "")
                + self.timetable_back(job)
                + f'<details class="sheet-more no-print"><summary>All destination colors</summary>{self.color_table()}</details>'
                + self.actions(self.ghost("crew/index.html", "All sheets") + self.ghost("briefing/index.html", "Primer")))

    # —— station maps ——
    def sheet_figure(self, sid: str, with_title: bool) -> str:
        title, what = self.d["sheets"][sid]
        src = esc(self.sheet_src(sid))
        alt = esc(f"{title} station map, {what[:1].lower()}{what[1:]}")
        return (f'<figure class="map-figure">{f"<h2 class=\"sub-h\">{esc(title)}</h2>" if with_title else ""}'
                f'<a class="map-open" href="{src}"><img src="{src}" alt="{alt}" width="1056" height="816"></a>'
                f'<figcaption class="no-print">{esc(f"{title}: {what}")}. <a href="{src}">Open the drawing full size</a>. '
                f"{ROTATE_HINT}</figcaption></figure>")

    def map_tracks(self, m: dict) -> str:
        def row(t):
            purpose = esc(t.get("purpose"))
            if t.get("spots"):
                many = len(t["spots"]) > 1
                purpose += ('<br><span class="small">' + join(
                    t["spots"], lambda s: f'<a href="{self.spot_href(s)}">'
                                          f'{esc(f"Spot sheet: {self.spot_name(s)}" if many else "Spot sheet")}</a>', " · ")
                            + "</span>")
            if t.get("map"):
                purpose += f'<br><a class="small" href="{self.map_href(t["map"])}">{esc(self.map_by(t["map"])["title"])} map</a>'
            return f'<tr><th scope="row">{esc(t.get("track"))}</th><td>{purpose}</td><td>{self.chips(t.get("colors"), small=True)}</td></tr>'

        return ('<section class="sheet-sec no-print"><h2>Tracks</h2>'
                + self.table("data-table", ["Track", "What is there", "Color"], m.get("tracks"), row) + "</section>")

    def map_switches(self, m: dict) -> str:
        return ('<section class="sheet-sec no-print"><h2>Switches</h2>'
                + self.table("data-table", ["No.", "What it does"], m.get("switches"),
                             lambda s: f'<tr><th scope="row"><span class="sw-badge">{esc(s["n"])}</span></th><td>{esc(s["what"])}</td></tr>')
                + "</section>")

    def map_page(self, m: dict) -> str:
        if self.archive:
            src = esc(self.u(m["img"]))
            figures = (f'<figure class="map-figure"><a class="map-open" href="{src}"><img src="{src}" alt="{esc(m.get("alt"))}"'
                       f' width="1600" height="1000"></a><figcaption class="no-print">{ROTATE_HINT}</figcaption></figure>')
            note = (f'<p class="muted small no-print">Earlier hand-drawn map with the old switch numbers. '
                    f'<a href="{self.u(f"crew/maps/{m["id"]}/index.html")}">Current {esc(m["title"])} map</a></p>')
        else:
            sheets = m.get("sheets") or []
            figures = join(sheets, lambda i: self.sheet_figure(i, len(sheets) > 1))
            note = ""
        connects = (f'<section class="sheet-sec no-print"><h2>Connects to</h2><div class="map-cards">'
                    f'{join(m.get("connects"), lambda i: self.map_card(self.map_by(i)))}</div></section>')
        return (note + figures + self.map_tracks(m) + (self.map_switches(m) if self.archive else "") + connects
                + self.actions(self.ghost("crew/maps/archive/index.html" if self.archive else "crew/maps/index.html", "All maps")
                               + self.ghost("crew/index.html", "Crew sheets")))

    def map_list_item(self, href, img, title, small, what) -> str:
        return (f'<li><a href="{href}"><img src="{esc(img)}" alt="" loading="lazy">'
                f"<span><strong>{esc(title)}</strong><small>{esc(small)}</small><em>{esc(what)}</em></span></a></li>")

    def maps_index(self) -> str:
        if self.archive:
            return self.maps_archive()
        sc = self.d["schematic"]
        rev = sc.get("revision")
        eff = f" · Effective {sc['effective']}" if sc.get("effective") else ""
        revision = f" Revision {rev}{eff}." if rev else ""
        levels = join(self.d.get("levels"), lambda i: (
            f'<li><a href="{esc(self.sheet_src(i))}"><img src="{esc(self.sheet_src(i))}" alt="" loading="lazy" width="1056" height="816">'
            f'<span><strong>{esc(self.d["sheets"][i][0])}</strong><em>{esc(self.d["sheets"][i][1])}</em></span></a></li>'))
        svg = esc(self.u(sc["svg"]))
        return ('<section class="maps-index">'
                f'<figure class="key-map"><a class="map-open" href="{svg}"><img src="{svg}" alt="{esc(sc.get("alt"))}"'
                f' width="1056" height="816"></a><figcaption>{esc(sc.get("caption", "") + revision)} '
                f'<a href="{esc(self.u(sc["pdf"]))}">PDF to print</a>.</figcaption></figure>'
                '<div><h2 class="sub-h">Station maps</h2><ul class="map-list">'
                + join(self.d.get("maps"), lambda m: self.map_list_item(
                    self.map_href(m["id"]), self.map_thumb(m), m["title"], m["pub"] + (f" · Rev {rev}" if rev else ""),
                    m.get("now") or m.get("what")))
                + "</ul>"
                f'<h2 class="sub-h">Levels</h2><ul class="map-list">{levels}</ul>'
                f'<p class="small">The earlier hand-drawn maps, with the old switch numbers, are in the '
                f'<a href="{self.u("crew/maps/archive/index.html")}">archive</a>.</p></div></section>'
                + self.actions(self.ghost("crew/index.html", "Crew sheets")))

    def maps_archive(self) -> str:
        o = self.d["overview"]
        img = esc(self.u(o["img"]))
        line = " · ".join(f"{k} {o[f]}" for k, f in (("Publication", "pub"), ("Revision", "revision"),
                                                       ("Effective", "effective")) if o.get(f))
        return ('<section class="maps-index">'
                f'<figure class="key-map"><a class="map-open" href="{img}"><img src="{img}" alt="{esc(o.get("alt"))}"></a>'
                f'<figcaption><strong>{esc(o["title"])}</strong> · {esc(line)}<br>{esc(o.get("what"))}</figcaption></figure>'
                '<div><h2 class="sub-h">Station maps</h2><ul class="map-list">'
                + join(self.d.get("maps"), lambda m: self.map_list_item(
                    self.map_href(m["id"]), self.u(m["img"]), m["title"],
                    m["pub"] + (f" · Rev {m['revision']}" if m.get("revision") else ""), m.get("what")))
                + "</ul></div></section>"
                + self.actions(self.ghost("crew/maps/index.html", "Current station maps")))

    # —— reference pages ——
    def colors_page(self) -> str:
        def group(g, title):
            return (f'<section class="sheet-sec"><h2>{esc(title)}</h2><ul class="cc-list cc-big">'
                    + join([c for c in self.d["colors"] if c.get("group") == g],
                           lambda c: f'<li>{self.chip(c)}<a href="{self.spot_href(c["spot"])}">{esc(c["dest"])}</a>'
                                     f'<small>{esc(c["train"])}</small></li>')
                    + "</ul></section>")

        return (group("island", "Local industries") + group("interchange", "Interchange")
                + f'<details class="sheet-more" data-print-open><summary>As a table</summary>{self.color_table()}</details>'
                + self.actions(self.ghost("crew/index.html", "Crew sheets")))

    def tt23_page(self) -> str:
        tt = self.d["timetable"]
        return (f'<p class="tt-sub">{esc(tt.get("subtitle"))}</p>'
                f'<div class="tt-layout"><div>{self.tt_table()}</div>'
                f'<section class="sheet-sec"><h2>Special instructions</h2><ol>{join(tt.get("instructions"), lambda i: f"<li>{esc(i)}</li>")}'
                f'</ol><p class="muted small">{esc(tt.get("bulletin"))}</p>'
                f'<p class="small no-print">Where the stations are: <a href="{self.u("crew/maps/index.html")}">subdivision diagram and station maps</a>.</p></section></div>'
                + self.actions(self.ghost("crew/dispatcher/index.html", "Dispatcher train list")
                               + self.ghost("crew/index.html", "Crew sheets")))

    @staticmethod
    def rule_item(i: str) -> str:
        m = re.match(r"^(PASS|REJECTED) — (.*)$", i)
        if m:
            return f'<li><strong class="verdict verdict-{m[1].lower()}">{m[1]}</strong> {esc(m[2])}</li>'
        return f"<li>{esc(i)}</li>"

    def scale_page(self) -> str:
        s = self.d["scale"]

        def part(p):
            tag = "ol" if p.get("ordered") else "ul"
            return f'<h3>{esc(p["h"])}</h3><{tag} class="rule-list">{join(p["items"], self.rule_item)}</{tag}>'

        return (f'<p class="sheet-summary">{esc(s.get("summary"))}</p>'
                + join(s.get("sections"), lambda sec: f'<section class="sheet-sec"><h2>{esc(sec["heading"])}</h2>'
                                                      + join(sec.get("parts"), part) + "</section>")
                + self.actions(self.ghost("crew/ck1/index.html", "CK1 crew sheet") + self.ghost("crew/index.html", "Crew sheets")))

    def industries_page(self) -> str:
        sh = self.d["spotsheet"]
        ind, off, desk = sh.get("industries") or [], sh.get("offline") or [], sh.get("desk") or []

        def where(i):
            m = self.map_by(i.get("map"))
            return f'<a href="{self.map_href(m["id"])}">{esc(m["title"])} map</a>' if m else ""

        def lst(label, items, ordered=False):
            tag = "ol" if ordered else "ul"
            return f'<h3>{esc(label)}</h3><{tag}>{join(items, lambda x: f"<li>{esc(x)}</li>")}</{tag}>'

        def paras(ps):
            return join(ps, lambda p: f"<p>{esc(p)}</p>")

        def industry(i):
            head = i.get("trackHead") or ["Spot", "Track", "Cars", "In", "Out"]
            return (f'<section class="panel spot-sheet" id="{esc(i["id"])}"><div class="spot-head">{self.chip(self.color(i.get("color")))}'
                    f'<h2>{esc(i["name"])}</h2></div><p class="spot-meta">Track {esc(i.get("track"))} · {where(i)}'
                    f' · Served by {esc(i.get("served"))}</p>'
                    f'<details class="spot-history no-print" open><summary>About the company</summary><ul>'
                    f'{join(i.get("history"), lambda x: f"<li>{esc(x)}</li>")}</ul></details>'
                    f'<p class="spot-traffic"><strong>Traffic:</strong> {esc(i.get("traffic"))}</p>'
                    f'<h3>{"Tracks" if i.get("trackHead") else "Tracks &amp; spots"}</h3>'
                    + self.table("data-table", [esc(h) for h in head], i.get("spots"),
                                 lambda r: "<tr>" + "".join(f'<th scope="row">{esc(c)}</th>' if ci == 0 else f"<td>{esc(c)}</td>"
                                                            for ci, c in enumerate(r)) + "</tr>")
                    + (f'<p class="small muted">{esc(i["spotNote"])}</p>' if i.get("spotNote") else "") + "</section>")

        jump = ('<nav class="jump no-print" aria-label="Jump to"><ul>'
                + join(ind + off, lambda i: f'<li><a href="#{esc(i["id"])}">'
                                            f'{self.chip(self.color(i.get("color")), small=True, swatch_only=True)}{esc(i["name"])}</a></li>')
                + join(desk, lambda d: f'<li><a href="#{esc(d["id"])}">{esc(d["name"])}</a></li>') + "</ul></nav>")
        offline = join(off, lambda o: (
            f'<section class="panel spot-sheet" id="{esc(o["id"])}"><div class="spot-head">{self.chip(self.color(o.get("color")))}'
            f'<h2>{esc(o["name"])}</h2></div><p class="spot-meta">{esc(o.get("tag"))} · {where(o)}</p>' + paras(o.get("about"))
            + f'<div class="two-col"><div>{lst(o.get("inLabel"), o.get("inbound"))}</div><div>{lst(o.get("outLabel"), o.get("outbound"))}</div></div>'
            + f'{lst("Jobs", o.get("jobs"))}</section>'))
        desks = join(desk, lambda d: (
            f'<section class="panel spot-sheet" id="{esc(d["id"])}"><h2>{esc(d["name"])}</h2><p class="spot-meta">{esc(d.get("tag"))}'
            f'{f" · {where(d)}" if d.get("map") else ""}</p>' + paras(d.get("about"))
            + join(d.get("lists"), lambda l: lst(l["label"], l["items"], l.get("ordered"))) + "</section>"))
        return (f'<p class="sheet-summary">{esc(sh.get("summary"))}</p>{jump}'
                f'<h2 class="sub-h">On the island</h2>{join(ind, industry)}'
                f'<h2 class="sub-h">Interchange</h2>{offline}'
                f'<h2 class="sub-h">Yard and desk notes</h2>{desks}'
                + self.actions(self.ghost("briefing/index.html#industries", "Industries") + self.ghost("crew/index.html", "Crew sheets")))

    # —— one page ——
    def render(self, kind: str, pid: str) -> tuple[str, str | None]:
        """(the #crew-root content, the #sheet-head content or None) for HARTCrew.page(kind, pid)."""
        if kind == "sheet":
            job = next(j for j in self.d.get("jobs") or [] if j.get("id") == pid)
            return self.sheet_body(job), self.sheet_head(job)
        if kind == "map":
            m = self.map_by(pid)
            if not m:
                raise KeyError(pid)
            return self.map_page(m), None
        pages = {"maps": self.maps_index, "colors": self.colors_page, "tt23": self.tt23_page,
                 "scale": self.scale_page, "industries": self.industries_page}
        return pages[kind](), None


def render_page(text: str, data: dict) -> str | None:
    """A built crew page with its content filled in, or None when it is not a crew page this stage knows."""
    call, nav = _PAGE_CALL.search(text), _NAV_SRC.search(text)
    if not call or not nav or not _CREW_ROOT.search(text):
        return None
    kind, pid = call.groups()
    archive = kind.endswith("-archive")
    try:
        body, head = Crew(data, nav.group(1), archive).render(kind.removesuffix("-archive"), pid)
    except (KeyError, StopIteration):
        return None
    new = _CREW_ROOT.sub(lambda _m: f'<div id="crew-root" data-static>{body}</div>', text, count=1)
    if head is not None:
        new = _SHEET_HEAD.sub(lambda m: m.group(1) + head + m.group(2), new, count=1)
    return _CREW_NOTE.sub("", new, count=1)


def shelf_html(data: dict, base: str) -> str:
    """docs/index.html's shelf, public site (no source docx buttons); Print needs JavaScript and is left out."""
    def resolve(rel):
        return base + rel if rel else ""

    def item(d):
        acts = []
        if d.get("page"):
            acts.append(f'<a class="btn" href="{esc(resolve(d["page"]))}">Open</a>')
        if d.get("pdf"):
            acts.append(f'<a class="btn{" btn-ghost" if d.get("page") else ""}" href="{esc(encode_uri(resolve(d["pdf"])))}">Download PDF</a>')
        r = d.get("revision")
        rev = (r if re.match(r"^(v|Rev)", r) else "Rev " + r) if r else ""
        return (f'<li><p class="pub-no">{esc(d.get("pub") or "—")}<small>{esc(rev)}</small></p>'
                f'<div><h3>{esc(d.get("title"))}</h3><p>{esc(d.get("blurb"))}</p></div>'
                f'<div class="actions">{"".join(acts)}</div></li>')

    items = data.get("items") or []
    out = []
    for g in data.get("groups") or []:
        rows = [d for d in items if d.get("group") == g.get("id")]
        if rows:
            out.append(f'<section class="shelf-group" id="{esc(g["id"])}"><h2>{esc(g.get("label"))}</h2>'
                       + (f'<p class="muted small">{esc(g["note"])}</p>' if g.get("note") else "")
                       + '<ul class="shelf">' + "".join(item(d) for d in rows) + "</ul></section>")
    return "".join(out)


def add_shelf(dest: Path) -> bool:
    page = dest / DOCS_REL
    if not page.is_file():
        return False
    text = page.read_text(encoding="utf-8")
    if not _PUB_ROOT.search(text):
        return False
    data = json.loads((dest / "data" / "publications.json").read_text(encoding="utf-8"))
    new = _PUB_ROOT.sub(lambda _m: f'<div id="pub-shelf" data-static>{shelf_html(data, "../")}</div>', text, count=1)
    new = new.replace('<p class="muted" id="pub-lede"></p>', f'<p class="muted" id="pub-lede">{esc(data.get("lede"))}</p>', 1)
    page.write_text(_PUB_NOTE.sub("", new, count=1), encoding="utf-8")
    return True


def add_crew_pages(dest: Path) -> list[str]:
    """Fill every built crew page; the pages filled, relative to dest."""
    crew = dest / "data" / "crew.json"
    if not crew.is_file() or not (dest / "crew").is_dir():
        return []
    data = json.loads(crew.read_text(encoding="utf-8"))
    done = []
    for page in sorted((dest / "crew").rglob("*.html")):
        new = render_page(page.read_text(encoding="utf-8"), data)
        if new is not None:
            page.write_text(new, encoding="utf-8")
            done.append(page.relative_to(dest).as_posix())
    return done
