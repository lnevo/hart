#!/usr/bin/env python3
"""Bring the signal heads and masts in tables.xml in line with masts.csv (build_masts.py), every level alike.

    python3 tools/schematic/sync_signals.py --check                 # exit 1 if tables.xml differs
    python3 tools/schematic/sync_signals.py --tables OTHER.xml      # edit another tables file

tables.xml is generated since R9c (ADR-029): tools/schematic/build_tables.py writes its heads and masts from
the device master (staging's beans) and the Layout Editor build (main and upper's), so this script only checks it and
refuses to write it (hartlib.tables_build.refuse_generated).

The masts it holds are the masts whose user name is a mast name of any level (hartlib.level_masts.MAST_USER:
"Mast 2L", "Mast 67", Mast <main or upper switch><L|R>, "Mast A83"), and their heads (level_masts.HEAD_USER). For each such mast in the
file: a SignalHeadSignalMast over VirtualSignalHeads (the heads' user names from head_system_names), or a
VirtualSignalMast for IF$vsm; an element whose system name, user name and class already match is left as it is (its
comment, aspects and the rest carry over). Every other such mast and every such head no mast of the file uses goes,
with the Signal Mast Logic that names any mast that went or changed (the logic whose source it is, each destination
naming it, and a logic left with none): stock discovery in a sandbox derives it again from the panel the LE build
draws. A new head's comment is its device row's (comment and notes), read through hartlib.devices. Run with JMRI
closed (a Store would undo it).
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft  # noqa: E402,F401  puts hartlib on the path
import le_tables  # noqa: E402  place
from hartlib import devices, level_masts, paths, railroad, tables, tables_build  # noqa: E402

VSM_CLASS = tables_build.VIRTUAL_MAST_CLASS


class SyncError(Exception):
    """tables.xml cannot follow masts.csv as it stands (a missing section, a head under another user name); the
    message names it. main() prints it and exits 1."""


def is_mast(user: str) -> bool:
    """A mast of the file's kind: its user name is a mast name of any level (level_masts.MAST_USER)."""
    return bool(level_masts.MAST_USER.fullmatch(user or ""))


def is_head(user: str) -> bool:
    return bool(level_masts.HEAD_USER.fullmatch(user or ""))


def want_masts(path: Path = level_masts.PATH) -> list[dict]:
    """masts.csv's rows, every level (hartlib.level_masts.read checks the file)."""
    return level_masts.read(path)


def head_comments(files: devices.Files | None = None) -> dict:
    """{head JMRI name: its device row's comment and notes} of every level's head rows (hartlib.devices)."""
    rows = devices.device_map_rows([r.cells() for r in devices.load(files)],
                                   tuple(str(lv) for lv in level_masts.LEVELS))
    return {r["jmri_name"]: " | ".join(x for x in (r["comment"], r["notes"]) if x)
            for r in rows if r["layer"] == "head"}


def sync(root: ET.Element, rows: list[dict], comments: dict) -> dict:
    """Edit tables `root` in place; returns counts by what changed. SyncError when the file cannot follow `rows`."""
    heads_el, masts_el = root.find("signalheads"), root.find("signalmasts")
    if heads_el is None or masts_el is None:
        raise SyncError("tables.xml has no signalheads or signalmasts section")
    counts = dict.fromkeys(("masts kept", "masts added", "masts removed", "heads added", "heads removed",
                            "logics removed", "destinations removed"), 0)
    have = {tables.user_name(m): m for m in tables.masts(root) if is_mast(tables.user_name(m))}
    want = {r["mast"]: r for r in rows}
    used_heads = {h for r in rows for h in level_masts.mast_heads(r["system_name"])}
    old_heads = {h for m in have.values() for h in level_masts.mast_heads(tables.system_name(m))}
    old_heads |= {tables.system_name(h) for h in tables.signal_heads(root) if is_head(tables.user_name(h))}
    gone = set()
    for user, el in have.items():
        r = want.get(user)
        cls = VSM_CLASS if (r and r["system_name"].startswith("IF$vsm:")) else tables_build.MAST_CLASS
        if r and tables.system_name(el) == r["system_name"] and el.get("class") == cls:
            counts["masts kept"] += 1
            continue
        gone |= {user, tables.system_name(el)}
        for parent in root.iter():
            if el in list(parent):
                tables.remove_child(parent, el)
                break
        counts["masts removed"] += 1
    head_by_sys = {tables.system_name(h): h for h in tables.signal_heads(root)}
    for h in sorted(old_heads - used_heads):
        if h in head_by_sys:
            tables.remove_child(heads_el, head_by_sys.pop(h))
            counts["heads removed"] += 1
    new_heads, new_masts, new_vsm = [], [], []
    kept = {u for u in have if u not in gone}
    for r in rows:
        pairs = [tuple(p.split("=", 1)) for p in r["head_system_names"].split(";") if p]
        for h, user in pairs:
            if h in head_by_sys:
                if tables.user_name(head_by_sys[h]) != user:
                    raise SyncError(f"head {h} is {tables.user_name(head_by_sys[h])!r} in tables.xml, "
                                    f"{user!r} in {level_masts.PATH.name}")
                continue
            el = ET.Element("signalhead", {"class": tables_build.HEAD_CLASS})
            ET.SubElement(el, "systemName").text = h
            ET.SubElement(el, "userName").text = user
            ET.SubElement(el, "comment").text = comments.get(h, "")
            new_heads.append(el)
            head_by_sys[h] = el
            counts["heads added"] += 1
        if r["mast"] in kept:
            continue
        vsm = r["system_name"].startswith("IF$vsm:")
        el = ET.Element("virtualsignalmast" if vsm else "signalmast", {"class": VSM_CLASS if vsm else tables_build.MAST_CLASS})
        ET.SubElement(el, "systemName").text = r["system_name"]
        ET.SubElement(el, "userName").text = r["mast"]
        ET.SubElement(el, "comment").text = " | ".join(x for x in (r["cp"], f"Switch {r['switch']}" if r["switch"] else "") if x)
        ET.SubElement(el, "unlit", {"allowed": "yes" if vsm else "no"})
        (new_vsm if vsm else new_masts).append(el)
        counts["masts added"] += 1
    if new_heads:
        le_tables.place(heads_el, new_heads, 2)
    if new_masts:
        le_tables.place(masts_el, new_masts, 2)
    if new_vsm:
        box = root.find("signalmasts")
        le_tables.place(box, new_vsm, 2)
    # Signal Mast Logic naming a mast that went or changed
    for box in root.findall("signalmastlogics"):
        for logic in list(box.findall("signalmastlogic")):
            source = tables.text(logic, "sourceSignalMast") or (logic.get("source") or "").strip()
            if source in gone:
                tables.remove_child(box, logic)
                counts["logics removed"] += 1
                continue
            drop = [d for d in logic.findall("destinationMast") if tables.names_any(d, gone)]
            for d in drop:
                tables.remove_child(logic, d)
                counts["destinations removed"] += 1
            if drop and logic.find("destinationMast") is None:
                tables.remove_child(box, logic)
                counts["logics removed"] += 1
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if tables.xml differs from masts.csv")
    ap.add_argument("--tables", type=Path, default=paths.TABLES_XML)
    args = ap.parse_args(argv)
    t = tables.load(args.tables)
    try:
        rows, comments = want_masts(), head_comments()
    except railroad.FactsError as exc:          # level_masts and hartlib.devices (DevicesError) name the file and line
        print(f"{Path(__file__).name}: {exc}", file=sys.stderr)
        return 2
    try:
        counts = sync(t.root, rows, comments)
    except SyncError as exc:
        print(exc, file=sys.stderr)
        return 1
    changed = {k: v for k, v in counts.items() if v and k != "masts kept"}
    if args.check:
        if changed:
            print(f"{paths.rel(args.tables)} differs from {level_masts.PATH.name}: {changed}; tables.xml is generated: "
                  "run tools/schematic/build_masts.py, then tools/schematic/build_tables.py", file=sys.stderr)
            return 1
        print(f"ok: every level's signals in {paths.rel(args.tables)} follow {level_masts.PATH.name} "
              f"({counts['masts kept']} masts)")
        return 0
    try:
        tables_build.refuse_generated(args.tables, Path(__file__).name)
    except tables_build.GeneratedTablesError as exc:
        print(exc, file=sys.stderr)
        return 1
    try:
        running = tables.jmri_running()
    except tables.JmriCheckError as exc:
        print(f"{exc}; {paths.rel(args.tables)} not written", file=sys.stderr)
        return 2
    if running:
        print("JMRI is running: quit PanelPro and CATS first (a Store would undo this)", file=sys.stderr)
        return 2
    t.save()
    print(", ".join(f"{v} {k}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
