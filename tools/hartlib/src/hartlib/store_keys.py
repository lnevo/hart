"""The store split's item keys (hartlib.store_split.index): one NamedTuple per kind of item, so code reads a key's
parts by name. Each is a plain tuple too: a key built as a tuple of the same shape is the same key."""
from __future__ import annotations

from typing import NamedTuple

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
