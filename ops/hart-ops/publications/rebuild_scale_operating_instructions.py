#!/usr/bin/env python3
"""Rebuild HART Railroad Scale Operating Instructions (Revision D).

The body text comes from the crew master, ops/hart-ops/data/crew.json ("scale"); this holds the layout. Preserves masthead artwork
from the canonical docx, then rewrites publication lines and everything
from SECTION 1 onward.

Usage (from repo root):
  .venv/bin/python publications/rebuild_scale_operating_instructions.py

Writes:
  docs/HART Railroad Scale Operating Instructions.docx
"""

from __future__ import annotations

import shutil
import sys
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
CANONICAL = DOCS / "HART Railroad Scale Operating Instructions.docx"
# Masthead/art baseline (Revision D layout). Prefer canonical if present.
TEMPLATE_CANDIDATES = [
    CANONICAL,
    DOCS / "HART Railroad Scale Operating Instructions_RevD.docx",
    DOCS / "HART Railroad Scale Operating Instructions.docx",
]

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crew_master  # noqa: E402

# The title, publication line and body come from the crew master (ops/hart-ops/data/crew.json, "scale", ADR-039).
_SCALE = crew_master.load()["scale"]
REVISION = _SCALE["revision"]
PUBLICATION = {
    "title_line": f"{_SCALE['title']}  ·  Revision {REVISION}",
    "ops": "Neville Island Operations",
    "authority": "Issuing Authority: Office of the Superintendent",
    "eq": f"Publication {_SCALE['pub']}",
    "effective": f"Effective {_SCALE['effective']}",
    "revision": f"Revision {REVISION}",
    "official": "Official Publication",
}

# Layout of each section's heading, by section number (the Revision D layout). A spacer is an empty Heading 1 that
# keeps the column rhythm (user edit) before Section 3.
SECTION_LAYOUT: dict[int, dict] = {
    1: {"space_before": "0"},
    2: {"column_break_before": True, "space_before": "0", "heading_color": "0F4761"},
    3: {"spacer_before": True},
}


def _content() -> list[dict]:
    """Body content after Official Publication. kind: h1 | h2 | intro | steps | spacer."""
    out: list[dict] = []
    n = 0
    for block in crew_master.scale_blocks({"scale": _SCALE}):
        if block["kind"] == "h1":
            n += 1
            layout = dict(SECTION_LAYOUT.get(n, {}))
            if layout.pop("spacer_before", False):
                out.append({"kind": "spacer"})
            block = {**block, **layout}
        out.append(block)
    return out


CONTENT: list[dict] = _content()


def _ensure_pPr(p_el):
    pPr = p_el.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p_el.insert(0, pPr)
    return pPr


def _set_p_style(p_el, style_id: str) -> None:
    pPr = _ensure_pPr(p_el)
    pStyle = pPr.find(qn("w:pStyle"))
    if pStyle is None:
        pStyle = OxmlElement("w:pStyle")
        pPr.insert(0, pStyle)
    pStyle.set(qn("w:val"), style_id)


def _set_spacing_before(p_el, before: str) -> None:
    pPr = _ensure_pPr(p_el)
    sp = pPr.find(qn("w:spacing"))
    if sp is None:
        sp = OxmlElement("w:spacing")
        pPr.append(sp)
    sp.set(qn("w:before"), before)


def _set_ind_left(p_el, left: str = "540") -> None:
    pPr = _ensure_pPr(p_el)
    ind = pPr.find(qn("w:ind"))
    if ind is None:
        ind = OxmlElement("w:ind")
        numPr = pPr.find(qn("w:numPr"))
        if numPr is not None:
            numPr.addnext(ind)
        else:
            pPr.append(ind)
    ind.set(qn("w:left"), left)


def _clear_runs(p_el) -> None:
    for child in list(p_el):
        if child.tag != qn("w:pPr"):
            p_el.remove(child)


def _add_text_run(
    p_el,
    text: str,
    *,
    sz: str | None = None,
    color: str | None = None,
) -> None:
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    if sz is not None:
        for tag in ("w:sz", "w:szCs"):
            el = OxmlElement(tag)
            el.set(qn("w:val"), sz)
            rPr.append(el)
    if color is not None:
        c = OxmlElement("w:color")
        c.set(qn("w:val"), color)
        c.set(qn("w:themeColor"), "accent1")
        c.set(qn("w:themeShade"), "BF")
        rPr.append(c)
    if len(rPr):
        r.append(rPr)
    t = OxmlElement("w:t")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = text
    r.append(t)
    p_el.append(r)


def _add_break_run(p_el, break_type: str, at_start: bool = False) -> None:
    r = OxmlElement("w:r")
    br = OxmlElement("w:br")
    br.set(qn("w:type"), break_type)
    r.append(br)
    pPr = p_el.find(qn("w:pPr"))
    if at_start and pPr is not None:
        pPr.addnext(r)
    else:
        p_el.append(r)


def _set_numPr(p_el, num_id: str) -> None:
    pPr = _ensure_pPr(p_el)
    old = pPr.find(qn("w:numPr"))
    if old is not None:
        pPr.remove(old)
    numPr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    numId = OxmlElement("w:numId")
    numId.set(qn("w:val"), str(num_id))
    numPr.append(ilvl)
    numPr.append(numId)
    pStyle = pPr.find(qn("w:pStyle"))
    if pStyle is not None:
        pStyle.addnext(numPr)
    else:
        pPr.insert(0, numPr)
    # Match Compact list mark size used elsewhere in this doc.
    rPr = pPr.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        pPr.append(rPr)
    for child in list(rPr):
        rPr.remove(child)
    for tag, val in (("w:sz", "16"), ("w:szCs", "16")):
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        rPr.append(el)


def _new_list_num(numbering, abstract_src: str = "2") -> str:
    """Clone abstract + num with startOverride so each subsection restarts at 1."""
    src = None
    for an in numbering.findall(qn("w:abstractNum")):
        if an.get(qn("w:abstractNumId")) == abstract_src:
            src = an
            break
    if src is None:
        raise RuntimeError(f"abstractNum {abstract_src} not found")

    abs_ids = [int(a.get(qn("w:abstractNumId"))) for a in numbering.findall(qn("w:abstractNum"))]
    num_ids = [int(n.get(qn("w:numId"))) for n in numbering.findall(qn("w:num"))]
    new_abs_id = max(abs_ids) + 1
    new_num_id = max(num_ids) + 1

    new_abs = deepcopy(src)
    new_abs.set(qn("w:abstractNumId"), str(new_abs_id))
    nsid = new_abs.find(qn("w:nsid"))
    if nsid is not None:
        nsid.set(qn("w:val"), f"{new_abs_id:08X}")
    for lvl in new_abs.findall(qn("w:lvl")):
        if lvl.get(qn("w:ilvl")) == "0":
            start = lvl.find(qn("w:start"))
            if start is None:
                start = OxmlElement("w:start")
                lvl.insert(0, start)
            start.set(qn("w:val"), "1")

    first_num = numbering.find(qn("w:num"))
    if first_num is not None:
        first_num.addprevious(new_abs)
    else:
        numbering.append(new_abs)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(new_num_id))
    abs_ref = OxmlElement("w:abstractNumId")
    abs_ref.set(qn("w:val"), str(new_abs_id))
    num.append(abs_ref)
    override = OxmlElement("w:lvlOverride")
    override.set(qn("w:ilvl"), "0")
    start_override = OxmlElement("w:startOverride")
    start_override.set(qn("w:val"), "1")
    override.append(start_override)
    num.append(override)
    numbering.append(num)
    return str(new_num_id)


def _set_text_preserve_runs(p, text: str) -> None:
    texts = p._p.findall(".//" + qn("w:t"))
    if texts:
        texts[0].text = text
        for t in texts[1:]:
            t.text = ""
    else:
        _add_text_run(p._p, text)


def _find_template() -> Path:
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "No masthead template found. Expected one of:\n  "
        + "\n  ".join(str(p) for p in TEMPLATE_CANDIDATES)
    )


def _update_masthead(doc: Document) -> None:
    """Refresh publication block lines; leave decorative drawings alone."""
    replacements = {
        "Scale Operating Instructions": PUBLICATION["title_line"],
        "Neville Island Operations": PUBLICATION["ops"],
        "Issuing Authority:": PUBLICATION["authority"],
        "Publication EQ-": PUBLICATION["eq"],
        "Effective ": PUBLICATION["effective"],
        "Revision ": PUBLICATION["revision"],
        "Official Publication": PUBLICATION["official"],
    }
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if not t:
            continue
        for prefix, new in replacements.items():
            if t.startswith(prefix) or t == new:
                # Exact / prefix match for known masthead lines
                if prefix == "Revision " and not (
                    t.startswith("Revision ") or t.startswith("Scale Operating")
                ):
                    continue
                if prefix == "Scale Operating Instructions" and "Scale Operating" not in t:
                    continue
                if prefix == "Revision " and t.startswith("Scale Operating"):
                    continue
                _set_text_preserve_runs(p, new)
                break
        # Title line may already be full string
        if "Scale Operating Instructions" in t and "Revision" in t:
            _set_text_preserve_runs(p, PUBLICATION["title_line"])


def _strip_body_after_official(doc: Document):
    """Remove all paragraphs after Official Publication; return that paragraph."""
    official = None
    for p in doc.paragraphs:
        if (p.text or "").strip() == "Official Publication":
            official = p
            break
    if official is None:
        raise RuntimeError("Official Publication paragraph not found in template")

    body = doc.element.body
    # Collect removable elements after official._p until final sectPr
    remove = []
    seen_official = False
    for child in list(body):
        if child is official._p:
            seen_official = True
            continue
        if not seen_official:
            continue
        if child.tag == qn("w:sectPr"):
            break
        remove.append(child)
    for el in remove:
        body.remove(el)

    # Ensure page break on Official Publication (not a following empty para)
    for r in list(official._p.findall(qn("w:r"))):
        for br in list(r.findall(qn("w:br"))):
            if br.get(qn("w:type")) == "page":
                r.remove(br)
        if (
            r.find(qn("w:t")) is None
            and r.find(qn("w:br")) is None
            and r.find(qn("w:drawing")) is None
        ):
            # orphan rPr-only run after stripping break
            if r.find(qn("w:tab")) is None:
                official._p.remove(r)
    _add_break_run(official._p, "page", at_start=False)
    return official


def _ensure_two_columns(doc: Document) -> None:
    body = doc.element.body
    sect = None
    for child in body:
        if child.tag == qn("w:sectPr"):
            sect = child
    if sect is None:
        raise RuntimeError("Document has no body sectPr")
    stype = sect.find(qn("w:type"))
    if stype is not None:
        sect.remove(stype)
    cols = sect.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sect.append(cols)
    cols.set(qn("w:num"), "2")
    if cols.get(qn("w:space")) is None:
        cols.set(qn("w:space"), "400")
    cols.set(qn("w:equalWidth"), "1")


def _new_paragraph(style_id: str) -> OxmlElement:
    p = OxmlElement("w:p")
    _set_p_style(p, style_id)
    return p


def rebuild(out: Path = CANONICAL) -> Path:
    template = _find_template()
    if template.resolve() != out.resolve():
        shutil.copy2(template, out)
    else:
        # Working copy so we can rebuild in place safely
        tmp = out.with_suffix(".rebuild.docx")
        shutil.copy2(template, tmp)
        out = tmp

    doc = Document(out)
    numbering = doc.part.numbering_part._element

    _update_masthead(doc)
    official = _strip_body_after_official(doc)
    insert_after = official._p

    def append_p(p_el):
        nonlocal insert_after
        insert_after.addnext(p_el)
        insert_after = p_el

    for block in CONTENT:
        kind = block["kind"]
        if kind == "spacer":
            p = _new_paragraph("Heading1")
            append_p(p)
            continue

        if kind == "h1":
            p = _new_paragraph("Heading1")
            if block.get("space_before") is not None:
                _set_spacing_before(p, block["space_before"])
            if block.get("column_break_before"):
                _add_break_run(p, "column", at_start=True)
            _add_text_run(
                p,
                block["text"],
                sz="26",
                color=block.get("heading_color"),
            )
            append_p(p)
            continue

        if kind == "h2":
            p = _new_paragraph("Heading2")
            # Match existing Heading 2 outdent used in this publication
            pPr = _ensure_pPr(p)
            ind = OxmlElement("w:ind")
            ind.set(qn("w:left"), "-180")
            pPr.append(ind)
            _add_text_run(p, block["text"], sz="23")
            append_p(p)
            continue

        if kind == "intro":
            p = _new_paragraph("FirstParagraph")
            _add_text_run(p, block["text"], sz="22")
            append_p(p)
            continue

        if kind == "steps":
            num_id = _new_list_num(numbering, "2")
            for item in block["items"]:
                p = _new_paragraph("Compact")
                _set_numPr(p, num_id)
                _set_ind_left(p, "540")
                _add_text_run(p, item, sz="22")
                append_p(p)
            continue

        raise ValueError(f"Unknown block kind: {kind}")

    _ensure_two_columns(doc)
    final = CANONICAL
    doc.save(final)
    if out != final and out.exists() and out.suffix == ".docx" and "rebuild" in out.name:
        out.unlink(missing_ok=True)
    return final


def main() -> None:
    path = rebuild()
    print(f"Wrote {path} (Revision {REVISION})")


if __name__ == "__main__":
    main()
