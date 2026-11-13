#!/usr/bin/env python3
"""Build the public operator portal tree that deploy_hartrailroad.sh publishes.

Only git-tracked files are published (never gitignored previews, drafts, or
stray local files), minus the engineering-desk material below. Gallery,
rolling-stock, and historical-archive photos that live in gitignored
../external/ mirrors are vendored in, resized, when present; without the
mirrors (or Pillow) they drop out, unless --require-mirrors is passed: then a
missing mirror or Pillow stops the build (deploy_hartrailroad.sh passes it, so a
deploy from a worktree without media/ cannot strip the photos). The build fails
if the output still names local hosts or paths. (The file name predates the move
off GitHub Pages.)

Usage: prepare_github_pages.py [DEST] [--site-url URL] [--require-mirrors]
"""

from __future__ import annotations

import argparse
import html
import os
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_tables_browser  # noqa: E402
import share_cards  # noqa: E402

PORTAL = Path(__file__).resolve().parents[1]
# The private-name check works by fingerprint, so the name itself is never written in this script.
sys.path.insert(0, str(PORTAL.parent / "ops/hart-ops/card_pipeline"))
from private_name import contains_private_name  # noqa: E402
# Build scripts, the owner's review desk, and pages that only work at the layout (localhost tools,
# workspace pointers) stay off the public site.
SKIP_DIRS = {Path("scripts"), Path("review"), Path("review-data"), Path("tools"), Path("reference")}
# Engineering-desk pages that name hosts, ports, or deploy steps stay off the public site,
# as do author notes and files no page links to.
SKIP_FILES = {
    Path("README.md"),
    Path("guides/digicon-system.html"),
    Path("data/signal-splits.json"),  # signal splits are under review; the wiring viewer hides that tab
    Path("data/invites.json"),  # invitation drafts; author reference only
    Path("data/panels.json"),
    Path("library/updated-history.txt"),
    Path("assets/media/hart-logo.png"),  # favicon source; the built icons are in assets/icons/
    Path("assets/media/coal-types.png"),
    Path("assets/icons/icon-192.png"),
    Path("helix/build-status.html"),  # the helix build status is a working file, not published
    Path("helix/files/HART_Neville_Helix_BUILD_STATUS.md"),
}
# Markdown sources for the library articles (the HTML pages are what's published) and invitation drafts.
SKIP_GLOBS = ("docs/*.md",)
# Strings that mean a local host, port, or workspace path leaked into the public tree.
LEAK_PATTERNS = re.compile(r"localhost|127\.0\.0\.1|/Users/|external/sts-docker-data|\.\./media/|media/archive/|media/hart-research|media/photos-layout|media/dj-trains|ops/car-cards")
# Data must not point into the mirrors either; scripts (and inline page scripts) test for that
# prefix when resolving logos and photos, so only data files are checked for it.
MIRROR_PREFIXES = ("../external/", "../media/", "../ops/", "../docs/")
DATA_LEAK = re.compile(r"\.\./(?:external|media|ops|docs)/")
LEAK_SUFFIXES = {".html", ".json", ".css", ".md", ".txt"}
# Share previews (Facebook, iMessage, …) read static tags only, so every page gets them at build time.
# The site is served at the domain root; override with --site-url or HART_SITE_URL.
SITE_URL = os.environ.get("HART_SITE_URL", "https://www.hartrailroad.com/")
SHARE_DESCRIPTION = (
    "Neville Island on the HART Railroad: the prototype's history and industries, "
    "operating sessions, and the layout build."
)


def _published_files() -> list[Path]:
    """Git-tracked portal files (working-tree content) that belong on the public site."""
    out = subprocess.run(
        ["git", "-C", str(PORTAL), "ls-files", "-z", "--", "."],
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    files = []
    for name in filter(None, out.split("\0")):
        rel = Path(name)
        if not (PORTAL / rel).is_file():  # deleted in the working tree
            continue
        if rel in SKIP_FILES or any(d in rel.parents for d in SKIP_DIRS):
            continue
        if any(rel.match(g) for g in SKIP_GLOBS) or rel.suffix == ".pyc" or rel.name == ".DS_Store":
            continue
        files.append(rel)
    return files


def _manifest() -> dict[str, str]:
    return json.loads((PORTAL / "scripts/published-files.json").read_text(encoding="utf-8"))


def _source(rel: str) -> Path:
    """Where a site-relative file really lives: its manifest source, or the site tree."""
    source = _manifest().get(rel)
    return PORTAL.parent / source if source else (PORTAL / rel).resolve()


def _copy_published(dest: Path) -> None:
    for rel in _published_files():
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PORTAL / rel, out)
    # Files the site publishes but does not hold: one source, named in the manifest.
    for name, source in _manifest().items():
        rel, src = Path(name), PORTAL.parent / source
        if rel in SKIP_FILES:
            continue
        if not src.is_file():
            raise SystemExit(f"published-files.json: missing source {source}")
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)


_LOCAL_ONLY = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\bdata-local-only\b[^>]*>")


def _strip_local_only(text: str) -> str:
    """Drop every element marked data-local-only (with its contents), not just hide it with JS."""
    while m := _LOCAL_ONLY.search(text):
        tag = m.group(1).lower()
        tags = re.compile(rf"<(/?){tag}\b[^>]*>", re.I)
        depth, end = 1, len(text)
        for t in tags.finditer(text, m.end()):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                end = t.end()
                break
        text = text[: m.start()] + text[end:]
    return text


def _strip_local_only_pages(dest_root: Path) -> None:
    for page in dest_root.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        if "data-local-only" in text:
            page.write_text(_strip_local_only(text), encoding="utf-8")


def _drop_external_paths(node: object) -> None:
    """Remove fields still pointing into ../external/ (source docx/pptx); pages already skip them when public."""
    if isinstance(node, dict):
        for key in [k for k, v in node.items() if isinstance(v, str) and v.startswith(MIRROR_PREFIXES)]:
            del node[key]
        for value in node.values():
            _drop_external_paths(value)
    elif isinstance(node, list):
        for value in node:
            _drop_external_paths(value)


def _strip_external_data(dest_root: Path) -> None:
    for path in sorted((dest_root / "data").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        _drop_external_paths(data)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _check_leaks(dest_root: Path) -> list[str]:
    hits = []
    for path in sorted(dest_root.rglob("*")):
        if path.suffix not in LEAK_SUFFIXES or not path.is_file():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if m := LEAK_PATTERNS.search(line) or (path.suffix == ".json" and DATA_LEAK.search(line)):
                hits.append(f"{path.relative_to(dest_root)}:{n}: {m.group(0)}")
    return hits


# ---- Search index (search-index.json) -------------------------------------------------------
# Written last, from the built HTML, so it never holds text the leak checks or the data-local-only
# strip removed. Stage 1 has one "page" record per page; the search box (js/search.js) reads it.
INDEX_NAME = "search-index.json"
INDEX_VERSION = 1
SNIPPET_MAX, TEXT_MAX = 160, 8000  # about 85 KB gzipped for the whole index, fetched on first open
# Pages that are never found: the 404 page and the document viewer shell.
INDEX_SKIP_PAGES = {"404.html", "docs/view.html"}
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


def _record(title: str, url: str, kind: str, snippet: str, text: str) -> dict:
    return {"title": title, "url": url, "kind": kind, "snippet": _clip(snippet or title, SNIPPET_MAX), "text": _clip(text, TEXT_MAX)}


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
        if sid not in seen and s.get("history"):  # a sheet with no card still deserves a record
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
            j.get("lineup"), j.get("talk"), j.get("links"))
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
    records = [r for r in records if r["url"] not in {e["url"] for e in extra}] + extra
    index = {
        "version": INDEX_VERSION,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "records": records,
    }
    if bad := _check_index(index):
        raise SystemExit("search index holds text that must not publish:\n" + "\n".join("  " + b for b in bad))
    (dest_root / INDEX_NAME).write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return index


def _keep_src(src: str, dest_root: Path) -> bool:
    if not src or src.startswith("../"):
        return False
    if src.startswith("http://") or src.startswith("https://"):
        return True
    return (dest_root / src).is_file()


PHOTO_DATA = ("data/gallery.json", "data/fleet-gallery.json", "data/archive.json")


def _missing_mirrors(portal: Path = PORTAL) -> list[str]:
    """Public photo items whose ../ mirror original is not on this machine, plus Pillow if absent.

    The mirrors (media/, ops/car-cards/) are gitignored and live only in the main
    checkout, so a git worktree builds without them and every such photo drops out.
    """
    missing = []
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("Pillow (python3 -m pip install Pillow)")
    for rel in PHOTO_DATA:
        path = portal / rel
        if not path.is_file():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")).get("items") or []:
            src = str(item.get("src") or "")
            if item.get("public") is False or item.get("bucket", "curated") != "curated":
                continue
            if src.startswith("../") and not (portal / src).resolve().is_file():
                missing.append(f"{rel}: {src}")
    return missing


def _filter_gallery(path: Path, dest_root: Path) -> None:
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = [
        item
        for item in (data.get("items") or [])
        if _keep_src(str(item.get("src") or ""), dest_root)
    ]
    data["items"] = kept
    albums = []
    for album in data.get("albums") or []:
        count = sum(1 for item in kept if item.get("album") == album.get("id"))
        if count:
            album = dict(album)
            album["count"] = count
            albums.append(album)
    data["albums"] = albums
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _vendor_fleet_images(path: Path, dest_root: Path, max_px: int = 1600, subdir: str = "fleet") -> None:
    """Copy ../external/ gallery photos (rolling stock, layout) into the tree as web-sized JPEGs.

    The originals (~150 MB of 2200 px PNG/JPEG) live in gitignored mirrors, so this
    only fills in when the mirrors and Pillow are present; otherwise _filter_gallery
    drops those items.
    """
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data.get("items") or []:
        src_rel = str(item.get("src") or "")
        if not src_rel.startswith(MIRROR_PREFIXES):
            continue
        src = _source(src_rel)
        if not src.is_file():
            continue
        album = re.sub(r"[^a-z0-9]+", "-", str(item.get("album") or "misc").lower())
        rel = Path("assets") / subdir / album / f"{src.stem}.jpg"
        if _web_jpeg(src, dest_root / rel, max_px):
            item["src"] = rel.as_posix()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _web_jpeg(src: Path, out: Path, max_px: int) -> bool:
    """Write a resized JPEG; False when Pillow is missing."""
    try:
        from PIL import Image
    except ImportError:
        return False

    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im.seek(0)  # first frame of an animated GIF/WebP
        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            im = Image.new("RGB", rgba.size, (255, 255, 255))
            im.paste(rgba, mask=rgba.getchannel("A"))
        else:
            im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return True


def _gallery_thumbs(path: Path, dest_root: Path, subdir: str, thumb_px: int = 640) -> None:
    """Give every local gallery image a grid thumbnail (assets/<subdir>/thumbs/) and its full size.

    Pages show item["thumb"] in the grid and open item["src"]; width/height let them
    reserve space before the image loads. Skipped quietly without Pillow.
    """
    if not path.is_file():
        return
    try:
        from PIL import Image
    except ImportError:
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data.get("items") or []:
        src_rel = str(item.get("src") or "")
        src = dest_root / src_rel
        if not src_rel or src_rel.startswith(("http://", "https://", "../")) or not src.is_file():
            continue
        album = re.sub(r"[^a-z0-9]+", "-", str(item.get("album") or "misc").lower())
        thumb = Path("assets") / subdir / "thumbs" / album / f"{src.stem}.jpg"
        try:
            with Image.open(src) as im:
                item["width"], item["height"] = im.size
        except OSError:  # not an image Pillow reads (e.g. SVG)
            continue
        if _web_jpeg(src, dest_root / thumb, thumb_px):
            item["thumb"] = thumb.as_posix()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _vendor_archive_images(path: Path, dest_root: Path, max_px: int = 1600, thumb_px: int = 640) -> None:
    """Resize historical-archive images from ../external/ mirrors into assets/archive/.

    Every item gets a small grid thumbnail; mirror-only originals also get a web-sized
    copy. Items marked "public": false or whose original is missing (no mirrors)
    are dropped, and local-only
    fields (PDF paths, where the owner found the file) are stripped.
    """
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = []
    for item in data.get("items") or []:
        if item.get("public") is False:  # rights not cleared; local review only
            continue
        if item.get("bucket", "curated") != "curated":  # review/discard stay on the engineering desk
            continue
        src_rel = str(item.get("src") or "")
        src = _source(src_rel)
        if not src_rel or not src.is_file():
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", str(item.get("id") or src.stem).lower()).strip("-")
        if src_rel.startswith("../"):
            rel = Path("assets") / "archive" / f"{slug}.jpg"
            if not _web_jpeg(src, dest_root / rel, max_px):
                continue
            item["src"] = rel.as_posix()
        thumb = Path("assets") / "archive" / "thumbs" / f"{slug}.jpg"
        if _web_jpeg(src, dest_root / thumb, thumb_px):
            item["thumb"] = thumb.as_posix()
        if str(item.get("pdf") or "").startswith("../"):
            item.pop("pdf")
        item.pop("origin", None)
        kept.append(item)
    data["items"] = kept
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _vendor_logo(logo: str, dest_root: Path) -> str:
    """Copy one ../external/ logo into assets/logos/ and return its public path ("" if missing)."""
    src = _source(logo)
    if not src.is_file():
        return ""
    rel = Path("assets") / "logos" / src.name
    out = dest_root / rel
    if out.exists() and out.read_bytes() != src.read_bytes():
        # Same file name from another folder (e.g. operator_logos/ and downloads/).
        rel = Path("assets") / "logos" / f"{src.parent.name}-{src.name}"
        out = dest_root / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out)
    return rel.as_posix()


def _vendor_logos_in(node: object, dest_root: Path) -> None:
    """Rewrite every "logo" field under node that points into ../external/."""
    if isinstance(node, dict):
        logo = node.get("logo")
        if isinstance(logo, str) and logo.startswith("../"):
            node["logo"] = _vendor_logo(logo, dest_root)
        for value in node.values():
            _vendor_logos_in(value, dest_root)
    elif isinstance(node, list):
        for value in node:
            _vendor_logos_in(value, dest_root)


def _vendor_json_logos(path: Path, dest_root: Path) -> None:
    """Copy ../external/ logos named in a data file into the tree; the public site has no external/ mirror."""
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    _vendor_logos_in(data, dest_root)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _head_tags(rel: Path, title: str) -> str:
    # The 404 page is served for any missing path, so its links start at the site root.
    up = "/" if rel == Path("404.html") else "../" * (len(rel.parts) - 1)
    url = SITE_URL + ("" if rel == Path("index.html") else rel.as_posix().removesuffix("index.html"))
    title = html.escape(title, quote=True)
    desc = html.escape(SHARE_DESCRIPTION, quote=True)
    card = share_cards.card_for(rel)  # the page's own thumbnail, or the site card
    image, alt = card["image"], html.escape(card["alt"], quote=True)
    return f"""
  <link rel="icon" href="{up}favicon.ico" sizes="any">
  <link rel="icon" type="image/png" href="{up}assets/icons/favicon-32.png" sizes="32x32">
  <link rel="apple-touch-icon" href="{up}assets/icons/apple-touch-icon.png">
  <meta name="description" content="{desc}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="HART Railroad">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{url}">
  <meta property="og:image" content="{SITE_URL}{image}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{alt}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="hart-search" content="{INDEX_NAME}">"""


def _add_head_tags(dest_root: Path) -> None:
    for page in dest_root.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        if 'rel="icon"' in text or "</title>" not in text:
            continue
        m = re.search(r"<title>(.*?)</title>", text, re.S)
        title = html.unescape(m.group(1).strip()) if m else "HART Railroad"
        page.write_text(
            text.replace("</title>", "</title>" + _head_tags(page.relative_to(dest_root), title), 1),
            encoding="utf-8",
        )


def _card_thumbs(dest_root: Path) -> None:
    """Hub cards in a grid marked data-card-thumbs show the linked page's share picture.

    The pictures are small copies of the share cards (assets/share/thumbs/). A page is left as it
    is when a copy cannot be made (no Pillow), so no card points at a missing picture.
    """
    cards, links = share_cards.load(), share_cards.load_links()
    for page in dest_root.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        if "data-card-thumbs" not in text:
            continue
        new, thumbs = share_cards.add_card_thumbs(text, page.relative_to(dest_root), cards, links)
        made = all(
            (dest_root / thumb).is_file() or _web_jpeg(dest_root / image, dest_root / thumb, share_cards.THUMB_PX)
            for thumb, image in thumbs.items()
        )
        if thumbs and made:
            page.write_text(new, encoding="utf-8")


def _refresh_tables_page(dest_root: Path) -> None:
    """Rebuild the tables browser data and fill the tables file page from tables.xml, so the
    published copy always describes the current file even when the committed one is stale."""
    if (dest_root / build_tables_browser.PAGE_REL).is_file():
        build_tables_browser.write(dest_root)


def _unsafe_dest(dest: Path) -> bool:
    """True when rmtree(dest) would delete the repo, the portal, or a folder holding either."""
    repo = Path(
        subprocess.run(
            ["git", "-C", str(PORTAL), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    ).resolve()
    return any(dest == p or dest in p.parents for p in (repo, PORTAL))


def main() -> int:
    global SITE_URL
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("dest", nargs="?", default=str(PORTAL.parent / ".pages-dist"), help="output folder (replaced)")
    parser.add_argument("--site-url", default=SITE_URL, help="public root URL for share tags (default %(default)s)")
    parser.add_argument(
        "--require-mirrors",
        action="store_true",
        help="stop when a public photo's gitignored original (media/, ops/car-cards/) or Pillow is missing",
    )
    args = parser.parse_args()
    if args.require_mirrors and (missing := _missing_mirrors()):
        print(
            f"Refusing to build: {len(missing)} public photo original(s) are missing, so they would vanish from the site.\n"
            "media/ and ops/car-cards/ are gitignored and exist only in the main checkout; in a worktree, symlink them\n"
            "from there (ln -s <main>/media media; ln -s <main>/ops/car-cards ops/car-cards) or deploy from the main checkout.",
            file=sys.stderr,
        )
        print("\n".join("  " + m for m in missing[:10]) + (f"\n  … and {len(missing) - 10} more" if len(missing) > 10 else ""), file=sys.stderr)
        return 4
    SITE_URL = args.site_url.rstrip("/") + "/"
    dest = Path(args.dest).resolve()
    if _unsafe_dest(dest):
        print(f"Refusing to replace {dest}: it is the repo, the portal, or a parent of one.", file=sys.stderr)
        return 2
    if dest.exists():
        shutil.rmtree(dest)
    _copy_published(dest)
    _refresh_tables_page(dest)

    site_path = dest / "data" / "site.json"
    site = json.loads(site_path.read_text(encoding="utf-8"))
    site["engDesk"] = ""
    site["public"] = True
    site.pop("tools", None)  # localhost service URLs
    site_path.write_text(json.dumps(site, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    _vendor_json_logos(dest / "data" / "industries.json", dest)
    for lineage in sorted((dest / "data").glob("*-lineage.json")):  # Who became who charts
        _vendor_json_logos(lineage, dest)
    _vendor_fleet_images(dest / "data" / "gallery.json", dest, subdir="gallery")
    _filter_gallery(dest / "data" / "gallery.json", dest)
    _gallery_thumbs(dest / "data" / "gallery.json", dest, "gallery")
    _vendor_fleet_images(dest / "data" / "fleet-gallery.json", dest)
    _filter_gallery(dest / "data" / "fleet-gallery.json", dest)
    _gallery_thumbs(dest / "data" / "fleet-gallery.json", dest, "fleet")
    _vendor_archive_images(dest / "data" / "archive.json", dest)
    _strip_external_data(dest)

    # 404.html is a tracked page (site-root links); the web server must point error_page 404 at it
    # (nginx; .htaccess is ignored).
    _strip_local_only_pages(dest)
    _add_head_tags(dest)
    _card_thumbs(dest)
    leaks = _check_leaks(dest)
    if leaks:
        print("Local hosts or paths in the public tree; fix the source or skip the file:", file=sys.stderr)
        print("\n".join("  " + h for h in leaks), file=sys.stderr)
        return 1
    index = build_search_index(dest)
    print(f"Search index: {len(index['records'])} pages")
    print(f"Prepared public portal tree → {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
