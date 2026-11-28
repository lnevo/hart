"""Stage 7b of the site build (prepare_github_pages.py): what a page shows when JavaScript is off or fails.

Every portal page carries an empty <header data-ops-header> and <footer data-ops-footer> that js/nav.js
(mountChrome) fills. In the built copy the header gets the skip link and the brand link home, as nav.js draws them,
with the section links from data/site.json "nav" (each section's "sub" entries after it) in a <noscript>, and the
footer gets the line nav.js writes. mountChrome replaces both with innerHTML, so a page with JavaScript ends up with
the same chrome and no second set of links. A page's <main> with no id gets id="main", the skip link's target.

The primer (briefing/index.html) is drawn from data/briefing.json in the browser; its built copy also carries the
primer's text as plain HTML in a <noscript> inside #briefing-body. The crew pages and the publications shelf get
their content from portal_nojs_crew.py.

Reads the built tree only (data/site.json after the scrub stage, so engDesk and the localhost tools are gone).
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import portal_nojs_crew

_MAIN = re.compile(r"<main\b([^>]*)>")
_EMPTY_HEADER = re.compile(r"(<header\b[^>]*\bdata-ops-header\b[^>]*>)\s*(</header>)")
_EMPTY_FOOTER = re.compile(r"(<footer\b[^>]*\bdata-ops-footer\b[^>]*>)\s*(</footer>)")
# The same match nav.js base() makes: the ../ (or /) in front of the page's js/nav.js.
_NAV_SRC = re.compile(r"""<script\b[^>]*\bsrc=["']((?:\.\./)*|/)js/nav\.js(?:\?[^"']*)?["']""")
PRIMER_REL = Path("briefing/index.html")
_PRIMER_BODY = re.compile(r'(<div id="briefing-body">)(<p class="muted">Loading…</p>)(</div>)')


def esc(s: object) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def header_html(site: dict, base: str, main_id: str = "main") -> str:
    """Skip link and brand link home (nav.js headerHtml's markup), then the section links with each section's sub
    entries after it, shown only without JavaScript. No skip link when the page has no <main> (main_id empty)."""
    links = "".join(
        f'<a href="{esc(base + n["href"])}">{esc(n["label"])}</a>'
        + "".join(f'<a href="{esc(base + s["href"])}">{esc(s["label"])}</a>' for s in n.get("sub") or [])
        for n in site.get("nav", []) if n.get("id") != "home"
    )
    skip = f'<a class="skip-link" href="#{esc(main_id)}">Skip to content</a>' if main_id else ""
    return (
        skip + '<div class="site-header-inner">'
        f'<a class="brand" href="{esc(base)}index.html">HART<span>Railroad · Neville Island</span></a>'
        '<noscript><nav class="nav" aria-label="Primary" style="display:flex;flex-wrap:wrap;gap:0.3rem 1rem;'
        f'font-weight:600">{links}</nav></noscript></div>'
    )


def footer_html(site: dict, base: str) -> str:
    """The footer line mountChrome writes (the public site has no engineering desk link)."""
    about = next((n for n in site.get("nav", []) if n.get("id") == "about"), None)
    out = "HART Railroad · Neville Island"
    if about:
        out += f' · <a href="{esc(base + about["href"])}">About</a>'
    ch = site.get("channels") or {}
    follow = [f'<a href="{esc(ch[k])}">{label}</a>' for k, label in (("youtube", "YouTube"), ("tiktok", "TikTok")) if ch.get(k)]
    if follow:
        out += " · Follow along: " + " · ".join(follow)
    return out


def add_static_chrome(dest: Path) -> int:
    """Fill each built page's empty header and footer; the number of pages changed."""
    site = json.loads((dest / "data" / "site.json").read_text(encoding="utf-8"))
    changed = 0
    for page in sorted(dest.rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        m = _NAV_SRC.search(text)
        if not m or "data-ops-" not in text or not _EMPTY_HEADER.search(text):
            continue
        base = m.group(1)
        main_id, new = main_target(text)
        new = _EMPTY_HEADER.sub(lambda h: h.group(1) + header_html(site, base, main_id) + h.group(2), new, count=1)
        new = _EMPTY_FOOTER.sub(lambda f: f.group(1) + footer_html(site, base) + f.group(2), new, count=1)
        if new != text:
            page.write_text(new, encoding="utf-8")
            changed += 1
    return changed


def main_target(text: str) -> tuple[str, str]:
    """(the skip link's target, the page): the first <main>'s id, after giving it id="main" when it has none, as
    nav.js mountSkipTarget does; ("", page) when the page has no <main>."""
    m = _MAIN.search(text)
    if not m:
        return "", text
    found = re.search(r"""\bid=["']([^"']+)["']""", m.group(1))
    if found:
        return found.group(1), text
    return "main", text[: m.start()] + f'<main id="main"{m.group(1)}>' + text[m.end():]


def _href(rel: str, base: str) -> str:
    """The primer script's href(): web links and ../ paths as given, the rest from the site root."""
    return rel if re.match(r"https?:", rel, re.I) or rel.startswith("../") else base + rel


def _paras(items: list | None, cls: str = "") -> str:
    attr = f' class="{cls}"' if cls else ""
    return "".join(f"<p{attr}>{esc(p)}</p>" for p in items or [])


def _list(items: list) -> str:
    return f"<ul>{''.join(f'<li>{i}</li>' for i in items)}</ul>" if items else ""


def _link(href: str, label: str) -> str:
    return f'<a href="{esc(href)}">{esc(label)}</a>'


def _job_code(job: dict, base: str) -> str:
    """A job's code, linked to its sheet when it has one (D749, NVL, CK1), as the page script draws it."""
    return _link(_href(job["href"], base), job["code"]) if job.get("href") else esc(job["code"])


def primer_html(data: dict, industries: list, base: str = "../") -> str:
    """The primer's text from briefing.json, in the sections and order the page script draws (no photos)."""
    out = [f"<p>{esc(data.get('lede'))}</p>"] if data.get("lede") else []
    fn = data.get("firstNight")
    if fn:
        out.append('<section class="panel first-night" id="first-night">')
        if fn.get("kicker"):
            out.append(f'<p class="box-kicker">{esc(fn["kicker"])}</p>')
        out.append(f"<h2>{esc(fn.get('heading'))}</h2>" + _paras(fn.get("paragraphs")))
        out.append(_list([f"<strong>{esc(b['label'])}.</strong> {esc(b['text'])}" for b in fn.get("bullets") or []]))
        if fn.get("links"):
            out.append('<p class="small">Before you come: '
                       + " · ".join(_link(_href(l["href"], base), l["label"]) for l in fn["links"]) + "</p>")
        out.append("</section>")
    for sec in data.get("sections") or []:
        out.append(f'<section class="panel" id="{esc(sec.get("id"))}"><h2>{esc(sec.get("heading"))}</h2>')
        if sec.get("intro"):
            out.append(f'<p class="muted">{esc(sec["intro"])}</p>')
        out.append(_paras(sec.get("paragraphs")) + _list([esc(b) for b in sec.get("bullets") or []]))
        if sec.get("placards"):
            skip = sec.get("exclude") or []
            out.append(_list([esc(i.get("name")) for i in industries
                              if i.get("category") != "interchange" and i.get("spot") not in skip]))
        out.append(_list([f"<strong>{_job_code(j, base)}</strong>, {esc(j['name'])}: {esc(j['blurb'])}"
                          for j in sec.get("jobs") or []]))
        out.append(_list([f"<strong>{esc(b['color'])}</strong>: {esc(b['dest'])} ({esc(b['train'])})"
                          for b in sec.get("blocks") or []]))
        fg = sec.get("figure")
        if fg:
            out.append(f'<p class="small">{esc(fg.get("caption"))} {_link(_href(fg["pdf"], base), "PDF to print")}</p>'
                       if fg.get("pdf") else f'<p class="small">{esc(fg.get("caption"))}</p>')
        if sec.get("link"):
            out.append(f"<p>{_link(_href(sec['link']['href'], base), sec['link']['label'])}</p>")
        out.append("</section>")
    deeper = data.get("deeper") or {}
    out.append(f'<section class="panel" id="deeper"><h2>{esc(deeper.get("heading", "If you want to dig deeper"))}</h2>')
    out.append(_paras(deeper.get("paragraphs")))
    out.append(_list([_link(_href(r["href"], base), r["label"]) for r in deeper.get("refs") or []]))
    if data.get("links"):
        if deeper.get("linksIntro"):
            out.append(f"<p>{esc(deeper['linksIntro'])}</p>")
        out.append(_list([_link(l["href"], l["label"]) for l in data["links"]]))
    so = data.get("signoff")
    if so:
        out.append(f'<div class="signoff"><p>{esc(so.get("text"))}</p><p><strong>{esc(so.get("name"))}</strong></p>'
                   f'<p>{esc(so.get("title"))}</p><p class="muted">{esc(so.get("org"))}</p></div>')
    out.append("</section>")
    return "".join(out)


def add_primer_text(dest: Path) -> bool:
    """Put the primer's text in a <noscript> inside #briefing-body, hiding the Loading line without JavaScript.
    False when the page or its Loading line is not there (nothing written)."""
    page = dest / PRIMER_REL
    if not page.is_file():
        return False
    text = page.read_text(encoding="utf-8")
    if not _PRIMER_BODY.search(text):
        return False
    data = json.loads((dest / "data" / "briefing.json").read_text(encoding="utf-8"))
    ind_path = dest / "data" / "industries.json"
    industries = json.loads(ind_path.read_text(encoding="utf-8")).get("industries", []) if ind_path.is_file() else []
    block = ("<noscript><style>#briefing-body > p.muted { display: none; }</style>"
             + primer_html(data, industries) + "</noscript>")
    page.write_text(_PRIMER_BODY.sub(lambda m: m.group(1) + m.group(2) + block + m.group(3), text, count=1),
                    encoding="utf-8")
    return True


def nojs_stage(dest: Path) -> None:
    """Stage 7b: static header and footer on every page, the primer's text on the primer, and the crew pages' and
    the publications shelf's content."""
    n = add_static_chrome(dest)
    primer = add_primer_text(dest)
    crew = portal_nojs_crew.add_crew_pages(dest)
    shelf = portal_nojs_crew.add_shelf(dest)
    print(f"No-JS fallbacks: header and footer on {n} pages" + (", primer text" if primer else "")
          + f", content on {len(crew)} crew pages" + (", publications shelf" if shelf else ""))
    if not primer and (dest / PRIMER_REL).is_file():
        print("WARNING: primer text not added: #briefing-body no longer holds the Loading line portal_nojs.py looks for")
