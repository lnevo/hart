#!/usr/bin/env python3
"""Point Digicon BUTTON PRIMARY/ALTERNATE at JMRI user-files.

CATS opens those attributes with java.io.File (not FileUtil). A
preference: prefix will not resolve. Deploy therefore writes a real
directory under the host user-files tree:

  <user-files>/resources/buttons/<file>

Git Masters keep the Mac repo paths. Pi/Windows copies are rewritten
here so CATS does not look in the hart clone.

  python3 cats/scripts/rewrite_button_icon_paths.py \\
    --panel cats/panels/HART_Master.xml \\
    --user-files /home/pi/JMRI_UserFiles
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

_BTN_RE = re.compile(
    r'(PRIMARY|ALTERNATE)="[^"]*?[/\\](?:cats[/\\])?resources[/\\]buttons[/\\]([^"]+)"'
)


def buttons_dir(user_files: str) -> str:
    root = user_files.rstrip("/\\").replace("\\", "/")
    return f"{root}/resources/buttons"


def rewrite(text: str, user_files: str) -> str:
    dest = buttons_dir(user_files)

    def repl(m: re.Match[str]) -> str:
        name = m.group(2).replace("\\", "/").rsplit("/", 1)[-1]
        return f'{m.group(1)}="{dest}/{name}"'

    return _BTN_RE.sub(repl, text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument(
        "--user-files",
        required=True,
        help="JMRI user-files root, e.g. /home/pi/JMRI_UserFiles",
    )
    ap.add_argument(
        "--hart-root",
        default="",
        help="deprecated; ignored if --user-files is set",
    )
    ap.add_argument("--out", type=Path, help="default: overwrite --panel")
    args = ap.parse_args()
    user_files = args.user_files or args.hart_root
    if not user_files:
        raise SystemExit("need --user-files")
    out = args.out or args.panel
    text = args.panel.read_text(encoding="utf-8")
    new = rewrite(text, user_files)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(new, encoding="utf-8")
    dest = buttons_dir(user_files)
    n = new.count(f"{dest}/")
    print(f"rewrote button icon paths → {dest} ({n} refs) → {out}")


if __name__ == "__main__":
    main()
