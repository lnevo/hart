#!/usr/bin/env python3
"""Rewrite Digicon BUTTON PRIMARY/ALTERNATE icon paths for a target host root.

Mac source panels store /Users/lnevo/hart/... paths. Pi/Windows need local roots
or buttons are invisible (Digicon loads via java.io.File absolute path).

  python3 cats/scripts/rewrite_button_icon_paths.py \\
    --panel cats/panels/sheets/HART_Master_ABS.xml \\
    --hart-root /home/pi/hart \\
    --out /tmp/HART_Master_ABS.xml
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# Any absolute .../cats/resources/buttons/<file> → <hart_root>/cats/resources/buttons/<file>
_BTN_RE = re.compile(
    r'(PRIMARY|ALTERNATE)="[^"]*?[/\\]cats[/\\]resources[/\\]buttons[/\\]([^"]+)"'
)


def rewrite(text: str, hart_root: str) -> str:
    root = hart_root.rstrip("/\\").replace("\\", "/")

    def repl(m: re.Match[str]) -> str:
        attr, name = m.group(1), m.group(2).replace("\\", "/")
        return f'{attr}="{root}/cats/resources/buttons/{name}"'

    return _BTN_RE.sub(repl, text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument("--hart-root", required=True, help="e.g. /home/pi/hart or C:/Users/lnevo/hart")
    ap.add_argument("--out", type=Path, help="default: overwrite --panel")
    args = ap.parse_args()
    out = args.out or args.panel
    text = args.panel.read_text(encoding="utf-8")
    new = rewrite(text, args.hart_root)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(new, encoding="utf-8")
    n = new.count("/cats/resources/buttons/")
    print(f"rewrote button icon paths → {args.hart_root} ({n} refs) → {out}")


if __name__ == "__main__":
    main()
