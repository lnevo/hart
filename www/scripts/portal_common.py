"""What the parts of the site build share: the portal folder, the site URL and share text, the leak patterns,
and where a published file really lives (scripts/published-files.json).

The site build is prepare_github_pages.py; it re-exports these names. SITE_URL is the one setting that changes
while it runs (main() sets it from --site-url), so the other parts read it as portal_common.SITE_URL, never as an
imported name.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[1]
# Strings that mean a local host, port, or workspace path leaked into the public tree.
LEAK_PATTERNS = re.compile(r"localhost|127\.0\.0\.1|/Users/|external/sts-docker-data|\.\./media/|media/archive/|media/hart-research|media/photos-layout|media/dj-trains|ops/car-cards")
# The gitignored mirrors and source folders that data files point into with ../; the photo and logo stages copy
# from them, and the scrub stage drops any field still pointing there.
MIRROR_PREFIXES = ("../external/", "../media/", "../ops/", "../docs/")
# Share previews (Facebook, iMessage, …) read static tags only, so every page gets them at build time.
# The site is served at the domain root; override with --site-url or HART_SITE_URL.
SITE_URL = os.environ.get("HART_SITE_URL", "https://www.hartrailroad.com/")
SHARE_DESCRIPTION = (
    "Neville Island on the HART Railroad: the prototype's history and industries, "
    "operating sessions, and the layout build."
)


class PortalBuildError(Exception):
    """A public-site build stage found something it must not publish or cannot build; the message names the file."""


def _manifest() -> dict[str, str]:
    return json.loads((PORTAL / "scripts/published-files.json").read_text(encoding="utf-8"))


def _source(rel: str) -> Path:
    """Where a site-relative file really lives: its manifest source, or the site tree."""
    source = _manifest().get(rel)
    return PORTAL.parent / source if source else (PORTAL / rel).resolve()
