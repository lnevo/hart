"""Generate F-root preview thumbnails and extract document text."""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from f_root_common import DOC_EXT, FROOT, IMAGE_EXT, PDF_EXT, PREVIEW_DIR

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def preview_id(relative_path: str) -> str:
    return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]


def preview_path(relative_path: str) -> Path:
    return PREVIEW_DIR / f"{preview_id(relative_path)}.jpg"


def preview_rel_url(relative_path: str) -> str:
    return f"assets/f-root-previews/{preview_id(relative_path)}.jpg"


SKIP_PREVIEW_EXT = {".dmg", ".db"}


def _run(cmd: list[str], timeout: int = 90) -> bool:
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _png_to_jpg(src: Path, dest: Path, max_px: int = 640) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if _run(["sips", "-s", "format", "jpeg", "-Z", str(max_px), str(src), "--out", str(dest)]):
        return dest.is_file()
    return False


def _batch_qlmanage(relative_paths: list[str], force: bool) -> dict[str, Path | None]:
    """Generate previews for non-image files via batched qlmanage."""
    results: dict[str, Path | None] = {}
    pending: list[str] = []
    for rel in relative_paths:
        out = preview_path(rel)
        ext = Path(rel).suffix.lower()
        if ext in SKIP_PREVIEW_EXT or Path(rel).name.startswith("~$"):
            results[rel] = None
            continue
        if out.is_file() and not force:
            results[rel] = out
        elif (FROOT / rel).is_file():
            pending.append(rel)

    batch_size = 8
    for i in range(0, len(pending), batch_size):
        chunk = pending[i : i + batch_size]
        # Large files get their own qlmanage call with a longer timeout.
        for rel in chunk:
            src = FROOT / rel
            if src.stat().st_size > 8_000_000:
                with tempfile.TemporaryDirectory(prefix="froot-ql-one-") as tmp:
                    tmp_path = Path(tmp)
                    if not _run(["qlmanage", "-t", "-s", "512", "-o", str(tmp_path), str(src)], timeout=120):
                        results[rel] = None
                        continue
                    png = tmp_path / (src.name + ".png")
                    out = preview_path(rel)
                    if png.is_file() and _png_to_jpg(png, out):
                        results[rel] = out
                    else:
                        results[rel] = None
                continue

        small = [rel for rel in chunk if (FROOT / rel).stat().st_size <= 8_000_000]
        if not small:
            continue
        with tempfile.TemporaryDirectory(prefix="froot-ql-batch-") as tmp:
            tmp_path = Path(tmp)
            args = ["qlmanage", "-t", "-s", "640", "-o", str(tmp_path)]
            args.extend(str(FROOT / rel) for rel in small)
            if not _run(args, timeout=90):
                for rel in small:
                    results.setdefault(rel, None)
                continue
            png_by_stem = {p.name: p for p in tmp_path.glob("*.png")}
            for rel in small:
                out = preview_path(rel)
                src_name = Path(rel).name + ".png"
                png = png_by_stem.get(src_name)
                if png and _png_to_jpg(png, out):
                    results[rel] = out
                else:
                    results[rel] = None
    return results


def generate_all_previews(relative_paths: list[str], force: bool = False) -> tuple[int, int]:
    ok = 0
    missing = 0
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    images: list[str] = []
    others: list[str] = []
    for rel in relative_paths:
        if not (FROOT / rel).is_file():
            missing += 1
            continue
        ext = Path(rel).suffix.lower()
        if ext in SKIP_PREVIEW_EXT or Path(rel).name.startswith("~$"):
            missing += 1
            continue
        if ext in IMAGE_EXT:
            images.append(rel)
        else:
            others.append(rel)

    for rel in images:
        if generate_preview(rel, force=force):
            ok += 1
        else:
            missing += 1

    batch_results = _batch_qlmanage(others, force=force)
    for rel in others:
        if batch_results.get(rel):
            ok += 1
        else:
            missing += 1

    return ok, missing


def generate_preview(relative_path: str, force: bool = False) -> Path | None:
    """Return preview JPG path, generating via qlmanage/sips when needed."""
    src = FROOT / relative_path
    out = preview_path(relative_path)
    if out.is_file() and not force:
        return out
    if not src.is_file():
        return None

    out.parent.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()

    if ext in IMAGE_EXT:
        if _run(["sips", "-s", "format", "jpeg", "-Z", "640", str(src), "--out", str(out)]):
            return out if out.is_file() else None
        return None

    with tempfile.TemporaryDirectory(prefix="froot-ql-") as tmp:
        tmp_path = Path(tmp)
        if not _run(["qlmanage", "-t", "-s", "640", "-o", str(tmp_path), str(src)]):
            return None
        png_candidates = list(tmp_path.glob("*.png"))
        if not png_candidates:
            return None
        png = max(png_candidates, key=lambda p: p.stat().st_mtime)
        if _png_to_jpg(png, out):
            return out
    return None


def _xml_text(blob: bytes) -> str:
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return ""
    chunks = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            chunks.append(node.text)
        if node.tag.endswith("}tab"):
            chunks.append(" ")
    text = re.sub(r"\s+", " ", " ".join(chunks)).strip()
    return text


def _docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile, OSError):
        return ""
    return _xml_text(xml)


def _xlsx_text(path: Path, limit: int = 1200) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in root:
                    parts = [t.text or "" for t in si.iter() if t.tag.endswith("}t")]
                    shared.append("".join(parts))
            sheet_names = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet"))
            cells: list[str] = []
            for sheet in sheet_names[:2]:
                root = ET.fromstring(zf.read(sheet))
                for c in root.iter():
                    if not c.tag.endswith("}c"):
                        continue
                    ref = c.attrib.get("t")
                    v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                    if v is None or v.text is None:
                        continue
                    val = v.text
                    if ref == "s":
                        try:
                            val = shared[int(val)]
                        except (IndexError, ValueError):
                            pass
                    val = val.strip()
                    if val:
                        cells.append(val)
                    if len(" ".join(cells)) >= limit:
                        break
                if len(" ".join(cells)) >= limit:
                    break
            return re.sub(r"\s+", " ", " ".join(cells)).strip()[:limit]
    except (zipfile.BadZipFile, OSError, ET.ParseError):
        return ""


def _pptx_text(path: Path, limit: int = 1200) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            slide_names = sorted(n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
            chunks: list[str] = []
            for slide in slide_names[:4]:
                chunks.append(_xml_text(zf.read(slide)))
                if len(" ".join(chunks)) >= limit:
                    break
            return re.sub(r"\s+", " ", " ".join(chunks)).strip()[:limit]
    except (zipfile.BadZipFile, OSError, ET.ParseError):
        return ""


def extract_text(relative_path: str, limit: int = 1200) -> str:
    path = FROOT / relative_path
    if not path.is_file():
        return ""
    ext = path.suffix.lower()
    if ext == ".docx":
        return _docx_text(path)[:limit]
    if ext in {".xlsx", ".xls"}:
        return _xlsx_text(path, limit=limit)
    if ext in {".pptx", ".ppt"}:
        return _pptx_text(path, limit=limit)
    if ext in PDF_EXT:
        if _run(["which", "pdftotext"]):
            try:
                proc = subprocess.run(
                    ["pdftotext", "-l", "1", str(path), "-"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return re.sub(r"\s+", " ", proc.stdout).strip()[:limit]
            except subprocess.CalledProcessError:
                pass
    return ""
