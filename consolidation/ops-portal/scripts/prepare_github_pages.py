#!/usr/bin/env python3
"""Build the public operator portal tree that deploy_hartrailroad.sh publishes.

Only git-tracked files are published (never gitignored previews, drafts, or
stray local files), minus the engineering-desk material below. Gallery,
rolling-stock, and historical-archive photos that live in gitignored
../external/ mirrors are vendored in, resized, when present; without the
mirrors (or Pillow) they drop out. The build fails if the output still names
local hosts or paths. (The file name predates the move off GitHub Pages.)

Usage: prepare_github_pages.py [DEST] [--site-url URL]
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
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
# Build scripts, the owner's review desk, and pages that only work at the layout (localhost tools,
# workspace pointers) stay off the public site.
SKIP_DIRS = {Path("scripts"), Path("review"), Path("tools"), Path("reference")}
# Engineering-desk pages that name hosts, ports, or deploy steps stay off the public site,
# as do author notes and files no page links to.
SKIP_FILES = {
    Path("README.md"),
    Path("guides/digicon-system.html"),
    Path("data/signal-splits.json"),  # signal splits are under review; the wiring viewer hides that tab
    Path("data/f-root-review.json"),  # F-root review desk (review/ is local-only)
    Path("data/f-root-curation.json"),
    Path("js/f-root-review.js"),
    Path("data/invites.json"),  # invitation drafts; author reference only
    Path("data/panels.json"),
    Path("library/updated-history.txt"),
    Path("assets/media/hart-logo.png"),  # favicon source; the built icons are in assets/icons/
    Path("assets/media/loco-cr-1993.png"),  # crew sheets use the assets/crew/ thumbnails
    Path("assets/media/loco-pohc-2091.png"),
    Path("assets/media/coal-types.png"),
    Path("assets/icons/icon-192.png"),
    Path("helix/build-status.html"),  # the helix build status is a working file, not published
    Path("helix/files/HART_Neville_Helix_BUILD_STATUS.md"),
}
# Markdown sources for the library articles (the HTML pages are what's published) and invitation drafts.
SKIP_GLOBS = ("docs/*.md",)
# Strings that mean a local host, port, or workspace path leaked into the public tree.
LEAK_PATTERNS = re.compile(r"localhost|127\.0\.0\.1|/Users/|consolidation/external")
# Data must not point into the mirrors either; scripts (and inline page scripts) test for that
# prefix when resolving logos and photos, so only data files are checked for it.
DATA_LEAK = re.compile(r"\.\./external/")
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


def _copy_published(dest: Path) -> None:
    for rel in _published_files():
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PORTAL / rel, out)


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
        for key in [k for k, v in node.items() if isinstance(v, str) and v.startswith("../external/")]:
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


def _keep_src(src: str, dest_root: Path) -> bool:
    if not src or src.startswith("../"):
        return False
    if src.startswith("http://") or src.startswith("https://"):
        return True
    return (dest_root / src).is_file()


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
        if not src_rel.startswith("../external/"):
            continue
        src = (PORTAL / src_rel).resolve()
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
        src = (PORTAL / src_rel).resolve()
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
    src = (PORTAL / logo).resolve()
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
    up = "../" * (len(rel.parts) - 1)
    url = SITE_URL + ("" if rel == Path("index.html") else rel.as_posix().removesuffix("index.html"))
    title = html.escape(title, quote=True)
    desc = html.escape(SHARE_DESCRIPTION, quote=True)
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
  <meta property="og:image" content="{SITE_URL}assets/icons/share-card.jpg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Neville Island from above">
  <meta name="twitter:card" content="summary_large_image">"""


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
    args = parser.parse_args()
    SITE_URL = args.site_url.rstrip("/") + "/"
    dest = Path(args.dest).resolve()
    if _unsafe_dest(dest):
        print(f"Refusing to replace {dest}: it is the repo, the portal, or a parent of one.", file=sys.stderr)
        return 2
    if dest.exists():
        shutil.rmtree(dest)
    _copy_published(dest)

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

    # nginx serves this for any missing path, so its links are site-root-relative.
    (dest / "404.html").write_text(
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HART Operator Portal</title>
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="stylesheet" href="/css/ops.css">
</head>
<body>
  <main>
    <p>That page is not on the public portal. <a href="/">Back to HART</a>.</p>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    _strip_local_only_pages(dest)
    _add_head_tags(dest)
    leaks = _check_leaks(dest)
    if leaks:
        print("Local hosts or paths in the public tree; fix the source or skip the file:", file=sys.stderr)
        print("\n".join("  " + h for h in leaks), file=sys.stderr)
        return 1
    print(f"Prepared public portal tree → {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
