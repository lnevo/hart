#!/usr/bin/env python3
"""Copy the operator portal into a static GitHub Pages tree.

Excludes the local review API, Python scripts, and photo-gallery items that
point at gitignored Desktop/HART mirrors (those stay on the LAN server).
Rolling-stock photos from those mirrors are vendored in, resized, when present.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
SKIP_TOP = {"scripts", "review"}


def _ignore(directory: str, names: list[str]) -> list[str]:
    rel = Path(directory).resolve().relative_to(PORTAL)
    skipped = [n for n in names if n == ".DS_Store" or n.endswith(".pyc")]
    if rel == Path("."):
        skipped.extend(n for n in names if n in SKIP_TOP)
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


def _vendor_fleet_images(path: Path, dest_root: Path, max_px: int = 1600) -> None:
    """Copy ../external/ rolling-stock photos into the tree as web-sized JPEGs.

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
        rel = Path("assets") / "fleet" / album / f"{src.stem}.jpg"
        out = dest_root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((max_px, max_px))
            im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
        item["src"] = rel.as_posix()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _vendor_industry_logos(path: Path, dest_root: Path) -> None:
    """Copy ../external/ logos into the tree; the public site has no external/ mirror."""
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("industries") or data.get("items") or []
    for ind in items:
        logo = str(ind.get("logo") or "")
        if not logo.startswith("../"):
            continue
        src = (PORTAL / logo).resolve()
        if not src.is_file():
            ind["logo"] = ""
            continue
        rel = Path("assets") / "logos" / src.name
        (dest_root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_root / rel)
        ind["logo"] = rel.as_posix()
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

    _vendor_industry_logos(dest / "data" / "industries.json", dest)
    _filter_gallery(dest / "data" / "gallery.json", dest)
    _vendor_fleet_images(dest / "data" / "fleet-gallery.json", dest)
    _filter_gallery(dest / "data" / "fleet-gallery.json", dest)

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
