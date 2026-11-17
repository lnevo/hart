"""The approval fingerprint of the staging cut-over candidate's panel (approved_staging.sha256): written by
build_layout_le.py --approve-staging and checked by both cut-over builds. tools/schematic/approval.py fingerprints
the installed panels and CATS desks the same way."""
from __future__ import annotations

import copy
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
from hartlib import paths  # noqa: E402
from le_common import BuildError  # noqa: E402


# The staging candidate's panel as the owner approved it: a hash per element (approved_fingerprint), so a plugin bump
# or an overlay edit that changes the approved staging panel stops both cut-over builds. Refreshed only by
# --approve-staging, after the owner approves the new panel in PanelPro.
APPROVED = pd.DATA / "approved_staging.sha256"
APPROVED_NOTE = ("# The staging cut-over candidate's \"HART Railroad\" panel as approved by the owner in PanelPro on {date}\n"
                 "# (build_layout_le.py --approve-staging; checked by --levels staging --as-live and --as-live). One line\n"
                 "# per element, in panel order: its sha256 (attributes sorted, layout whitespace dropped) and what it\n"
                 "# is; the first line is the panel's own attributes, the last the whole panel's hash.\n")


def canon_sorted(el: ET.Element) -> str:
    """An element as text with each element's attributes in name order and no layout whitespace."""
    e = copy.deepcopy(el)
    for c in e.iter():
        c.attrib = dict(sorted(c.attrib.items()))
        c.tail = None
        c.text = (c.text or "").strip() or None
    return ET.tostring(e, encoding="unicode")


def element_label(el: ET.Element, index: int) -> str:
    """What a panel element is, for a message: its tag and name (ident, mast, text, block, sensor, turnout)."""
    name = next((el.get(a) for a in ("ident", "signalmast", "text", "blockcontents", "sensor", "turnout") if el.get(a)),
                f"#{index}")
    return f"{el.tag} {name}"


def approved_fingerprint(panel_el: ET.Element) -> list[tuple[str, str]]:
    """[(sha256, what)]: the panel's own attributes, then each element in order, then the whole panel."""
    head = ET.Element(panel_el.tag, panel_el.attrib)
    out = [(hashlib.sha256(canon_sorted(head).encode()).hexdigest(), f"LayoutEditor {panel_el.get('name')}")]
    out += [(hashlib.sha256(canon_sorted(el).encode()).hexdigest(), element_label(el, i))
            for i, el in enumerate(panel_el)]
    out.append((hashlib.sha256(canon_sorted(panel_el).encode()).hexdigest(), "panel"))
    return out


def write_approved(panel_el: ET.Element, path: Path = APPROVED, date: str | None = None) -> None:
    """Write the staging panel's fingerprint (approved_fingerprint) to `path` (--approve-staging)."""
    import datetime
    lines = [f"{h} {what}" for h, what in approved_fingerprint(panel_el)]
    try:
        path.write_text(APPROVED_NOTE.format(date=date or datetime.date.today().isoformat()) + "\n".join(lines) + "\n",
                        encoding="utf-8")
    except OSError as exc:
        raise BuildError(f"cannot write {path}: {exc}") from None


def read_approved(path: Path = APPROVED) -> list[tuple[str, str]]:
    """The approved fingerprint's [(sha256, what)]; stops on a missing file or a line of the wrong shape."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BuildError(f"cannot read the approved staging fingerprint {paths.rel(path)}: {exc}; after the owner "
                         "approves the staging panel, run build_layout_le.py --approve-staging") from None
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        m = re.fullmatch(r"([0-9a-f]{64}) (\S.*)", line)
        if not m:
            raise BuildError(f"{paths.rel(path)} line {n}: not '<sha256> <what>'")
        out.append((m.group(1), m.group(2)))
    if len(out) < 2 or out[-1][1] != "panel":
        raise BuildError(f"{paths.rel(path)}: no panel hash on its last line")
    return out


def check_approved(panel_el: ET.Element, path: Path = APPROVED) -> None:
    """Stop with BuildError unless the staging candidate's panel is the one the owner approved (`path`), naming the
    first element that differs."""
    want, got = read_approved(path), approved_fingerprint(panel_el)
    if want[-1] == got[-1]:
        return
    for i, (w, g) in enumerate(zip(want, got)):
        if w != g:
            raise BuildError(f"the staging panel is not the one the owner approved ({paths.rel(path)}): element {i} "
                             f"is {g[1]}, approved {w[1]}" + (" (changed)" if w[1] == g[1] else ""))
    raise BuildError(f"the staging panel is not the one the owner approved ({paths.rel(path)}): it has "
                     f"{len(got) - 2} elements, approved {len(want) - 2}")
