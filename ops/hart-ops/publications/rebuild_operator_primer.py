#!/usr/bin/env python3
"""Rebuild Neville Island New Operator Primer (HB-01, Revision B).

Readable pre-session handbook for new crew: island background, how the
railroad works, jobs at a glance, destination colors, scale overview, and
pointers to the desk sheets used during the session.

The text is in publications/data/operator_primer.json: the publication id, the jobs, the
primer's train for each crew-master colour, and the pages as a list of blocks (heading,
body, bullets, jobs, color_table, links, signature). The colours and destinations come from
the crew master, ops/hart-ops/data/crew.json.

Usage (from ops/hart-ops):
  .venv/bin/python publications/rebuild_operator_primer.py

Writes:
  docs/ops/Neville_Island_New_Operator_Primer.docx
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple, NotRequired, TypedDict, TypeVar, cast

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT.parents[1] / "docs/ops"
PUB = Path(__file__).resolve().parent
sys.path.insert(0, str(PUB))

import crew_master  # noqa: E402
from hart_pub_helpers import (  # noqa: E402
    ACCENT,
    BODY,
    MUTED,
    RULE,
    _set_run_font,
    add_horizontal_rule,
    add_publication_footer,
    add_station_map_page,
    fill_header_row,
    fill_swatch_cell,
    style_table,
)

CANONICAL = DOCS / "Neville_Island_New_Operator_Primer.docx"
TEXT = PUB / "data" / "operator_primer.json"


class PrimerDataError(ValueError):
    """operator_primer.json is missing a field or holds a block the builder does not know."""


class Publication(TypedDict):
    title: str
    pub_id: str
    revision: str
    effective: str


class Job(NamedTuple):
    code: str
    name: str
    blurb: str


class Link(TypedDict):
    label: str
    url: str


class Block(TypedDict):
    """One block of a page. kind picks the fields: heading and body take text, bullets take
    items, links take link items; jobs, color_table and signature take nothing."""

    kind: str
    text: NotRequired[str]
    space_before: NotRequired[float]
    space_after: NotRequired[float]
    items: NotRequired[list[str] | list[Link]]


class SignatureLine(TypedDict):
    text: str
    bold: bool


class Signature(TypedDict):
    closing: str
    lines: list[SignatureLine]


class PrimerText(NamedTuple):
    publication: Publication
    subtitle: str
    block_train: dict[str, str]
    jobs: list[Job]
    pages: list[list[Block]]
    signature: Signature


BLOCK_FIELDS: dict[str, frozenset[str]] = {
    "heading": frozenset({"text", "space_before"}),
    "body": frozenset({"text", "space_before", "space_after"}),
    "bullets": frozenset({"items"}),
    "links": frozenset({"items"}),
    "jobs": frozenset(),
    "color_table": frozenset(),
    "signature": frozenset(),
}


T = TypeVar("T")


def _require(raw: Mapping[str, object], key: str, kind: type[T], where: str) -> T:
    """raw[key] when it is a kind; PrimerDataError naming where, the key and what was there otherwise."""
    value = raw.get(key)
    if not isinstance(value, kind):
        raise PrimerDataError(f"{where}: {key!r} must be a {kind.__name__}, got {value!r}")
    return value


def _check_block(block: object, where: str) -> Block:
    """block when its kind is known and it carries the fields that kind reads, and no others."""
    if not isinstance(block, dict):
        raise PrimerDataError(f"{where}: a block must be an object, got {block!r}")
    kind = block.get("kind")
    if kind not in BLOCK_FIELDS:
        raise PrimerDataError(f"{where}: unknown block kind {kind!r} (known: {', '.join(BLOCK_FIELDS)})")
    extra = set(block) - {"kind"} - BLOCK_FIELDS[kind]
    if extra:
        raise PrimerDataError(f"{where}: {kind} block has fields it does not use: {sorted(extra)}")
    if kind in ("heading", "body"):
        _require(block, "text", str, where)
    elif kind == "bullets":
        if not all(isinstance(i, str) for i in _require(block, "items", list, where)):
            raise PrimerDataError(f"{where}: bullets items must be strings")
    elif kind == "links":
        for link in _require(block, "items", list, where):
            if not (isinstance(link, dict) and isinstance(link.get("label"), str) and isinstance(link.get("url"), str)):
                raise PrimerDataError(f"{where}: a link needs a label and a url, got {link!r}")
    return cast(Block, block)


def _check_signature(raw: Mapping[str, object], where: str) -> Signature:
    signature = _require(raw, "signature", dict, where)
    _require(signature, "closing", str, f"{where} signature")
    for line in _require(signature, "lines", list, f"{where} signature"):
        if not (isinstance(line, dict) and isinstance(line.get("text"), str) and isinstance(line.get("bold"), bool)):
            raise PrimerDataError(f"{where} signature: a line needs text and bold, got {line!r}")
    return cast(Signature, signature)


def load_text(path: Path = TEXT) -> PrimerText:
    """The primer text, checked up front: every block kind known, every field the builder reads present."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrimerDataError(f"{path}: cannot read the primer text: {exc}") from exc
    where = path.name
    if not isinstance(raw, dict):
        raise PrimerDataError(f"{where}: the top level must be an object")
    publication = _require(raw, "publication", dict, where)
    for key in Publication.__annotations__:
        _require(publication, key, str, f"{where} publication")
    jobs = []
    for i, job in enumerate(_require(raw, "jobs", list, where)):
        if not isinstance(job, dict):
            raise PrimerDataError(f"{where} job {i + 1}: must be an object, got {job!r}")
        jobs.append(Job(*(_require(job, key, str, f"{where} job {i + 1}") for key in Job._fields)))
    pages: list[list[Block]] = []
    for p, page in enumerate(_require(raw, "pages", list, where)):
        if not isinstance(page, list):
            raise PrimerDataError(f"{where} page {p + 1}: must be a list of blocks")
        pages.append([_check_block(b, f"{where} page {p + 1} block {i + 1}") for i, b in enumerate(page)])
    kinds = [b["kind"] for page in pages for b in page]
    for once in ("jobs", "color_table", "signature"):
        if kinds.count(once) != 1:
            raise PrimerDataError(f"{where}: the pages need one {once} block, found {kinds.count(once)}")
    block_train = _require(raw, "block_train", dict, where)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in block_train.items()):
        raise PrimerDataError(f"{where}: block_train maps colour ids to train names (strings)")
    return PrimerText(
        publication=cast(Publication, publication),
        subtitle=_require(raw, "subtitle", str, where),
        block_train=block_train,
        jobs=jobs,
        pages=pages,
        signature=_check_signature(raw, where),
    )


PRIMER = load_text()
PUBLICATION = PRIMER.publication
# The primer's short train name for each master colour; the colours and destinations come from the master.
PRIMER_BLOCK_TRAIN = PRIMER.block_train
JOBS = PRIMER.jobs


def _block_legend() -> list[tuple[str, str, str, str, str]]:
    """(label, fill, ink, destination, train) per master colour; a colour with no primer train stops the build."""
    rows = []
    for color_id, sw in crew_master.swatches(crew_master.load()).items():
        if color_id not in PRIMER_BLOCK_TRAIN:
            raise ValueError(f"{crew_master.MASTER.name}: colour {color_id!r} has no train in {TEXT.name} block_train")
        rows.append((sw.label, sw.fill, sw.ink, sw.dest, PRIMER_BLOCK_TRAIN[color_id]))
    return rows


BLOCK_LEGEND = _block_legend()


def _set_comfortable_page(doc: DocxDocument) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1.0)
    section.bottom_margin = Inches(1.0)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)
    section.header_distance = Inches(0.5)
    section.footer_distance = Inches(0.5)


def _page_break(doc: DocxDocument) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.add_run().add_break(WD_BREAK.PAGE)


def _light_masthead(doc: DocxDocument, text: PrimerText) -> None:
    brand = doc.add_paragraph()
    brand.alignment = WD_ALIGN_PARAGRAPH.CENTER
    brand.paragraph_format.space_before = Pt(0)
    brand.paragraph_format.space_after = Pt(4)
    r = brand.add_run("HART Railroad")
    _set_run_font(r, size_pt=20, bold=True, color=ACCENT)

    div = doc.add_paragraph()
    div.alignment = WD_ALIGN_PARAGRAPH.CENTER
    div.paragraph_format.space_before = Pt(0)
    div.paragraph_format.space_after = Pt(10)
    r = div.add_run("Pittsburgh & Chartiers Valley Division")
    _set_run_font(r, size_pt=11, color=MUTED)

    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(0)
    rule.paragraph_format.space_after = Pt(12)
    add_horizontal_rule(rule, RULE)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(4)
    r = title.add_run(text.publication["title"])
    _set_run_font(r, size_pt=16, bold=True, color=BODY)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_before = Pt(0)
    sub.paragraph_format.space_after = Pt(18)
    r = sub.add_run(text.subtitle)
    _set_run_font(r, size_pt=11, color=MUTED)


def _heading(doc: DocxDocument, text: str, *, space_before: float = 18) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    _set_run_font(r, size_pt=13, bold=True, color=ACCENT)
    add_horizontal_rule(p, ACCENT)


def _body(
    doc: DocxDocument,
    text: str,
    *,
    space_before: float = 0,
    space_after: float = 10,
) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.35
    r = p.add_run(text)
    _set_run_font(r, size_pt=11, color=BODY, name="Calibri")


def _bullets(doc: DocxDocument, items: list[str]) -> None:
    for item in items:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.3
        p.paragraph_format.left_indent = Inches(0.2)
        r = p.add_run(f"•  {item}")
        _set_run_font(r, size_pt=11, color=BODY, name="Calibri")


def _job_block(doc: DocxDocument, code: str, name: str, blurb: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(code)
    _set_run_font(r, size_pt=12, bold=True, color=ACCENT, name="Calibri")
    r = p.add_run(f"  ·  {name}")
    _set_run_font(r, size_pt=11, bold=True, color=BODY, name="Calibri")
    _body(doc, blurb, space_before=0, space_after=6)


def _add_color_table(doc: DocxDocument) -> None:
    table = doc.add_table(rows=1 + len(BLOCK_LEGEND), cols=3)
    style_table(table)
    fill_header_row(table.rows[0], ["Color", "Destination", "Train"])
    for i, (label, fill, text_hex, dest, blocking) in enumerate(BLOCK_LEGEND, start=1):
        row = table.rows[i]
        fill_swatch_cell(row.cells[0], label, fill_hex=fill, text_hex=text_hex)
        for cell, text in ((row.cells[1], dest), (row.cells[2], blocking)):
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            r = p.add_run(text)
            _set_run_font(r, size_pt=10, color=BODY, name="Calibri")


def _link_line(doc: DocxDocument, label: str, url: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.left_indent = Inches(0.2)
    p.paragraph_format.line_spacing = 1.3
    r = p.add_run(f"•  {label}\n     ")
    _set_run_font(r, size_pt=10.5, color=BODY, name="Calibri")
    r = p.add_run(url)
    _set_run_font(r, size_pt=9.5, color=ACCENT, name="Calibri")


def _station_map_banner(doc: DocxDocument) -> None:
    """The whole railroad on one strip, full text width, under the masthead."""
    pic = doc.add_paragraph()
    pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pic.paragraph_format.space_before = Pt(0)
    pic.paragraph_format.space_after = Pt(10)
    pic.add_run().add_picture(str(PUB / "assets" / "station_map_full.png"), width=Inches(6.5))


def _signature(doc: DocxDocument, signature: Signature) -> None:
    """A rule, the closing line, then the name (bold) and the titles under it."""
    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(20)
    rule.paragraph_format.space_after = Pt(12)
    add_horizontal_rule(rule)

    sig = doc.add_paragraph()
    sig.paragraph_format.space_before = Pt(0)
    sig.paragraph_format.space_after = Pt(2)
    r = sig.add_run(signature["closing"])
    _set_run_font(r, size_pt=11, color=BODY, name="Calibri")

    for line in signature["lines"]:
        bold = line["bold"]
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(line["text"])
        _set_run_font(
            r,
            size_pt=10.5 if bold else 10,
            bold=bold,
            color=BODY if bold else MUTED,
            name="Calibri",
        )


def _add_block(doc: DocxDocument, block: Block, text: PrimerText) -> None:
    """Write one page block; load_text has checked its kind and fields."""
    kind = block["kind"]
    if kind == "heading":
        _heading(doc, block["text"], space_before=block.get("space_before", 18))
    elif kind == "body":
        _body(doc, block["text"], space_before=block.get("space_before", 0), space_after=block.get("space_after", 10))
    elif kind == "bullets":
        _bullets(doc, cast("list[str]", block["items"]))
    elif kind == "jobs":
        for job in text.jobs:
            _job_block(doc, job.code, job.name, job.blurb)
    elif kind == "color_table":
        _add_color_table(doc)
    elif kind == "links":
        for link in cast("list[Link]", block["items"]):
            _link_line(doc, link["label"], link["url"])
    elif kind == "signature":
        _signature(doc, text.signature)
    else:
        raise PrimerDataError(f"{TEXT.name}: unknown block kind {kind!r}")


def build(text: PrimerText = PRIMER, out: Path = CANONICAL) -> Path:
    """Masthead and the full-railroad banner, the pages of text (a page break between pages),
    the station map page, the footer; saved to out."""
    doc = Document()
    _set_comfortable_page(doc)
    _light_masthead(doc, text)
    _station_map_banner(doc)

    for number, page in enumerate(text.pages):
        if number:
            _page_break(doc)
        for block in page:
            _add_block(doc, block, text)

    add_station_map_page(doc, page_break=True)
    add_publication_footer(
        doc,
        pub_id=text.publication["pub_id"],
        revision=text.publication["revision"],
        effective=text.publication["effective"],
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path}")
