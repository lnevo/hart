#!/usr/bin/env python3
"""Rename public labels and write meaningful JMRI comments.

- Main West Brick–Plane → Brick-Plane
- OS n (CP) → OS n, CP goes in the comment
- Blocks, occupancy/FB sensors, CTC internals, and plant turnouts get comments
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_public_names import RenameEntry, apply_renames_to_text

RENAMES = [
    RenameEntry("block", "Main West Brick–Plane", "Brick-Plane"),
    RenameEntry("block", "Main West Brick-Plane", "Brick-Plane"),
    RenameEntry("block", "OS 111a (East End)", "OS 111a"),
    RenameEntry("block", "OS 111b (East End)", "OS 111b"),
    RenameEntry("block", "OS 107 (East End)", "OS 107"),
    RenameEntry("block", "OS 108 (East End)", "OS 108"),
    RenameEntry("block", "OS 109 (East End)", "OS 109"),
    RenameEntry("block", "OS 110 (East End)", "OS 110"),
    RenameEntry("block", "OS 112 (East End)", "OS 112"),
    RenameEntry("block", "OS 113a (Princess)", "OS 113a"),
    RenameEntry("block", "OS 113b (Princess)", "OS 113b"),
    RenameEntry("block", "OS 114 (Princess)", "OS 114"),
    RenameEntry("block", "OS 115 (Princess)", "OS 115"),
    RenameEntry("block", "OS 103 (South Yard)", "OS 103"),
    RenameEntry("block", "OS 104 (South Yard)", "OS 104"),
    RenameEntry("block", "OS 105 (South Yard)", "OS 105"),
    RenameEntry("block", "OS 106 (South Yard)", "OS 106"),
    RenameEntry("block", "OS 117b (Barn)", "OS 117b"),
    RenameEntry("block", "OS 117 (Barn)", "OS 117"),
    RenameEntry("block", "OS 102 (Plane)", "OS 102"),
    RenameEntry("block", "OS 100 (Brick)", "OS 100"),
    RenameEntry("block", "OS 101 (Brick)", "OS 101"),
]
RENAMES.sort(key=lambda item: len(item.current), reverse=True)

BEAN_RE = re.compile(
    r"(<(sensor|turnout|block|layoutblock|memory|signalhead|signalmast|virtualsignalmast|route|LogixNG|ConditionalNG)\b[^>]*>)(.*?)(</\2>)",
    re.S,
)

CTC_SWITCH = {
    "1": "Switch 101",
    "2": "Switch 101 signals",
    "3": "Switch 100",
    "4": "Switch 100 signals",
    "5": "Switch 102",
    "6": "Switch 102 signals",
    "7": "Switch 117",
    "8": "Switch 117 signals",
    "9": "Switch 116",
    "10": "Switch 116 lock",
    "11": "Switch 103",
    "12": "Switch 103 lock",
    "17": "Switch 111",
    "18": "Switch 111 signals",
    "21": "Switch 110",
    "22": "Switch 110 lock",
    "23": "Switch 112",
    "24": "Switch 112 signals",
    "25": "Switch 113",
    "26": "Switch 113 signals",
    "27": "Switch 114",
    "28": "Switch 114 signals",
    "29": "Switch 115",
    "30": "Switch 115 signals",
}

CTC_SUFFIX = {
    "LEVER": "switch lever (ACTIVE=Normal, INACTIVE=Reverse)",
    "LOCKTOGGLE": "Local/Locked (ACTIVE=Local)",
    "CB": "code button",
    "LDGK": "left signal indicator lamp",
    "NGK": "normal signal indicator lamp",
    "RDGK": "right signal indicator lamp",
    "LDGL": "left signal lever",
    "NGL": "normal signal lever",
    "RDGL": "right signal lever",
    "SWNI": "switch normal indicator",
    "SWRI": "switch reverse indicator",
    "CALLON": "call-on toggle",
    "UNLOCKEDINDICATOR": "unlocked indicator",
}

CTC_SUFFIX_SHORT = {
    "LEVER": "lever",
    "LOCKTOGGLE": "local",
    "CB": "code",
    "LDGK": "L lamp",
    "NGK": "N lamp",
    "RDGK": "R lamp",
    "LDGL": "L lever",
    "NGL": "N lever",
    "RDGL": "R lever",
    "SWNI": "N ind",
    "SWRI": "R ind",
    "CALLON": "call-on",
    "UNLOCKEDINDICATOR": "unlocked",
}

SPECIAL_SENSOR_USERNAMES = {
    "M2S201": "unused Block 2-2",
    "M2S307": "unused Block 3-8",
    "IS:DEBUGCTC": "CTC debug",
    "IS:FLEETING": "CTC fleeting",
    "IS:RELOADCTC": "CTC reload",
    "IS:PRECONDITIONING_ENABLED": "Dispatcher preconditioning",
    "ISCLOCKRUNNING": "Clock running",
    "MS01.01.02.00.00.FF.00.EA;01.01.02.00.00.FF.00.EB": "OLCB leftover 114",
    "MS01.01.02.00.00.FF.00.EC;01.01.02.00.00.FF.00.ED": "OLCB leftover 115",
}

MTT_USERNAMES = {
    "MTT100": "Switch 100 alias",
    "MTT111": "Switch 111 alias",
    "MTT113": "Switch 113 alias",
    "MTT114": "Switch 114 alias",
    "MTT115": "Switch 115 alias",
}

MEMORY_USERNAMES = {
    "IMCURRENTTIME": "Current time",
    "IMIS:ISMEM:versionNo": "Dispatcher version",
    "IMRATEFACTOR": "Clock rate",
}

LOGIXNG_USERNAMES = {
    "IQ:AUTO:0001": "Hide windows on start",
    "IQC:AUTO:0001": "Hide USS CTC Editor",
    "IQC:AUTO:0002": "Hide Dispatcher System",
    "IQC:AUTO:0003": "Hide WiThrottle",
    "IQC:AUTO:0004": "Keep HART Railroad",
}

BLOCK_COMMENTS = {
    "Brick-Plane": "Main West between Brick and Plane; occupancy Block 4-6 / M2S405; stop",
    "Main West": "Main west of Brick toward East End; occupancy Block 2-1 / M2S200; stop",
    "Main East": "Main east of East End; occupancy Block 2-3 / M2S202; stop",
    "West Main Ext": "Main West stub west of 111; occupancy Block 1-8 / M2S107; stop",
    "East Main Ext": "Main east of Plane toward Barn; occupancy Block 4-7 / M2S406; stop",
    "East Lead": "South Yard lead east of 110/112 toward Princess; occupancy Block 1-7 / M2S106; stop",
    "McKees Rocks": "Princess balloon, McKees Rocks; occupancy Block 1-1 / M2S100; stop",
    "McKeesport": "Princess balloon, McKeesport; occupancy Block 1-2 / M2S101; stop",
    "OS 100": "Brick CP, Switch 100; occupancy Block 4-2 / M2S401",
    "OS 101": "Brick CP, Switch 101; occupancy Block 4-1 / M2S400",
    "OS 102": "Plane CP, Switch 102; occupancy Block 4-5 / M2S404",
    "OS 103": "South Yard, Switch 103; occupancy Block 3-2 / M2S301",
    "OS 104": "South Yard, Switch 104; occupancy Block 3-3 / M2S302",
    "OS 105": "South Yard, Switch 105; occupancy Block 3-5 / M2S304",
    "OS 106": "South Yard, Switch 106; occupancy Block 3-7 / M2S306",
    "OS 107": "East End, Switch 107; occupancy Block 12-1 / M2S1200",
    "OS 108": "East End, Switch 108; occupancy Block 12-3 / M2S1202",
    "OS 109": "East End, Switch 109; occupancy Block 12-5 / M2S1204",
    "OS 110": "East End, Switch 110; occupancy Block 12-7 / M2S1206",
    "OS 111a": "East End crossover 111 north/west leg; occupancy Block 12-4 / M2S1203",
    "OS 111b": "East End crossover 111 south/east leg; occupancy Block 12-6 / M2S1205",
    "OS 112": "East End, Switch 112; occupancy Block 12-8 / M2S1207",
    "OS 113a": "Princess crossover 113 south/yard leg; occupancy Block 1-6 / M2S105",
    "OS 113b": "Princess crossover 113 north/main leg; occupancy Block 1-5 / M2S104",
    "OS 114": "Princess, Switch 114 (same detector as K-2); occupancy Block 1-3 / M2S102",
    "OS 115": "Princess, Switch 115 (same detector as K-1); occupancy Block 1-4 / M2S103",
    "OS 116": "Hand-throw west of South Yard 103; occupancy Block 3-1 / M2S300",
    "OS 117": "Barn CP crossover north/west leg; occupancy Block 13-3 / M2S1302",
    "OS 117b": "Barn CP crossover south/east leg; occupancy Block 13-4 / M2S1303",
    "OS 118": "Hand-throw Engine House lead; occupancy Block 13-2 / M2S1301",
    "OS 119": "Hand-throw Engine House; occupancy Block 13-8 / M2S1307",
    "Scale": "Plane diverging lead to Barn; occupancy Block 4-8 / M2S407; stop",
    "Barn": "Lead 117 to 116; occupancy Block 13-1 / M2S1300; stop",
    "S-1": "Run-through east of 103; occupancy Block 2-8 / M2S207; stop",
    "S-2": "South Yard body; occupancy Block 2-7 / M2S206; stop",
    "S-3": "South Yard body; occupancy Block 2-6 / M2S205; stop",
    "S-4": "South Yard body; occupancy Block 2-5 / M2S204; stop",
    "S-5": "South Yard body; occupancy Block 2-4 / M2S203; stop",
    "W-1": "Brick yard W-1; access Switch 101 only; occupancy Block 4-4 / M2S403; stop",
    "W-2": "Brick yard W-2; access Switch 101 only; occupancy Block 4-3 / M2S402; stop",
    "EH-1": "Top house track; occupancy Block 13-5 / M2S1304; stop",
    "EH-2": "Middle house track; occupancy Block 13-6 / M2S1305; stop",
    "EH-3": "Bottom house track; occupancy Block 13-7 / M2S1306; stop",
    "K-1": "Princess stub east of Switch 115; shares Block 1-4 with OS 115; occupancy Block 1-4 / M2S103; stop",
    "K-2": "Princess stub east of Switch 114; shares Block 1-3 with OS 114; occupancy Block 1-3 / M2S102; stop",
}

TURNOUT_COMMENTS = {
    "Switch 100": "Brick CP; MQTT M2T408; FB Switch 4-1; rests Thrown",
    "Switch 101": "Brick CP, West Yard access; MQTT M2T409; FB Switch 4-2",
    "Switch 102": "Plane CP; MQTT M2T410; FB Switch 4-3",
    "Switch 103": "South Yard ladder; MQTT M2T308; FB Switch 3-1; CTC local",
    "Switch 104": "South Yard; MQTT M2T309; FB Switch 3-2; hand-throw",
    "Switch 105": "South Yard; MQTT M2T310; FB Switch 3-3; hand-throw",
    "Switch 106": "South Yard; MQTT M2T311; FB Switch 3-4; hand-throw",
    "Switch 107": "East End; MQTT M2T1208; FB Switch 12-1",
    "Switch 108": "East End; MQTT M2T1209; FB Switch 12-2",
    "Switch 109": "East End; MQTT M2T1210; FB Switch 12-3",
    "Switch 110": "East End ladder; MQTT M2T1211; FB Switch 12-4; CTC local",
    "Switch 111": "East End crossover 111a/111b; MQTT M2T1212; FB Switch 12-5",
    "Switch 112": "East End; MQTT M2T1213; FB Switch 12-6; rests Thrown",
    "Switch 113": "Princess crossover 113a/113b; MQTT M2T108; FB Switch 1-1",
    "Switch 114": "Princess; MQTT M2T109; FB Switch 1-2; rests Thrown",
    "Switch 115": "Princess; MQTT M2T110; FB Switch 1-3; rests Thrown",
    "Switch 116": "Hand-throw west of South Yard; MQTT M2T411; CTC local",
    "Switch 117": "Barn CP crossover 117/117b; MQTT M2T1308; field hand-throw",
    "Switch 118": "Hand-throw Engine House lead; MQTT M2T1309",
    "Switch 119": "Hand-throw Engine House; MQTT M2T1310",
}

OCC_SENSOR = {
    "Block 1-1": "Occupancy McKees Rocks; MQTT M2S100",
    "Block 1-2": "Occupancy McKeesport; MQTT M2S101",
    "Block 1-3": "Occupancy OS 114 / K-2; MQTT M2S102",
    "Block 1-4": "Occupancy OS 115 / K-1; MQTT M2S103",
    "Block 1-5": "Occupancy OS 113b; MQTT M2S104",
    "Block 1-6": "Occupancy OS 113a; MQTT M2S105",
    "Block 1-7": "Occupancy East Lead; MQTT M2S106",
    "Block 1-8": "Occupancy West Main Ext; MQTT M2S107",
    "Block 2-1": "Occupancy Main West; MQTT M2S200",
    "Block 2-3": "Occupancy Main East; MQTT M2S202",
    "Block 2-4": "Occupancy S-5; MQTT M2S203",
    "Block 2-5": "Occupancy S-4; MQTT M2S204",
    "Block 2-6": "Occupancy S-3; MQTT M2S205",
    "Block 2-7": "Occupancy S-2; MQTT M2S206",
    "Block 2-8": "Occupancy S-1; MQTT M2S207",
    "Block 3-1": "Occupancy OS 116; MQTT M2S300",
    "Block 3-2": "Occupancy OS 103; MQTT M2S301",
    "Block 3-3": "Occupancy OS 104; MQTT M2S302",
    "Block 3-5": "Occupancy OS 105; MQTT M2S304",
    "Block 3-7": "Occupancy OS 106; MQTT M2S306",
    "Block 4-1": "Occupancy OS 101; MQTT M2S400",
    "Block 4-2": "Occupancy OS 100; MQTT M2S401",
    "Block 4-3": "Occupancy W-2; MQTT M2S402",
    "Block 4-4": "Occupancy W-1; MQTT M2S403",
    "Block 4-5": "Occupancy OS 102; MQTT M2S404",
    "Block 4-6": "Occupancy Brick-Plane; MQTT M2S405",
    "Block 4-7": "Occupancy East Main Ext; MQTT M2S406",
    "Block 4-8": "Occupancy Scale; MQTT M2S407",
    "Block 12-1": "Occupancy OS 107; MQTT M2S1200",
    "Block 12-3": "Occupancy OS 108; MQTT M2S1202",
    "Block 12-4": "Occupancy OS 111a; MQTT M2S1203",
    "Block 12-5": "Occupancy OS 109; MQTT M2S1204",
    "Block 12-6": "Occupancy OS 111b; MQTT M2S1205",
    "Block 12-7": "Occupancy OS 110; MQTT M2S1206",
    "Block 12-8": "Occupancy OS 112; MQTT M2S1207",
    "Block 13-1": "Occupancy Barn; MQTT M2S1300",
    "Block 13-2": "Occupancy OS 118; MQTT M2S1301",
    "Block 13-3": "Occupancy OS 117; MQTT M2S1302",
    "Block 13-4": "Occupancy OS 117b; MQTT M2S1303",
    "Block 13-5": "Occupancy EH-1; MQTT M2S1304",
    "Block 13-6": "Occupancy EH-2; MQTT M2S1305",
    "Block 13-7": "Occupancy EH-3; MQTT M2S1306",
    "Block 13-8": "Occupancy OS 119; MQTT M2S1307",
}

SKIP_DIRS = (
    "data/baselines",
    "ctc/history",
    "wiki/STATUS.md",
    "linear5/",
    "linear6/",
    "linear4/",
    "tables/checkpoints",
    "cats/panels/checkpoints",
    "authoritative/",
    "anyrail/",
    "reference/",
    "public_name_map.csv",
    "tables/tables.xml",
    "hart_blocked.xml",
)


def should_skip(path: Path) -> bool:
    rel = str(path)
    return any(part in rel for part in SKIP_DIRS)


def child_text(body: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", body, re.S)
    return match.group(1).strip() if match else ""


def set_comment(body: str, comment: str) -> str:
    escaped = (
        comment.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    if re.search(r"<comment>.*?</comment>", body, re.S):
        return re.sub(
            r"<comment>.*?</comment>",
            f"<comment>{escaped}</comment>",
            body,
            count=1,
            flags=re.S,
        )
    # JMRI block schema: comment must precede path/permissive, not follow them.
    insert = f"\n      <comment>{escaped}</comment>"
    for tag in ("userName", "systemName"):
        match = re.search(rf"</{tag}>", body)
        if match:
            return body[: match.end()] + insert + body[match.end() :]
    return body.rstrip() + insert + "\n    "


def set_user_name(body: str, user_name: str) -> str:
    if re.search(r"<userName>.*?</userName>", body, re.S):
        return body
    escaped = (
        user_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    insert = f"\n      <userName>{escaped}</userName>"
    match = re.search(r"</systemName>", body)
    if match:
        return body[: match.end()] + insert + body[match.end() :]
    return insert + body


def ctc_user_name(system_name: str) -> str | None:
    match = re.fullmatch(r"IS(\d+):([A-Z]+)", system_name)
    if not match:
        return None
    number, suffix = match.group(1), match.group(2)
    plant = CTC_SWITCH.get(number)
    role = CTC_SUFFIX_SHORT.get(suffix, suffix.lower())
    if not plant:
        return f"CTC leftover {number} {role}"
    if plant.endswith(" signals"):
        num = plant.removeprefix("Switch ").removesuffix(" signals")
        return f"CTC {num} sig {role}"
    if plant.endswith(" lock"):
        num = plant.removeprefix("Switch ").removesuffix(" lock")
        return f"CTC {num} lock {role}"
    num = plant.removeprefix("Switch ")
    return f"CTC {num} {role}"


def allocate_user_name(candidate: str, used: set[str], system_name: str) -> str:
    if candidate and candidate not in used:
        return candidate
    fallback = system_name
    if fallback not in used:
        return fallback
    n = 2
    while f"{candidate} {n}" in used:
        n += 1
    return f"{candidate} {n}"


def user_name_for(kind: str, system_name: str) -> str | None:
    if kind == "sensor":
        if system_name in SPECIAL_SENSOR_USERNAMES:
            return SPECIAL_SENSOR_USERNAMES[system_name]
        return ctc_user_name(system_name) or system_name
    if kind == "turnout":
        return MTT_USERNAMES.get(system_name)
    if kind == "memory":
        return MEMORY_USERNAMES.get(system_name, system_name)
    if kind in {"LogixNG", "ConditionalNG"}:
        return LOGIXNG_USERNAMES.get(system_name, system_name)
    if kind in {
        "block",
        "layoutblock",
        "signalhead",
        "signalmast",
        "virtualsignalmast",
        "route",
    }:
        return system_name
    return system_name


def ctc_comment(system_name: str) -> str | None:
    match = re.fullmatch(r"IS(\d+):([A-Z]+)", system_name)
    if not match:
        return None
    number, suffix = match.group(1), match.group(2)
    plant = CTC_SWITCH.get(number, f"CTC column {number}")
    role = CTC_SUFFIX.get(suffix, suffix)
    return f"USS CTC {plant}: {role}"


def comment_for(kind: str, system_name: str, user_name: str, existing: str) -> str | None:
    if kind in {"block", "layoutblock"}:
        return BLOCK_COMMENTS.get(user_name)
    if kind == "turnout":
        if user_name in TURNOUT_COMMENTS:
            return TURNOUT_COMMENTS[user_name]
        if system_name.startswith("IT:HART:YL:"):
            return f"Internal yard-ladder control {user_name}"
        if system_name.startswith("MTT"):
            alias = {
                "MTT100": "Switch 100; same FB as MQTT hardware (Switch 4-1)",
                "MTT111": "Switch 111; same FB as MQTT hardware (Switch 12-5)",
                "MTT113": "Switch 113; same FB as MQTT hardware (Switch 1-1)",
                "MTT114": "Switch 114; same FB as MQTT hardware (Switch 1-2)",
                "MTT115": "Switch 115; same FB as MQTT hardware (Switch 1-3)",
            }.get(system_name)
            if alias:
                return f"OpenLCB alias of {alias}"
            return "Unused OpenLCB leftover; not connected on the railroad"
        return None
    if kind == "sensor":
        if user_name in OCC_SENSOR:
            return OCC_SENSOR[user_name]
        if user_name.startswith("Switch ") and " FB " in user_name:
            return existing or f"Points feedback {user_name}"
        ctc = ctc_comment(system_name)
        if ctc:
            extra = f"; {existing}" if existing and "Default Reverse" in existing else ""
            return ctc + extra
        if user_name.startswith("MoveTo") and user_name.endswith("_stored"):
            station = user_name[len("MoveTo") : -len("_stored")].replace("_", " ")
            return f"Dispatcher System MoveTo for {station}"
        if user_name.startswith("MoveInProgress"):
            station = user_name[len("MoveInProgress") :].replace("_", " ")
            return f"Dispatcher System move-in-progress for {station}"
        if system_name == "IS:RELOADCTC":
            return "Reload USS CTC configuration in place"
        if system_name == "ISCLOCKRUNNING":
            return "JMRI fast-clock running"
        if system_name == "IS:PRECONDITIONING_ENABLED":
            return "Dispatcher preconditioning enable"
        if system_name == "IS:DEBUGCTC":
            return existing or "USS CTC debug"
        if system_name == "IS:FLEETING":
            return existing or "USS CTC fleeting"
        if system_name.startswith("IS:IY:AUTO:"):
            return f"Auto warrant direction {user_name or system_name}"
        if system_name.startswith("ISNX:"):
            mast = system_name.split(":", 1)[-1]
            return existing or (
                f"Entry/Exit at mast {mast}. Full interlock. "
                "CATS CTC and USS Logic off while NX is in use."
            )
        if system_name.startswith("IS:DS"):
            return existing or f"Dispatcher System {user_name or system_name}"
        if "unused LCOS" in existing:
            return existing
        if user_name.startswith("unused ") or user_name.startswith("OLCB leftover"):
            return existing or user_name
        return None
    if existing:
        return None
    if kind in {"signalmast", "virtualsignalmast"}:
        return f"Mast {user_name}" if user_name else None
    if kind == "signalhead":
        return f"Head {user_name}" if user_name else None
    if kind == "memory":
        return {
            "IMCURRENTTIME": "JMRI fast-clock time",
            "IMIS:ISMEM:versionNo": "Dispatcher System version",
            "IMRATEFACTOR": "JMRI fast-clock rate",
        }.get(system_name)
    if kind == "route":
        return f"Route {user_name}" if user_name else None
    return None


def refresh_comments(text: str) -> tuple[str, int]:
    changed = 0
    used = {
        match.group(1).strip()
        for match in re.finditer(r"<userName>(.*?)</userName>", text, re.S)
        if match.group(1).strip()
    }

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        open_tag, kind, body, close_tag = match.group(1), match.group(2), match.group(3), match.group(4)
        system_name = child_text(body, "systemName")
        user_name = child_text(body, "userName")
        existing = child_text(body, "comment")
        if not user_name:
            candidate = user_name_for(kind, system_name)
            if candidate:
                user_name = allocate_user_name(candidate, used, system_name)
                used.add(user_name)
                body = set_user_name(body, user_name)
                changed += 1
        comment = comment_for(kind, system_name, user_name, existing)
        if comment and comment != existing:
            changed += 1
            body = set_comment(body, comment)
        return open_tag + body + close_tag

    return BEAN_RE.sub(repl, text), changed


def main() -> int:
    targets = [
        ROOT / "jmri/layouts/hart/output/tables.xml",
        ROOT / "tables/new_tables.xml",
        ROOT / "jmri/layouts/hart/output/hart_prod.xml",
        ROOT / "jmri/layouts/hart/ctc/GUIObjects.xml",
        ROOT / "cats/panels/HART_Master.xml",
        ROOT / "cats/panels/HART_Master_ABS.xml",
        ROOT / "cats/panels/HART_Master_ABS_hold.xml",
        ROOT / "cats/panels/HART_Master_CTC_hold.xml",
        ROOT / "cats/panels/sheets/HART_sheet_West_Yard2.xml",
        ROOT / "cats/panels/sheets/HART_sheet_West_Yard.xml",
        ROOT / "cats/panels/sheets/HART_sheet_West_Yard_SOR.xml",
        ROOT / "cats/data",
        ROOT / "cats/scripts/wire_hart_sheet_west_yard2.py",
        ROOT / "cats/scripts/validate_cats_panel.py",
        ROOT / "cats/scripts/apply_sml_cats_pairs.py",
        ROOT / "cats/docs/DISPATCHER_GUIDE_CTC.md",
        ROOT / "jmri/layouts/hart/scripts/gen_ctc_track_plan.py",
        ROOT / "jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py",
        ROOT / "jmri/layouts/hart/scripts/audit_panel_contracts.py",
        ROOT / "jmri/layouts/hart/scripts/panelpro_smoke_test.py",
        ROOT / "jmri/layouts/hart/scripts/annotate_mqtt_sensors_and_dispatcher.py",
        ROOT / "jmri/scripts/check_hart_phase02.py",
        ROOT / "jmri/layouts/hart/data/block_display_names.csv",
        ROOT / "jmri/layouts/hart/data/block_lengths.csv",
        ROOT / "jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md",
        ROOT / "jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md",
        ROOT / "jmri/layouts/hart/dispatcher/traininfo",
        ROOT / "jmri/layouts/hart/README.md",
    ]
    files = 0
    for raw in targets:
        paths = list(raw.rglob("*")) if raw.is_dir() else [raw]
        for path in paths:
            if not path.is_file() or should_skip(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            updated, counts = apply_renames_to_text(text, RENAMES)
            if counts or path.name.endswith(".xml"):
                if path.name.endswith(".xml") and path.name in {
                    "tables.xml",
                    "new_tables.xml",
                    "hart_prod.xml",
                }:
                    updated, n_comments = refresh_comments(updated)
                else:
                    n_comments = 0
                if updated != text:
                    path.write_text(updated, encoding="utf-8")
                    files += 1
                    print(f"{path.relative_to(ROOT)}: names={sum(counts.values())} comments={n_comments}")
    print(f"updated {files} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
