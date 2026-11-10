#!/usr/bin/env python3
"""Fail if a tracked file would publish the private name or a person's name in document metadata.

The repo is public. Two checks:

* the private name, in any tracked text file or inside Word, PowerPoint and Excel files,
  found by fingerprint (``ops/hart-ops/card_pipeline/private_name.py``) so it is never
  written down here;
* the author fields (creator, last modified by) of Office files: blank or the name of the
  library that wrote the file. ``--fix`` blanks any other name in place.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ops/hart-ops/card_pipeline"))

from private_name import contains_private_name  # noqa: E402

OFFICE = (".docx", ".pptx", ".xlsx", ".dotx", ".potx", ".xltx")
AUTHOR_TAGS = ("dc:creator", "cp:lastModifiedBy")
TOOL_AUTHORS = {"", "python-docx", "python-pptx", "openpyxl"}
MAX_TEXT = 30_000_000


def git_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT, text=True)
    return [p for p in out.split("\0") if p]


def office_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        parts = [z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.endswith(".xml")]
    return re.sub(r"<[^>]+>", " ", " ".join(parts))


def authors(core: str) -> dict[str, str]:
    found = {}
    for tag in AUTHOR_TAGS:
        m = re.search(rf"<{tag}>([^<]*)</{tag}>", core)
        if m:
            found[tag] = m.group(1).strip()
    return found


def blank_authors(core: str) -> str:
    for tag in AUTHOR_TAGS:
        core = re.sub(rf"<{tag}>([^<]*)</{tag}>",
                      lambda m, t=tag: m.group(0) if m.group(1).strip() in TOOL_AUTHORS else f"<{t}></{t}>",
                      core)
    return core


def rewrite_core(path: Path) -> None:
    """Blank personal author names in docProps/core.xml, keeping every other part as it is."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=path.suffix, dir=path.parent) as tmp:
        tmp_path = Path(tmp.name)
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp_path, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = blank_authors(data.decode("utf-8")).encode("utf-8")
            dst.writestr(info, data)
    shutil.move(tmp_path, path)


def problems(files: list[str], fix: bool = False) -> list[str]:
    out = []
    for rel in files:
        path = ROOT / rel
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() in OFFICE:
            try:
                with zipfile.ZipFile(path) as z:
                    core = z.read("docProps/core.xml").decode("utf-8", "ignore") if "docProps/core.xml" in z.namelist() else ""
                text = office_text(path)
            except zipfile.BadZipFile:
                continue
            people = {t: v for t, v in authors(core).items() if v not in TOOL_AUTHORS}
            if people and fix:
                rewrite_core(path)
                print(f"fixed author fields: {rel}")
            elif people:
                out.append(f"author name in {rel} ({', '.join(people)}); run with --fix")
            if contains_private_name(text):
                out.append(f"private name in {rel}")
            continue
        if path.stat().st_size > MAX_TEXT:
            continue
        data = path.read_bytes()
        if b"\0" in data[:8000]:
            continue  # binary
        if contains_private_name(data.decode("utf-8", "ignore")):
            out.append(f"private name in {rel}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fix", action="store_true", help="blank personal author names in Office files")
    ap.add_argument("paths", nargs="*", help="files to check (default: every tracked file)")
    args = ap.parse_args()
    found = problems(args.paths or git_files(), fix=args.fix)
    for line in found:
        print(f"FAIL {line}")
    if not found:
        print("OK: no private name, no personal author names")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
