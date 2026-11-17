"""Approval fingerprints for the built panels the owner approved (shared by tools/schematic/check_approved.py).

A fingerprint is one line per element: its sha256 (attributes sorted, layout whitespace dropped) and what it is. The
first line is the root's own attributes, the last the whole document's hash. It is the same file shape as
jmri/layouts/hart/data/schematic/approved_staging.sha256, which build_layout_le.py still writes and reads itself
(approved_fingerprint, write_approved, read_approved, check_approved there; they should move here later and
build_layout_le.py import them).

What is guarded (OUTPUTS): the three-level "HART Railroad" Layout Editor panel in the live tables.xml (staging, main
and upper in one panel) and the two CATS desks. The check reads the built files; it never builds.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "hartlib" / "src"))

from hartlib import paths, tables  # noqa: E402

DATA = paths.LAYOUT_DATA / "schematic"
PANEL_NAME = "HART Railroad"
NAME_ATTRS = ("ident", "signalmast", "text", "blockcontents", "sensor", "turnout",
              "NAME", "USERNAME", "FONTKEY", "KEY", "LABEL")
REAPPROVE = "python3 tools/schematic/check_approved.py --approve"


class ApprovalError(Exception):
    """A fingerprint cannot be read or written, or an output is not the approved one."""


def canon_sorted(el: ET.Element) -> str:
    """An element as text with each element's attributes in name order and no layout whitespace."""
    e = copy.deepcopy(el)
    for c in e.iter():
        c.attrib = dict(sorted(c.attrib.items()))
        c.tail = None
        c.text = (c.text or "").strip() or None
    return ET.tostring(e, encoding="unicode")


def _sha(el: ET.Element) -> str:
    return hashlib.sha256(canon_sorted(el).encode()).hexdigest()


def element_label(el: ET.Element, index: int) -> str:
    """What an element is, for a message: its tag and a name-like attribute, else its position."""
    name = next((el.get(a) for a in NAME_ATTRS if el.get(a)), f"#{index}")
    return f"{el.tag} {' '.join(name.split())}"


def fingerprint(root: ET.Element, kind: str) -> list[tuple[str, str]]:
    """[(sha256, what)]: the root's own attributes, each child in order, then the whole root."""
    head = ET.Element(root.tag, root.attrib)
    out = [(_sha(head), f"{kind} {root.get('name') or root.tag}")]
    out += [(_sha(el), element_label(el, i)) for i, el in enumerate(root)]
    out.append((_sha(root), "panel"))
    return out


def format_fingerprint(fp: list[tuple[str, str]], note: str) -> str:
    return note + "\n".join(f"{h} {what}" for h, what in fp) + "\n"


def parse_fingerprint(text: str, label: str) -> list[tuple[str, str]]:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        m = re.fullmatch(r"([0-9a-f]{64}) (\S.*)", line)
        if not m:
            raise ApprovalError(f"{label} line {n}: not '<sha256> <what>'")
        out.append((m.group(1), m.group(2)))
    if len(out) < 2 or out[-1][1] != "panel":
        raise ApprovalError(f"{label}: no panel hash on its last line")
    return out


def compare(want: list[tuple[str, str]], got: list[tuple[str, str]]) -> str | None:
    """None when the two fingerprints agree, else the first difference in words."""
    if want[-1] == got[-1]:
        return None
    for i, (w, g) in enumerate(zip(want[:-1], got[:-1])):
        if w != g:
            return f"element {i} is {g[1]}, approved {w[1]}" + (" (changed)" if w[1] == g[1] else "")
    if len(got) != len(want):
        return f"it has {len(got) - 2} elements, approved {len(want) - 2}"
    return "the whole-panel hash differs"


@dataclass(frozen=True)
class Output:
    key: str
    what: str
    source: Path      # the built file
    approved: Path    # its fingerprint
    kind: str
    panel: str | None = None   # for tables.xml: the Layout Editor panel's name


OUTPUTS = (
    Output("le-panel", 'the "HART Railroad" Layout Editor panel (staging, main and upper)', paths.TABLES_XML,
           DATA / "approved_le_panel.sha256", "LayoutEditor", PANEL_NAME),
    Output("cats-ctc", "the CATS CTC desk", paths.REPO_ROOT / "cats/panels/HART_CTC.xml",
           DATA / "approved_cats_ctc.sha256", "DOCUMENT"),
    Output("cats-abs", "the CATS ABS desk", paths.REPO_ROOT / "cats/panels/HART_ABS.xml",
           DATA / "approved_cats_abs.sha256", "DOCUMENT"),
)


def load_root(out: Output) -> ET.Element:
    """The element to fingerprint: the named panel of a tables file, or a desk file's root."""
    try:
        data = out.source.read_bytes()
    except OSError as exc:
        raise ApprovalError(f"cannot read {out.what} ({paths.rel(out.source)}): {exc}") from None
    try:
        if out.panel is None:
            return ET.fromstring(data)
        panel = tables.layout_editor(tables.loads(data).root, out.panel)
    except ET.ParseError as exc:
        raise ApprovalError(f"{paths.rel(out.source)} is not valid XML: {exc}") from None
    if panel is None:
        raise ApprovalError(f"{paths.rel(out.source)} has no Layout Editor panel named {out.panel!r}")
    return panel


def note_for(out: Output, date: str) -> str:
    return (f"# {out.what[0].upper()}{out.what[1:]} ({paths.rel(out.source)}) as approved by the owner on {date}\n"
            "# (recorded by tools/schematic/check_approved.py --approve; checked by ./tools/check.sh and make panels\n"
            "# CHECK=1). One line per element, in order: its sha256 (attributes sorted, layout whitespace dropped) and\n"
            "# what it is; the first line is the root's own attributes, the last the whole document's hash.\n")


def approve(out: Output, date: str | None = None) -> None:
    fp = fingerprint(load_root(out), out.kind)
    text = format_fingerprint(fp, note_for(out, date or datetime.date.today().isoformat()))
    try:
        out.approved.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ApprovalError(f"cannot write {paths.rel(out.approved)}: {exc}") from None


def check(out: Output) -> None:
    """Stop with ApprovalError unless the built output is the approved one, saying which and how to re-approve."""
    try:
        text = out.approved.read_text(encoding="utf-8")
    except OSError as exc:
        raise ApprovalError(f"{out.key}: cannot read the approved fingerprint {paths.rel(out.approved)}: {exc}; "
                            f"after the owner approves {out.what}, run {REAPPROVE}") from None
    want = parse_fingerprint(text, paths.rel(out.approved))
    diff = compare(want, fingerprint(load_root(out), out.kind))
    if diff:
        raise ApprovalError(f"{out.key}: {out.what} ({paths.rel(out.source)}) is not the one the owner approved "
                            f"({paths.rel(out.approved)}): {diff}. If the owner approved this change, run "
                            f"{REAPPROVE} {out.key}; otherwise undo it")
