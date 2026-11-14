"""public_name_map.csv: the DCC address column and the JMRI comment a row stands for.

The map keeps a turnout's DCC address in its own ``dcc`` column and the rest of the
wiring text in ``comment``. JMRI's turnout comment carries the address as the group
after the first one (ADR-005), groups joined by exactly `` | ``::

    comment  Node: 4 Turnout: 0 | OU: 1 Ports: 1,2
    dcc      100
    JMRI     Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2

LCC aliases (``DCC Switch N``, hardware ``MTTN``) leave ``dcc`` blank: their address
is their system name and their JMRI comment has no DCC group.

``split_dcc`` only takes a DCC group out when ``jmri_comment`` puts the very same
text back; a comment that mentions DCC any other way raises instead of being reordered.
"""
from __future__ import annotations

import re

SEP = " | "
_DCC_GROUP = re.compile(r"DCC: (\d+)")
_DCC_ANY = re.compile(r"DCC:?\s*\d")


def jmri_comment(comment: str, dcc: str) -> str:
    """The comment JMRI stores: ``comment`` with ``DCC: <dcc>`` as its second group."""
    comment, dcc = (comment or "").strip(), (dcc or "").strip()
    if not dcc:
        return comment
    parts = comment.split(SEP) if comment else []
    parts.insert(1 if parts else 0, f"DCC: {dcc}")
    return SEP.join(parts)


def split_dcc(comment: str) -> tuple[str, str]:
    """(comment without its DCC group, address); ``jmri_comment`` of the result is ``comment``.

    A comment with no DCC text comes back unchanged with ``""``. One whose DCC text is
    not exactly a ``DCC: N`` second group raises ValueError, so nothing is moved silently.
    """
    comment = (comment or "").strip()
    if not _DCC_ANY.search(comment):
        return comment, ""
    parts = comment.split(SEP)
    m = _DCC_GROUP.fullmatch(parts[1]) if len(parts) > 1 else None
    rest = SEP.join(parts[:1] + parts[2:])
    if not m or _DCC_ANY.search(rest) or jmri_comment(rest, m.group(1)) != comment:
        raise ValueError(f"comment {comment!r}: DCC is not a 'DCC: N' second group; fix the comment by hand")
    return rest, m.group(1)


def row_comment(row: dict) -> str:
    """The JMRI comment for a public_name_map.csv row (a csv.DictReader dict)."""
    return jmri_comment(row.get("comment") or "", row.get("dcc") or "")
