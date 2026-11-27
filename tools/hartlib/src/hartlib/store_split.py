"""Split a PanelPro Store back into the sources of tables.xml (ADR-029, R9d; the owner's design in
archive/history/wiki/projects/project-health-handoff.md, "R9d redesign").

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
- the build: everything else, the device-master beans, the Layout Editor panel and its LogixNG, the Signal Mast Logic,
  the Digicon boot rule.

What happens to an item the owner changed (store differs from base):

    KEPT     a template item the repo did not change since the base: the template takes the Store's version (no
             review; listed so it is clear what was taken)
    CLASH    a template item the repo changed too, or any template item when the base is not known: reviewed, merge
             takes the Store's version, drop keeps the repo's
    DEVICE   a rename or comment of a bean whose row is a level-less device in devices_field.csv: reviewed, merge writes the
             row (user_name, and jmri_name where the tables bind it by its user name; jmri_comment), drop leaves it.
             Also a device the Store added (merge adds a level-less row, its beans in jmri_bean)
             and a change to or deletion of a level-less device (merge rewrites or deletes its row)
    DROPPED  anything else of the build's: the repo wins, and the item is listed with what to change instead

<jmriversion> is the one exception: a Store from a newer JMRI is KEPT whatever the base and the repo say, so the next
tables carry the newer version; a Store from the same JMRI gives no item, and one from an older JMRI a DROPPED item
that says to check the host's JMRI.

Nothing reads or writes a file here; tools/schematic/split_store.py runs it, rebuilds tables.xml and verifies the
rebuild (verify). Every failure is a SplitError.

The work is in three modules: hartlib.store_items (the items: index, label, change_text, who claims an item),
hartlib.store_plan (plan and its records) and this one (the owner's choices, the new template, verify, report). The
names callers use are imported here, so `store_split.X` is the one place to reach them.
"""
from __future__ import annotations

import copy
import difflib
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from . import devices, tables
from . import tables_build as tb
from .store_items import LOGIC, PANEL, SplitError, index, index_section, label, normalised, value  # noqa: F401
from .store_keys import (BY_CONTENT, BY_ID, AttrsKey, BeanKey, ByContent, ById, LogicKey, PanelKey,  # noqa: F401
                         SectionKey, SettingKey, canon)
from .store_plan import (CLASH, DEVICE, DROPPED, KEPT, KINDS, REVIEWED, ROW, DeviceEdit, Edit, Item,  # noqa: F401
                         Plan, RowAdd, RowDelete, plan, unplaced_row)


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
    cells: dict[tuple[devices.RowKey, str], str] = {}
    for d in both:
        for e in d.edits:
            if not isinstance(e, Edit):
                continue
            if cells.setdefault((e.key, e.column), e.new) != e.new:
                raise SplitError(f"{d.id} and another merge write {devices.FIELD_FILE} {devices.key_text(e.key)} "
                                 f"{e.column} two ways")


def template_changes(p: Plan, c: Choices) -> list[Item]:
    """The template items the split writes: every KEPT item not dropped and every CLASH merged."""
    return [i for i in p.items if (i.kind == KEPT and i.id not in c.drop) or (i.kind == CLASH and i.id in c.merge)]


def device_edits(p: Plan, c: Choices) -> list[DeviceEdit]:
    """The device-master edits of the merged DEVICE items, in plan order."""
    return [e for i in p.of(DEVICE) if i.id in c.merge for e in i.edits]


def edited_rows(rows: Iterable[Mapping[str, str]], edits: Iterable[DeviceEdit]) -> list[dict[str, str]]:
    """The field file's rows (`rows`) with `edits` written, each edit finding its row by key (never by its place in
    the file). SplitError when the file has no row of an edit's key, or a cell no longer holds the old value."""
    out = [dict(r) for r in rows]
    edits = list(edits)
    at = {devices.key_of(r): n for n, r in enumerate(out)}

    def find(key: devices.RowKey) -> int:
        if key not in at:
            raise SplitError(f"{devices.FIELD_FILE} has no row {devices.key_text(key)} (a Store's device or an "
                             "owner's row); change it by hand")
        return at[key]

    places = [(find(e.key), e) for e in edits if isinstance(e, (Edit, RowDelete))]    # every key before any edit
    for n, e in places:
        if isinstance(e, Edit):
            if out[n][e.column] != e.old:
                raise SplitError(f"{devices.FIELD_FILE} {devices.key_text(e.key)} {e.column} is "
                                 f"{out[n][e.column]!r}, not {e.old!r}")
            out[n][e.column] = e.new
    for n, gone in sorted(((n, e) for n, e in places if isinstance(e, RowDelete)), key=lambda t: -t[0]):
        if not devices.is_unplaced(out[n]):
            raise SplitError(f"{devices.FIELD_FILE} {devices.key_text(gone.key)} is not a level-less row")
        del out[n]
    for add in edits:
        if isinstance(add, RowAdd):
            new = add.row
            rank = devices._rank(new)
            pos = next((n for n, r in enumerate(out) if devices._rank(r) > rank), len(out))
            out.insert(pos, new)
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
        return {tb.section_key(s): s for s in tables.elements(root) if s.tag != PANEL}

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
        if i.part == ROW:
            for key, store_el in ((i.key, i.store),) + i.also:
                if canon(N.get(key)) != canon(store_el):
                    bad.append(f"{i.id} {label(key)}: the rebuilt tables do not hold the Store's version")
            continue
        for key, store_el in ((i.key, i.store),) + i.also:
            if store_el is None:        # a rename or comment is of a bean the Store holds (store_plan._build_drafts)
                bad.append(f"{i.id} {label(key)}: the plan merges a {i.part} of a bean the Store lacks")
                continue
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
        DEVICE: "DEVICE, review: merge writes devices_field.csv, drop leaves it",
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
