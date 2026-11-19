#!/usr/bin/env python3
"""Bring the staging signal heads and masts in tables.xml in line with staging_masts.csv (build_staging_masts.py).

    python3 tools/schematic/sync_staging_signals.py           # edit jmri/layouts/hart/output/tables.xml
    python3 tools/schematic/sync_staging_signals.py --check   # exit 1 if tables.xml differs from the file

Staging masts are the masts whose user name is "Mast " and a number under 100 (main and upper masts are 101 and up,
or a line code and a milepost: hartlib.level_devices.LEVEL_USER), and their heads. For each staging mast in the file:
a SignalHeadSignalMast over VirtualSignalHeads (the heads' user names from head_system_names), or a VirtualSignalMast
for IF$vsm; an element whose system name, user name and class already match is left as it is (its comment, aspects
and the rest carry over). Every other staging mast and every staging head no mast of the file uses goes, with the
Signal Mast Logic that names any mast that went or changed (the logic whose source it is, each destination naming
it, and a logic left with none): stock discovery in a sandbox derives it again from the panel the LE build draws.
Run with JMRI closed (a Store would undo it), then make panels.
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft  # noqa: E402,F401  puts hartlib on the path
import le_tables  # noqa: E402  HEAD_CLASS, MAST_CLASS, place
import staging_device_map as sdm  # noqa: E402
from hartlib import level_masts, paths, tables  # noqa: E402

VSM_CLASS = "jmri.implementation.configurexml.VirtualSignalMastXml"
STAGING_MAST = re.compile(r"Mast \d{1,2}(?:[LR][A-C]?)?")


def is_staging_mast(user: str) -> bool:
    return bool(STAGING_MAST.fullmatch(user or ""))


def want_masts(path: Path = sdm.MASTS) -> list[dict]:
    return sdm.read_rows(path, level_masts.FIELDS)


def head_comments(device_map: Path = sdm.DEVICE_MAP) -> dict:
    return {r["system_name"]: " | ".join(x for x in (r["comment"], r["notes"]) if x)
            for r in sdm.read_rows(device_map, sdm.bdm.COLUMNS) if r["layer"] == "head"}


def sync(root: ET.Element, rows: list[dict], comments: dict) -> dict:
    """Edit tables `root` in place; returns counts by what changed."""
    heads_el, masts_el = root.find("signalheads"), root.find("signalmasts")
    if heads_el is None or masts_el is None:
        raise SystemExit("tables.xml has no signalheads or signalmasts section")
    counts = dict.fromkeys(("masts kept", "masts added", "masts removed", "heads added", "heads removed",
                            "logics removed", "destinations removed"), 0)
    have = {tables.user_name(m): m for m in tables.masts(root) if is_staging_mast(tables.user_name(m))}
    want = {r["mast"]: r for r in rows}
    used_heads = {h for r in rows for h in level_masts.mast_heads(r["system_name"])}
    old_heads = {h for m in have.values() for h in level_masts.mast_heads(tables.system_name(m))}
    old_heads |= {tables.system_name(h) for h in tables.signal_heads(root)
                  if re.fullmatch(r"Head \d{1,2}[LR]?[A-C]?(?: (?:Top|Bottom))?", tables.user_name(h) or "")}
    gone = set()
    for user, el in have.items():
        r = want.get(user)
        cls = VSM_CLASS if (r and r["system_name"].startswith("IF$vsm:")) else le_tables.MAST_CLASS
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
                    raise SystemExit(f"head {h} is {tables.user_name(head_by_sys[h])!r} in tables.xml, "
                                     f"{user!r} in {sdm.MASTS.name}")
                continue
            el = ET.Element("signalhead", {"class": le_tables.HEAD_CLASS})
            ET.SubElement(el, "systemName").text = h
            ET.SubElement(el, "userName").text = user
            ET.SubElement(el, "comment").text = comments.get(h, "")
            new_heads.append(el)
            head_by_sys[h] = el
            counts["heads added"] += 1
        if r["mast"] in kept:
            continue
        vsm = r["system_name"].startswith("IF$vsm:")
        el = ET.Element("virtualsignalmast" if vsm else "signalmast", {"class": VSM_CLASS if vsm else le_tables.MAST_CLASS})
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
    ap.add_argument("--check", action="store_true", help="exit 1 if tables.xml differs from staging_masts.csv")
    ap.add_argument("--tables", type=Path, default=paths.TABLES_XML)
    args = ap.parse_args(argv)
    t = tables.load(args.tables)
    counts = sync(t.root, want_masts(), head_comments())
    changed = {k: v for k, v in counts.items() if v and k != "masts kept"}
    if args.check:
        if changed:
            print(f"{paths.rel(args.tables)} differs from {sdm.MASTS.name}: {changed}; run "
                  "tools/schematic/sync_staging_signals.py", file=sys.stderr)
            return 1
        print(f"ok: staging signals in {paths.rel(args.tables)} follow {sdm.MASTS.name}")
        return 0
    if tables.jmri_running():
        print("JMRI is running: quit PanelPro and CATS first (a Store would undo this)", file=sys.stderr)
        return 2
    t.save()
    print(", ".join(f"{v} {k}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
