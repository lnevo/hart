"""The jmri_bean column of the device master: a device not on the layout yet, its beans as the PanelPro Store wrote
them, as compact JSON (bean_json writes it, row_beans reads it back, kept_beans gives the beans to the build).
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from typing import Any

from . import tables
from .tables_sections import BLOCKS, MASTER_SECTIONS, BeanKey, SectionKey, TablesBuildError, sort_group

#
# A device the owner adds in PanelPro (a test turnout, a DCC accessory) has a device-master row with no level, cp or role
# until its details are known, and the beans exactly as the Store wrote them in its jmri_bean
# column, as compact JSON:
#     {"beans": [{"section": [tag, class], "element": NODE}, ...]}
#     NODE = {"tag": ..., "attrs": {...}, "text": ... (only when not blank), "children": [NODE, ...]}
# A child <userName> or <comment> whose text is the row's user_name or jmri_comment is {"tag": ..., "column": ...}
# instead, so a rename or a new comment changes one cell, not the JSON too.

BEAN_COLUMNS = {"userName": "user_name", "comment": "jmri_comment"}


def _node(el: ET.Element, row: Mapping[str, str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"tag": el.tag, "attrs": dict(el.attrib)}
    if el.text is not None and el.text.strip():
        out["text"] = el.text
    kids = []
    for c in tables.elements(el):
        col = BEAN_COLUMNS.get(c.tag)
        if row is not None and col and not len(c) and not c.attrib and (c.text or "") == row[col] and row[col]:
            kids.append({"tag": c.tag, "column": col})
        else:
            kids.append(_node(c, None))
    if kids:
        out["children"] = kids
    return out


def _element(node: Mapping[str, Any], row: Mapping[str, str], where: str) -> ET.Element:
    if not isinstance(node, Mapping) or not isinstance(node.get("tag"), str):
        raise TablesBuildError(f"{where}: an element of jmri_bean has no tag")
    if "column" in node:
        if node["column"] not in BEAN_COLUMNS.values():
            raise TablesBuildError(f"{where}: jmri_bean names column {node['column']!r}, not "
                                   f"{' or '.join(BEAN_COLUMNS.values())}")
        el = ET.Element(node["tag"])
        el.text = row[node["column"]]
        return el
    attrs = node.get("attrs", {})
    if not isinstance(attrs, Mapping) or not all(isinstance(v, str) for v in attrs.values()):
        raise TablesBuildError(f"{where}: <{node['tag']}> attrs in jmri_bean are not text")
    el = ET.Element(node["tag"], dict(attrs))
    if "text" in node:
        el.text = node["text"]
    for c in node.get("children", []):
        el.append(_element(c, row, where))
    return el


def bean_json(beans: Iterable[tuple[SectionKey, ET.Element]], row: Mapping[str, str]) -> str:
    """The jmri_bean text of `row` for `beans` ((section key, element) as the Store holds them)."""
    return json.dumps({"beans": [{"section": list(k), "element": _node(el, row)} for k, el in beans]},
                      separators=(",", ":"), ensure_ascii=False)


def row_beans(row: Mapping[str, str]) -> list[tuple[SectionKey, ET.Element]]:
    """[(section key, element)] of a row's jmri_bean (bean_json); TablesBuildError when the text is not that shape, a
    section is not one the master gives (MASTER_SECTIONS), or a bean names no system name."""
    where = f"the device master: {row['layer']} {row['user_name']!r}"
    try:
        doc = json.loads(row["jmri_bean"])
    except json.JSONDecodeError as exc:
        raise TablesBuildError(f"{where}: jmri_bean is not JSON ({exc.msg})") from exc
    beans = doc.get("beans") if isinstance(doc, dict) else None
    if not isinstance(beans, list) or not beans:
        raise TablesBuildError(f"{where}: jmri_bean is not {{\"beans\": [...]}} with at least one bean")
    out: list[tuple[SectionKey, ET.Element]] = []
    for b in beans:
        given = tuple(b.get("section") or ()) if isinstance(b, dict) else ()
        sec = next((k for k in MASTER_SECTIONS if k == given), None)
        if sec is None:
            raise TablesBuildError(f"{where}: jmri_bean section {list(given)} is not one a device master row gives")
        el = _element(b.get("element"), row, where)
        if not tables.system_name(el):
            raise TablesBuildError(f"{where}: a <{el.tag}> in jmri_bean has no system name")
        out.append((sec, el))
    return out


def kept_beans(rows: Iterable[Mapping[str, str]]) -> dict[BeanKey, list[ET.Element]]:
    """{section: [bean, ...]} of the rows with a jmri_bean, as master_beans gives them (a block's names-only pass
    under ("blocks-names", ...))."""
    out: dict[BeanKey, list[ET.Element]] = {}
    bad = []
    for r in rows:
        if not r["jmri_bean"]:
            continue
        try:
            for sec, el in row_beans(r):
                key = ("blocks-names",) + BLOCKS if sec == BLOCKS and sort_group(el) == "block-names" else sec
                out.setdefault(key, []).append(el)
        except TablesBuildError as exc:
            bad.append(str(exc).removeprefix("the device master: "))
    if bad:
        raise TablesBuildError("the device master: " + "; ".join(bad))
    return out
