"""Parked features: Entry/Exit (NX), the stock Dispatcher System and the USS CTC machine (owner, 2026-11-17).

A parked feature is out of the active tables.xml with all its data kept in the repo, in
jmri/layouts/hart/parked/tables_parked.xml (README.md beside it): a frozen snapshot of the live elements, split once
from the deployed tables.xml at a recorded commit (`freeze`, `python3 -m hartlib.parked freeze --from COMMIT`) and
kept as data; nothing regenerates it. `PARKED` names the parked features; the Layout Editor cut-over build
(tools/schematic/build_layout_le.py --as-live) calls `split` on the tables it writes and leaves their elements out.
Unpark a feature by taking it out of `PARKED` and rebuilding: the snapshot is the data that comes back, and Stage 1
or NX Discover then refresh it against the current geometry. The deploy (tools/hosts/sync_hart_package.sh) reads
`PARKED` too, through `shipped_dirs`.

What each feature holds (`FEATURES`):
- nx: <entryexitpairs>, the ISNX sensors (nx_contract.ISNX_SYSTEM), and every panel slot that binds one
  (layoutturnout sensorA..D, an anchor's east- or westboundsensor, a sensor icon).
- dispatcher: <sections>, <transits>, the "Dispatcher System" Layout Editor panel, the section direction sensors
  (IS:IY:AUTO:*), the Dispatcher System's control, MoveTo and move-in-progress sensors (IS:DSCT*, IS:DSMT*,
  IS:DSMP*) with their icons on the main panel, memory IMIS:ISMEM:versionNo, Logix IX:DSLX:1 and its conditional,
  and LogixNG ConditionalNG IQC:AUTO:0003 ("Hide Dispatcher System") with its action.
- uss: <ctcdata>, the "USS CTC" Panel Editor panel, the CTC lever and indication sensors (IS<n>:<role>), IS:DEBUGCTC,
  IS:RELOADCTC, IS:FLEETING and IS:PRECONDITIONING_ENABLED (JMRI's CTC CodeButtonHandler creates and reads it), Logix
  IX:CTC:REVDEF and its conditional, and LogixNG ConditionalNG IQC:AUTO:0002 ("Hide USS CTC") with its action.

`check` holds both files to that: the tables hold no element of a parked feature and no reference to a parked
name, and the parked file holds each parked feature's parts.
"""
from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from . import paths
from .tables import _serialize

PARKED: frozenset[str] = frozenset({"nx", "dispatcher", "uss"})
FEATURES = {
    "nx": "Entry/Exit (NX)",
    "dispatcher": "Dispatcher System",
    "uss": "USS CTC machine",
}
FOLDER = paths.LAYOUT_DIR / "parked"
PARKED_XML = FOLDER / "tables_parked.xml"

# Files outside tables.xml that stop shipping while a feature is parked (repo paths; the deploy skips them and
# leaves installed copies on the hosts alone).
SHIPPED_DIRS = {
    "dispatcher": ("jmri/layouts/hart/dispatcher",),
    "uss": ("jmri/layouts/hart/ctc",),
}
SHIPPED_JYTHON = {
    "dispatcher": ("repair_dispatcher_traininfo.py",),
}

# top-level tables sections that belong to one feature as a whole
WHOLE = {
    "nx": ("entryexitpairs",),
    "dispatcher": ("sections", "transits"),
    "uss": ("ctcdata",),
}
PANELS = {
    "dispatcher": ("LayoutEditor", "Dispatcher System"),
    "uss": ("paneleditor", "USS CTC"),
}
SENSOR_PATTERNS = {
    "nx": re.compile(r"^ISNX:"),
    "dispatcher": re.compile(r"^IS:(IY:AUTO:\d+:(forward|reverse)|DSCT[AB]?:\d+|DSMT:\d+|DSMP:\d+)$"),
    "uss": re.compile(r"^IS(\d+:[A-Z]+|:DEBUGCTC|:RELOADCTC|:FLEETING|:PRECONDITIONING_ENABLED)$"),
}
MEMORIES = {"dispatcher": ("IMIS:ISMEM:versionNo",)}
LOGIX = {"dispatcher": ("IX:DSLX:1",), "uss": ("IX:CTC:REVDEF",)}
CONDITIONAL_NGS = {"dispatcher": ("IQC:AUTO:0003",), "uss": ("IQC:AUTO:0002",)}
# what the parked file must hold for each feature, at least (check)
EXPECTED_SENSORS = {"nx": 23, "dispatcher": 51, "uss": 264}

SLOT_TAGS = ("sensorA", "sensorB", "sensorC", "sensorD")
SLOT_ATTRS = ("eastboundsensor", "westboundsensor")
ORDER = ("nx", "dispatcher", "uss")


class ParkError(ValueError):
    """A tables file or parked file that does not hold to the parking rules."""


def _name(el: ET.Element) -> str:
    return (el.findtext("systemName") or el.get("systemName") or "").strip()


def _user(el: ET.Element) -> str:
    return (el.findtext("userName") or el.get("userName") or "").strip()


def _remove(parent: ET.Element, child: ET.Element) -> None:
    """Remove `child`, keeping the indentation of what follows (the last child's tail closes the parent)."""
    kids = list(parent)
    i = kids.index(child)
    if i == len(kids) - 1 and i > 0:
        kids[i - 1].tail = child.tail
    parent.remove(child)
    if not len(parent):
        parent.text = None


def _copy(el: ET.Element) -> ET.Element:
    out = ET.Element(el.tag, el.attrib)
    out.text = el.text
    out.extend(list(el))
    return out


def _container(el: ET.Element) -> ET.Element:
    """An empty copy of a tables section (its tag and attributes), to hold the parked children of it."""
    return ET.Element(el.tag, el.attrib)


def _conditional_of(name: str, logix: str) -> bool:
    """Whether conditional `name` belongs to Logix `logix`: named <logix>C<n> (JMRI) or <logix>:C<n> (the USS CTC
    machine's IX:CTC:REVDEF:C1), so IX:DSLX:10C1 is not IX:DSLX:1's."""
    return re.fullmatch(re.escape(logix) + r":?C\d+", name) is not None


def parked_in(root: ET.Element, parked=None) -> frozenset[str]:
    """The features of `parked` (default PARKED) that these tables leave out: none of the feature's whole sections
    is in them. Tables from before the parking (a trial, the staging candidate, the last hand-drawn tables) still hold
    their features and are read as they are; check() holds the checkout's tables to PARKED."""
    parked = PARKED if parked is None else parked
    return frozenset(f for f in parked if not any(root.find(w) is not None for w in WHOLE.get(f, ())))


def feature_sensors(root: ET.Element, feature: str) -> dict[str, str]:
    """{system name: user name} of the sensors of `feature` in `root` (any <sensors> section)."""
    pat = SENSOR_PATTERNS[feature]
    out = {}
    for sec in root.findall("sensors"):
        for s in sec.findall("sensor"):
            sn = _name(s)
            if pat.match(sn):
                out[sn] = _user(s)
    return out


def split(root: ET.Element, parked=PARKED) -> ET.Element:
    """Move every element of the features in `parked` out of the tables `root` (edited in place) and return the
    parked document's root (<hartParked>, one <feature> per parked feature, in ORDER)."""
    unknown = sorted(set(parked) - set(FEATURES))
    if unknown:
        raise ParkError(f"unknown parked features {unknown}; known: {', '.join(ORDER)}")
    doc = ET.Element("hartParked")
    for feature in ORDER:
        if feature in parked:
            doc.append(_split_one(root, feature))
    return doc


def _split_one(root: ET.Element, feature: str) -> ET.Element:
    out = ET.Element("feature", {"name": feature, "title": FEATURES[feature]})
    held = ET.SubElement(out, "tables")
    bindings = ET.SubElement(out, "bindings")
    sensors = feature_sensors(root, feature)
    names = set(sensors) | {u for u in sensors.values() if u}
    actions = {_socket_action(root, c) for c in CONDITIONAL_NGS.get(feature, ())} - {None}
    section_names = {n for whole in WHOLE.get(feature, ()) if whole == "sections"
                     for sec in root.findall("sections") for s in sec for n in (_name(s), _user(s)) if n}

    def park_children(sec: ET.Element, pick) -> None:
        kids = [c for c in sec if pick(c)]
        if not kids:
            return
        box = _container(sec)
        for c in kids:
            box.append(_copy(c))
            _remove(sec, c)
        held.append(box)
        if not len(sec):
            _remove(root, sec)

    for sec in list(root):
        tag = sec.tag
        if tag in WHOLE.get(feature, ()):
            held.append(_copy(sec))
            _remove(root, sec)
        elif tag == "sensors":
            park_children(sec, lambda c: c.tag == "sensor" and _name(c) in sensors)
        elif tag == "memories":
            park_children(sec, lambda c: _name(c) in MEMORIES.get(feature, ()))
        elif tag == "logixs":
            park_children(sec, lambda c: _name(c) in LOGIX.get(feature, ()))
        elif tag == "conditionals":
            park_children(sec, lambda c: any(_conditional_of(_name(c), x) for x in LOGIX.get(feature, ())))
        elif tag == "LogixNGConditionalNGs":
            park_children(sec, lambda c: _name(c) in CONDITIONAL_NGS.get(feature, ()))
        elif tag == "LogixNGDigitalActions":
            park_children(sec, lambda c: _name(c) in actions)
        elif (tag, sec.get("name")) == PANELS.get(feature):
            held.append(_copy(sec))
            _remove(root, sec)
    for sml in root.iter("signalmastlogic"):  # a Signal Mast Logic destination's section (Dispatcher sections)
        for dest in sml.findall("destinationMast"):
            for sec in dest.findall("associatedSection"):
                if (sec.text or "").strip() in section_names:
                    ET.SubElement(bindings, "binding", {"element": "signalmastlogic", "ident": sml.get("source", ""),
                                                        "destination": dest.get("destination", ""),
                                                        "child": "associatedSection", "value": sec.text.strip()})
                    _remove(dest, sec)
    for ng in root.iter("LogixNG"):            # a LogixNG's list of its ConditionalNGs
        lst = ng.find("ConditionalNGs")
        if lst is None:
            continue
        for c in list(lst):
            if c.text and c.text.strip() in CONDITIONAL_NGS.get(feature, ()):
                ET.SubElement(bindings, "binding", {"element": "LogixNG", "ident": _name(ng),
                                                    "child": "ConditionalNGs/systemName", "value": c.text.strip()})
                _remove(lst, c)
    for panel in [p for p in root if p.tag in ("LayoutEditor", "paneleditor")]:
        icons = [el for el in panel if el.get("sensor") in names]
        if icons:
            box = ET.Element(panel.tag, {"name": panel.get("name", "")})
            for el in icons:
                box.append(_copy(el))
                _remove(panel, el)
            held.append(box)
        for el in panel:
            for tag in SLOT_TAGS:
                for slot in el.findall(tag):
                    if (slot.text or "").strip() in names:
                        ET.SubElement(bindings, "binding", _where(panel, el, child=tag, value=slot.text.strip()))
                        _remove(el, slot)
            for attr in SLOT_ATTRS:
                if el.get(attr) in names:
                    ET.SubElement(bindings, "binding", _where(panel, el, attribute=attr, value=el.get(attr)))
                    del el.attrib[attr]
    if not len(bindings):
        out.remove(bindings)
    return out


def _socket_action(root: ET.Element, cng: str) -> str | None:
    for sec in root.findall("LogixNGConditionalNGs"):
        for c in sec:
            if _name(c) == cng:
                return (c.findtext("Socket/systemName") or "").strip() or None
    return None


def _where(panel: ET.Element, el: ET.Element, **what) -> dict:
    return {"panel": panel.get("name", ""), "element": el.tag, "ident": el.get("ident", ""), **what}


NOTE = ("A frozen snapshot of the parked features' live elements, split verbatim (hartlib.parked.freeze) from "
        "jmri/layouts/hart/output/tables.xml at commit {source}, the tables deployed before the helix-join release. "
        "Data, not regenerated; not a JMRI file; do not edit by hand. See README.md beside it.")
SOURCE_PATH = "jmri/layouts/hart/output/tables.xml"


def to_bytes(doc: ET.Element, source: str | None = None) -> bytes:
    """The parked file: `doc` with the commit its elements were split from (`source`, kept as its source attribute)."""
    doc = _copy(doc)
    source = source or doc.get("source") or ""
    if not re.fullmatch(r"[0-9a-f]{7,40}", source):
        raise ParkError(f"the parked file records the commit its elements came from; got {source!r}")
    doc.set("source", source)
    ET.indent(doc, space="  ")
    return (b'<?xml version="1.0" encoding="UTF-8"?>\n<!-- ' + NOTE.format(source=source).encode() + b" -->\n"
            + _serialize(doc, "jdom") + b"\n")


def freeze(commit: str, out: Path = PARKED_XML) -> ET.Element:
    """Split the parked features once from tables.xml as committed at `commit` (the live tables) into `out`."""
    import subprocess
    sha = subprocess.run(["git", "-C", str(paths.REPO_ROOT), "rev-parse", "--short=8", f"{commit}^{{commit}}"],
                         capture_output=True, text=True, check=True).stdout.strip()
    data = subprocess.run(["git", "-C", str(paths.REPO_ROOT), "show", f"{sha}:{SOURCE_PATH}"],
                          capture_output=True, check=True).stdout
    doc = split(ET.fromstring(data), PARKED)
    out.write_bytes(to_bytes(doc, sha))
    return read(out)


def read(path: Path = PARKED_XML) -> ET.Element:
    return ET.parse(path).getroot()


def restore(root: ET.Element, doc: ET.Element, features=None) -> ET.Element:
    """A copy of the tables `root` with the parked `features` (default: every one `doc` holds) put back: their
    sections and panels appended, their beans and panel items appended to the section or panel they came from, and
    their bindings set again. For the checks that keep a parked feature's data consistent with the active tables
    (the USS CTC levers and switches, the Dispatcher stations): an unparked view, never a file to load."""
    out = ET.fromstring(ET.tostring(root))
    for f in doc.findall("feature"):
        if features is not None and f.get("name") not in features:
            continue
        tables_el = f.find("tables")
        for box in tables_el if tables_el is not None else ():
            panel = box.tag in ("LayoutEditor", "paneleditor")
            if (panel and box.get("class")) or box.tag in sum(WHOLE.values(), ()):
                out.append(copy.deepcopy(box))
                continue
            home = next((s for s in out if s.tag == box.tag and (
                s.get("name") == box.get("name") if panel else s.get("class") == box.get("class"))), None)
            if home is None:
                home = ET.SubElement(out, box.tag, dict(box.attrib))
            home.extend(copy.deepcopy(list(box)))
        for b in f.iter("binding"):
            _rebind(out, b)
    ET.indent(out, space="  ")          # JMRI's two-space layout, so text readers see the stored form
    return out


def _rebind(root: ET.Element, b: ET.Element) -> None:
    value, child, attr = b.get("value"), b.get("child"), b.get("attribute")
    if b.get("element") == "LogixNG":
        for ng in root.iter("LogixNG"):
            lst = ng.find("ConditionalNGs")
            if _name(ng) == b.get("ident") and lst is not None:
                ET.SubElement(lst, "systemName").text = value
        return
    if b.get("element") == "signalmastlogic":
        for sml in root.iter("signalmastlogic"):
            if sml.get("source") == b.get("ident"):
                for dest in sml.findall("destinationMast"):
                    if dest.get("destination") == b.get("destination"):
                        ET.SubElement(dest, child).text = value
        return
    for panel in root:
        if panel.get("name") != b.get("panel"):
            continue
        for el in panel.findall(b.get("element")):
            if el.get("ident") == b.get("ident"):
                if attr:
                    el.set(attr, value)
                else:
                    ET.SubElement(el, child).text = value


def with_parked(features, tables_path: Path | None = None, parked_path: Path = PARKED_XML) -> ET.Element:
    """The tables (this checkout's by default) as a root element, with `features` put back where they are parked
    (restore); the tables unchanged when none of them is."""
    from . import tables
    root = tables.read(tables_path or paths.TABLES_XML)
    # a tables file that still holds a feature (one from before the parking, read from history) is read as it is
    wanted = [f for f in features if f in PARKED and not any(root.find(w) is not None for w in WHOLE.get(f, ()))]
    if not wanted:
        return root
    return restore(root, read(parked_path), wanted)


def with_parked_file(features, tables_path: Path | None = None) -> Path:
    """with_parked as a file, for readers that take a path or read the text: a temporary copy (removed when the
    process ends) while one of `features` is parked, else the tables file itself."""
    import atexit
    import shutil
    import tempfile
    from . import tables
    path = Path(tables_path or paths.TABLES_XML)
    root = tables.read(path)
    if not any(f in PARKED and not any(root.find(w) is not None for w in WHOLE.get(f, ())) for f in features):
        return path
    folder = Path(tempfile.mkdtemp(prefix="hart-unparked-"))
    atexit.register(shutil.rmtree, folder, True)
    out = folder / "tables.xml"
    out.write_bytes(tables.Tables(root=with_parked(features, path)).tobytes())
    return out


def counts(doc: ET.Element) -> dict[str, Counter]:
    """{feature: Counter of what it parks} for the README and the report."""
    out = {}
    for f in doc.findall("feature"):
        c = Counter()
        for box in f.find("tables") if f.find("tables") is not None else ():
            if box.tag in ("LayoutEditor", "paneleditor") and box.get("class"):
                c[f"{box.tag} panel {box.get('name')!r}"] += 1
            elif box.tag in ("LayoutEditor", "paneleditor"):
                for el in box:
                    c[f"{el.tag} on {box.get('name')!r}"] += 1
            elif box.tag in ("sections", "transits", "ctcdata"):
                c[box.tag] += len(box)
            elif box.tag == "entryexitpairs":
                c["entryexit pairs"] += sum(1 for _ in box.iter("destination"))
            else:
                for el in box:
                    c[el.tag] += 1
        for b in f.iter("binding"):
            c[f"binding {b.get('child') or b.get('attribute')}"] += 1
        out[f.get("name")] = c
    return out


def names_in(doc: ET.Element) -> set[str]:
    """Every bean name (system and user) the parked file defines, and its panel names."""
    out = set()
    for f in doc.findall("feature"):
        tables_el = f.find("tables")
        if tables_el is None:
            continue
        for box in tables_el:
            if box.tag in ("sensors", "memories", "logixs", "conditionals", "LogixNGConditionalNGs",
                           "LogixNGDigitalActions", "sections", "transits"):
                for el in box:
                    out |= {n for n in (_name(el), _user(el)) if n}
    return out


def check(tables_root: ET.Element, doc: ET.Element, parked=PARKED) -> list[str]:
    """Problems with a tables file and its parked file under `parked` (none: both hold to the rules)."""
    bad = []
    if not re.fullmatch(r"[0-9a-f]{7,40}", doc.get("source") or ""):
        bad.append("the parked file does not record the commit its elements were split from (source)")
    have = {f.get("name") for f in doc.findall("feature")}
    if have != set(parked):
        bad.append(f"the parked file holds features {sorted(have)}, PARKED is {sorted(parked)}")
    # the tables hold nothing a split would still move
    probe = ET.fromstring(ET.tostring(tables_root))
    left = split(probe, parked)
    for f in left.findall("feature"):
        tables_el = f.find("tables")
        n = (len(tables_el) if tables_el is not None else 0) + len(list(f.iter("binding")))
        if n:
            what = [e.tag for e in (tables_el if tables_el is not None else [])] + \
                   [b.get("value") for b in f.iter("binding")]
            bad.append(f"tables.xml still holds parked {f.get('name')} elements: {what[:8]}")
    # no reference in the tables to a name the parked file defines
    # (a name the tables still define for a bean of their own is not a parked name: Dispatcher sections over one
    # block take the block's user name)
    own = {n for el in tables_root.iter() for n in (el.findtext("systemName"), el.findtext("userName")) if n}
    gone = names_in(doc) - {n.strip() for n in own}
    refs = Counter()
    for el in tables_root.iter():
        for v in list(el.attrib.values()) + [(el.text or "").strip()]:
            if v in gone:
                refs[v] += 1
    if refs:
        bad.append(f"tables.xml refers to {len(refs)} parked names: {sorted(refs)[:8]}")
    # the parked file holds each feature's parts
    for f in doc.findall("feature"):
        name = f.get("name")
        tables_el = f.find("tables")
        tags = [b.tag for b in tables_el] if tables_el is not None else []
        for whole in WHOLE.get(name, ()):
            if whole not in tags:
                bad.append(f"the parked file's {name} has no <{whole}>")
        if name in PANELS:
            tag, title = PANELS[name]
            if tables_el is None or not any(b.tag == tag and b.get("name") == title and b.get("class")
                                            for b in tables_el):
                bad.append(f"the parked file's {name} has no {tag} panel {title!r}")
        parked_sensors = feature_sensors(tables_el, name) if tables_el is not None else {}
        if len(parked_sensors) < EXPECTED_SENSORS[name]:
            bad.append(f"the parked file's {name} holds {len(parked_sensors)} sensors, expected at least "
                       f"{EXPECTED_SENSORS[name]}")
    return bad


def shipped_dirs(parked=PARKED) -> list[str]:
    """Repo folders the deploy leaves out while their feature is parked."""
    return [d for f in ORDER if f in parked for d in SHIPPED_DIRS.get(f, ())]


def shipped_jython(parked=PARKED) -> list[str]:
    """Jython scripts the deploy leaves out while their feature is parked."""
    return [j for f in ORDER if f in parked for j in SHIPPED_JYTHON.get(f, ())]


def main(argv=None) -> int:
    """python3 -m hartlib.parked [features|dirs|jython|check|freeze --from COMMIT]: the parked features, the folders
    and jython the deploy skips (one per line), the check of tables.xml against the parked file, or (once, when a
    feature is parked) the snapshot of its live elements from tables.xml at COMMIT."""
    import argparse
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("what", choices=("features", "dirs", "jython", "check", "freeze"))
    ap.add_argument("--from", dest="commit", help="freeze: the commit whose tables.xml holds the live elements")
    args = ap.parse_args(argv)
    if args.what == "freeze":
        if not args.commit:
            ap.error("freeze needs --from COMMIT")
        paths.exit_if_overridden("hartlib.parked freeze")
        doc = freeze(args.commit)
        print(f"wrote {paths.rel(PARKED_XML)} from {SOURCE_PATH} at {doc.get('source')}: " + "; ".join(
            f"{f}: " + ", ".join(f"{v} {k}" for k, v in sorted(c.items())) for f, c in counts(doc).items()))
    elif args.what == "features":
        print("\n".join(f for f in ORDER if f in PARKED))
    elif args.what == "dirs":
        print("\n".join(shipped_dirs()))
    elif args.what == "jython":
        print("\n".join(shipped_jython()))
    else:
        from . import tables
        if not PARKED:
            print("ok: nothing parked")
            return 0
        bad = check(tables.read(paths.TABLES_XML), read())
        for b in bad:
            print(f"FAIL: {b}")
        if bad:
            return 1
        c = counts(read())
        print("ok: tables.xml holds no parked element or name; parked: "
              + "; ".join(f"{f} ({sum(v.values())} items)" for f, v in c.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
