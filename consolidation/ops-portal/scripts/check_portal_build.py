#!/usr/bin/env python3
"""Smoke-test the public portal build: every internal link and asset resolves to a file.

Builds with prepare_github_pages.py into a temp folder (or checks an existing
build with --dist), then checks href/src in every built HTML page and the asset
and link fields of every built data/*.json. External links and #fragments are
skipped; "/x" resolves from the site root.

--manifest writes a summary of the build (file count, archive items, industry
logos, gallery items); with --previous it also stops when a count dropped by
more than 10% since that manifest (deploy_hartrailroad.sh passes --force through
as --allow-drop).

Usage: check_portal_build.py [--dist DIR] [--manifest OUT] [--previous OLD] [--allow-drop]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

SCRIPTS = Path(__file__).resolve().parent
# Data fields that pages turn into links or image sources (provenance fields such as
# layout-index "source" name workspace files and are only shown as text).
LINK_KEYS = {"src", "thumb", "logo", "img", "rotated", "href", "html", "pdf", "page", "pages", "article", "more", "path", "previewSrc"}
SKIP_SCHEMES = ("http:", "https:", "mailto:", "tel:", "javascript:", "data:")
MAX_DROP = 0.10


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.found.append(value)


def _target(ref: str, base: Path, root: Path) -> Path | None:
    """The file a link points at, or None when it is external, a fragment, or a template."""
    ref = ref.strip()
    if not ref or ref.startswith("#") or ref.startswith("//") or ref.lower().startswith(SKIP_SCHEMES):
        return None
    if "${" in ref or "{{" in ref:
        return None
    path = unquote(urlsplit(ref).path)
    if not path:
        return None
    out = root / path.lstrip("/") if path.startswith("/") else base / path
    return out / "index.html" if path.endswith("/") else out


def _resolves(target: Path, root: Path) -> bool:
    try:
        resolved = target.resolve()
        resolved.relative_to(root.resolve())  # a link climbing out of the site fails
    except ValueError:
        return False
    return resolved.is_file() or (resolved / "index.html").is_file()


def _data_refs(node: object, key: str | None = None):
    if isinstance(node, dict):
        for k, v in node.items():
            if k != "source":
                yield from _data_refs(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from _data_refs(v, key)
    elif isinstance(node, str) and key in LINK_KEYS and ("/" in node or "." in node):
        yield node  # site.json nav "pages" are page ids, not paths


def broken_links(root: Path) -> list[str]:
    bad = []
    for page in sorted(root.rglob("*.html")):
        parser = _Links()
        parser.feed(page.read_text(encoding="utf-8", errors="replace"))
        for ref in parser.found:
            target = _target(ref, page.parent, root)
            if target is not None and not _resolves(target, root):
                bad.append(f"{page.relative_to(root)}: {ref}")
    for data in sorted((root / "data").glob("*.json")):
        for ref in _data_refs(json.loads(data.read_text(encoding="utf-8"))):
            # Data paths are relative to the site root; a leading "../" is written for the
            # one-folder-deep page that reads the file (briefing/ → ../library/…).
            target = _target(ref.removeprefix("../"), root, root)
            if target is not None and not _resolves(target, root):
                bad.append(f"data/{data.name}: {ref}")
    return bad


def _items(root: Path, name: str, key: str = "items") -> list:
    path = root / "data" / name
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get(key) or []


def manifest(root: Path) -> dict[str, int]:
    return {
        "files": sum(1 for p in root.rglob("*") if p.is_file()),
        "archive_items": len(_items(root, "archive.json")),
        "industry_logos": sum(1 for i in _items(root, "industries.json", "industries") if i.get("logo")),
        "gallery_items": len(_items(root, "gallery.json")),
        "fleet_items": len(_items(root, "fleet-gallery.json")),
    }


def drops(new: dict[str, int], old: dict[str, int]) -> list[str]:
    return [
        f"{k}: {old[k]} → {new.get(k, 0)}"
        for k in old
        if isinstance(old[k], int) and old[k] and new.get(k, 0) < old[k] * (1 - MAX_DROP)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dist", help="check this built tree instead of building one")
    parser.add_argument("--manifest", help="write the build summary here (JSON)")
    parser.add_argument("--previous", help="the last deploy's manifest to compare with")
    parser.add_argument("--allow-drop", action="store_true", help="report count drops without failing")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # keep stdout and stderr in order under deploy

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(args.dist) if args.dist else Path(tmp) / "dist"
        if not args.dist:
            subprocess.run([sys.executable, str(SCRIPTS / "prepare_github_pages.py"), str(root)], check=True)
        bad = broken_links(root)
        summary = manifest(root)

    status = 0
    if bad:
        print(f"{len(bad)} broken internal link(s) in the build:", file=sys.stderr)
        print("\n".join("  " + b for b in bad), file=sys.stderr)
        status = 1
    else:
        print("Links OK: every internal href/src and data path resolves.")
    print("Build: " + ", ".join(f"{k} {v}" for k, v in summary.items()))
    if args.manifest:
        Path(args.manifest).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.previous and Path(args.previous).is_file():
        old = json.loads(Path(args.previous).read_text(encoding="utf-8"))
        print("Last deploy: " + ", ".join(f"{k} {v}" for k, v in old.items()))
        if lost := drops(summary, old):
            print(f"Counts dropped more than {MAX_DROP:.0%} since the last deploy:", file=sys.stderr)
            print("\n".join("  " + d for d in lost), file=sys.stderr)
            if not args.allow_drop:
                print("Pass --force to deploy anyway.", file=sys.stderr)
                status = status or 3
    return status


if __name__ == "__main__":
    raise SystemExit(main())
