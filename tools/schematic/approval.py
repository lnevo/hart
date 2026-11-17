"""Approval fingerprints for the built panels the owner approved (shared by tools/schematic/check_approved.py).

A fingerprint is one line per element: its sha256 (attributes sorted, layout whitespace dropped) and what it is. The
first line is the root's own attributes, the last the whole document's hash. It is the same file shape as
jmri/layouts/hart/data/schematic/approved_staging.sha256, which build_layout_le.py still writes and reads itself
(approved_fingerprint, write_approved, read_approved, check_approved there; they should move here later and
build_layout_le.py import them).

What is guarded (OUTPUTS): the three-level "HART Railroad" Layout Editor panel in the live tables.xml (staging, main
and upper in one panel) and the two CATS desks. The check reads the built files; it never builds. The Layout Editor
window and view attributes (VIEW_ATTRS: position, window and panel size, zoom, edit-mode switches) are left out of
the hash, since every PanelPro Store rewrites them; everything that draws or joins track is kept. The live panel is
read from this checkout's tables.xml (paths.REPO_TABLES_XML), never from HART_TABLES. `le-candidate` is the panel of the
cut-over candidate that build_layout_le.py --as-live writes, with a fingerprint of its own (PanelPro's Store reorders
and rewrites the installed panel, so the two differ); it catches a change before it is installed.
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
NAME_ATTRS = ("ident", "signalmast", "text", "blockcontents", "sensor", "turnout", "TEMPLATENAME",
              "NAME", "USERNAME", "FONTKEY", "KEY", "LABEL")
# Written by PanelPro itself on every Store, or when the editor's mode is switched: not the panel's drawing.
VIEW_ATTRS = frozenset({
    "x", "y", "windowheight", "windowwidth", "panelheight", "panelwidth", "xscale", "yscale", "editable",
    "positionable", "controlling", "showhelpbar", "drawgrid", "snaponadd", "snaponmove", "tooltipsnotedit",
    "tooltipsinedit", "sliders", "scrollable", "gridSize", "gridSize2nd"})
# Elements whose children are fingerprinted one by one (a desk keeps nearly everything in one TRACKPLAN).
EXPAND = frozenset({"TRACKPLAN"})
REAPPROVE = "python3 tools/schematic/check_approved.py --approve"


class ApprovalError(Exception):
    """A fingerprint cannot be read or written, or an output is not the approved one."""


def elements(el: ET.Element) -> list[ET.Element]:
    """el's children without comments and processing instructions (their tag is a function, not text)."""
    return [c for c in el if isinstance(c.tag, str)]


def canon_sorted(el: ET.Element, drop_attrs: frozenset[str] = frozenset()) -> str:
    """An element as text with each element's attributes in name order, no comments, no whitespace-only text or
    tail; text with content is kept exactly. `drop_attrs` leaves those attributes of `el` itself out."""
    e = copy.deepcopy(el)
    for k in drop_attrs:
        e.attrib.pop(k, None)
    for c in e.iter():
        for child in [x for x in c if not isinstance(x.tag, str)]:
            c.remove(child)
    for c in e.iter():
        c.attrib = dict(sorted(c.attrib.items()))
        c.tail = c.tail if (c.tail or "").strip() else None
        c.text = c.text if (c.text or "").strip() else None
    e.tail = None
    return ET.tostring(e, encoding="unicode")


def _sha(el: ET.Element, drop_attrs: frozenset[str] = frozenset()) -> str:
    return hashlib.sha256(canon_sorted(el, drop_attrs).encode()).hexdigest()


def element_label(el: ET.Element, index: int, prefix: str = "") -> str:
    """What an element is, for a message: its tag and a name-like attribute, else its X,Y place (and its first
    child's name), else its position."""
    name = next((el.get(a) for a in NAME_ATTRS if el.get(a)), None)
    if name is None and el.get("X") is not None and el.get("Y") is not None:
        inner = next((c.get("NAME") for c in elements(el) if c.get("NAME")), None)
        name = f"{el.get('X')},{el.get('Y')}" + (f" {inner}" if inner else "")
    return f"{prefix}{el.tag} {' '.join((name or f'#{index}').split())}"


def fingerprint(root: ET.Element, kind: str, drop_attrs: frozenset[str] = frozenset()) -> list[tuple[str, str]]:
    """[(sha256, what)]: the root's own attributes (less `drop_attrs`), each child in order (the children of an
    EXPAND element one by one, labelled TAG/CHILD), then the whole root (less `drop_attrs`)."""
    head = ET.Element(root.tag, root.attrib)
    out = [(_sha(head, drop_attrs), f"{kind} {root.get('name') or root.tag}")]
    n = 0
    for el in elements(root):
        if el.tag in EXPAND:
            out.append((_sha(ET.Element(el.tag, el.attrib)), element_label(el, n)))
            out += [(_sha(c), element_label(c, i, f"{el.tag}/")) for i, c in enumerate(elements(el))]
        else:
            out.append((_sha(el), element_label(el, n)))
        n += 1
    out.append((_sha(root, drop_attrs), "panel"))
    return out


def format_fingerprint(fp: list[tuple[str, str]], note: str) -> str:
    return note + "\n".join(f"{h} {what}" for h, what in fp) + "\n"


def parse_fingerprint(text: str, label: str, kind: str) -> list[tuple[str, str]]:
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
    if not out[0][1].startswith(f"{kind} "):
        raise ApprovalError(f"{label}: its first line should be the {kind} root's own attributes, not {out[0][1]!r}")
    return out


def compare(want: list[tuple[str, str]], got: list[tuple[str, str]]) -> str | None:
    """None when the two fingerprints agree, else the first difference in words (child 1 is the first child)."""
    if want[-1] == got[-1]:
        return None
    for i, (w, g) in enumerate(zip(want[:-1], got[:-1])):
        if w != g:
            if i == 0:
                return "the root's own attributes changed"
            return f"child {i} is {g[1]}, approved {w[1]}" + (" (changed)" if w[1] == g[1] else "")
    if len(got) != len(want):
        return f"it has {len(got) - 2} children, approved {len(want) - 2}"
    return "the whole-document hash differs"


@dataclass(frozen=True)
class Output:
    key: str
    what: str
    source: Path      # the built file
    approved: Path    # its fingerprint
    kind: str
    panel: str | None = None                    # for tables.xml: the Layout Editor panel's name
    drop_attrs: frozenset[str] = frozenset()    # attributes of the root left out of the hash
    default: bool = True                        # checked when no key is named


OUTPUTS = (
    Output("le-panel", 'the "HART Railroad" Layout Editor panel (staging, main and upper)', paths.REPO_TABLES_XML,
           DATA / "approved_le_panel.sha256", "LayoutEditor", PANEL_NAME, VIEW_ATTRS),
    Output("le-candidate", 'the cut-over candidate\'s "HART Railroad" Layout Editor panel',
           paths.LAYOUT_OUTPUT / "trial" / "tables_cutover.xml", DATA / "approved_le_candidate.sha256", "LayoutEditor",
           PANEL_NAME, VIEW_ATTRS, default=False),
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
            "# CHECK=1). One line per element, in order: its sha256 (attributes sorted, layout whitespace dropped, the\n"
            "# editor's window and view attributes left out) and what it is; the first line is the root's own\n"
            "# attributes, the last the whole document's hash.\n")


def approve(out: Output, date: str | None = None) -> None:
    fp = fingerprint(load_root(out), out.kind, out.drop_attrs)
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
                            f"after the owner approves {out.what}, run {REAPPROVE} {out.key}") from None
    want = parse_fingerprint(text, paths.rel(out.approved), out.kind)
    diff = compare(want, fingerprint(load_root(out), out.kind, out.drop_attrs))
    if diff:
        raise ApprovalError(f"{out.key}: {out.what} ({paths.rel(out.source)}) is not the one the owner approved "
                            f"({paths.rel(out.approved)}): {diff}. If the owner approved this change, run "
                            f"{REAPPROVE} {out.key}; otherwise undo it")
