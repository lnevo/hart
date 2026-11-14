"""public_name_map.csv: the DCC address column and the JMRI comment a row stands for.

The map keeps a turnout's DCC address in its own ``dcc`` column and the rest of the
wiring text in ``comment``. JMRI's turnout comment carries the address as the group
after the first one (ADR-005)::

    comment  Node: 4 Turnout: 0 | OU: 1 Ports: 1,2
    dcc      100
    JMRI     Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2

LCC aliases (``DCC Switch N``, hardware ``MTTN``) leave ``dcc`` blank: their address
is their system name and their JMRI comment has no DCC group.
"""
from __future__ import annotations

import re

_DCC_GROUP = re.compile(r"\s*\|\s*DCC:\s*(\d+)\s*(?=\||$)")


def jmri_comment(comment: str, dcc: str) -> str:
    """The comment JMRI stores: ``comment`` with ``DCC: <dcc>`` as its second group."""
    comment, dcc = (comment or "").strip(), (dcc or "").strip()
    if not dcc:
        return comment
    parts = comment.split(" | ") if comment else []
    parts.insert(1 if parts else 0, f"DCC: {dcc}")
    return " | ".join(parts)


def split_dcc(comment: str) -> tuple[str, str]:
    """(comment without its DCC group, address) for a JMRI or Device-map comment.

    Only a DCC group after the first group is taken, so ``jmri_comment`` puts it back
    where it was. A comment with no such group comes back unchanged with ``""``.
    """
    comment = (comment or "").strip()
    m = _DCC_GROUP.search(comment)
    if not m:
        return comment, ""
    rest = (comment[: m.start()] + (" " if m.end() < len(comment) else "") + comment[m.end():].lstrip())
    return rest.strip(), m.group(1)


def row_comment(row: dict) -> str:
    """The JMRI comment for a public_name_map.csv row (a csv.DictReader dict)."""
    return jmri_comment(row.get("comment") or "", row.get("dcc") or "")
