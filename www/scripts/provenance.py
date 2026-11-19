"""What kind of truth each public page carries, for search engines and AI crawlers.

The site mixes real history of Neville Island with an invented railroad set on it. Every
published HTML page is classified in provenance.json (prototype, fiction, hobby or mixed); the
build writes that class into each page's head as schema.org JSON-LD and lists it in llms.txt,
and writes robots.txt and sitemap.xml beside them. A page the map does not cover stops the build.
"""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from xml.sax.saxutils import escape

MAP = Path(__file__).resolve().parent / "provenance.json"
CLASSES = ("prototype", "fiction", "hobby", "mixed")

# schema.org type and genre per class. Fiction is a CreativeWork; the others are factual articles.
_SCHEMA = {
    "prototype": ("Article", "History"),
    "fiction": ("CreativeWork", "Fiction"),
    "hobby": ("TechArticle", "Model railroad documentation"),
    "mixed": ("CreativeWork", None),
}


def load(path: Path = MAP) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("site", "classes", "rules"):
        if key not in data:
            raise ValueError(f"{path.name}: missing '{key}'")
    if set(data["classes"]) != set(CLASSES):
        raise ValueError(f"{path.name}: 'classes' must describe exactly {', '.join(CLASSES)}")
    for pattern, rule in data["rules"].items():
        if rule.get("class") not in CLASSES:
            raise ValueError(f"{path.name}: rule {pattern!r} has class {rule.get('class')!r}")
        if rule["class"] == "mixed" and not rule.get("parts"):
            raise ValueError(f"{path.name}: mixed rule {pattern!r} must name its parts")
        for part in rule.get("parts", []):
            if part.get("class") not in ("prototype", "fiction", "hobby") or not part.get("section"):
                raise ValueError(f"{path.name}: rule {pattern!r} has a bad part {part!r}")
    return data


def rule_for(rel: Path, data: dict) -> dict | None:
    """The most specific rule for a page: an exact path beats a folder, a longer folder beats a shorter."""
    path = rel.as_posix()
    if path in data["rules"]:
        return data["rules"][path]
    best = None
    for pattern, rule in data["rules"].items():
        if pattern.endswith("/") and path.startswith(pattern) and (best is None or len(pattern) > len(best[0])):
            best = (pattern, rule)
    return best[1] if best else None


class _Meta(HTMLParser):
    """Whether a page's meta tags redirect it or keep it out of search, in any attribute order or quoting."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if a.get("http-equiv", "").lower() == "refresh":
            self.skip = True
        elif a.get("name", "").lower() == "robots" and "noindex" in a.get("content", "").lower():
            self.skip = True


def skipped(text: str) -> bool:
    """Redirect stubs and noindex pages carry no content of their own."""
    p = _Meta()
    p.feed(text)
    return p.skip


def unclassified(pages: dict[Path, str], data: dict) -> list[str]:
    """Pages with content of their own that no rule covers; pass only the pages to be published."""
    return sorted(rel.as_posix() for rel, text in pages.items() if not skipped(text) and rule_for(rel, data) is None)


_BLOCKS = {"p", "div", "section", "article", "footer", "nav", "table", "figure", "aside", "header", "main"}


class _Sources(HTMLParser):
    """Items of the first list after a heading that reads "Source" or "Sources"."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[str] = []
        self._heading: list[str] | None = None
        self._armed = self._done = False
        self._depth = 0  # list nesting inside the sources list
        self._item: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        if re.fullmatch(r"h[1-6]", tag):
            if self._armed and not self._depth:
                self._done = True  # next section began before any list
            else:
                self._heading = []
        elif tag in ("ul", "ol") and self._armed:
            self._depth += 1
        elif self._armed and not self._depth and tag in _BLOCKS:
            self._done = True  # the section is prose, not a list: no citations to read
        elif tag == "li" and self._depth == 1:
            self._item = []

    def handle_endtag(self, tag):
        if self._done:
            return
        if re.fullmatch(r"h[1-6]", tag) and self._heading is not None:
            self._armed = "".join(self._heading).strip().lower() in ("source", "sources")
            self._heading = None
        elif tag == "li" and self._item is not None and self._depth == 1:
            text = re.sub(r"\s+", " ", "".join(self._item)).strip()
            if text:
                self.items.append(text if len(text) <= 300 else text[:299].rstrip() + "…")
            self._item = None
        elif tag in ("ul", "ol") and self._depth:
            self._depth -= 1
            if not self._depth:
                self._done = True

    def handle_data(self, data):
        if self._heading is not None:
            self._heading.append(data)
        elif self._item is not None:
            self._item.append(data)


def sources(text: str) -> list[str]:
    """The page's own source list, as plain text citations."""
    p = _Sources()
    p.feed(text)
    return p.items


def json_ld(rel: Path, title: str, site_url: str, desc: str, data: dict, cited: list[str] = ()) -> str:
    """The page's JSON-LD; site_url is the public root the build is made for."""
    url = site_url + url_path(rel)
    rule = rule_for(rel, data)
    if rule is None:
        raise KeyError(f"provenance.json does not classify {rel.as_posix()}")
    kind, genre = _SCHEMA[rule["class"]]
    site = data["site"]
    work: dict = {
        "@type": kind,
        "name": title,
        "description": rule.get("note") or data["classes"][rule["class"]],
        "additionalProperty": {"@type": "PropertyValue", "name": "provenance", "value": rule["class"]},
    }
    if genre:
        work["genre"] = genre
    if rule["class"] == "fiction":
        work["isBasedOn"] = site["setting"]
    if rule.get("parts"):
        work["hasPart"] = [
            {
                "@type": _SCHEMA[p["class"]][0],
                "name": p["section"],
                "genre": _SCHEMA[p["class"]][1],
                "additionalProperty": {"@type": "PropertyValue", "name": "provenance", "value": p["class"]},
            }
            for p in rule["parts"]
        ]
    # A map citation starting with / is a page on this site.
    mapped = [site_url + c[1:] if c.startswith("/") else c for c in rule.get("citation", [])]
    citation = mapped + [c for c in cited if c not in mapped]
    if citation:
        work["citation"] = citation
    page = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "url": url,
        "description": desc,
        "isPartOf": {"@type": "WebSite", "name": site["name"], "url": site_url},
        "mainEntity": work,
    }
    body = json.dumps(page, ensure_ascii=False, indent=None).replace("</", "<\\/")
    return f'\n  <script type="application/ld+json">{body}</script>'


def llms_txt(pages: dict[Path, tuple[str, str]], data: dict, site_url: str) -> str:
    """llms.txt (llmstxt.org): what the site is, then every page grouped by class."""
    site = data["site"]
    out = [f"# {site['name']}", "", f"> {site['summary']}", ""]
    out += [line for line in site["notes"]] + [""]
    for cls in CLASSES:
        rows = sorted((rel, t, d) for rel, (t, d) in pages.items() if rule_for(rel, data)["class"] == cls)
        if not rows:
            continue
        out += [f"## {data['classes'][cls]}", ""]
        # A folder's note covers every page in it, so it is written once, above the pages.
        folders = sorted(
            (pattern, rule["note"]) for pattern, rule in data["rules"].items()
            if pattern.endswith("/") and rule["class"] == cls and rule.get("note")
            and any(rule_for(rel, data) is rule for rel, _, _ in rows)
        )
        out += [f"Everything under /{pattern}: {note}" for pattern, note in folders]
        if folders:
            out.append("")
        for rel, title, desc in rows:
            rule = rule_for(rel, data)
            own = data["rules"].get(rel.as_posix()) is rule
            extra = (rule.get("note") if own else None) or desc
            if rule.get("parts"):
                extra = (extra + " " if extra else "") + "Sections: " + "; ".join(f"{p['section']} ({p['class']})" for p in rule["parts"]) + "."
            line = f"- [{title}]({site_url}{url_path(rel)})"
            out.append(f"{line}: {extra}" if extra else line)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def robots_txt(site_url: str) -> str:
    return (
        "# Everyone may crawl the whole site, AI crawlers included.\n"
        "# Which pages are real history and which are fiction: /llms.txt\n"
        "User-agent: *\n"
        "Allow: /\n"
        "Crawl-delay: 10\n"
        "\n"
        f"Sitemap: {site_url}sitemap.xml\n"
    )


def sitemap_xml(paths: list[Path], site_url: str) -> str:
    urls = "".join(f"  <url><loc>{escape(site_url + url_path(p))}</loc></url>\n" for p in sorted(paths))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n"
    )


def url_path(rel: Path) -> str:
    """Site-relative URL of a built page: a folder's index.html is served as the folder."""
    if rel.name != "index.html":
        return rel.as_posix()
    return "" if rel.parent == Path(".") else rel.parent.as_posix() + "/"


def page_title(text: str) -> str:
    m = re.search(r"<title>(.*?)</title>", text, re.S)
    # Same cleanup as the search index: the site name suffix adds nothing in a list of the site's pages.
    return re.sub(r"\s+[—-]\s+HART$", "", html.unescape(m.group(1).strip())) if m else ""
