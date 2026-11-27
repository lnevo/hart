#!/usr/bin/env python3
"""The files the website publishes that are built from their sources, not committed (ADR-036).

    python3 www/scripts/site_views.py           # (make site-data) build every view into www/, for the local preview
    python3 www/scripts/site_views.py --list    # the views' paths under www/, one a line

VIEWS maps each view's path in the site to the builder that returns its checked text or raises one of ERRORS. The
site build (prepare_github_pages.py, stage 1b) writes each into the build it uploads and stops when one cannot be
built; the local preview (serve_portal.py) builds them all into www/ when it starts, and removes the local copy of
one that cannot be built, so a page there never reads a missing or stale file without saying so. The files are
gitignored; tools/check.sh builds each in memory and runs its checks (its own step in tools/pipeline/checks.toml).

The two layout indexes are built once per process: the CATS index joins to the layout index.
"""
from __future__ import annotations

import argparse
import functools
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_cats_layout_index  # noqa: E402
import build_layout_index  # noqa: E402
import build_tables_browser  # noqa: E402
import build_wiring_json  # noqa: E402
import png_stamp  # noqa: E402

PORTAL = HERE.parent
BUILD = "make site-data"


def _load_tool(rel: str):
    """A repo tool outside www/scripts, loaded by path once (tools/ops is not a package)."""
    spec = importlib.util.spec_from_file_location(Path(rel).stem, PORTAL.parent / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pipeline_map = _load_tool("tools/ops/build_pipeline_map.py")


class ViewError(Exception):
    """A view that cannot be built or written; the message names it and says why."""


@functools.cache
def _layout_index() -> dict:
    return build_layout_index.build()


def _layout_index_text() -> str:
    return build_layout_index.index_text(_layout_index())


def _cats_index_text() -> str:
    return build_cats_layout_index.index_text(le_index=_layout_index())


# site path -> builder of its checked text
VIEWS = {
    pipeline_map.SITE_REL: pipeline_map.site_page,
    build_tables_browser.OUT_REL.as_posix(): build_tables_browser.view,
    build_layout_index.OUT_JSON.relative_to(PORTAL).as_posix(): _layout_index_text,
    build_cats_layout_index.OUT_JSON.relative_to(PORTAL).as_posix(): _cats_index_text,
    build_wiring_json.OUT_REL: build_wiring_json.view,
}
# what a builder raises when its sources are broken or what it built fails a check
ERRORS = (pipeline_map.GraphError, build_tables_browser.BrowserDataError, build_layout_index.LayoutIndexError,
          build_cats_layout_index.CatsIndexError, build_wiring_json.WiringDataError, png_stamp.PngError, OSError)


def build(rel: str, make=None) -> str:
    """The text of view `rel`, from `make` (VIEWS[rel] when None). ViewError when the builder fails or returns
    nothing."""
    make = VIEWS[rel] if make is None else make
    try:
        text = make()
    except ERRORS as err:
        raise ViewError(f"Cannot build {rel}:\n{err}") from err
    if not isinstance(text, str) or not text.strip():
        raise ViewError(f"Cannot build {rel}:\nits builder returned no page")
    return text


def write(out: Path, text: str) -> None:
    """Write a view and read it back; ViewError when either fails."""
    try:
        pipeline_map.write_page(out, text)
    except pipeline_map.GraphError as err:
        raise ViewError(str(err)) from err


def refresh(root: Path = PORTAL, views: dict | None = None) -> list[str]:
    """Build every view into `root` (www/ by default). A view that cannot be built has its old copy removed, so
    nothing serves it stale; returns the error of each such view (empty when all were written)."""
    root = Path(root)
    if not root.is_dir():
        raise ViewError(f"{root} is not a folder")
    failed = []
    for rel, make in (VIEWS if views is None else views).items():
        out = root / rel
        try:
            write(out, build(rel, make))
        except ViewError as err:
            try:
                out.unlink(missing_ok=True)
            except OSError as gone:
                err = f"{err}\n(and cannot remove the old {out}: {gone.strerror or gone})"
            failed.append(str(err))
    return failed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true", help="print the views' paths under www/ and build nothing")
    args = ap.parse_args(argv)
    if args.list:
        print("\n".join(f"www/{rel}" for rel in VIEWS))
        return 0
    failed = refresh()
    for rel in VIEWS:
        if (PORTAL / rel).is_file():
            print(f"wrote www/{rel}")
    if failed:
        print("\n".join(failed), file=sys.stderr)
        print(f"{len(failed)} of {len(VIEWS)} views not built; their local copies are removed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
