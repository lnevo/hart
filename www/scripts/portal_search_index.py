"""The site search index (search-index.json, stage 13 of the site build): one record per built page, glossary
term, industry, crew sheet and public photo, written last from the finished tree. It fails on a leak pattern or the
private name in any record.

Part of the site build, prepare_github_pages.py, which re-exports these names.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from photo_tabs import tab_subs
from portal_common import LEAK_PATTERNS, PORTAL, SHARE_DESCRIPTION, PortalBuildError

# The private-name check works by fingerprint, so the name itself is never written in this script.
sys.path.insert(0, str(PORTAL.parent / "ops/hart-ops/card_pipeline"))
from private_name import contains_private_name  # noqa: E402


# ---- Search index (search-index.json) -------------------------------------------------------
# Written last, from the built HTML, so it never holds text the leak checks or the data-local-only
# strip removed. Stage 1 has one "page" record per page; the search box (js/search.js) reads it.
INDEX_NAME = "search-index.json"
INDEX_VERSION = 1
SNIPPET_MAX, TEXT_MAX = 160, 8000  # about 95 KB gzipped for the whole index, fetched on first open
# Pages that are never found: the 404 page, the document viewer shell, and Google's Search Console
# ownership file, which must be served byte for byte (no provenance tag, not in the sitemap).
INDEX_SKIP_PAGES = {"404.html", "docs/view.html", "google542f49f1175c633f.html"}
# Pages whose content is rows drawn by script: only the title and the intro paragraph are indexed.
INDEX_TITLE_ONLY = {"behind/tables-file.html", "behind/wiring.html"}
_INDEX_SKIP_TAGS = {"script", "style", "template", "noscript", "svg", "header", "nav", "footer", "button", "select", "option"}
_REDIRECT = re.compile(r'http-equiv=["\']?refresh|location\.replace\(|(?<![\w-])location(?:\.href)?\s*=[^=]', re.I)
# Publication headers ("SM-02 · Revision A · Effective 23 July 2026") say nothing about the page.
_BOILERPLATE = re.compile(r"\bRevision [A-Z]\b|\bEffective \d", re.I)
# List, table and definition text is searchable too (glossary terms, spot-sheet rows).
_INDEX_TEXT_TAGS = ("h1", "h2", "h3", "p", "li", "dt", "dd", "td", "th")


class _PageText(HTMLParser):
    """Title, headings and paragraphs of a built page, outside chrome, scripts and templates."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title, self.description = "", ""
        self.h1: list[str] = []
        self.h2: list[str] = []
        self.paras: list[str] = []
        self.other: list[str] = []  # h3, list items, table cells, definitions
        self.noindex = False
        self._skip = 0
        self._cur: str | None = None  # tag being collected
        self._buf: list[str] = []
        self._in_title = False
        self._title_done = False  # inline SVGs carry their own <title>; only the page's counts

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title" and not self._title_done:
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or "").lower()
            content = a.get("content") or ""
            if name == "robots" and "noindex" in content.lower():
                self.noindex = True
            elif name == "description" and content and content != SHARE_DESCRIPTION:
                self.description = content  # the page's own, not the share-tag default
        if tag in _INDEX_SKIP_TAGS:
            self._skip += 1
        elif not self._skip and self._cur is None and tag in _INDEX_TEXT_TAGS:
            self._cur, self._buf = tag, []

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title, self._title_done = False, True
        if tag in _INDEX_SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag == self._cur:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if text and not text.startswith("Loading"):  # placeholders the page script replaces
                {"h1": self.h1, "h2": self.h2, "p": self.paras}.get(tag, self.other).append(text)
            self._cur = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._cur is not None and not self._skip:
            self._buf.append(data)


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"<[^<>]{0,60}>", " ", text)  # tags quoted as page text (code samples) are noise
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-—") + "…"


def _index_record(rel: Path, text: str) -> dict | None:
    """One search record for a built page, or None when the page should not be found."""
    name = rel.as_posix()
    if name in INDEX_SKIP_PAGES:
        return None
    page = _PageText()
    page.feed(text)
    if page.noindex:
        return None
    title = re.sub(r"\s+", " ", page.title).strip()
    title = re.sub(r"\s+[—-]\s+HART$", "", title) or (page.h1[0] if page.h1 else "")
    paras = [p for p in page.paras if len(p) >= 40 and not _BOILERPLATE.search(p)]
    # Redirect stubs: a refresh or script jump with little to read, or a "Moved" notice.
    if page.h1[:1] == ["Moved"] or (_REDIRECT.search(text) and len(" ".join(paras)) < 200):
        return None
    if not title or not (page.h1 or paras or page.description):
        return None
    intro = page.description or (paras[0] if paras else "")
    if name in INDEX_TITLE_ONLY:
        body = [intro]
    else:
        heads = [h for h in page.h1[:1] + page.h2 if h.lower() != title.lower()]
        rest = [p for p in page.paras + page.other if p != intro and not _BOILERPLATE.search(p)]
        body = heads + rest
    return {
        "title": title,
        "url": name,
        "kind": "page",
        "snippet": _clip(intro or title, SNIPPET_MAX),
        "text": _clip(" ".join(b for b in body if b), TEXT_MAX),
    }


def _check_index(index: dict) -> list[str]:
    """Leak patterns (hosts, workspace paths) and the private name, per record field."""
    bad = []
    for rec in index["records"]:
        for field, value in rec.items():
            if LEAK_PATTERNS.search(value) or contains_private_name(value):
                bad.append(f"{rec['url']} ({field})")  # never echo the matched text
    return bad


# ---- Term, industry and crew-sheet records --------------------------------------------------
# Read from the built copies (after the local-only and external-path strips), public fields only.
GLOSSARY_PAGE = "operators/glossary/index.html"
SPOT_SHEETS = "crew/industries/index.html"  # spot sheets are drawn by js/crew.js with id=<industry id>


class _Terms(HTMLParser):
    """The glossary's <dt id> / <dd> pairs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.terms: list[dict] = []
        self._tag: str | None = None
        self._buf: list[str] = []
        self._id = ""

    def handle_starttag(self, tag, attrs):
        if tag in ("dt", "dd"):
            self._tag, self._buf = tag, []
            if tag == "dt":
                self._id = dict(attrs).get("id") or ""

    def handle_endtag(self, tag):
        if tag != self._tag:
            return
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if tag == "dt":
            self.terms.append({"id": self._id, "term": text, "defn": ""})
        elif self.terms and not self.terms[-1]["defn"]:
            self.terms[-1]["defn"] = text
        self._tag = None

    def handle_data(self, data):
        if self._tag:
            self._buf.append(data)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _record(title: str, url: str, kind: str, snippet: str, text: str, thumb: str = "") -> dict:
    rec = {"title": title, "url": url, "kind": kind, "snippet": _clip(snippet or title, SNIPPET_MAX), "text": _clip(text, TEXT_MAX)}
    if thumb:
        rec["thumb"] = thumb  # the one optional field: a small built image, for photo-like kinds only
    return rec


def _thumb(dest_root: Path, item: dict) -> str:
    """The item's built grid thumbnail as a site-root-relative path, or "" when it is not in the build."""
    rel = str(item.get("thumb") or "")
    if not rel or rel.startswith(("/", "http:", "https:")) or ".." in rel.split("/"):
        return ""
    return rel if (dest_root / rel).is_file() else ""


def _glossary_records(dest_root: Path) -> list[dict]:
    """One "term" record per glossary entry, linked to its #id on the glossary page."""
    page = dest_root / GLOSSARY_PAGE
    if not page.is_file():
        return []
    parsed = _Terms()
    parsed.feed(page.read_text(encoding="utf-8", errors="replace"))
    return [
        _record(t["term"], f"{GLOSSARY_PAGE}#{t['id']}", "term", t["defn"], t["defn"])
        for t in parsed.terms
        if t["id"] and t["term"] and t["defn"]
    ]


def _industry_records(dest_root: Path) -> list[dict]:
    """One "industry" record per company: blurb and commodities (industries.json) merged with the
    spot sheet's history, traffic and spots (crew.json). Links to the spot sheet, where the history,
    traffic and every spot are; the Primer placard shows only the blurb and links there anyway."""
    cards = _read_json(dest_root / "data" / "industries.json").get("industries") or []
    sheet = _read_json(dest_root / "data" / "crew.json").get("spotsheet") or {}
    sheets = {i["id"]: i for i in (sheet.get("industries") or []) if i.get("id")}
    for o in sheet.get("offline") or []:
        if o.get("id"):
            sheets.setdefault(o["id"], o)
    records, seen = [], set()
    for card in cards:
        sid = card.get("spot") or ""
        if sid in sheets:
            seen.add(sid)
            records.append(_industry(card, sheets[sid], sid))
    for sid, s in sheets.items():
        if sid not in seen and (s.get("history") or s.get("about")):  # a sheet with no card still deserves a record
            records.append(_industry({}, s, sid))
    return records


def _industry(card: dict, s: dict, sid: str) -> dict:
    name = s.get("name") or card.get("name") or sid
    blurb = card.get("blurb") or (s.get("about") or [""])[0]
    parts = [blurb, ", ".join(card.get("commodities") or []), s.get("traffic", ""), *(s.get("history") or []), *(s.get("about") or [])]
    parts += [s.get("inLabel", ""), *(s.get("inbound") or []), s.get("outLabel", ""), *(s.get("outbound") or [])]
    parts += [" ".join(r[1:3]) for r in s.get("spots") or []]  # spot name and car type
    return _record(name, f"{SPOT_SHEETS}#{sid}", "industry", blurb, " ".join(p for p in parts if p))


def _flat(*items) -> list[str]:
    """Strings from nested lists and dicts of display values, in order."""
    out: list[str] = []
    for it in items:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, list):
            out += _flat(*it)
        elif isinstance(it, dict):
            out += _flat(*it.values())
    return out


def _crew_records(dest_root: Path) -> list[dict]:
    """One "crew" record per job or publication in crew.json: jobs, TT-23, EQ-01, colors, station maps.
    Each links to its own crew page (a single sheet, so no anchor). Fields are listed, not walked,
    so source paths, image paths and engine photos never reach the index."""
    crew = _read_json(dest_root / "data" / "crew.json")
    out: list[dict] = []

    def add(title, url, snippet, *parts):
        if (dest_root / url).is_file():
            out.append(_record(title, url, "crew", snippet, " ".join(_flat(*parts))))

    for j in crew.get("jobs") or []:
        add(f"{j['code']} {j['name']}", f"crew/{j['id']}/index.html", j.get("summary", ""), j.get("title"), j.get("pub"),
            (j.get("engine") or {}).get("label"), j.get("summary"), j.get("steps"), j.get("sequence"), j.get("priority"),
            j.get("lineup"), j.get("talk"), [link.get("label") for link in j.get("links") or [] if isinstance(link, dict)])
    tt = crew.get("timetable")
    if tt:
        add(f"{tt['pub']} {tt['title']}", "crew/tt23/index.html", tt.get("summary", ""), tt.get("name"), tt.get("subtitle"),
            tt.get("summary"), tt.get("columns"), tt.get("rows"), tt.get("note"), tt.get("instructions"), tt.get("bulletin"))
    sc = crew.get("scale")
    if sc:
        add(f"{sc['pub']} {sc['title']}", "crew/scale/index.html", sc.get("summary", ""), sc.get("summary"), sc.get("sections"))
    colors = crew.get("colors") or []
    if colors:
        rows = [f"{c['label']} {c.get('dest', '')} {c.get('train', '')}" for c in colors]
        add("Color board", "crew/colors/index.html", "Which color goes to which destination and train.", "Colors", rows)
    ov = crew.get("overview")
    if ov:
        add(f"{ov['pub']} {ov['title']}", "crew/maps/index.html", ov.get("what", ""), ov.get("what"), ov.get("alt"))
    for m in crew.get("maps") or []:
        add(f"{m['pub']} {m['title']} station map", f"crew/maps/{m['id']}/index.html", m.get("what", ""), m.get("what"),
            m.get("alt"), m.get("tracks"), m.get("switches"), m.get("connects"))
    return out


FLEET_PAGE = "photos/index.html"
FLEET_KINDS = {"locos": "locomotive", "mow": "mow"}  # every other album is freight cars


def _fleet_records(dest_root: Path) -> list[dict]:
    """One record per rolling-stock photo that survived the build, from the built data/fleet-gallery.json.

    Only the public display fields are read (id, title, caption, road, number, type). The url opens the
    item on the Photos page (js/fleet.js: #rolling-stock/<id>); an item without an id has no link, so it is skipped.
    """
    path = dest_root / "data" / "fleet-gallery.json"
    if not path.is_file():
        return []
    records = []
    for item in json.loads(path.read_text(encoding="utf-8")).get("items") or []:
        fid, title = str(item.get("id") or ""), str(item.get("title") or "").strip()
        if not fid or not title:
            continue
        caption = str(item.get("caption") or "")
        kind = FLEET_KINDS.get(item.get("album"), "locomotive" if item.get("type") == "Locomotive" else "car")
        words = [str(item.get(k) or "") for k in ("road", "number", "type")] + [caption]
        records.append(_record(title, f"{FLEET_PAGE}#rolling-stock/{fid}", kind, caption, " ".join(w for w in words if w), _thumb(dest_root, item)))
    return records


# A published credit is a source line; one carrying an address or phone number is left out.
_CONTACT = re.compile(r"@|https?://|www\.|\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", re.I)


def _archive_records(dest_root: Path) -> list[dict]:
    """One "archive" record per item the public Curated tab shows, from the built data/archive.json.

    js/archive.js shows a public visitor only bucket "curated" (the build also drops "public": false and
    items whose original is missing). Read: title, caption, date, kind label, tags and a credit with no contact
    details. Never read: reason, origin, rights, credit_confidence, src, pdf or source_url. Opens at
    photos/#historical/<id> (HARTArchive.openItem).
    """
    data = _read_json(dest_root / "data" / "archive.json")
    labels = {k.get("id"): str(k.get("label") or "") for k in data.get("kinds") or []}
    records = []
    for item in data.get("items") or []:
        aid, title = str(item.get("id") or ""), str(item.get("title") or "").strip()
        if not aid or not title or item.get("bucket") != "curated" or item.get("public") is False:
            continue
        credit = str(item.get("credit") or "").strip()
        credit = "" if _CONTACT.search(credit) else credit
        tags = [str(t).replace("-", " ") for t in item.get("tags") or []]
        words = [str(item.get("date") or ""), labels.get(item.get("kind"), ""), *tags, credit]
        caption = str(item.get("caption") or "")
        records.append(_record(title, f"{FLEET_PAGE}#historical/{aid}", "archive", caption, " ".join(w for w in [caption, *words] if w), _thumb(dest_root, item)))
    return records


def _photo_records(dest_root: Path) -> list[dict]:
    """One "photo" record per layout-room photo that survived the build, from the built data/gallery.json.

    Read: title, caption, date, credit and the album's label. Opens at photos/#layout/<id> (HARTGallery.openItem);
    an item without an id has no link, so it is skipped.
    """
    data = _read_json(dest_root / "data" / "gallery.json")
    labels = {a.get("id"): str(a.get("label") or "") for a in data.get("albums") or []}
    shown = set(tab_subs(dest_root, "layout").values())  # the albums the Layout tab has chips for and mounts
    records = []
    for item in data.get("items") or []:
        pid, title = str(item.get("id") or ""), str(item.get("title") or "").strip()
        if not pid or not title or item.get("album") not in shown:
            continue
        caption = str(item.get("caption") or "")
        words = [caption, labels.get(item.get("album"), ""), str(item.get("date") or ""), str(item.get("credit") or "")]
        records.append(_record(title, f"{FLEET_PAGE}#layout/{pid}", "photo", caption, " ".join(w for w in words if w), _thumb(dest_root, item)))
    return records


def _mark_articles(records: list[dict], dest_root: Path) -> None:
    """Page records for the articles listed in data/articles.json (the ones under library/) become kind "article"."""
    hrefs = {str(a.get("href") or "") for a in _read_json(dest_root / "data" / "articles.json").get("items") or []}
    for rec in records:
        if rec["kind"] == "page" and rec["url"] in hrefs and rec["url"].startswith("library/"):
            rec["kind"] = "article"


SEARCH_THUMB_PX = 80  # shown at 40 px; 2x for sharp screens


def _search_thumb_stamp(dest: Path) -> bytes | None:
    """The source stamp saved in a search copy's JPEG comment, or None when there is no readable copy."""
    from PIL import Image
    try:
        with Image.open(dest) as im:
            return im.info.get("comment")
    except OSError:
        return None


def _search_thumbs(records: list[dict], dest_root: Path) -> None:
    """Point each record's thumb at a small square copy (assets/search/), so a results list does not pull
    640 px grid thumbnails. Without Pillow, or if a copy cannot be made, the record keeps the grid thumb."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return
    out_dir = dest_root / "assets" / "search"
    for rec in records:
        src = rec.get("thumb")
        if not src:
            continue
        name = re.sub(r"[^a-z0-9]+", "-", Path(src).with_suffix("").as_posix().lower()).strip("-") + ".jpg"
        dest = out_dir / name
        try:
            source = dest_root / src
            try:
                st = source.stat()
                stamp = f"{st.st_size}:{st.st_mtime_ns}".encode()  # kept in the copy, so a replaced photo is noticed
            except OSError:
                stamp = None
            if stamp is None:
                if not dest.is_file():
                    continue                                      # no source and no copy: keep the grid thumb
            elif _search_thumb_stamp(dest) != stamp:
                out_dir.mkdir(parents=True, exist_ok=True)
                with Image.open(source) as im:
                    small = ImageOps.fit(im.convert("RGB"), (SEARCH_THUMB_PX, SEARCH_THUMB_PX))
                    small.save(dest, "JPEG", quality=78, optimize=True, comment=stamp)
            rec["thumb"] = dest.relative_to(dest_root).as_posix()
        except OSError:
            continue


def build_search_index(dest_root: Path) -> dict:
    """Write dest_root/search-index.json from the built pages; fail if it holds a leak or the private name."""
    records = []
    for page in sorted(dest_root.rglob("*.html")):
        rec = _index_record(page.relative_to(dest_root), page.read_text(encoding="utf-8", errors="replace"))
        if rec:
            records.append(rec)
    # Record kinds built from data or a few pages' markup, one call each (add new kinds here).
    extra = _glossary_records(dest_root) + _industry_records(dest_root) + _crew_records(dest_root)
    # A crew page is drawn by script, so its own page record is a bare title; the sheet record replaces it.
    extra_urls = {e["url"] for e in extra}
    records = [r for r in records if r["url"] not in extra_urls] + extra
    records += _fleet_records(dest_root) + _archive_records(dest_root) + _photo_records(dest_root)
    _mark_articles(records, dest_root)
    _search_thumbs(records, dest_root)
    index = {
        "version": INDEX_VERSION,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "records": records,
    }
    if bad := _check_index(index):
        raise PortalBuildError("search index holds text that must not publish:\n" + "\n".join("  " + b for b in bad))
    (dest_root / INDEX_NAME).write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return index
