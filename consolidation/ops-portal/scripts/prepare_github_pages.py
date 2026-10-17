#!/usr/bin/env python3
"""Copy the operator portal into a static GitHub Pages tree.

Excludes the local review API and Python scripts. Gallery, rolling-stock, and
historical-archive photos that live in gitignored ../external/ mirrors are
vendored in, resized, when present (local deploys); CI builds drop them.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
SKIP_TOP = {"scripts", "review"}
# Engineering-desk pages that name hosts, ports, or deploy steps stay off the public site.
SKIP_FILES = {
    Path("README.md"),
    Path("guides/digicon-system.html"),
    Path("data/signal-splits.json"),  # signal splits are under review; the wiring viewer hides that tab
}


def _ignore(directory: str, names: list[str]) -> list[str]:
    rel = Path(directory).resolve().relative_to(PORTAL)
    skipped = [n for n in names if n == ".DS_Store" or n.endswith(".pyc")]
    if rel == Path("."):
        skipped.extend(n for n in names if n in SKIP_TOP)
    skipped.extend(n for n in names if rel / n in SKIP_FILES)
    if "__pycache__" in names:
        skipped.append("__pycache__")
    return skipped


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
    only fills in on a local build (deploy_hartrailroad.sh); CI builds drop them
    in _filter_gallery as before.
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
        from PIL import Image  # local builds only; CI has no mirrors to resize

        album = re.sub(r"[^a-z0-9]+", "-", str(item.get("album") or "misc").lower())
        rel = Path("assets") / subdir / album / f"{src.stem}.jpg"
        out = dest_root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((max_px, max_px))
            im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
        item["src"] = rel.as_posix()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _web_jpeg(src: Path, out: Path, max_px: int) -> bool:
    """Write a resized JPEG; False when Pillow is missing (CI runner without it)."""
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


def _vendor_archive_images(path: Path, dest_root: Path, max_px: int = 1600, thumb_px: int = 640) -> None:
    """Resize historical-archive images from ../external/ mirrors into assets/archive/.

    Every item gets a small grid thumbnail; mirror-only originals also get a web-sized
    copy. Items marked "public": false or whose original is missing (CI, no mirrors)
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


def main() -> int:
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else PORTAL.parent / ".pages-dist").resolve()
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(PORTAL, dest, ignore=_ignore)

    site_path = dest / "data" / "site.json"
    site = json.loads(site_path.read_text(encoding="utf-8"))
    site["engDesk"] = ""
    site["public"] = True
    site_path.write_text(json.dumps(site, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    _vendor_json_logos(dest / "data" / "industries.json", dest)
    for lineage in sorted((dest / "data").glob("*-lineage.json")):  # Who became who charts
        _vendor_json_logos(lineage, dest)
    _vendor_fleet_images(dest / "data" / "gallery.json", dest, subdir="gallery")
    _filter_gallery(dest / "data" / "gallery.json", dest)
    _vendor_fleet_images(dest / "data" / "fleet-gallery.json", dest)
    _filter_gallery(dest / "data" / "fleet-gallery.json", dest)
    _vendor_archive_images(dest / "data" / "archive.json", dest)

    (dest / ".nojekyll").write_text("", encoding="utf-8")
    (dest / "404.html").write_text(
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HART Operator Portal</title>
  <link rel="stylesheet" href="css/ops.css">
</head>
<body>
  <main>
    <p>That page is not on the public portal. <a href="index.html">Back to HART</a>.</p>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    print(f"Prepared GitHub Pages tree → {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
