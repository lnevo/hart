"""The store split's items and who owns them (hartlib.store_split): the Store, the repo's tables, the base and the
template parsed, normalised and indexed item by item (index), the words for an item and a change (label,
change_text), and what claims an item the Store added (claimed_by). Every failure is a SplitError."""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping

from . import devices, level_devices, parked, tables
from . import tables_build as tb
from .errors import HartlibError
from .store_keys import (BY_CONTENT, BY_ID, AttrsKey, BeanKey, ByContent, ById, LogicKey, PanelKey, SecKey,
                         SectionKey, SettingKey, canon)

PANEL = "LayoutEditor"
LOGIC = "signalmastlogic"
KNOWN_SECTIONS = frozenset(tb.SECTIONS)
VERSION = ("jmriversion", None)
VERSION_PARTS = ("major", "minor", "test")
# Top-level tags that never go into the template: the panels and the file history.
NEVER_TEMPLATE = frozenset({PANEL, "filehistory", "paneleditor"})


def row_at(r: Mapping[str, str]) -> str:
    """A master row as a review note names it: the file that holds it (a writer's row is devices_generated.csv's, the
    owner's level-less device devices_field.csv's) and its layer and user name."""
    return f"{devices.GENERATED_FILE if r['written_by'] else devices.FIELD_FILE} row {r['layer']} {r['user_name']!r}"


# The bean sections a master row can give, and the layers that give them.
BEAN_LAYERS = {"turnouts": ("turnout",), "sensors": ("fb", "occupancy", "sensor"), "signalheads": ("head",),
               "signalmasts": ("mast",), "blocks": ("block",), "layoutblocks": ("block",)}
# Names the build makes (on top of the master's rows and the main and upper naming rule).
BUILD_PREFIXES = ("IQ$HART:", "IQC$HART:", "IQDA$HART:", "IS:HART:", "IT:HART:", "IH:HART:", "IB:HART:")
# The device-master layer of a bean section, for a device the Store added.
LAYER_OF = {"turnouts": "turnout", "sensors": "sensor", "signalheads": "head", "signalmasts": "mast",
            "blocks": "block", "layoutblocks": "block"}


class SplitError(HartlibError, ValueError):
    """The split cannot run: a file is not tables, or an item is given twice."""


# ---------------------------------------------------------------- items


def normalised(data: bytes, what: str) -> ET.Element:
    """Tables bytes parsed and normalised (tables_build.normalise_store); SplitError naming `what` when they do not
    parse."""
    try:
        doc = tables.loads(data)
    except (ET.ParseError, ValueError) as exc:
        raise SplitError(f"{what}: not a tables file ({exc})") from exc
    if doc.root.tag != "layout-config":
        raise SplitError(f"{what}: the root is <{doc.root.tag}>, not <layout-config>")
    tb.normalise_store(doc.root)
    return doc.root


def _ident(el: ET.Element) -> str | None:
    """A setting's own id: its id attribute, <id> child, name attribute or <name> child, the first given."""
    for got in (el.get("id"), el.findtext("id"), el.get("name"), el.findtext("name")):
        if got is not None and got.strip():
            return got.strip()
    return None


def _settings(sec: ET.Element) -> list[ET.Element]:
    return [el for el in tables.elements(sec) if el.tag != LOGIC and not tables.system_name(el)]


def repeated_settings(*roots: ET.Element | None) -> frozenset[tuple]:
    """(section, tag, how) for each setting tag that any of `roots` gives more than once in a section: how is BY_ID
    when every copy in every root has an id (_ident) no other copy in its root has, else BY_CONTENT."""
    copies: dict[tuple, list[list[ET.Element]]] = {}
    for root in roots:
        if root is None:
            continue
        for sec in tables.elements(root):
            if sec.tag == PANEL or tb.section_key(sec) not in KNOWN_SECTIONS:
                continue
            here: dict[str, list[ET.Element]] = {}
            for el in _settings(sec):
                here.setdefault(el.tag, []).append(el)
            for tag, els in here.items():
                copies.setdefault((tb.section_key(sec), tag), []).append(els)
    out = set()
    for (sk, tag), groups in copies.items():
        if max(len(g) for g in groups) < 2:
            continue
        idents = [[_ident(el) for el in g] for g in groups]
        by_id = all(None not in i and len(set(i)) == len(i) for i in idents)
        out.add((sk, tag, BY_ID if by_id else BY_CONTENT))
    return frozenset(out)


def _setting_keys(sec: ET.Element, sk: SecKey, repeated: frozenset[tuple]) -> list[tuple[SettingKey, ET.Element]]:
    """The settings of a known section with their keys: ("setting", section, tag, 0) for a tag given once (any
    change to it is a change of that one item); for a tag in `repeated` (repeated_settings), ("setting", section,
    tag, (BY_ID, id)) or ("setting", section, tag, (BY_CONTENT, content, n)), the nth copy of the same content."""
    how = {(k, t): h for k, t, h in repeated}
    out: list[tuple[SettingKey, ET.Element]] = []
    seen: dict[tuple[str, str], int] = {}
    for el in _settings(sec):
        mode = how.get((sk, el.tag))
        if mode == BY_ID:
            out.append((SettingKey("setting", sk, el.tag, ById(BY_ID, _ident(el))), el))
            continue
        content = canon(el) if mode == BY_CONTENT else ""     # a tag given once counts its copies by tag alone
        n = seen.get((el.tag, content), 0)
        seen[(el.tag, content)] = n + 1
        out.append((SettingKey("setting", sk, el.tag, ByContent(BY_CONTENT, content, n) if mode else n), el))
    return out


def index(root: ET.Element, what: str, by_content: frozenset[tuple] = frozenset()) -> dict[tuple, ET.Element]:
    """{item key: element} of normalised tables (the module docstring's items). Keys:
    ("panel", name), ("section", tag, class) for a whole section outside tables_build.SECTIONS,
    ("attrs", section) for a known section's own attributes (an element with no children),
    ("logic", source mast), ("bean", section, tag, block pass, system name), and a setting's key (_setting_keys;
    `by_content` from repeated_settings over every file compared, so all of them key a tag the same way).
    SplitError on a key given twice (JMRI would load only one)."""
    out: dict[tuple, ET.Element] = {}

    def put(key: tuple, el: ET.Element) -> None:
        if key in out:
            raise SplitError(f"{what}: {label(key)} is given twice")
        out[key] = el

    for sec in tables.elements(root):
        if sec.tag == PANEL:
            put(PanelKey("panel", sec.get("name") or ""), sec)
            continue
        sk = tb.section_key(sec)
        if sk not in KNOWN_SECTIONS:
            put(SectionKey("section", *sk), sec)
            continue
        put(AttrsKey("attrs", sk), ET.Element(sec.tag, sec.attrib))
        for el in tables.elements(sec):
            name = tables.system_name(el)
            if el.tag == LOGIC:
                put(LogicKey("logic", el.get("source") or tables.text(el, "sourceSignalMast")), el)
            elif name:
                put(BeanKey("bean", sk, el.tag, tb.sort_group(el), name), el)
        for key, el in _setting_keys(sec, sk, by_content):
            put(key, el)
    return out


def index_section(sec: ET.Element, sk: SecKey, by_content: frozenset[tuple] = frozenset()) -> dict[tuple, ET.Element]:
    """index() of one known section's children."""
    out: dict[tuple, ET.Element] = {}
    for el in tables.elements(sec):
        name = tables.system_name(el)
        if name:
            out[BeanKey("bean", sk, el.tag, tb.sort_group(el), name)] = el
    out.update(_setting_keys(sec, sk, by_content))
    return out

def label(key: tuple) -> str:
    """An item key as words: "turnout M2T408", "<timebase> settings", "panel 'HART Railroad'"."""
    kind = key[0]
    if kind == "panel":
        return f"panel {PanelKey(*key).name!r}"
    if kind == "section":
        sec = SectionKey(*key)
        return f"section <{sec.tag}>" + (f" ({sec.cls.rsplit('.', 1)[-1]})" if sec.cls else "")
    if kind == "attrs":
        return f"<{AttrsKey(*key).section[0]}> settings"
    if kind == "logic":
        return f"Signal Mast Logic from {LogicKey(*key).source!r}"
    if kind == "bean":
        bean = BeanKey(*key)
        return f"{bean.tag} {bean.name}" + (" (names-only pass)" if bean.group == "block-names" else "")
    setting = SettingKey(*key)
    where = f"<{setting.section[0]}> <{setting.tag}>"
    which = setting.which
    if isinstance(which, tuple):
        if which[0] == BY_ID:
            return f"{where} {ById(*which).ident!r}"
        got = ByContent(*which)
        hint = " ".join(" ".join(ET.fromstring(got.content).itertext()).split())[:40] or "no text"
        tag = hashlib.sha256(got.content.encode()).hexdigest()[:6]
        return f"{where} ({hint}; {tag})" + (f" copy {got.copy + 1}" if got.copy else "")
    return where + (f" #{which + 1}" if which else "")


def parts(a: ET.Element | None, b: ET.Element | None) -> list[str]:
    """What differs between two versions of one element: "@attr" for an attribute, "text", and each child tag whose
    children (in order) differ."""
    if a is None or b is None:
        return ["(whole)"]
    out = [f"@{n}" for n in sorted(set(a.attrib) | set(b.attrib)) if a.get(n) != b.get(n)]
    if (a.text or "").strip() != (b.text or "").strip():
        out.append("text")
    ak: dict[str, list[str]] = {}
    bk: dict[str, list[str]] = {}
    for side, kids in ((a, ak), (b, bk)):
        for c in tables.elements(side):
            kids.setdefault(c.tag, []).append(canon(c))
    out += [t for t in dict.fromkeys([*ak, *bk]) if ak.get(t) != bk.get(t)]
    return out


def value(el: ET.Element | None, part: str) -> str:
    """One part of an element as text, for a report: an attribute's value, the text, or a single child's text."""
    if el is None:
        return "(none)"
    if part.startswith("@"):
        v = el.get(part[1:])
        return "(none)" if v is None else v
    if part == "text":
        return (el.text or "").strip()
    kids = el.findall(part)
    if len(kids) == 1 and not len(kids[0]):
        return (kids[0].text or "").strip()
    return "(none)" if not kids else f"{len(kids)} <{part}>"


def change_text(a: ET.Element | None, b: ET.Element | None) -> str:
    """A short account of a change from `a` to `b`."""
    if a is None and b is None:
        return "(nothing)"
    if a is None:
        return "added"
    if b is None:
        return "deleted"
    got = []
    for p in parts(a, b):
        va, vb = value(a, p), value(b, p)
        if len(va) + len(vb) <= 120 and "<" not in va + vb:
            got.append(f"{p.lstrip('@')} {va!r} -> {vb!r}")
        else:
            got.append(f"{p.lstrip('@')} changed")
    return "; ".join(got) or "layout only"


# ---------------------------------------------------------------- who owns an item


def row_index(rows: Iterable[Mapping[str, str]]) -> dict[tuple[str, str], list[int]]:
    """{(section tag, bean name): [device-master row numbers]}: the rows a bean of the tables comes from. A turnout by
    its system or JMRI name; a sensor, head, mast or block by its JMRI name; a layout block by its layout_block or
    "user:" and its block's user name (every block row with a JMRI name has its layout_block,
    the main and upper ones copied from block_numbering.csv; the user name is kept for a Store's layout block JMRI
    renumbered)."""
    out: dict[tuple[str, str], list[int]] = {}

    def add(tag: str, name: str, i: int) -> None:
        if name and i not in out.setdefault((tag, name), []):
            out[(tag, name)].append(i)

    for i, r in enumerate(rows):
        if r["assignment"] == "none":
            continue
        for tag, layers in BEAN_LAYERS.items():
            if r["layer"] not in layers:
                continue
            if tag == "layoutblocks":
                add(tag, r["layout_block"], i)
                add(tag, "user:" + r["user_name"], i)
            else:
                add(tag, r["jmri_name"], i)
                if r["layer"] == "turnout":
                    add(tag, r["system_name"], i)
    return out


def rows_of(rindex: Mapping[tuple[str, str], list[int]], key: tuple, el: ET.Element) -> list[int]:
    """The device-master rows the bean `key` (element `el`, the repo's or the base's) comes from."""
    tag = key[1][0]
    got = rindex.get((tag, key[4]), [])
    if not got and tag == "layoutblocks":
        got = rindex.get((tag, "user:" + tables.user_name(el)), [])
    return list(got)


def claimed_by(key: tuple, el: ET.Element, rows: Iterable[Mapping[str, str]]) -> str | None:
    """What claims a new item of the Store, so it cannot go into the template; None when nothing does. A bean in a
    section the device master gives (tables_build.MASTER_SECTIONS), Signal Mast Logic, a panel, a parked feature's section
    or name, the build's names, the main and upper naming rule or a device-master row's name."""
    kind = key[0]
    if kind in ("panel", "logic"):
        return "the build" if kind == "logic" else "the schematic (the Layout Editor build)"
    if kind == "section":
        if key[1] in NEVER_TEMPLATE or key[1].lower().endswith("editor"):
            return "the schematic (a panel is never in the template)"
        if key[1] in {t for t, _ in tb.SECTIONS}:
            return "the device master and the build (a section of a known kind with another connection)"
        for feature, tags in parked.WHOLE.items():
            if key[1] in tags:
                return f"the parked {parked.FEATURES[feature]}"
        return None
    if kind != "bean":
        return None
    if key[1] in tb.MASTER_SECTIONS:
        return f"the device master (a device needs a row in {devices.FIELD_FILE} with its level, cp and role)"
    return claimed_name(key, el, rows)


def claimed_name(key: tuple, el: ET.Element, rows: Iterable[Mapping[str, str]]) -> str | None:
    """What claims a bean by its system or user name (claimed_by's checks after the section's): the build's names,
    the main and upper naming rule, a parked feature or a device-master row's name; None when nothing does."""
    names = [n for n in (key[4], tables.user_name(el)) if n]
    for name in names:
        if name.startswith(BUILD_PREFIXES) or level_devices.is_level_name(name):
            return "the build's names (the device master's main and upper rows and hartlib.level_devices)"
        for feature, pattern in parked.SENSOR_PATTERNS.items():
            if pattern.match(name):
                return f"the parked {parked.FEATURES[feature]}"
        for table in (parked.MEMORIES, parked.LOGIX, parked.CONDITIONAL_NGS):
            for feature, held in table.items():
                if name in held:
                    return f"the parked {parked.FEATURES[feature]}"
        for r in rows:
            if name in (r["user_name"], r["jmri_name"], r["system_name"]):
                return row_at(r)
    return None


def name_holder(key: tuple, el: ET.Element, rows: Iterable[Mapping[str, str]]) -> str | None:
    """Why a bean the Store added cannot be a new row because a device-master row holds one of its names, with what to do;
    None when no row does."""
    names = [(n, what, cols) for n, what, cols in (
        (key[4], "system name", ("system_name", "jmri_name", "user_name")),
        (tables.user_name(el), "user name", ("user_name", "jmri_name", "system_name"))) if n]
    for r in rows:
        for name, what, cols in names:
            for col in cols:
                if r[col] != name:
                    continue
                at = row_at(r)
                if col == "system_name" and what == "system name" and r["assignment"] in ("virtual", "none"):
                    return (f"{at} plans this device (system_name {name!r}, assignment {r['assignment']}); to bring "
                            "it into JMRI, set that row's assignment to field and rebuild, or give the Store's device "
                            "another name")
                return f"its {what} {name!r} is that row's {col}; give the Store's device another name in PanelPro"
    return None


# ---------------------------------------------------------------- the JMRI version


def jmri_version(root: ET.Element | None) -> tuple[int, ...] | None:
    """(major, minor, test) of a tables root's <jmriversion>; None when it has none. SplitError when a part is not a
    number (the comparison would be a guess)."""
    sec = root.find("jmriversion") if root is not None else None
    if sec is None:
        return None
    out = []
    for part in VERSION_PARTS:
        text = (sec.findtext(part) or "0").strip() or "0"
        if not (text.isascii() and text.isdigit()):
            raise SplitError(f"<jmriversion> <{part}> is {text!r}, not a number")
        out.append(int(text))
    return tuple(out)


def newer_jmri(store: ET.Element, repo: ET.Element) -> bool:
    """True when `store` names a newer JMRI than `repo` (one without a <jmriversion> counts as the oldest)."""
    s, g = jmri_version(store), jmri_version(repo)
    return s is not None and (g is None or s > g)

