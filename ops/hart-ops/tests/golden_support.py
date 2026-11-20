"""Shared helpers for the golden-output tests (card template, waybills, station maps).

A golden file is plain data under tests/golden/w4c/. Each test feeds the code small frozen
fixtures (never live repo data), so a snapshot changes only when the behaviour does.
"""
from __future__ import annotations

import difflib
import hashlib
import os
import re
from pathlib import Path

from docx.oxml.ns import qn

GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "w4c"
VML_ROUNDRECT = "{urn:schemas-microsoft-com:vml}roundrect"


def check_golden(case, name: str, actual: str, *, depends_on: str, test_id: str) -> None:
    """Compare ``actual`` with golden/w4c/<name>; UPDATE_GOLDEN=1 rewrites it.

    ``depends_on`` says what the snapshot is built from; ``test_id`` is the test module name
    used in the refresh command printed on failure.
    """
    path = GOLDEN_DIR / name
    refresh = (
        "UPDATE_GOLDEN=1 python3 -m unittest discover -s ops/hart-ops/tests "
        f"-p '{test_id}.py'   (from the repo root, with the packages in "
        "ops/hart-ops/requirements-test.txt, e.g. ops/hart-ops/.venv/bin/python)"
    )
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return
    if not path.is_file():
        case.fail(f"golden file {path} is missing. It is built from {depends_on}. Create it with:\n  {refresh}")
    expected = path.read_text(encoding="utf-8")
    if expected != actual:
        diff = "\n".join(
            list(
                difflib.unified_diff(
                    expected.splitlines(), actual.splitlines(), "golden", "actual", lineterm="", n=1
                )
            )[:60]
        )
        case.fail(
            f"{name} differs from its golden. The snapshot depends on {depends_on}; it should change "
            f"only when the code's behaviour changes. If the change is intended, refresh it with:\n"
            f"  {refresh}\n{diff}"
        )


def _para_text(p) -> str:
    out = []
    for el in p.iter():
        if el.tag == qn("w:t"):
            out.append(el.text or "")
        elif el.tag == qn("w:instrText"):
            out.append("{" + (el.text or "").strip() + "}")
        elif el.tag == qn("w:br"):
            out.append("<br>")
    return "".join(out)


def docx_summary(element) -> str:
    """Readable digest of a docx body or cell element: paragraph texts, layout numbers, XML hash."""
    from lxml import etree

    lines = [t for t in (_para_text(p) for p in element.iter(qn("w:p"))) if t]
    fills = sorted({e.get(qn("w:fill")) for e in element.iter(qn("w:shd"))})
    heights = [e.get(qn("w:val")) for e in element.iter(qn("w:trHeight"))]
    summary = [
        "-- text --",
        *lines,
        "-- layout --",
        f"tables={len(list(element.iter(qn('w:tbl'))))}",
        f"rows={len(list(element.iter(qn('w:tr'))))}",
        f"pictures={len(list(element.iter(qn('w:drawing'))))}",
        f"frames={len(list(element.iter(VML_ROUNDRECT)))}",
        f"shd_fills={fills}",
        f"row_heights={heights}",
    ]
    xml = etree.tostring(element, method="c14n")
    xml = re.sub(rb' w:id="\d+"', b"", xml)
    summary.append("xml_sha256=" + hashlib.sha256(xml).hexdigest())
    return "\n".join(summary) + "\n"
