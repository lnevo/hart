#!/usr/bin/env python3
"""Copy the operator portal into a static GitHub Pages tree.

Excludes the local review API, Python scripts, and gallery items that
point at gitignored Desktop/HART mirrors (those stay on the LAN server).
"""

from __future__ import annotations

import json
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

    _filter_gallery(dest / "data" / "gallery.json", dest)
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
