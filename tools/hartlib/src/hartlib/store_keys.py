"""The store split's item keys (hartlib.store_split.index): one NamedTuple per kind of item (ItemKey), so code reads a
key's parts by name and tells the kinds apart by class. index() builds every key as its NamedTuple; a bare tuple of
the same shape hashes and compares as the same key, but the readers that test a key's kind (claimed_by,
new_template) do not take one."""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from typing import NamedTuple, overload

BY_ID, BY_CONTENT = "id", "="
SecKey = tuple[str, str | None]     # a section's (tag, class): tables_build.section_key


class ById(NamedTuple):
    """A repeated setting keyed by its own id (_ident)."""
    how: str            # BY_ID
    ident: str | None


class ByContent(NamedTuple):
    """A repeated setting keyed by its content: the nth copy (from 0) of the same canonical text."""
    how: str            # BY_CONTENT
    content: str
    copy: int


class PanelKey(NamedTuple):
    kind: str           # "panel"
    name: str


class SectionKey(NamedTuple):
    """A whole section outside tables_build.SECTIONS."""
    kind: str           # "section"
    tag: str
    cls: str | None


class AttrsKey(NamedTuple):
    """A known section's own attributes."""
    kind: str           # "attrs"
    section: SecKey


class LogicKey(NamedTuple):
    kind: str           # "logic"
    source: str | None


class BeanKey(NamedTuple):
    kind: str           # "bean"
    section: SecKey
    tag: str
    group: str          # tables_build.sort_group: "block-names" for the names-only pass of blocks
    name: str           # its system name


class SettingKey(NamedTuple):
    kind: str           # "setting"
    section: SecKey
    tag: str
    which: ById | ByContent | int   # an int counts the copies of a tag that is not repeated (0 when given once)


ItemKey = PanelKey | SectionKey | AttrsKey | LogicKey | BeanKey | SettingKey


@overload
def canon(el: ET.Element) -> str: ...
@overload
def canon(el: None) -> None: ...
def canon(el: ET.Element | None) -> str | None:
    """An element as text with its layout whitespace taken out, for comparing; None stays None."""
    if el is None:
        return None
    c = copy.deepcopy(el)
    for x in c.iter():
        x.tail = None
        if x.text is not None and not x.text.strip():
            x.text = None
    return ET.tostring(c, encoding="unicode")
