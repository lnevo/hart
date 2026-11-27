"""The store split's plan (hartlib.store_split, whose docstring gives the rules): each item the owner changed in a
Store, sorted KEPT, CLASH, DEVICE or DROPPED, with the device-master edits a DEVICE merge writes.

plan() runs four steps over the items of hartlib.store_items.index: who owns an item (_owner), a template item's
draft (_template_draft), a build item's drafts (_build_drafts, which gathers the beans of level-less devices for
_added_drafts and _changed_drafts), and the grouping of DEVICE drafts that write the same edits (_grouped). A Draft is
an item before its id; _numbered gives the ids. Every failure is a SplitError."""
from __future__ import annotations

import copy
import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final, Literal, NamedTuple

from . import devices, tables
from . import tables_build as tb
from .store_items import (LAYER_OF, VERSION, SplitError, change_text, claimed_by, claimed_name, index, label,
                          name_holder, newer_jmri, parts, repeated_settings, row_at, row_index, rows_of, value)
from .store_keys import BeanKey, canon

Kind = Literal["kept", "clash", "device", "dropped"]
KEPT: Final = "kept"
CLASH: Final = "clash"
DEVICE: Final = "device"
DROPPED: Final = "dropped"
KINDS: tuple[Kind, ...] = (KEPT, CLASH, DEVICE, DROPPED)
ID_PREFIX: dict[Kind, str] = {KEPT: "K", CLASH: "C", DEVICE: "D", DROPPED: "G"}
REVIEWED: tuple[Kind, ...] = (CLASH, DEVICE)        # the kinds a merge or drop is asked for
ROW = "row"                         # a DEVICE item's part when it adds, rewrites or deletes a level-less row
UNPLACED_DESCRIPTION = "Added in PanelPro; its level, cp and role come later."


@dataclass(frozen=True)
class Edit:
    """One devices_field.csv cell a DEVICE merge writes, its row named by its key (devices.key_of: level, id)."""
    key: devices.RowKey
    column: str
    old: str
    new: str


@dataclass(frozen=True)
class RowAdd:
    """A device-master row a DEVICE merge adds: a device added in the Store, kept by its beans with no level yet."""
    cells: tuple[tuple[str, str], ...]      # (column, value) in devices.COLUMNS order

    @property
    def row(self) -> dict[str, str]:
        return dict(self.cells)


@dataclass(frozen=True)
class RowDelete:
    """A level-less devices_field.csv row a DEVICE merge deletes: its device was deleted in the Store."""
    key: devices.RowKey


DeviceEdit = Edit | RowAdd | RowDelete
# The other beans a DEVICE item's edits come from (a block's other pass, its layout block), each with its Store
# version (None: deleted in the Store).
Also = tuple[tuple[tuple, ET.Element | None], ...]


@dataclass(frozen=True)
class Item:
    id: str             # K1, C1, D1, G1: stable for one (base, repo, Store)
    kind: Kind
    key: tuple
    what: str           # the owner's change: "userName 'Switch 1' -> 'Switch 1X'"
    note: str           # where it goes, or for DROPPED what to change instead
    store: ET.Element | None = field(default=None, compare=False, repr=False)   # the Store's version (None: deleted)
    repo: ET.Element | None = field(default=None, compare=False, repr=False)
    base: ET.Element | None = field(default=None, compare=False, repr=False)
    edits: tuple[DeviceEdit, ...] = ()
    part: str = ""      # DEVICE: the part merged ("userName" or "comment"), or ROW for a level-less device's row
    also: Also = ()     # DEVICE: the other beans the same edits come from

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


class Sides(NamedTuple):
    """One item's versions: the base's, the repo's and the Store's (None where that file lacks it)."""
    base: ET.Element | None
    repo: ET.Element | None
    store: ET.Element | None


@dataclass
class Draft:
    """An item of the plan before its id: _grouped adds to `also`, _numbered gives the ids."""
    kind: Kind
    key: tuple
    sides: Sides
    what: str
    note: str
    edits: tuple[DeviceEdit, ...] = ()
    part: str = ""
    also: Also = ()

    def item(self, ident: str) -> Item:
        return Item(ident, self.kind, self.key, self.what, self.note, self.sides.store, self.sides.repo,
                    self.sides.base, self.edits, self.part, self.also)


class Added(NamedTuple):
    """A bean of a device the Store added, with no row yet."""
    key: tuple
    base: ET.Element | None
    store: ET.Element


class Touched(NamedTuple):
    """A bean of a level-less row that the Store changed or deleted."""
    key: tuple
    sides: Sides


@dataclass
class LevelLess:
    """The beans plan() gathers for the level-less device rows: the devices the Store added, by (layer, name), and
    the beans of existing level-less rows it changed, by row number."""
    added: dict[tuple[str, str], list[Added]] = field(default_factory=dict)
    changed: dict[int, list[Touched]] = field(default_factory=dict)


@dataclass(frozen=True)
class Compared:
    """The four files indexed, and what the steps of plan() read of them."""
    base: dict[tuple, ET.Element]           # the repo's when there is no base
    repo: dict[tuple, ET.Element]
    store: dict[tuple, ET.Element]
    template: dict[tuple, ET.Element]
    rows: list[Mapping[str, str]]
    rindex: Mapping[tuple[str, str], list[int]]
    has_base: bool
    newer: bool                             # the Store is from a newer JMRI than the repo
    older: bool                             # from an older one
    by_content: frozenset[tuple]


class Candidate(NamedTuple):
    """A rename or comment of a build bean: the edits that merge it, or None and why it cannot be merged."""
    part: str
    edits: tuple[Edit, ...] | None
    note: str


# ---------------------------------------------------------------- the plan


def plan(base: ET.Element | None, repo: ET.Element, store: ET.Element, template: ET.Element,
         rows: Iterable[Mapping[str, str]]) -> Plan:
    """The plan for a Store: each item the owner changed, and where it goes (store_split's docstring). All four roots
    normalised (store_items.normalised); `template` is data/tables_template.xml as read_template gives it."""
    c = compare(base, repo, store, template, list(rows))
    drafts: list[Draft] = []
    level_less = LevelLess()
    for key in sorted(set(c.base) | set(c.repo) | set(c.store), key=repr):
        drafts += _drafts(c, key, Sides(c.base.get(key), c.repo.get(key), c.store.get(key)), level_less)
    drafts += _added_drafts(level_less.added, c.rows)
    drafts += _changed_drafts(level_less.changed, c.rows, c.has_base)
    items = _numbered(_grouped(drafts))
    return Plan(items, c.has_base, _fingerprint(items, base, repo, store), c.by_content)


def compare(base: ET.Element | None, repo: ET.Element, store: ET.Element, template: ET.Element,
            rows: list[Mapping[str, str]]) -> Compared:
    """The four roots indexed by the same repeated settings (the base's index is the repo's when there is none)."""
    by_content = repeated_settings(base, repo, store, template)
    return Compared(
        base=index(base, "the base", by_content) if base is not None else index(repo, "the repo", by_content),
        repo=index(repo, "the repo", by_content), store=index(store, "the Store", by_content),
        template=index(template, "the template", by_content), rows=rows, rindex=row_index(rows),
        has_base=base is not None, newer=newer_jmri(store, repo), older=newer_jmri(repo, store), by_content=by_content)


def _drafts(c: Compared, key: tuple, sides: Sides, level_less: LevelLess) -> list[Draft]:
    """The drafts of one item key; none when the owner changed nothing or the repo has the change already."""
    b, g, s = sides
    if key[0] == "attrs" and s is None:
        return []                       # JMRI writes no section once it holds nothing; its children say what went
    if key[0] != "panel" and key[1] == VERSION:
        return _version_drafts(c, key, sides)
    if canon(s) in (canon(b), canon(g)):
        return []
    el = s if s is not None else g if g is not None else b
    assert el is not None, key          # key comes from the base, the repo or the Store, so one of them holds it
    if _owner(c, key, el) == "template":
        return [_template_draft(c, key, sides)]
    return _build_drafts(c, key, sides, el, level_less)


def _version_drafts(c: Compared, key: tuple, sides: Sides) -> list[Draft]:
    """<jmriversion>: KEPT from a newer JMRI, DROPPED from an older one, nothing from the same one."""
    if canon(sides.store) == canon(sides.repo):
        return []
    what = change_text(sides.repo, sides.store)
    if c.newer:
        return [Draft(KEPT, key, sides, what, "a newer JMRI wrote the Store: the template always takes it")]
    if c.older:
        return [Draft(DROPPED, key, sides, what, "an older JMRI wrote the Store than the tables name: the repo keeps "
                                                 "its version; check the host's JMRI before the deploy")]
    return []


def _owner(c: Compared, key: tuple, el: ET.Element) -> Literal["template", "build"]:
    """The template owns what it holds, and an item of the Store's or the base's that nothing claims (claimed_by);
    the build owns the rest."""
    if key in c.template:
        return "template"
    if key in c.repo or claimed_by(key, el, c.rows):
        return "build"
    return "template"


def _template_draft(c: Compared, key: tuple, sides: Sides) -> Draft:
    b, g, s = sides
    if c.has_base and canon(g) == canon(b):
        return Draft(KEPT, key, sides, change_text(b, s), "the template takes it")
    why = "the repo changed it too since the deploy" if c.has_base else "no base: who changed it is unknown"
    return Draft(CLASH, key, sides, change_text(g, s), f"{why}; merge takes the Store's, drop keeps the repo's")


def _build_drafts(c: Compared, key: tuple, sides: Sides, el: ET.Element, level_less: LevelLess) -> list[Draft]:
    """The drafts of an item the build owns: a level-less device's bean goes to `level_less` instead."""
    b, g, s = sides
    if key[0] == "bean" and key[1] in tb.MASTER_SECTIONS:
        found = rows_of(c.rindex, key, g if g is not None else b if b is not None else el)
        mine = [i for i in found if devices.is_unplaced(c.rows[i])]
        if mine:
            level_less.changed.setdefault(mine[0], []).append(Touched(key, sides))
            return []
        if g is None and b is None and s is not None and not claimed_name(key, s, c.rows):
            name = tables.user_name(s) if key[1] in (tb.BLOCKS, tb.LAYOUT_BLOCKS) else ""
            level_less.added.setdefault((LAYER_OF[key[1][0]], name or key[4]), []).append(Added(key, b, s))
            return []
    if s is None:
        return [Draft(DROPPED, key, sides, "deleted in the Store", f"delete it in its source ({_source(key)}) and "
                                                                   "rebuild")]
    if g is None:
        new = b is None
        holder = name_holder(key, s, c.rows) if new and key[0] == "bean" else None
        if holder:
            return [Draft(DROPPED, key, sides, "added in the Store", holder)]
        why = (claimed_name(key, s, c.rows) if key[0] == "bean" else None) or claimed_by(key, s, c.rows) or "the build"
        return [Draft(DROPPED, key, sides, "added in the Store" if new else "the repo no longer makes it",
                      f"{why} makes it")]
    since_base = parts(b, s) if b is not None else None
    owner_parts = [p for p in parts(g, s) if since_base is None or p in since_base]
    cands, rest = _device_items(key, g, s, owner_parts, c) if key[0] == "bean" else ([], owner_parts)
    out = []
    for cand in cands:
        what = f"{cand.part} {value(g, cand.part)!r} -> {value(s, cand.part)!r}"
        if cand.edits is None:
            out.append(Draft(DROPPED, key, sides, what, cand.note))
        else:
            out.append(Draft(DEVICE, key, sides, what, f"merge writes {cand.note}", edits=cand.edits, part=cand.part))
    if rest:
        out.append(Draft(DROPPED, key, sides, change_text(_only(g, rest), _only(s, rest)),
                         f"the repo wins: change it in {_source(key)}"))
    return out


def _grouped(drafts: list[Draft]) -> list[Draft]:
    """The drafts with each DEVICE draft that writes the same edits as an earlier one folded into that one's `also`
    (a rename on both passes of a block is one question)."""
    out: list[Draft] = []
    first: dict[tuple[str, tuple[DeviceEdit, ...]], Draft] = {}
    for d in drafts:
        if d.kind == DEVICE:
            got = first.get((d.part, d.edits))
            if got is not None:
                got.also += ((d.key, d.sides.store),)
                continue
            first[(d.part, d.edits)] = d
        out.append(d)
    return out


def _numbered(drafts: list[Draft]) -> list[Item]:
    """The items, numbered by kind in order; SplitError when a DEVICE item has no edits or another kind has some."""
    counts = dict.fromkeys(KINDS, 0)
    items = []
    for d in drafts:
        if (d.kind == DEVICE) != bool(d.edits):
            raise SplitError(f"{d.kind} item {d.key!r} has {len(d.edits)} edits")
        counts[d.kind] += 1
        items.append(d.item(f"{ID_PREFIX[d.kind]}{counts[d.kind]}"))
    return items


def _fingerprint(items: list[Item], *roots: ET.Element | None) -> str:
    h = hashlib.sha256()
    for root in roots:
        h.update(b"-" if root is None else hashlib.sha256(canon(root).encode()).digest())
    for i in items:
        h.update(repr((i.id, i.kind, i.key, i.what, i.edits)).encode())
    return h.hexdigest()[:12]


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
        return f"the device master ({devices.FIELD_FILE} for the owner's cells, else the builders' inputs)"
    return "the Layout Editor build's sources (wiki/pipelines/schematic-panels.md)"


# ---------------------------------------------------------------- a build bean's rename or comment


def _device_items(key: tuple, g: ET.Element, s: ET.Element, owner_parts: list[str], c: Compared
                  ) -> tuple[list[Candidate], list[str]]:
    """(a Candidate for each rename or comment the owner made to a build bean, the other parts for DROPPED)."""
    out: list[Candidate] = []
    rest: list[str] = []
    for p in owner_parts:
        if p not in ("userName", "comment"):
            rest.append(p)
            continue
        found = rows_of(c.rindex, key, g)
        if len(found) != 1:
            out.append(Candidate(p, None, "no row of the device master gives this bean" if not found else
                                 f"{len(found)} rows of the device master give this bean; change the right one by "
                                 "hand"))
            continue
        r = c.rows[found[0]]
        why = _written(r, p)
        if why:
            out.append(Candidate(p, None, why))
        elif p == "userName":
            out.append(_rename(r, value(g, p), value(s, p), c.rows))
        else:
            out.append(_comment(r, value(s, p)))
    return out, rest


def _written(r: Mapping[str, str], p: str) -> str | None:
    """Why a script-written row takes no merge of part `p`, with what to do; None for an owner's row."""
    who = row_at(r)
    if r["written_by"] == "build_device_map.py" and r["layer"] in ("turnout", "fb") and p == "userName":
        # by the row's layer and writer, not its level: every level's switch rows are
        # the builder's, the owner's name a devices_field.csv cell
        return (f"{who} is a switch's row the builder makes: rename it by hand in its devices_field.csv row (keyed by "
                "its id): change user_name, and jmri_name with it when that binds the turnout by its user name (the "
                "build stops on one without the other); wiring.csv keeps the generated name the id gives")
    if r["written_by"] == "build_device_map.py" and r["layer"] == "block" and p == "userName":
        # a block of any level (main and upper's are virtual beans): the owner's
        # name is a devices_field.csv cell, its bean names stay (numbered over the generated name)
        return (f"{who} is a block the builder names: rename it by hand in its devices_field.csv row (keyed by its "
                "id): change user_name; its jmri_name and layout_block stay")
    if r["written_by"]:
        return f"{r['written_by']} writes {who}: change its inputs and rebuild"
    return None


def _rename(r: Mapping[str, str], old: str, new: str, rows: list[Mapping[str, str]]) -> Candidate:
    """The user_name edit (and jmri_name, when the row binds the bean by its user name) of an owner's row."""
    p, who = "userName", row_at(r)
    if r["user_name"] != old:
        return Candidate(p, None, f"{who} gives {r['user_name']!r}, not {old!r}; rename it by hand")
    taken = [x for x in rows if x is not r and x["layer"] == r["layer"] and x["user_name"] == new]
    if not new or taken:
        return Candidate(p, None, f"{new!r} is " + ("empty" if not new else "another row's name"))
    edits = [Edit(devices.key_of(r), "user_name", old, new)]
    if r["jmri_name"] == old:           # bound by its user name (owner decision Q13)
        edits.append(Edit(devices.key_of(r), "jmri_name", old, new))
    return Candidate(p, tuple(edits), f"{who}: user_name" + (" and jmri_name" if len(edits) > 1 else ""))


def _comment(r: Mapping[str, str], new: str) -> Candidate:
    """The jmri_comment edit of an owner's row: the Store's comment less what the build adds to it."""
    p = "comment"
    if r["bean_comment"]:
        return Candidate(p, None, "build_device_map.py writes this bean's comment (its bean_comment, a main or upper "
                                  "row's) from the row's columns; change those")
    if r["wiring"] or not r["jmri_comment"]:
        return Candidate(p, None, "the comment is generated from the row's wiring and dcc columns; change those")
    text = new
    if r["layer"] == "head" and r["role"] == "head" and r["assignment"] == "virtual":
        tail = f" | {tb.VIRTUAL_HEAD_NOTE}"
        if not text.endswith(tail):
            return Candidate(p, None, f"a virtual head's comment ends with {tail.strip(' |')!r}, which the build adds; "
                                      "keep it")
        text = text[: -len(tail)]
    if r["layer"] == "mast" and r["dir"] in tb.DIRECTION_WORD:
        word = tb.DIRECTION_WORD[r["dir"]]
        pieces = text.split(" | ")
        if word not in pieces:
            return Candidate(p, None, f"a mast's comment carries its direction {word!r}, which the build adds; keep it")
        pieces.remove(word)
        text = " | ".join(pieces)
    if r["layer"] == "block" and re.search(devices.OCCUPANCY_TEXT, r["jmri_comment"]):
        back = tb.occupancy_back(text)      # the build put the detector first; the master keeps it after
        if back is None:
            return Candidate(p, None, "a block's comment starts with its detector (Block n-k / M2S...), which the "
                                      "build puts there; keep it")
        text = back
    elif r["layer"] == "block" and text != tb.occupancy_first(text):
        return Candidate(p, None, "a block with no detector in the master gains one only by hand")
    return Candidate(p, (Edit(devices.key_of(r), "jmri_comment", r["jmri_comment"], text),),
                     f"{row_at(r)}: jmri_comment")


# ---------------------------------------------------------------- level-less devices


def unplaced_row(beans: list[tuple[tuple, ET.Element]], old: Mapping[str, str] | None = None) -> dict[str, str]:
    """The level-less device-master row of a device's Store beans ((section key, element)): its names and comment
    from the main bean (a block's full pass, else the one bean), the rest of the beans in jmri_bean. `old`, the row
    as it was, keeps its description."""
    layer = LAYER_OF[beans[0][0][0]]
    main = next((el for sk, el in beans if sk == tb.BLOCKS and tb.sort_group(el) == "block"),
                next(el for sk, el in beans if sk != tb.LAYOUT_BLOCKS))
    system = tables.system_name(main)
    row = dict.fromkeys(devices.COLUMNS, "")
    row.update(layer=layer, user_name=tables.user_name(main) or system, assignment="field", system_name=system,
               jmri_name=system, jmri_comment=(main.findtext("comment") or "").strip(),
               description=old["description"] if old else UNPLACED_DESCRIPTION)
    lb = [el for sk, el in beans if sk == tb.LAYOUT_BLOCKS]
    if lb:
        row["layout_block"] = tables.system_name(lb[0])
    row["jmri_bean"] = tb.bean_json(beans, row)
    return row


def _row_edits(old: Mapping[str, str], new: Mapping[str, str]) -> tuple[Edit, ...]:
    return tuple(Edit(devices.key_of(old), c, old[c], new[c]) for c in devices.COLUMNS if old[c] != new[c])


def _added_drafts(added: Mapping[tuple[str, str], list[Added]], rows: list[Mapping[str, str]]) -> list[Draft]:
    """A DEVICE draft that adds a level-less row for each device the Store added; DROPPED when a row has its name or
    it is a layout block alone."""
    out = []
    for got in added.values():
        first = got[0]
        sides = Sides(first.base, None, first.store)
        beans = [(a.key[1], a.store) for a in got]
        if all(sk == tb.LAYOUT_BLOCKS for sk, _ in beans):
            out.append(Draft(DROPPED, first.key, sides, "added in the Store", (
                "a layout block with no block of the same user name added with it; add the block, or name the "
                "layout block as its block")))
            continue
        row = unplaced_row(beans)
        taken = [r for r in rows if (r["level"], r["layer"], r["user_name"]) == ("", row["layer"], row["user_name"])
                 or r["jmri_name"] == row["jmri_name"]]
        also: Also = tuple((a.key, a.store) for a in got[1:])
        if taken:
            out.append(Draft(DROPPED, first.key, sides, "added in the Store",
                             f"{row_at(taken[0])} has its name; rename one in PanelPro", part=ROW, also=also))
            continue
        out.append(Draft(DEVICE, first.key, sides, "added in the Store",
                         f"merge adds a level-less devices_field.csv {row['layer']} row {row['user_name']!r} (its "
                         "level, cp and role come later)", edits=(RowAdd(tuple(row.items())),), part=ROW, also=also))
    return out


def _changed_drafts(changed: Mapping[int, list[Touched]], rows: list[Mapping[str, str]], has_base: bool
                    ) -> list[Draft]:
    """A DEVICE draft that rewrites or deletes each level-less row whose beans the Store changed or deleted."""
    out = []
    for i, got in changed.items():
        old = rows[i]
        first = got[0]
        also: Also = tuple((t.key, t.sides.store) for t in got[1:])
        if all(t.sides.store is None for t in got):
            out.append(Draft(DEVICE, first.key, first.sides, "deleted in the Store",
                             f"merge deletes devices_field.csv {old['layer']} row {old['user_name']!r}",
                             edits=(RowDelete(devices.key_of(old)),), part=ROW, also=also))
            continue
        new = unplaced_row(_row_side(old, got, store=True), old)
        known = has_base and any(t.sides.base is not None for t in got)
        base_side = _row_side(old, got, store=False)
        was = unplaced_row(base_side, old) if known and base_side else None
        # a cell the owner did not change (the Store's equals the base's) keeps the repo's, so a repo edit since the
        # deploy survives; with no base every difference is the owner's
        wanted = {col: v for col, v in new.items() if was is None or v != was[col]}
        edits = _row_edits(old, {**old, **wanted})
        if not edits:
            continue
        both = [e.column for e in edits if was is not None and old[e.column] != was[e.column]]
        out.append(Draft(DEVICE, first.key, first.sides, change_text(first.sides.repo, first.sides.store),
                         f"merge rewrites level-less devices_field.csv row {old['layer']} {old['user_name']!r} "
                         f"({', '.join(e.column for e in edits)})"
                         + (f"; the repo changed {', '.join(both)} too since the deploy, and merge takes the Store's"
                            if both else ""), edits=edits, part=ROW, also=also))
    return out


def _row_side(old: Mapping[str, str], got: list[Touched], *, store: bool) -> list[tuple[tuple, ET.Element]]:
    """A level-less row's beans with the Store's (`store`) or the base's version of each one the Store touched, and
    the touched beans the repo lacks."""
    by_key = {t.key: t.sides for t in got}

    def pick(sides: Sides) -> ET.Element | None:
        return sides.store if store else sides.base

    out = []
    for sk, el in tb.row_beans(old):
        k = BeanKey("bean", sk, el.tag, tb.sort_group(el), tables.system_name(el) or "")
        v = pick(by_key[k]) if k in by_key else el
        if v is not None:
            out.append((sk, v))
    for t in got:
        v = pick(t.sides)
        if t.sides.repo is None and v is not None:
            out.append((t.key[1], v))
    return out
