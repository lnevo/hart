"""The Signal Mast Logic of the generated tables: the logic and mast properties stock discovery wrote
(DISCOVERED, taken from a discovery Store by build_tables.py --discovered-from), merged into the tables
(merge_discovered), and the Digicon boot rule (the Digicon masts' destinations stored disabled: disable_digicon).
"""
from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

from . import paths, tables
from .tables_sections import TablesBuildError, sub

DISCOVERED = paths.LAYOUT_DATA / "schematic" / "discovered_sml.xml"
DISCOVERED_ROOT = "discovered-sml"
DISCOVERED_PROLOG = b'<?xml version="1.0" encoding="UTF-8"?>\n'


def discovered_from_store(store: ET.Element) -> ET.Element:
    """The discovered document of a discovery Store's root: its <signalmastlogic> elements in the order stored, and a
    <mastproperties mast="user name"> holding each mast's <properties> (discovery sets intermediateSignal).
    TablesBuildError when the Store holds no Signal Mast Logic or a logic with no source."""
    logics = tables.mast_logics(store)
    if not logics:
        raise TablesBuildError("the Store holds no Signal Mast Logic: discovery found nothing, or this is not its Store")
    out = ET.Element(DISCOVERED_ROOT)
    for m in tables.masts(store):
        props = m.find("properties")
        if props is not None:
            box = sub(out, "mastproperties", mast=tables.user_name(m) or tables.system_name(m))
            box.append(copy.deepcopy(props))
    for logic in logics:
        if not logic.get("source"):
            raise TablesBuildError("a stored <signalmastlogic> has no source attribute")
        out.append(copy.deepcopy(logic))
    ET.indent(out, space="  ")
    return out


def write_discovered(doc: ET.Element, path: Path = DISCOVERED) -> bool:
    """Write the discovered document (read_discovered reads it back); True when the bytes changed."""
    read_discovered_root(doc, paths.rel(path))       # never write what cannot be read back
    return tables.Tables(root=doc, path=path, prolog=DISCOVERED_PROLOG, epilog=b"\n").save(path)


def read_discovered(path: Path = DISCOVERED) -> tuple[list[ET.Element], dict[str, ET.Element]]:
    """([<signalmastlogic>, ...], {mast user name: <properties>}) of the discovered file."""
    try:
        root = tables.read(path)
    except OSError as exc:
        raise TablesBuildError(f"{paths.rel(path)}: cannot read it ({exc.strerror}); run "
                               "jmri/layouts/hart/scripts/run_sml_discover.sh") from exc
    except ET.ParseError as exc:
        raise TablesBuildError(f"{paths.rel(path)}: not XML ({exc})") from exc
    return read_discovered_root(root, paths.rel(path))


def read_discovered_root(root: ET.Element, where: str) -> tuple[list[ET.Element], dict[str, ET.Element]]:
    if root.tag != DISCOVERED_ROOT:
        raise TablesBuildError(f"{where}: the root is <{root.tag}>, not <{DISCOVERED_ROOT}>")
    logics, props, bad = [], {}, []
    sources = set()
    for el in tables.elements(root):
        if el.tag == "signalmastlogic":
            src = el.get("source") or ""
            if not src or src in sources:
                bad.append(f"a logic with source {src!r} (empty or given twice)")
            sources.add(src)
            logics.append(el)
        elif el.tag == "mastproperties":
            kids = list(tables.elements(el))
            mast = el.get("mast") or ""
            if not mast or mast in props or len(kids) != 1 or kids[0].tag != "properties":
                bad.append(f"mastproperties {mast!r}: needs a mast, given once, and exactly one <properties>")
                continue
            props[mast] = kids[0]
        else:
            bad.append(f"<{el.tag}> is neither signalmastlogic nor mastproperties")
    if bad:
        raise TablesBuildError(f"{where}: " + "; ".join(bad))
    return logics, props


def merge_discovered(root: ET.Element, logics: list[ET.Element], props: Mapping[str, ET.Element]) -> None:
    """Put the discovered logic into `root`'s <signalmastlogics> after its settings, and each mast's properties into
    that mast before <unlit>. TablesBuildError when a logic or a property names a mast the tables do not hold (the
    masts changed since discovery ran: run it again), or the tables hold logic already."""
    box = root.find("signalmastlogics")
    if box is None or tables.mast_logics(root):
        raise TablesBuildError("the tables have no <signalmastlogics>, or hold logic already")
    masts = {n: m for m in tables.masts(root) for n in (tables.user_name(m), tables.system_name(m)) if n}
    named = sorted({logic.get("source") or "" for logic in logics} |
                   {d.get("destination") or "" for logic in logics for d in logic.findall("destinationMast")})
    gone = [n for n in named if n not in masts] + [m for m in props if m not in masts]
    if gone:
        raise TablesBuildError(f"{paths.rel(DISCOVERED)} names masts the tables do not hold ({', '.join(gone[:8])}): "
                               "run jmri/layouts/hart/scripts/run_sml_discover.sh again")
    for logic in logics:
        box.append(copy.deepcopy(logic))
    for mast, p in props.items():
        el = masts[mast]
        if el.find("properties") is not None:
            raise TablesBuildError(f"mast {mast!r} has properties already")
        unlit = el.find("unlit")
        el.insert(list(el).index(unlit) if unlit is not None else len(el), copy.deepcopy(p))


def missing_logic(root: ET.Element) -> list[str]:
    """The masts of `root` without the discovered logic the rule expects: a head mast (<signalmast>) that is no
    logic's source, or a virtual mast (a buffer-stop destination) that no logic names. Stock discovery gives every
    one of them logic (data/schematic/discovered_sml.xml), so a gap means a mast added or renamed since
    discovery ran."""
    sources = {logic.get("source") for logic in tables.mast_logics(root)}
    named = sources | {d.get("destination") for logic in tables.mast_logics(root)
                       for d in logic.findall("destinationMast")}
    out = []
    for m in tables.masts(root):
        user = tables.user_name(m) or tables.system_name(m)
        if (m.tag == "signalmast" and user not in sources) or (m.tag != "signalmast" and user not in named):
            out.append(user)
    return out


# ---------------------------------------------------------------- Digicon boot rule

_LCOS_HEAD = re.compile(r"\(IH\d+\)")


def digicon_masts(root: ET.Element, wiring: Path = paths.WIRING) -> set[str]:
    """The masts signal_coordinator.py takes over: with a wired head in wiring.csv (hartlib.wiring.digicon_rows) and
    standing on wired LCOS heads (IH and digits) in `root`. A mast wiring.csv names that is on internal heads is never
    taken over."""
    from . import wiring as wiring_source     # here, not at the top: wiring imports railroad_facts
    from .railroad_facts import FactsError
    try:
        planned = {r["mast_user_name"] for r in wiring_source.digicon_rows(wiring)}
    except FactsError as exc:
        raise TablesBuildError(str(exc)) from exc
    wired = {tables.user_name(m) for m in tables.masts(root) if _LCOS_HEAD.search(tables.system_name(m))}
    return planned & wired


def disable_digicon(root: ET.Element, masts: set[str]) -> tuple[int, int]:
    """Set <enabled>no</enabled> on every destination of the logic whose source is one of `masts`, so they boot
    disabled until signal_coordinator.py takes control. (flipped, already disabled)."""
    flipped = already = 0
    for logic in tables.mast_logics(root):
        if logic.get("source") not in masts:
            continue
        for dest in logic.findall("destinationMast"):
            en = dest.find("enabled")
            if en is None:
                raise TablesBuildError(f"logic {logic.get('source')} -> {dest.get('destination')} has no <enabled>")
            if en.text == "no":
                already += 1
            else:
                en.text = "no"
                flipped += 1
    return flipped, already


def enabled_digicon(root: ET.Element, masts: set[str]) -> list[tuple[str, str]]:
    """(source, destination) of each Digicon destination still enabled."""
    return [(logic.get("source") or "", d.get("destination") or "") for logic in tables.mast_logics(root)
            if logic.get("source") in masts for d in logic.findall("destinationMast")
            if (d.findtext("enabled") or "") != "no"]
