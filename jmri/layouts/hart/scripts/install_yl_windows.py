"""Merge YL turnouts/routes into Windows JMRI tables + add sync startup script."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

HOME = Path.home()
TABLES = HOME / "JMRI/My_JMRI_Railroad.jmri/tables.xml"
PROF = HOME / "JMRI/My_JMRI_Railroad.jmri/profile/profile.xml"
FRAG = HOME / "hart/jmri/layouts/hart/scripts/yl_tables_fragment.xml"
SYNC = HOME / "hart/jmri/layouts/hart/scripts/sync_yard_ladder_buttons.py"
SYNC_HOME = "home:hart/jmri/layouts/hart/scripts/sync_yard_ladder_buttons.py"


def merge_tables() -> None:
    frag = ET.parse(FRAG).getroot()
    tree = ET.parse(TABLES)
    root = tree.getroot()
    it = None
    for el in root.findall("turnouts"):
        if "InternalTurnoutManager" in (el.get("class") or ""):
            it = el
            break
    if it is None:
        raise SystemExit("no InternalTurnoutManager in tables")
    for t in list(it.findall("turnout")):
        sn = t.findtext("systemName") or ""
        if sn.startswith("IT:HART:YL:"):
            it.remove(t)
    routes = root.find("routes")
    if routes is None:
        raise SystemExit("no routes element")
    for r in list(routes.findall("route")):
        sn = r.findtext("systemName") or ""
        if sn.startswith("IO:AUTO:02"):
            routes.remove(r)
    n_to = n_rt = 0
    for child in frag:
        if child.tag == "turnout":
            it.append(child)
            n_to += 1
        elif child.tag == "route":
            routes.append(child)
            n_rt += 1
    tree.write(TABLES, encoding="UTF-8", xml_declaration=True)
    print(f"tables: +{n_to} YL turnouts, +{n_rt} routes -> {TABLES}")


def patch_profile() -> None:
    if not SYNC.is_file():
        raise SystemExit(f"missing sync script: {SYNC}")
    txt = PROF.read_text(encoding="utf-8")
    if "sync_yard_ladder_buttons.py" in txt:
        print("profile: sync script already present")
        return
    insert = (
        '        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" '
        f'enabled="yes" name="{SYNC_HOME}" type="ScriptFile"/>\n'
    )
    key = "apply_maintain_mqtt.py"
    idx = txt.find(key)
    if idx < 0:
        raise SystemExit("apply_maintain_mqtt.py not in profile")
    end = txt.find("/>", idx)
    if end < 0:
        raise SystemExit("bad profile perform tag")
    end += 2
    txt = txt[:end] + "\n" + insert + txt[end:]
    PROF.write_text(txt, encoding="utf-8")
    print(f"profile: inserted {SYNC_HOME}")


if __name__ == "__main__":
    merge_tables()
    patch_profile()
