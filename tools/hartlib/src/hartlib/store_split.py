"""Split a PanelPro Store back into the sources of tables.xml (ADR-029, R9d; the owner's design of 2026-11-20 in
wiki/projects/project-health-handoff.md, "R9d redesign").

A Store mostly holds settings the owner made in PanelPro that must survive the next deploy, so the default is to keep
it. Three files are compared item by item, all normalised (tables_build.normalise_store):

    base   what the host had before the owner's session: the tables the last deploy shipped (or an earlier Store);
           None when it is not known, and then every difference is reviewed
    repo   this checkout's generated tables.xml
    store  the Store

An item is one bean (by section and system name), one setting of a section (a nameless child such as <defaultspeed>;
repeated_settings), a section's own attributes, a Signal Mast Logic (by source mast), a whole section the template has
no slot for, or a Layout Editor panel (by name). A setting is matched by its tag when the tag is given once; when any
file gives a tag more than once, by each copy's id (an id or name, such as a LogixNG <Thread>'s <id>) when every copy
has a distinct one, else by its content. So adding or deleting one copy shows no false change in the rest; with
content matching, an edit to a copy shows as that copy deleted and an edited one added. Who owns it:

- the template (data/tables_template.xml): every item it holds, and a new memory, internal sensor, LogixNG part,
  setting or extra section of the Store on a name nothing else claims (claimed_by);
- the build: everything else, the devices.csv beans, the Layout Editor panel and its LogixNG, the Signal Mast Logic,
  the Digicon boot rule.

What happens to an item the owner changed (store differs from base):

    KEPT     a template item the repo did not change since the base: the template takes the Store's version (no
             review; listed so it is clear what was taken)
    CLASH    a template item the repo changed too, or any template item when the base is not known: reviewed, merge
             takes the Store's version, drop keeps the repo's
    DEVICE   a rename or comment of a bean whose devices.csv row the owner keeps by hand: reviewed, merge writes the
             row (user_name, and jmri_name where the tables bind it by its user name; jmri_comment), drop leaves it
    DROPPED  anything else of the build's: the repo wins, and the item is listed with what to change instead

<jmriversion> is the one exception: a Store from a newer JMRI is KEPT whatever the base and the repo say, so the next
tables carry the newer version (owner, 2026-11-20); a Store from the same or an older JMRI gives no item.

Nothing reads or writes a file here; tools/schematic/split_store.py runs it, rebuilds tables.xml and verifies the
rebuild (verify). Every failure is a SplitError.
"""
from __future__ import annotations

import copy
import difflib
import functools
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from . import devices, level_devices, parked, tables
from . import tables_build as tb

KEPT, CLASH, DEVICE, DROPPED = "kept", "clash", "device", "dropped"
KINDS = (KEPT, CLASH, DEVICE, DROPPED)
ID_PREFIX = {KEPT: "K", CLASH: "C", DEVICE: "D", DROPPED: "G"}
REVIEWED = (CLASH, DEVICE)          # the kinds a merge or drop is asked for

PANEL = "LayoutEditor"
LOGIC = "signalmastlogic"
KNOWN_SECTIONS = frozenset(tb.SECTIONS)
VERSION = ("jmriversion", None)
VERSION_PARTS = ("major", "minor", "test")
# Top-level tags that never go into the template: the panels and the file history.
NEVER_TEMPLATE = frozenset({PANEL, "filehistory", "paneleditor"})
# The bean sections a devices.csv row can give, and the layers that give them.
BEAN_LAYERS = {"turnouts": ("turnout",), "sensors": ("fb", "occupancy", "sensor"), "signalheads": ("head",),
               "signalmasts": ("mast",), "blocks": ("block",), "layoutblocks": ("block",)}
# Names the build makes (on top of devices.csv rows and the main and upper naming rule).
BUILD_PREFIXES = ("IQ$HART:", "IQC$HART:", "IQDA$HART:", "IS:HART:", "IT:HART:", "IH:HART:", "IB:HART:")


class SplitError(ValueError):
    """The split cannot run: a file is not tables, or an item is given twice."""


# ---------------------------------------------------------------- items


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


def normalised(data: bytes, what: str) -> ET.Element:
    """Tables bytes parsed and normalised (tables_build.normalise_store); SplitError naming `what` when they do not
    parse."""
    try:
        doc = tables.loads(data)
    except (ET.ParseError, ValueError) as exc:
        raise SplitError(f"{what}: not a tables file ({exc})") from None
    if doc.root.tag != "layout-config":
        raise SplitError(f"{what}: the root is <{doc.root.tag}>, not <layout-config>")
    tb.normalise_store(doc.root)
    return doc.root


def section_key(sec: ET.Element) -> tuple[str, str | None]:
    return tb.section_key(sec)


BY_ID, BY_CONTENT = "id", "="


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
            if sec.tag == PANEL or section_key(sec) not in KNOWN_SECTIONS:
                continue
            here: dict[str, list[ET.Element]] = {}
            for el in _settings(sec):
                here.setdefault(el.tag, []).append(el)
            for tag, els in here.items():
                copies.setdefault((section_key(sec), tag), []).append(els)
    out = set()
    for (sk, tag), groups in copies.items():
        if max(len(g) for g in groups) < 2:
            continue
        idents = [[_ident(el) for el in g] for g in groups]
        by_id = all(None not in i and len(set(i)) == len(i) for i in idents)
        out.add((sk, tag, BY_ID if by_id else BY_CONTENT))
    return frozenset(out)


def _setting_keys(sec: ET.Element, sk: tuple, repeated: frozenset[tuple]) -> list[tuple[tuple, ET.Element]]:
    """The settings of a known section with their keys: ("setting", section, tag, 0) for a tag given once (any
    change to it is a change of that one item); for a tag in `repeated` (repeated_settings), ("setting", section,
    tag, (BY_ID, id)) or ("setting", section, tag, (BY_CONTENT, content, n)), the nth copy of the same content."""
    how = {(k, t): h for k, t, h in repeated}
    out = []
    seen: dict[tuple, int] = {}
    for el in _settings(sec):
        mode = how.get((sk, el.tag))
        if mode == BY_ID:
            out.append((("setting", sk, el.tag, (BY_ID, _ident(el))), el))
            continue
        mark = (el.tag, canon(el)) if mode == BY_CONTENT else (el.tag,)
        n = seen.get(mark, 0)
        seen[mark] = n + 1
        out.append((("setting", sk, el.tag, (BY_CONTENT, mark[1], n) if mode else n), el))
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
            put(("panel", sec.get("name") or ""), sec)
            continue
        sk = section_key(sec)
        if sk not in KNOWN_SECTIONS:
            put(("section",) + sk, sec)
            continue
        put(("attrs", sk), ET.Element(sec.tag, sec.attrib))
        for el in tables.elements(sec):
            name = tables.system_name(el)
            if el.tag == LOGIC:
                put(("logic", el.get("source") or tables.text(el, "sourceSignalMast")), el)
            elif name:
                put(("bean", sk, el.tag, tb._sort_group(el), name), el)
        for key, el in _setting_keys(sec, sk, by_content):
            put(key, el)
    return out


def label(key: tuple) -> str:
    """An item key as words: "turnout M2T408", "<timebase> settings", "panel 'HART Railroad'"."""
    kind = key[0]
    if kind == "panel":
        return f"panel {key[1]!r}"
    if kind == "section":
        return f"section <{key[1]}>" + (f" ({key[2].rsplit('.', 1)[-1]})" if key[2] else "")
    if kind == "attrs":
        return f"<{key[1][0]}> settings"
    if kind == "logic":
        return f"Signal Mast Logic from {key[1]!r}"
    if kind == "bean":
        return f"{key[2]} {key[4]}" + (" (names-only pass)" if key[3] == "block-names" else "")
    if isinstance(key[3], tuple):
        if key[3][0] == BY_ID:
            return f"<{key[1][0]}> <{key[2]}> {key[3][1]!r}"
        _, content, n = key[3]
        hint = " ".join(" ".join(ET.fromstring(content).itertext()).split())[:40] or "no text"
        tag = hashlib.sha256(content.encode()).hexdigest()[:6]
        return f"<{key[1][0]}> <{key[2]}> ({hint}; {tag})" + (f" copy {n + 1}" if n else "")
    return f"<{key[1][0]}> <{key[2]}>" + (f" #{key[3] + 1}" if key[3] else "")


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
    """{(section tag, bean name): [devices.csv row numbers]}: the rows a bean of the tables comes from. A turnout by
    its system or JMRI name; a sensor, head, mast or block by its JMRI name; a layout block by its layout_block or
    "user:" and its block's user name (the main and upper layout blocks are numbered by the Layout Editor build)."""
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
    """The devices.csv rows the bean `key` (element `el`, the repo's or the base's) comes from."""
    tag = key[1][0]
    got = rindex.get((tag, key[4]), [])
    if not got and tag == "layoutblocks":
        got = rindex.get((tag, "user:" + tables.user_name(el)), [])
    return list(got)


def claimed_by(key: tuple, el: ET.Element, rows: Iterable[Mapping[str, str]]) -> str | None:
    """What claims a new item of the Store, so it cannot go into the template; None when nothing does. A bean in a
    section devices.csv gives (tables_build.MASTER_SECTIONS), Signal Mast Logic, a panel, a parked feature's section
    or name, the build's names, the main and upper naming rule or a devices.csv row's name."""
    kind = key[0]
    if kind in ("panel", "logic"):
        return "the build" if kind == "logic" else "the schematic (the Layout Editor build)"
    if kind == "section":
        if key[1] in NEVER_TEMPLATE or key[1].lower().endswith("editor"):
            return "the schematic (a panel is never in the template)"
        if key[1] in {t for t, _ in tb.SECTIONS}:
            return "devices.csv and the build (a section of a known kind with another connection)"
        for feature, tags in parked.WHOLE.items():
            if key[1] in tags:
                return f"the parked {parked.FEATURES[feature]}"
        return None
    if kind != "bean":
        return None
    if key[1] in tb.MASTER_SECTIONS:
        return "devices.csv (a device needs a row with its level, cp and role)"
    names = [n for n in (key[4], tables.user_name(el)) if n]
    for name in names:
        if name.startswith(BUILD_PREFIXES) or level_devices.is_level_name(name):
            return "the build's names (the Layout Editor build and hartlib.level_devices)"
        for feature, pattern in parked.SENSOR_PATTERNS.items():
            if pattern.match(name):
                return f"the parked {parked.FEATURES[feature]}"
        for table in (parked.MEMORIES, parked.LOGIX, parked.CONDITIONAL_NGS):
            for feature, held in table.items():
                if name in held:
                    return f"the parked {parked.FEATURES[feature]}"
        for r in rows:
            if name in (r["user_name"], r["jmri_name"], r["system_name"]):
                return f"devices.csv row {r['layer']} {r['user_name']!r}"
    return None


# ---------------------------------------------------------------- the plan


@dataclass(frozen=True)
class Edit:
    """One devices.csv cell a DEVICE merge writes."""
    row: int            # the row's place among the data rows (0 is the first under the header)
    column: str
    old: str
    new: str


@dataclass(frozen=True)
class Item:
    id: str             # K1, C1, D1, G1: stable for one (base, repo, Store)
    kind: str           # KEPT, CLASH, DEVICE or DROPPED
    key: tuple
    what: str           # the owner's change: "userName 'Switch 1' -> 'Switch 1X'"
    note: str           # where it goes, or for DROPPED what to change instead
    store: ET.Element | None = field(default=None, compare=False, repr=False)   # the Store's version (None: deleted)
    repo: ET.Element | None = field(default=None, compare=False, repr=False)
    base: ET.Element | None = field(default=None, compare=False, repr=False)
    edits: tuple[Edit, ...] = ()
    part: str = ""      # DEVICE: the part merged ("userName" or "comment")
    also: tuple = ()    # DEVICE: the keys of other beans the same edits come from (a block's passes, its layout
                        # block), with their Store versions: ((key, store element), ...)

    @property
    def where(self) -> str:
        el = self.store if self.store is not None else self.repo if self.repo is not None else self.base
        user = tables.user_name(el) if el is not None and self.key[0] == "bean" else ""
        return label(self.key) + (f" ({user})" if user else "")


@dataclass
class Plan:
    items: list[Item]
    has_base: bool
    fingerprint: str
    by_content: frozenset[tuple] = frozenset()      # repeated_settings of the files compared

    def of(self, kind: str) -> list[Item]:
        return [i for i in self.items if i.kind == kind]

    def by_id(self) -> dict[str, Item]:
        return {i.id: i for i in self.items}


def _device_items(key: tuple, b: ET.Element | None, g: ET.Element, s: ET.Element, owner_parts: list[str],
                  rows: list[Mapping[str, str]], rindex) -> tuple[list[tuple], list[str]]:
    """(DEVICE candidates as (part, edits, note) or (part, None, reason), the parts left for DROPPED) of a build
    bean the owner changed."""
    out: list[tuple] = []
    rest: list[str] = []
    for p in owner_parts:
        if p not in ("userName", "comment"):
            rest.append(p)
            continue
        old, new = value(g, p), value(s, p)
        found = rows_of(rindex, key, g)
        if len(found) != 1:
            out.append((p, None, "no devices.csv row gives this bean" if not found else
                        f"{len(found)} devices.csv rows give this bean; change the right one by hand"))
            continue
        i = found[0]
        r = rows[i]
        who = f"devices.csv row {r['layer']} {r['user_name']!r}"
        if r["written_by"]:
            out.append((p, None, f"{r['written_by']} writes {who}: change its inputs and rebuild"))
            continue
        if p == "userName":
            if r["user_name"] != old:
                out.append((p, None, f"{who} gives {r['user_name']!r}, not {old!r}; rename it by hand"))
                continue
            taken = [x for x in rows if x is not r and x["layer"] == r["layer"] and x["user_name"] == new]
            if not new or taken:
                out.append((p, None, f"{new!r} is {'empty' if not new else 'another row' + chr(39) + 's name'}"))
                continue
            edits = [Edit(i, "user_name", old, new)]
            if r["jmri_name"] == old:           # bound by its user name (owner decision Q13)
                edits.append(Edit(i, "jmri_name", old, new))
            out.append((p, tuple(edits), f"{who}: user_name" + (" and jmri_name" if len(edits) > 1 else "")))
        else:
            if r["level"] not in tb.GENERATED_LEVELS:
                out.append((p, None, "the Layout Editor build writes main and upper comments from devices.csv; "
                                     "change the row's columns"))
                continue
            if r["wiring"] or not r["jmri_comment"]:
                out.append((p, None, "the comment is generated from the row's wiring and dcc columns; change those"))
                continue
            text = new
            if r["layer"] == "head" and r["role"] == "head" and r["assignment"] == "virtual":
                tail = f" | {tb.VIRTUAL_HEAD_NOTE}"
                if not text.endswith(tail):
                    out.append((p, None, f"a virtual head's comment ends with {tail.strip(' |')!r}, which the "
                                         "build adds; keep it"))
                    continue
                text = text[: -len(tail)]
            out.append((p, (Edit(i, "jmri_comment", r["jmri_comment"], text),), f"{who}: jmri_comment"))
    return out, rest


def plan(base: ET.Element | None, repo: ET.Element, store: ET.Element, template: ET.Element,
         rows: Iterable[Mapping[str, str]]) -> Plan:
    """The plan for a Store: each item the owner changed, and where it goes (the module docstring). All four roots
    normalised (normalised); `template` is data/tables_template.xml as read_template gives it (normalised too)."""
    rows = list(rows)
    rindex = row_index(rows)
    has_base = base is not None
    by_content = repeated_settings(base, repo, store, template)
    B = index(base, "the base", by_content) if has_base else index(repo, "the repo", by_content)
    G = index(repo, "the repo", by_content)
    S = index(store, "the Store", by_content)
    T = index(template, "the template", by_content)
    newer = newer_jmri(store, repo)
    older = newer_jmri(repo, store)
    found: list[tuple[str, tuple, dict]] = []
    order = functools.cmp_to_key(lambda a, b: (repr(a) > repr(b)) - (repr(a) < repr(b)))
    for key in sorted(set(B) | set(G) | set(S), key=order):
        b, g, s = B.get(key), G.get(key), S.get(key)
        if key[0] == "attrs" and s is None:
            continue                    # JMRI writes no section once it holds nothing; its children say what went
        cb, cg, cs = canon(b), canon(g), canon(s)
        if key[0] != "panel" and key[1] == VERSION:
            if newer and cs != cg:
                found.append((KEPT, key, dict(store=s, repo=g, base=b, what=change_text(g, s),
                                              note="a newer JMRI wrote the Store: the template always takes it")))
            elif older and cs != cg:
                found.append((DROPPED, key, dict(store=s, repo=g, base=b, what=change_text(g, s),
                                                 note="an older JMRI wrote the Store than the tables name: the repo "
                                                      "keeps its version; check the host's JMRI before the deploy")))
            continue
        if cs == cb or cs == cg:
            continue                    # the owner changed nothing, or the repo has it already
        el = s if s is not None else g if g is not None else b
        if key in T:
            owner = "template"
        elif key in G or key in B:
            owner = "build" if key in G or claimed_by(key, el, rows) else "template"
        else:
            owner = "build" if claimed_by(key, el, rows) else "template"
        info = dict(store=s, repo=g, base=b)
        if owner == "template":
            if has_base and cg == cb:
                found.append((KEPT, key, dict(info, what=change_text(b, s), note="the template takes it")))
            else:
                why = "the repo changed it too since the deploy" if has_base else "no base: who changed it is unknown"
                found.append((CLASH, key, dict(info, what=change_text(g, s),
                                                note=f"{why}; merge takes the Store's, drop keeps the repo's")))
            continue
        # the build's
        if s is None:
            found.append((DROPPED, key, dict(info, what="deleted in the Store",
                                             note=f"delete it in its source ({_source(key)}) and rebuild")))
            continue
        if g is None:
            why = claimed_by(key, s, rows) or "the build"
            new = b is None
            found.append((DROPPED, key, dict(info, what="added in the Store" if new else "the repo no longer makes it",
                                             note=f"{why} makes it" + (
                                                 ": add the devices.csv row, rebuild and deploy, then make the change"
                                                 " in PanelPro again" if new and key[0] == "bean" and
                                                 key[1] in tb.MASTER_SECTIONS else ""))))
            continue
        owner_parts = [p for p in parts(g, s) if b is None or p in parts(b, s)]
        cands, rest = (_device_items(key, b, g, s, owner_parts, rows, rindex) if key[0] == "bean"
                       else ([], owner_parts))
        for p, edits, note in cands:
            what = f"{p} {value(g, p)!r} -> {value(s, p)!r}"
            if edits is None:
                found.append((DROPPED, key, dict(info, what=what, note=note)))
            else:
                found.append((DEVICE, key, dict(info, what=what, note=f"merge writes {note}", edits=edits, part=p)))
        if rest:
            sub_g, sub_s = _only(g, rest), _only(s, rest)
            found.append((DROPPED, key, dict(info, what=change_text(sub_g, sub_s),
                                             note=f"the repo wins: change it in {_source(key)}")))
    grouped: list[tuple[str, tuple, dict]] = []
    by_edits: dict[tuple, dict] = {}
    for kind, key, info in found:
        if kind == DEVICE and (info["part"], info["edits"]) in by_edits:
            first = by_edits[(info["part"], info["edits"])]
            first["also"] = first.get("also", ()) + ((key, info["store"]),)
            continue
        if kind == DEVICE:
            by_edits[(info["part"], info["edits"])] = info
        grouped.append((kind, key, info))
    counts = dict.fromkeys(KINDS, 0)
    items = []
    for kind, key, info in grouped:
        counts[kind] += 1
        items.append(Item(f"{ID_PREFIX[kind]}{counts[kind]}", kind, key, **info))
    return Plan(items, has_base, _fingerprint(items, base, repo, store), by_content)


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


def _only(el: ET.Element, keep: list[str]) -> ET.Element:
    """A copy of `el` with only the parts `keep` (for a report of what was dropped)."""
    c = ET.Element(el.tag, {k[1:]: v for k, v in el.attrib.items() if f"@{k}" in keep})
    if "text" in keep:
        c.text = el.text
    for kid in tables.elements(el):
        if kid.tag in keep:
            c.append(copy.deepcopy(kid))
    return c


def _source(key: tuple) -> str:
    kind = key[0]
    if kind == "panel":
        return "the schematic sources (wiki/pipelines/schematic-panels.md)"
    if kind == "logic":
        return "the discovery (jmri/layouts/hart/scripts/run_sml_discover.sh)"
    if kind == "bean" and key[1] in tb.MASTER_SECTIONS:
        return "devices.csv"
    return "the Layout Editor build's sources (wiki/pipelines/schematic-panels.md)"


def _fingerprint(items: list[Item], *roots: ET.Element | None) -> str:
    h = hashlib.sha256()
    for root in roots:
        h.update(b"-" if root is None else hashlib.sha256(canon(root).encode()).digest())
    for i in items:
        h.update(repr((i.id, i.kind, i.key, i.what, i.edits)).encode())
    return h.hexdigest()[:12]


# ---------------------------------------------------------------- choices


@dataclass(frozen=True)
class Choices:
    """What the owner chose: merge these CLASH and DEVICE ids (the rest are dropped) and drop these KEPT ids."""
    merge: frozenset[str] = frozenset()
    drop: frozenset[str] = frozenset()


def check_choices(p: Plan, c: Choices) -> None:
    """SplitError on an id that is not in the plan, or of the wrong kind."""
    ids = p.by_id()
    bad = [i for i in c.merge if i not in ids or ids[i].kind not in REVIEWED]
    bad += [i for i in c.drop if i not in ids or ids[i].kind != KEPT]
    if bad:
        raise SplitError(f"not in this plan, or not of a kind that can take that choice: {', '.join(sorted(bad))} "
                         "(merge takes C and D ids, drop takes K ids)")
    both = [d for d in p.of(DEVICE) if d.id in c.merge]
    cells: dict[tuple[int, str], str] = {}
    for d in both:
        for e in d.edits:
            if cells.setdefault((e.row, e.column), e.new) != e.new:
                raise SplitError(f"{d.id} and another merge write devices.csv row {e.row + 2} {e.column} two ways")


def template_changes(p: Plan, c: Choices) -> list[Item]:
    """The template items the split writes: every KEPT item not dropped and every CLASH merged."""
    return [i for i in p.items if (i.kind == KEPT and i.id not in c.drop) or (i.kind == CLASH and i.id in c.merge)]


def device_edits(p: Plan, c: Choices) -> list[Edit]:
    return [e for i in p.of(DEVICE) if i.id in c.merge for e in i.edits]


def edited_rows(rows: Iterable[Mapping[str, str]], edits: Iterable[Edit]) -> list[dict[str, str]]:
    """devices.csv rows with `edits` written. SplitError when a cell no longer holds the old value."""
    out = [dict(r) for r in rows]
    for e in edits:
        if out[e.row][e.column] != e.old:
            raise SplitError(f"devices.csv row {e.row + 2} {e.column} is {out[e.row][e.column]!r}, not {e.old!r}")
        out[e.row][e.column] = e.new
    return out


def new_template(template: tables.Tables, store: ET.Element, changes: Iterable[Item],
                 by_content: frozenset[tuple] = frozenset()) -> tables.Tables:
    """A copy of the template with each change's Store version in it (or the item deleted), beans in JMRI order.
    An item the template lacks goes where the Store has it: a bean into its section, a setting after the section's
    last setting of that tag (else before its beans), an extra section after the section before it in the Store.
    `by_content` is the plan's (Plan.by_content), so settings are found by the keys the plan gave them."""
    doc = tables.Tables(root=copy.deepcopy(template.root), path=template.path, prolog=template.prolog,
                        epilog=template.epilog, original=template.original, escapes=template.escapes)
    root = doc.root
    store_top = [c for c in tables.elements(store)]

    def sections() -> dict[tuple, ET.Element]:
        return {section_key(s): s for s in tables.elements(root) if s.tag != PANEL}

    for item in changes:
        key, s = item.key, item.store
        kind = key[0]
        if kind == "section":
            have = sections().get(key[1:])
            if have is not None:
                idx = list(root).index(have)
                root.remove(have)
                if s is not None:
                    root.insert(idx, copy.deepcopy(s))
            elif s is not None:
                root.insert(_after(root, store_top, s), copy.deepcopy(s))
            continue
        sec = sections().get(key[1])
        if sec is None:
            raise SplitError(f"the template has no section for {label(key)}")
        if kind == "attrs":
            keep = s.attrib if s is not None else {}
            sec.attrib.clear()
            sec.attrib.update(keep)
            continue
        here = index_section(sec, key[1], by_content)
        if key in here:
            old = here[key]
            idx = list(sec).index(old)
            sec.remove(old)
            if s is not None:
                sec.insert(idx, copy.deepcopy(s))
        elif s is not None:
            sec.insert(_slot(sec, key), copy.deepcopy(s))
        else:
            raise SplitError(f"{item.id} {label(key)}: deleted in the Store, but the template has no such item")
    tb.jmri_sort(root)
    tb.finish(root)
    return doc


def index_section(sec: ET.Element, sk: tuple, by_content: frozenset[tuple] = frozenset()) -> dict[tuple, ET.Element]:
    """index() of one known section's children."""
    out: dict[tuple, ET.Element] = {}
    for el in tables.elements(sec):
        name = tables.system_name(el)
        if name:
            out[("bean", sk, el.tag, tb._sort_group(el), name)] = el
    out.update(_setting_keys(sec, sk, by_content))
    return out


def _slot(sec: ET.Element, key: tuple) -> int:
    kids = list(sec)
    if key[0] == "bean":
        return len(kids)
    same = [i for i, el in enumerate(kids) if isinstance(el.tag, str) and el.tag == key[2]]
    if same:
        return same[-1] + 1
    named = [i for i, el in enumerate(kids) if isinstance(el.tag, str) and tables.system_name(el)]
    return named[0] if named else len(kids)


def _after(root: ET.Element, store_top: list[ET.Element], s: ET.Element) -> int:
    """Where an extra section goes in the template: after the nearest section before it in the Store that the
    template has."""
    have = {(c.tag, c.get("class")): i for i, c in enumerate(root) if isinstance(c.tag, str)}
    at = next(i for i, c in enumerate(store_top) if c is s or canon(c) == canon(s))
    for c in reversed(store_top[:at]):
        k = (c.tag, c.get("class"))
        if k in have:
            return have[k] + 1
    return 0


# ---------------------------------------------------------------- the check after the rebuild


def verify(p: Plan, c: Choices, repo: ET.Element, rebuilt: ET.Element, template: ET.Element) -> list[str]:
    """[] when the rebuilt tables (normalised) are what the plan promised, else what is wrong:
    - each template change gives the Store's version (or the item is gone);
    - each merged device part gives the Store's value;
    - every other template item is the repo's as before;
    - with no device merge, every build item is the repo's as before too (a merged rename may change the panel,
      the logic and other beans that name the device)."""
    R = index(repo, "the repo", p.by_content)
    N = index(rebuilt, "the rebuilt tables", p.by_content)
    T = set(index(template, "the template", p.by_content))
    bad = []
    changed = {i.key for i in template_changes(p, c)}
    for i in template_changes(p, c):
        if canon(N.get(i.key)) != canon(i.store):
            bad.append(f"{i.id} {i.where}: the rebuilt tables do not hold the Store's version")
    merged = [i for i in p.of(DEVICE) if i.id in c.merge]
    for i in merged:
        for key, store_el in ((i.key, i.store),) + i.also:
            el = _rebuilt_bean(N, key, store_el)
            if el is None or value(el, i.part) != value(store_el, i.part):
                bad.append(f"{i.id} {label(key)}: the rebuilt tables give {i.part} {value(el, i.part)!r}, not the "
                           f"Store's {value(store_el, i.part)!r}")
    for key in set(R) | set(N):
        if key in changed:
            continue
        if key in T or not merged:
            if canon(R.get(key)) != canon(N.get(key)):
                bad.append(f"{label(key)}: the rebuild changed it, and no choice asked for that")
    return bad


def _rebuilt_bean(N: Mapping[tuple, ET.Element], key: tuple, store_el: ET.Element) -> ET.Element | None:
    """A merged bean in the rebuilt tables: by its key, else by the Store's system name in the same section."""
    el = N.get(key)
    if el is not None:
        return el
    want = tables.system_name(store_el)
    for k, cand in N.items():
        if k[0] == "bean" and k[1:4] == key[1:4] and k[4] == want:
            return cand
    return None


# ---------------------------------------------------------------- the report


def report(p: Plan, *, verbose: bool = False) -> list[str]:
    """The plan as lines, by kind, for the owner's review in chat."""
    head = {
        KEPT: "KEPT: the owner's changes to what the template holds; the template takes them (drop K.. to refuse one)",
        CLASH: "CLASH, review: the repo changed these too (or there is no base); merge takes the Store's, drop the repo's",
        DEVICE: "DEVICE, review: merge writes devices.csv, drop leaves it",
        DROPPED: "DROPPED: the build owns these, so the repo wins; change the source named to keep one",
    }
    out = [f"plan {p.fingerprint}: " + ", ".join(f"{len(p.of(k))} {k}" for k in KINDS)]
    if not p.has_base:
        out.append("NO BASE: what the host had before the session is not known, so every template change is a CLASH "
                   "and a repo change since the deploy shows as the owner's")
    for kind in KINDS:
        got = p.of(kind)
        if not got:
            continue
        out.append("")
        out.append(head[kind])
        for i in got:
            out.append(f"  {i.id:<4} {i.where}: {i.what}")
            if i.also:
                out.append(f"       also {', '.join(label(k) for k, _ in i.also)}")
            if kind != KEPT or verbose:
                out.append(f"       {i.note}")
    return out


def show(i: Item) -> list[str]:
    """A unified diff of one item: the repo's (or base's) version against the Store's."""
    def lines(el: ET.Element | None) -> list[str]:
        if el is None:
            return []
        c = copy.deepcopy(el)
        tb.finish(c)
        return ET.tostring(c, encoding="unicode").splitlines()
    before = i.repo if i.repo is not None else i.base
    return list(difflib.unified_diff(lines(before), lines(i.store), "repo", "store", lineterm="", n=2))
