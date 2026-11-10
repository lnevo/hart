#!/usr/bin/env python3
"""Fail if a tracked file would publish the private name, a personal email address or a person's name in document metadata.

The repo is public. Three checks:

* the private name, in any tracked text file or inside Word, PowerPoint, Excel and PDF
  files, found by fingerprint (``ops/hart-ops/card_pipeline/private_name.py``) so it is
  never written down here;
* personal email addresses (an address at a consumer mail provider such as iCloud or
  Gmail) in the same files. Service addresses (``git@github.com``, mailing lists) pass;
* the author fields (creator, last modified by) of Office files: blank or the name of the
  library that wrote the file. ``--fix`` blanks any other name in place.

PDF text and metadata need ``pypdf`` (in ``ops/hart-ops/.venv`` and CI). Without it the
PDF check is skipped with a note, except in CI, where that fails.
"""
from __future__ import annotations

import argparse
import logging
import os
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
MAIL_PROVIDERS = ("icloud.com", "me.com", "mac.com", "gmail.com", "googlemail.com", "yahoo.com",
                  "outlook.com", "hotmail.com", "live.com", "msn.com", "aol.com", "proton.me",
                  "protonmail.com", "comcast.net", "verizon.net")
PERSONAL_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+-]+@(?:" + "|".join(re.escape(d) for d in MAIL_PROVIDERS) + r")\b", re.I)


def personal_email(text: str) -> bool:
    return bool(PERSONAL_EMAIL.search(text))


def pdf_text(path: Path) -> str | None:
    """Page text plus document metadata, or None when pypdf is not installed."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # repairable xref noise
    reader = PdfReader(path)
    parts = [str(v) for v in (reader.metadata or {}).values()]
    parts += [page.extract_text() or "" for page in reader.pages]
    return " ".join(parts)


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
    pdf_skipped = 0
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
            if personal_email(text):
                out.append(f"personal email address in {rel}")
            continue
        if path.suffix.lower() == ".pdf":
            try:
                text = pdf_text(path)
            except Exception as exc:  # a damaged PDF should not hide the others
                out.append(f"cannot read {rel}: {exc}")
                continue
            if text is None:
                pdf_skipped += 1
                continue
            if contains_private_name(text):
                out.append(f"private name in {rel}")
            if personal_email(text):
                out.append(f"personal email address in {rel}")
            continue
        if path.stat().st_size > MAX_TEXT:
            continue
        data = path.read_bytes()
        if b"\0" in data[:8000]:
            continue  # binary
        text = data.decode("utf-8", "ignore")
        if contains_private_name(text):
            out.append(f"private name in {rel}")
        if personal_email(text):
            out.append(f"personal email address in {rel}")
    if pdf_skipped:
        if os.environ.get("CI"):
            out.append(f"pypdf not installed: {pdf_skipped} PDFs unchecked")
        else:
            print(f"note: {pdf_skipped} PDFs skipped, pypdf not installed (ops/hart-ops/.venv has it)")
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
        print("OK: no private name, no personal email address, no personal author names")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
