"""Paths the CPython tools use, resolved from the checkout hartlib sits in.

There is one railroad and one layout directory, ``jmri/layouts/hart``. ``JMRI_LAYOUT`` is
ignored here: a stale value left in a shell (old archive READMEs export linear4/linear5)
would otherwise point every path at a directory this repo does not have. When the
railroad is split later, the unit will be the level or district, not the layout name.

Every path names a file in *this* checkout, the one hartlib sits in, so a script in a
worktree reads that worktree's tables.xml. ``HART_REPO_ROOT`` and ``HART_RUNTIME_ROOT``
(exported by tools/env/load_env.sh) do not move them.

One exception, for checks only: ``HART_TABLES`` names another tables file (the Layout Editor
cut-over candidate, a sandbox copy) that ``TABLES_XML`` then points at, so
``HART_TABLES=<file> tools/check.sh`` runs every table check against it. It must be an
existing file outside the JMRI profile (``~/JMRI_UserFiles``), because scripts that write
tables write ``TABLES_XML``. ``REPO_TABLES_XML`` always names this checkout's file; deploy
scripts refuse to run while ``HART_TABLES`` is set.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _find_repo_root() -> Path:
    # src/hartlib/paths.py -> src -> tools/hartlib -> tools -> repo
    root = Path(__file__).resolve().parents[4]
    if not (root / "jmri" / "layouts").is_dir() or not (root / "tools" / "hartlib").is_dir():
        raise ImportError(
            f"hartlib at {Path(__file__).resolve()} is not inside a repo checkout; put "
            "<repo>/tools/hartlib/src on sys.path instead of installing a copy (README.md)"
        )
    return root


REPO_ROOT = _find_repo_root()
JMRI_DIR = REPO_ROOT / "jmri"

LAYOUT = "hart"  # pinned; see the module docstring
LAYOUT_DIR = JMRI_DIR / "layouts" / LAYOUT
LAYOUT_DATA = LAYOUT_DIR / "data"
LAYOUT_OUTPUT = LAYOUT_DIR / "output"
LAYOUT_SCRIPTS = LAYOUT_DIR / "scripts"

REPO_TABLES_XML = LAYOUT_OUTPUT / "tables.xml"
WIRING = LAYOUT_DATA / "wiring.csv"          # the physical wiring source (hartlib.wiring); it holds the Digicon heads
SIGNAL_HEAD_PLAN = REPO_ROOT / "jmri" / "layouts" / "hart" / "output" / "signal_head_plan.csv"
CATS_DIR = REPO_ROOT / "cats"

# Where PanelPro loads preference:tables.xml on every host (ADR-014).
JMRI_USER_FILES = Path.home() / "JMRI_UserFiles"


def main_checkout(root: Path | None = None) -> Path:
    """The main checkout of the repo ``root`` (default: this one) belongs to: the parent of git's common dir, so a
    worktree answers with the checkout it was made from. ``root`` itself where git cannot say (a copied tree).
    The shell twin is hart_main_checkout in tools/hosts/profile_tables_guard.sh."""
    root = root or REPO_ROOT
    try:
        done = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return root
    common = done.stdout.strip()
    return Path(common).parent if done.returncode == 0 and common else root


def cache_dir(name: str, root: Path | None = None) -> Path:
    """The shared cache folder ``name``: ``HART_CACHE_DIR``/name, else <main checkout>/.cache/hart/name (gitignored),
    so every worktree shares one warm cache. The shell twin is hart_cache_dir."""
    base = os.environ.get("HART_CACHE_DIR", "").strip()
    return (Path(base).expanduser() if base else main_checkout(root) / ".cache" / "hart") / name


def pulled_stores_dir(root: Path | None = None) -> Path:
    """Where PanelPro Stores taken off a host are kept: <main checkout>/media/pulled-stores (gitignored)."""
    return main_checkout(root) / "media" / "pulled-stores"


def _tables_xml() -> Path:
    """This checkout's tables.xml, or the file ``HART_TABLES`` names (see the module docstring)."""
    value = os.environ.get("HART_TABLES", "").strip()
    if not value:
        return REPO_TABLES_XML
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ImportError(f"HART_TABLES={value}: no such file; unset it or name a tables file")
    profile = JMRI_USER_FILES.resolve()
    if path == profile or profile in path.parents:
        raise ImportError(f"HART_TABLES={value} is in the JMRI profile ({profile}); name a copy elsewhere")
    return path


TABLES_XML = _tables_xml()
TABLES_OVERRIDDEN = TABLES_XML != REPO_TABLES_XML.resolve()


def check_only_message(what: str) -> str | None:
    """Why `what` (a script about to write tables, the profile or an output derived from the tables) must not
    run, or None. While HART_TABLES is set every such write is refused: the override is for checks only, so a
    candidate never reaches the repo's tables, its committed outputs or the JMRI profile."""
    if not TABLES_OVERRIDDEN:
        return None
    return (f"{what}: HART_TABLES is set ({TABLES_XML}); it is for checks only and nothing is written while it "
            "is set. Unset it, and name a candidate file explicitly (--panel) to edit one.")


def exit_if_overridden(what: str) -> None:
    """Stop the script (SystemExit, exit status 1) with check_only_message when HART_TABLES is set."""
    message = check_only_message(what)
    if message:
        raise SystemExit(message)


def lcos_bridge() -> Path:
    """The LCOS bridge source: the external/lcos-bridge submodule, else a sibling clone."""
    sub = REPO_ROOT / "external" / "lcos-bridge"
    if (sub / "serial_to_mqtt.py").is_file():
        return sub
    sibling = REPO_ROOT.parent / "LCOS_ESP32_MQTT_Client"
    return sibling if sibling.is_dir() else sub


def car_images_final() -> Path:
    """HART_CAR_IMAGES_FINAL, else the repo copy (~/Desktop/HART was retired 2026-11-09, ADR-007)."""
    value = os.environ.get("HART_CAR_IMAGES_FINAL", "").strip()
    if value:
        return Path(value).expanduser().resolve()
    return REPO_ROOT / "ops" / "car-cards" / "car-images" / "CarImagesFinal"


def rel(path: Path | str, root: Path | None = None) -> str:
    """``path`` relative to the checkout (or ``root``) for messages; absolute when outside it."""
    p = Path(path)
    try:
        return str(p.resolve().relative_to((root or REPO_ROOT).resolve()))
    except ValueError:
        return str(p)


def layout_paths(layout: str | None = None) -> dict[str, str]:
    """The old jmri/layout_paths.py dict. The one live caller is jmri/scripts/generate_nx_pairs.py
    (parked with NX), which reads ``output`` and ``nx_pairs``; the AnyRail-era scripts that used the rest
    are in archive/jmri-scripts.

    ``authoritative`` is tables.xml. ``anyrail``, ``style_defaults`` and ``layout_dir``
    exist; ``output``, ``excel``, ``merge``, ``nx_pairs`` and ``working`` are defaults for
    files those scripts create. The Dispatcher keys (NextTrain workbook and the rest) are
    gone: nothing reads them.
    """
    base = JMRI_DIR / "layouts" / (layout or LAYOUT)
    return {
        "layout_dir": str(base),
        "anyrail": str(base / "anyrail" / "hart.xml"),
        "authoritative": str(TABLES_XML if layout in (None, LAYOUT) else base / "output" / "tables.xml"),
        "output": str(base / "output" / "hart_blocked.xml"),
        "excel": str(base / "data" / "layout_blocks.xlsx"),
        "merge": str(base / "data" / "block_merges.txt"),
        "nx_pairs": str(base / "output" / "nx_pairs.txt"),
        "working": str(base / "working"),
        "style_defaults": str(JMRI_DIR / "templates" / "panel_style.xml"),
    }
