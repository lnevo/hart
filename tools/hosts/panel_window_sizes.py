#!/usr/bin/env python3
"""Set the window size a JMRI profile remembers for each Layout Editor panel to the size tables.xml gives it.

    python3 tools/hosts/panel_window_sizes.py USER_INTERFACE_XML [--tables PATH] [--check]

JMRI keeps every window's size, position and zoom in the profile's user-interface.xml (<windowDetails>, one
<window class="jmri.jmrit.display.layoutEditor.LayoutEditor:<panel>"> per panel), saved whenever a window moves, and
uses it over the panel's windowwidth / windowheight in tables.xml whenever it opens the panel. A size set in tables.xml
(the band panels' heights, band_panels.py) therefore reaches a host only through this file. This sets each saved
panel window's width and height to tables.xml's; its position and zoom stay as the owner left them. Every Layout
Editor panel in the tables is read, so a new panel needs no change here. A panel with no saved window is left out
(JMRI opens it at the tables' size anyway). Only the width and height attributes are edited, so the rest of the file
stays as JMRI wrote it.

Run it with JMRI closed: JMRI rewrites the file when a window moves and when it quits. For the Pi use
tools/hosts/pi_panel_window_sizes.sh, which quits and starts PanelPro round it. Not part of make panels or a deploy
(owner, 2026-11-22: a host utility, run by hand when panel sizes change).

--check: change nothing; exit 1 when a saved size differs from the tables'.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402

PREFIX = "jmri.jmrit.display.layoutEditor.LayoutEditor:"
WINDOW = re.compile(r'<window\b[^>]*\bclass="' + re.escape(PREFIX) + r'(?P<name>[^"]*)"[^>]*>')


class WindowSizesError(SystemExit):
    """The files cannot be read or matched (printed, exit 2)."""

    def __init__(self, message: str):
        super().__init__(f"panel_window_sizes: {message}")


def panel_sizes(tables_path: Path) -> dict[str, tuple[str, str]]:
    """{panel name: (windowwidth, windowheight)} of every Layout Editor panel in the tables at `tables_path`."""
    try:
        root = tables.read(tables_path)
    except (OSError, ValueError) as exc:
        raise WindowSizesError(f"cannot read {tables_path}: {exc}") from None
    out = {}
    for panel in tables.layout_editors(root):
        name = (panel.get("name") or "").strip()
        width, height = panel.get("windowwidth"), panel.get("windowheight")
        if not name or not width or not height:
            raise WindowSizesError(f"{tables_path}: Layout Editor panel {name or '(no name)'} has no window size")
        out[name] = (width, height)
    if not out:
        raise WindowSizesError(f"{tables_path}: no Layout Editor panel")
    return out


def _attr(tag: str, name: str, value: str) -> str:
    """`tag` with attribute `name` set to `value` (as JMRI writes it, a float: 652 -> "652.0")."""
    value = f"{float(value):.1f}"
    pattern = re.compile(r'\b' + name + r'="[^"]*"')
    if pattern.search(tag):
        return pattern.sub(f'{name}="{value}"', tag, count=1)
    return tag[:-1].rstrip("/").rstrip() + f' {name}="{value}"' + ("/>" if tag.endswith("/>") else ">")


def resize(text: str, sizes: dict[str, tuple[str, str]]) -> tuple[str, list[tuple[str, str, str]]]:
    """(the user-interface.xml text with each saved panel window at its tables size, [(panel, before, after)] of the
    windows that changed, sizes as "WxH")."""
    changes = []

    def one(m: re.Match) -> str:
        name = m.group("name")
        if name not in sizes:
            return m.group(0)
        tag = m.group(0)
        width, height = sizes[name]
        before = f"{_get(tag, 'width')}x{_get(tag, 'height')}"
        new = _attr(_attr(tag, "width", width), "height", height)
        after = f"{_get(new, 'width')}x{_get(new, 'height')}"
        if new != tag:
            changes.append((name, before, after))
        return new

    return WINDOW.sub(one, text), changes


def saved_windows(text: str) -> list[str]:
    """The panel names user-interface.xml holds a window for."""
    return [m.group("name") for m in WINDOW.finditer(text)]


def _get(tag: str, name: str) -> str:
    m = re.search(r'\b' + name + r'="([^"]*)"', tag)
    return m.group(1) if m else "?"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("user_interface", type=Path, help="the profile's user-interface.xml")
    ap.add_argument("--tables", type=Path, default=paths.REPO_TABLES_XML, help="tables.xml (default: the repo's)")
    ap.add_argument("--check", action="store_true", help="change nothing; exit 1 when a size differs")
    args = ap.parse_args(argv)
    sizes = panel_sizes(args.tables)
    try:
        text = args.user_interface.read_text(encoding="utf-8")
    except OSError as exc:
        raise WindowSizesError(f"cannot read {args.user_interface}: {exc}") from None
    if "<windowDetails" not in text:
        raise WindowSizesError(f"{args.user_interface}: no <windowDetails>; is it a JMRI user-interface.xml?")
    new, changes = resize(text, sizes)
    saved = set(saved_windows(text))
    for name in sorted(sizes):
        if name not in saved:
            print(f"{name}: no saved window (JMRI opens it at the tables' size)")
    for name, before, after in changes:
        print(f"{name}: {before} -> {after}")
    if not changes:
        print("every saved panel window already has the tables' size")
        return 0
    if args.check:
        return 1
    args.user_interface.write_text(new, encoding="utf-8")
    print(f"wrote {args.user_interface}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
