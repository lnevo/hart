"""Head tags and provenance for the built pages: icon and share tags (stage 8 of the site build) and the
schema.org JSON-LD, llms.txt, robots.txt and sitemap.xml (stage 9).

Part of the site build, prepare_github_pages.py, which re-exports these names.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path

import portal_common
import provenance
import share_cards
from portal_common import SHARE_DESCRIPTION, PortalBuildError
from portal_search_index import INDEX_NAME, INDEX_SKIP_PAGES


def _head_tags(rel: Path, title: str, desc: str | None = None, canonical: bool = True) -> str:
    """Icon and share tags; desc is the page's own meta description, which the page already carries.
    canonical adds <link rel="canonical"> to the www URL, so the bare domain and /index.html count as
    copies of it; redirect stubs, noindex pages and the 404 page go without."""
    # The 404 page is served for any missing path, so its links start at the site root.
    up = "/" if rel == Path("404.html") else "../" * (len(rel.parts) - 1)
    url = portal_common.SITE_URL + provenance.url_path(rel)
    title = html.escape(title, quote=True)
    # A page with its own description keeps its tag; the share tags repeat it.
    meta_desc = "" if desc is not None else f'\n  <meta name="description" content="{html.escape(SHARE_DESCRIPTION, quote=True)}">'
    desc = html.escape(desc or SHARE_DESCRIPTION, quote=True)
    card = share_cards.card_for(rel)  # the page's own thumbnail, or the site card
    image, alt = card["image"], html.escape(card["alt"], quote=True)
    link = f'\n  <link rel="canonical" href="{url}">' if canonical else ""
    return f"""
  <link rel="icon" href="{up}favicon.ico" sizes="any">
  <link rel="icon" type="image/png" href="{up}assets/icons/favicon-32.png" sizes="32x32">
  <link rel="apple-touch-icon" href="{up}assets/icons/apple-touch-icon.png">{link}{meta_desc}
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="HART Railroad">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{url}">
  <meta property="og:image" content="{portal_common.SITE_URL}{image}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{alt}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="hart-search" content="{INDEX_NAME}">"""


class _HeadDescription(HTMLParser):
    """The <head>'s own <meta name="description">, in any attribute order or quoting; None if it has none."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.description: str | None = None
        self._done = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._done or tag == "body":
            self._done = True
        elif tag == "meta" and (a.get("name") or "").lower() == "description" and self.description is None:
            self.description = (a.get("content") or "").strip()

    def handle_endtag(self, tag):
        if tag == "head":
            self._done = True


def _own_description(text: str) -> str | None:
    p = _HeadDescription()
    p.feed(text)
    return p.description


def _add_head_tags(dest_root: Path) -> None:
    for page in dest_root.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        if 'rel="icon"' in text or "</title>" not in text:
            continue
        m = re.search(r"<title>(.*?)</title>", text, re.S)
        title = html.unescape(m.group(1).strip()) if m else "HART Railroad"
        desc = _own_description(text)
        rel = page.relative_to(dest_root)
        canonical = rel.as_posix() not in INDEX_SKIP_PAGES and not provenance.skipped(text)
        page.write_text(
            text.replace("</title>", "</title>" + _head_tags(rel, title, desc, canonical), 1),
            encoding="utf-8",
        )


def _add_provenance(dest_root: Path) -> list[str]:
    """schema.org JSON-LD on every page saying whether it is real history, fiction or layout
    documentation, plus llms.txt, robots.txt and sitemap.xml at the root. Returns the pages
    provenance.json does not classify; the build stops on any."""
    data = provenance.load()
    # Pages the search index leaves out (the 404 page, the script redirect docs/view.html) stay out here too.
    pages = {
        rel: (dest_root / rel).read_text(encoding="utf-8")
        for rel in (page.relative_to(dest_root) for page in dest_root.rglob("*.html"))
        if rel.as_posix() not in INDEX_SKIP_PAGES
    }
    missing = provenance.unclassified(pages, data)
    if missing:
        return missing
    listed: dict[Path, tuple[str, str]] = {}
    for rel, text in pages.items():
        if provenance.skipped(text):
            continue
        # An implied <head> (no tag) still ends at the first body content, so after </title> is in it.
        anchor = "</head>" if "</head>" in text else "</title>" if "</title>" in text else None
        if anchor is None:
            raise PortalBuildError(f"{rel}: no </head> or </title> for the provenance JSON-LD")
        title = provenance.page_title(text) or "HART Railroad"
        desc = _own_description(text) or SHARE_DESCRIPTION
        tag = provenance.json_ld(rel, title, portal_common.SITE_URL, desc, data, provenance.sources(text))
        new = text.replace("</head>", tag + "\n</head>", 1) if anchor == "</head>" else text.replace("</title>", "</title>" + tag, 1)
        (dest_root / rel).write_text(new, encoding="utf-8")
        own = _own_description(text)
        listed[rel] = (title, "" if own in (None, SHARE_DESCRIPTION) else own)
    (dest_root / "llms.txt").write_text(provenance.llms_txt(listed, data, portal_common.SITE_URL), encoding="utf-8")
    (dest_root / "robots.txt").write_text(provenance.robots_txt(portal_common.SITE_URL), encoding="utf-8")
    (dest_root / "sitemap.xml").write_text(provenance.sitemap_xml(list(listed), portal_common.SITE_URL), encoding="utf-8")
    return []
