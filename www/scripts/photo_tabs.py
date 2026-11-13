"""The Photos page's tab map (photos/index.html CATS): which sub-hashes each tab reads as chips.

photos/#<tab>/<sub> opens a chip when <sub> is one of the tab's slugs and an item otherwise, so the
search index builder and the portal check both read the slugs (and the albums they stand for) here,
from the built page itself, rather than keeping their own lists.
"""
from __future__ import annotations

import re
from pathlib import Path


def tab_subs(root: Path, tab: str) -> dict[str, str]:
    """{slug: album or kind} for one tab, e.g. {"session-night": "layout", ...}; {} when not found."""
    page = root / "photos" / "index.html"
    text = page.read_text(encoding="utf-8") if page.is_file() else ""
    m = re.search(r'"?' + re.escape(tab) + r'"?:\s*\{[^{}]*subs:\s*\{([^}]*)\}', text)
    if not m:
        return {}
    return dict(re.findall(r'"?([\w-]+)"?\s*:\s*"([^"]*)"', m.group(1)))
