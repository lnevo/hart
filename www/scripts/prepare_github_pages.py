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

Usage: prepare_github_pages.py [DEST] [--site-url URL] [--require-mirrors] [--full]

The photo stages are reused from the last full run when their inputs are unchanged (see PHOTO_CODE_VERSION);
--full runs them anyway.

This file is the entry point: the CLI, the copy, scrub and check stages, and the order main() runs them in. The
other stages are in portal_photos.py (logos, photos, card thumbs, WebP and the photo cache), portal_head.py (head
tags and provenance) and portal_search_index.py (the search index); portal_common.py holds what they share.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_tables_browser  # noqa: E402
import repo_guide_page  # noqa: E402
import jmri_additions_page  # noqa: E402
import portal_common  # noqa: E402
import provenance  # noqa: E402,F401  (re-exported, as below)
import share_cards  # noqa: E402,F401
import site_views  # noqa: E402

# The build's parts live in portal_*.py beside this file. The names below are re-exported, so importers and tests
# keep reading them here; a test that patches one patches it in the module that holds it.
from portal_common import (  # noqa: E402,F401
    LEAK_PATTERNS, MIRROR_PREFIXES, PORTAL, SHARE_DESCRIPTION, PortalBuildError, _manifest, _source,
)
from portal_head import _add_head_tags, _add_provenance, _head_tags, _own_description  # noqa: E402,F401
from portal_photos import (  # noqa: E402,F401
    ARCHIVE_MAX_PX, JPEG_CACHE_ENV, JPEG_CACHE_KEEP_DAYS, PHOTO_CODE_VERSION, PHOTO_STORE, _archive_px,
    _card_thumbs, _filter_gallery, _gallery_thumbs, _jpeg_cache, _jpeg_cache_at, _missing_mirrors, _photo_code_key,
    _photo_early, _photo_late, _prune_jpeg_cache, _render_jpeg, _render_key, _vendor_archive_images,
    _vendor_fleet_images, _vendor_json_logos, _vendor_logo, _vendor_logos, _vendor_photos, _web_jpeg,
    _webp_companions,
)
from portal_search_index import (  # noqa: E402,F401
    INDEX_NAME, INDEX_SKIP_PAGES, INDEX_TITLE_ONLY, SEARCH_THUMB_PX, _archive_records, _check_index, _crew_records,
    _fleet_records, _glossary_records, _index_record, _industry_records, _photo_records, _search_thumbs,
    build_search_index, contains_private_name, tab_subs,
)


pipeline_map = site_views.pipeline_map  # loaded once, by site_views ("tools/ops/build_pipeline_map.py")
# Files the site publishes that are built here from their sources instead of committed (ADR-036): the pipeline map
# page and the generated JSON (site_views.VIEWS), each site path with the builder that returns its checked text or
# raises one of site_views.ERRORS.
BUILT_PAGES = site_views.VIEWS
# Build scripts, the owner's review desk, and pages that only work at the layout (localhost tools,
# workspace pointers) stay off the public site.
SKIP_DIRS = {Path("scripts"), Path("review"), Path("review-data"), Path("tools"), Path("reference")}
# Engineering-desk pages that name hosts, ports, or deploy steps stay off the public site,
# as do author notes and files no page links to.
SKIP_FILES = {
    Path("README.md"),
    Path("guides/digicon-system.html"),
    Path("data/invites.json"),  # invitation drafts; author reference only
    Path("assets/media/hart-logo.png"),  # favicon source; the built icons are in assets/icons/
    Path("helix/build-status.html"),  # the helix build status is a working file, not published
    Path("helix/files/HART_Neville_Helix_BUILD_STATUS.md"),
}
# Markdown sources for the library articles (the HTML pages are what's published) and invitation drafts.
SKIP_GLOBS = ("docs/*.md",)
# Data must not point into the mirrors (MIRROR_PREFIXES) either; scripts (and inline page scripts) test for that
# prefix when resolving logos and photos, so only data files are checked for it.
DATA_LEAK = re.compile(r"\.\./(?:external|media|ops|docs)/")
LEAK_SUFFIXES = {".html", ".json", ".css", ".md", ".txt", ".svg"}


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
    # Files the site publishes but does not hold: one source, named in the manifest.
    for name, source in _manifest().items():
        rel, src = Path(name), PORTAL.parent / source
        if rel in SKIP_FILES:
            continue
        if not src.is_file():
            raise PortalBuildError(f"published-files.json: missing source {source}")
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


def _refresh_tables_page(dest_root: Path) -> None:
    """Fill the tables file page from tables.xml (its browser data is a built page, _build_pages), and fill the
    repository guide's lists and counts from the checkout, so the published copies always describe
    the current files even when the committed ones are stale."""
    if (dest_root / build_tables_browser.PAGE_REL).is_file():
        build_tables_browser.write_page(dest_root)
    if (dest_root / repo_guide_page.PAGE_REL).is_file():
        # A repo change the guide does not describe yet must not stop a website deploy: keep the committed page and
        # say why. tools/check.sh (repo-guide) fails on the same thing, so it is fixed before the next merge.
        try:
            repo_guide_page.write(dest_root)
        except (repo_guide_page.PageError, subprocess.CalledProcessError, OSError) as e:
            print("WARNING: repository guide not refilled, the committed copy is published: %s" % e)
    if (dest_root / jmri_additions_page.PAGE_REL).is_file():
        try:
            jmri_additions_page.write(dest_root)
        except (jmri_additions_page.PageError, OSError, ValueError) as e:
            print("WARNING: JMRI additions page not refilled, the committed copy is published: %s" % e)


def _build_pages(dest: Path) -> bool:
    """Stage 1b: write each of BUILT_PAGES into the tree from its builder. False (said on stderr) when a builder
    fails or returns nothing, when the page is already in the tree (it would be committed again, or named in the
    manifest), or when the written file does not read back as built: a build never publishes a stale or missing page
    in its place."""
    for rel, make in BUILT_PAGES.items():
        out = dest / rel
        if out.exists():
            print(f"{rel} is built by the site build (ADR-036), but the copy stage already put one in the tree: "
                  f"untrack it (git rm --cached www/{rel}) or drop it from scripts/published-files.json",
                  file=sys.stderr)
            return False
        try:
            site_views.write(out, site_views.build(rel, make))  # writes, then reads back
        except site_views.ViewError as e:
            print(e, file=sys.stderr)
            return False
        print(f"Built {rel}")
    return True


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


def _scrub_site_json(dest: Path) -> None:
    """Stage 3: mark data/site.json public, empty the engineering desk link and drop the localhost tool URLs."""
    site_path = dest / "data" / "site.json"
    site = json.loads(site_path.read_text(encoding="utf-8"))
    site["engDesk"] = ""
    site["public"] = True
    site.pop("tools", None)  # localhost service URLs
    site_path.write_text(json.dumps(site, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _provenance_stage(dest: Path) -> bool:
    """Stage 9: provenance tags, llms.txt, robots.txt, sitemap. False (said on stderr) when a page has no rule."""
    unclassified = _add_provenance(dest)
    if unclassified:
        print("Pages missing from scripts/provenance.json (prototype, fiction, hobby or mixed):", file=sys.stderr)
        print("\n".join("  " + p for p in unclassified), file=sys.stderr)
        return False
    return True


def _leak_stage(dest: Path) -> bool:
    """Stage 12: False (said on stderr) when the finished tree names a local host or path."""
    leaks = _check_leaks(dest)
    if leaks:
        print("Local hosts or paths in the public tree; fix the source or skip the file:", file=sys.stderr)
        print("\n".join("  " + h for h in leaks), file=sys.stderr)
        return False
    return True


def _search_stage(dest: Path) -> None:
    """Stage 13: the search index over the finished tree."""
    index = build_search_index(dest)
    print(f"Search index: {len(index['records'])} records")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("dest", nargs="?", default=str(PORTAL.parent / ".pages-dist"), help="output folder (replaced)")
    parser.add_argument("--site-url", default=portal_common.SITE_URL, help="public root URL for share tags (default %(default)s)")
    parser.add_argument(
        "--require-mirrors",
        action="store_true",
        help="stop when a public photo's gitignored original (media/, ops/car-cards/) or Pillow is missing",
    )
    parser.add_argument("--full", action="store_true", help="run every photo stage even when the saved run of them still fits")
    args = parser.parse_args()
    try:
        return _prepare(args)
    except PortalBuildError as exc:
        raise SystemExit(str(exc)) from exc


def _prepare(args: argparse.Namespace) -> int:
    """Build the public tree into args.dest; the exit code main() returns. PortalBuildError stops a stage."""
    if args.require_mirrors and (missing := _missing_mirrors()):
        print(
            f"Refusing to build: {len(missing)} public photo original(s) are missing, so they would vanish from the site.\n"
            "media/ and ops/car-cards/ are gitignored and exist only in the main checkout; in a worktree, symlink them\n"
            "from there (ln -s <main>/media media; ln -s <main>/ops/car-cards ops/car-cards) or deploy from the main checkout.",
            file=sys.stderr,
        )
        print("\n".join("  " + m for m in missing[:10]) + (f"\n  … and {len(missing) - 10} more" if len(missing) > 10 else ""), file=sys.stderr)
        return 4
    portal_common.SITE_URL = args.site_url.rstrip("/") + "/"
    dest = Path(args.dest).resolve()
    if _unsafe_dest(dest):
        print(f"Refusing to replace {dest}: it is the repo, the portal, or a parent of one.", file=sys.stderr)
        return 2
    if dest.exists():
        shutil.rmtree(dest)
    _copy_published(dest)
    if not _build_pages(dest):
        return 1
    _refresh_tables_page(dest)
    _scrub_site_json(dest)
    early_stamp, early_files, reused = _photo_early(dest, args.full)
    _strip_external_data(dest)

    # 404.html is a tracked page (site-root links); the web server must point error_page 404 at it
    # (nginx; .htaccess is ignored).
    _strip_local_only_pages(dest)
    _add_head_tags(dest)
    if not _provenance_stage(dest):
        return 1
    _photo_late(dest, early_stamp, early_files, args.full)
    if not _leak_stage(dest):
        return 1
    _search_stage(dest)
    if not reused:      # a reused run touches no cache entry, so pruning by last use would empty the cache
        _prune_jpeg_cache()
    print(f"Prepared public portal tree → {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
