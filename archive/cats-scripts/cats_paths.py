"""Shared paths for Digicon builders (cloud-safe Armstrong shell)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Upstream CATS examples (optional; may be absent until fetch_cats_3.2.sh runs).
_CATS_EXAMPLES = ROOT / "tools/cats/release3.2/examples"

# Checked-in shell used when the full CATS 3.2 tree is not installed (Cloud Agents).
_REFERENCE_ARMSTRONG = ROOT / "cats/panels/reference_ArmstrongMagnet.xml"
_REFERENCE_CHUBB = ROOT / "cats/panels/HART_chubb_magnet.xml"


def armstrong_magnet() -> Path:
    """Armstrong Magnet DOCUMENT shell (fonts/templates/stores + empty TRACKPLAN)."""
    preferred = _CATS_EXAMPLES / "ArmstrongMagnet.xml"
    if preferred.is_file():
        return preferred
    if _REFERENCE_ARMSTRONG.is_file():
        return _REFERENCE_ARMSTRONG
    raise FileNotFoundError(
        f"No Armstrong Magnet shell. Expected {preferred} or {_REFERENCE_ARMSTRONG}. "
        "Run ./tools/cats/fetch_cats_3.2.sh on a Mac, or keep the reference panel in git."
    )


def chubb_route() -> Path:
    preferred = _CATS_EXAMPLES / "Chubb Route.xml"
    if preferred.is_file():
        return preferred
    # Chubb full route is not checked in; magnet rename panel is a last-resort shell.
    if _REFERENCE_CHUBB.is_file():
        return _REFERENCE_CHUBB
    raise FileNotFoundError(f"No Chubb shell at {preferred}")
