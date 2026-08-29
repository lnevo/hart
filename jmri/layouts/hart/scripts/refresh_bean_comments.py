#!/usr/bin/env python3
"""Rename public labels and write meaningful JMRI comments.

- Track Main West Brick–Plane → Track Brick-Plane
- Track n (CP) → Track n, CP goes in the comment
- Blocks, occupancy/FB sensors, CTC internals, and plant turnouts get comments
"""

from __future__ import annotations

import csv
import re
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_public_names import RenameEntry, apply_renames_to_text

SIGNAL_WIRING = ROOT / "cats/data/signal_wiring.csv"
PUBLIC_NAME_MAP = ROOT / "jmri/layouts/hart/data/public_name_map.csv"

# Old: "Node 4 / OU-1 / Ports 1,2 / DCC 100"
# New: "Node: 4 | OU-1: Port: 1,2 | DCC: 100"
_OLD_WIRING_RE = re.compile(
    r"^Node\s+(\d+)((?:\s*/\s*(?:OU|IN)-\d+\s*/\s*Ports?\s*[\d,\s]+)+)"
    r"(?:\s*/\s*DCC\s+(\d+))?\s*$",
    re.I,
)
_NEW_WIRING_RE = re.compile(
    r"^Node:\s*(\d+)((?:\s*\|\s*(?:OU|IN)-\d+:\s*Port:\s*[\d,\s]+)+)"
    r"(?:\s*\|\s*DCC:\s*(\d+))?\s*$",
    re.I,
)
_OLD_UNIT_RE = re.compile(r"(OU|IN)-(\d+)\s*/\s*Ports?\s*([\d,]+)", re.I)
_NEW_UNIT_RE = re.compile(r"(OU|IN)-(\d+):\s*Port:\s*([\d,]+)", re.I)
_MAST_NUM_RE = re.compile(r"^Mast\s+(\d+)[LR]", re.I)
_PORT_ID_RE = re.compile(r"^C(\d+)-(OU|IN)(\d+)-(\d+)$", re.I)

# Signal even → switch odd, except S-4 bumpers (26) sit on the last ladder frog.
MAST_SWITCH_OVERRIDE = {
    "Mast 26L": "Switch 21",
    "Mast 26R": "Switch 21",
}


def format_lcos_comment(comment: str) -> str:
    """Rewrite Node/OU|IN/Ports[/DCC] comments to labeled pipes."""
    text = (comment or "").strip()
    if not text:
        return text
    match = _NEW_WIRING_RE.fullmatch(text) or _OLD_WIRING_RE.fullmatch(text)
    if not match:
        return text
    node, body, dcc = match.group(1), match.group(2), match.group(3)
    unit_re = _NEW_UNIT_RE if "|" in body else _OLD_UNIT_RE
    units = [(kind.upper(), num, ports.replace(" ", "")) for kind, num, ports in unit_re.findall(body)]
    if not units:
        return text
    parts = [f"Node: {node}"]
    parts.extend(f"{kind}-{num}: Port: {ports}" for kind, num, ports in units)
    if dcc:
        parts.append(f"DCC: {dcc}")
    return " | ".join(parts)


def comment_from_port_ids(port_ids: list[str], dcc: str | None = None) -> str:
    """Build `Node: 4 | OU-2: Port: 1,2,3` from C4-OU2-1 style port ids.

    Consecutive ports on the same OU stay comma-separated (G/Y/R order).
    Leftover discs that spill (6LA, 32R, 38LA, 8LB, 2035) get extra `| OU-n:` groups.
    """
    groups: list[tuple[str, str, str, list[str]]] = []
    for pid in port_ids:
        match = _PORT_ID_RE.match((pid or "").strip())
        if not match:
            continue
        node, kind, num, port = (
            match.group(1),
            match.group(2).upper(),
            match.group(3),
            match.group(4),
        )
        if groups and groups[-1][0] == node and groups[-1][1] == kind and groups[-1][2] == num:
            groups[-1][3].append(port)
        else:
            groups.append((node, kind, num, [port]))
    if not groups:
        return ""
    parts = [f"Node: {groups[0][0]}"]
    parts.extend(f"{kind}-{num}: Port: {','.join(ports)}" for _, kind, num, ports in groups)
    if dcc:
        parts.append(f"DCC: {dcc}")
    return " | ".join(parts)


def jmri_head_user_name(mast_user_name: str, disc_role: str) -> str:
    """Wiring `Head 6LB T G` → JMRI `Head 6LB Top`."""
    base = (mast_user_name or "").replace("Mast ", "Head ", 1).strip()
    role = (disc_role or "").strip().upper()
    if role == "T":
        return f"{base} Top"
    if role == "B":
        return f"{base} Bottom"
    return base


def load_wiring_head_comments(path: Path | None = None) -> dict[str, str]:
    """JMRI head userName → LCOS port comment from signal_wiring.csv.

    Match by public head name, not packed IH. Wiring packed IDs moved with
    cabinets (40LB is IH1132 on C11); live tables still use the old IH beans.
    """
    csv_path = path or SIGNAL_WIRING
    grouped: OrderedDict[str, list[str]] = OrderedDict()
    if not csv_path.is_file():
        return {}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            uname = jmri_head_user_name(
                row.get("mast_user_name") or "",
                row.get("disc_role") or "",
            )
            if not uname:
                continue
            grouped.setdefault(uname, []).append((row.get("port_id") or "").strip())
    return {
        name: comment_from_port_ids(ports)
        for name, ports in grouped.items()
        if comment_from_port_ids(ports)
    }


def sync_map_head_comments(path: Path | None = None) -> int:
    """Write wiring comments onto public_name_map.csv head rows (identity + aliases)."""
    csv_path = path or PUBLIC_NAME_MAP
    comments = load_wiring_head_comments()
    if not csv_path.is_file() or not comments:
        return 0
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    changed = 0
    for row in rows:
        if (row.get("layer") or "").strip() != "head":
            continue
        proposed = (row.get("proposed") or "").strip()
        want = comments.get(proposed)
        if not want or (row.get("comment") or "").strip() == want:
            continue
        row["comment"] = want
        changed += 1
    if changed:
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return changed


def switch_protected_by_mast(user_name: str) -> str | None:
    """USS even signal lever protects the odd switch in the same column."""
    if user_name in MAST_SWITCH_OVERRIDE:
        return MAST_SWITCH_OVERRIDE[user_name]
    match = _MAST_NUM_RE.match(user_name or "")
    if not match:
        return None
    number = int(match.group(1))
    if number >= 2000:
        return None
    if number % 2 == 0:
        return f"Switch {number - 1}"
    return f"Switch {number}"


def mast_protect_comment(user_name: str, existing: str) -> str:
    """SignalMast comment is `Brick | Switch 1`. Intermediates stay CP-only."""
    parts = [part.strip() for part in (existing or "").split("|") if part.strip()]
    cp = next((part for part in parts if not part.startswith("Switch ")), "")
    switch = switch_protected_by_mast(user_name)
    if switch:
        return f"{cp} | {switch}" if cp else switch
    return cp or existing


def public_comment(layer: str, user_name: str, comment: str) -> str:
    """Device-map / CSV comment as stored on the JMRI bean."""
    text = format_lcos_comment(comment)
    if layer in {"mast", "Signal mast", "Virtual mast"}:
        return mast_protect_comment(user_name, text)
    return text


# Old 100-series plant numbers in prose. Never touch Block n-n or M2S*.
_PLANT_PHRASES = (
    ("110/112", "Switch 31/33"),
    ("117/117b", "Switch 7/7b"),
    ("111a/111b", "Switch 23a/23b"),
    ("113a/113b", "Switch 35a/35b"),
    ("117b", "Switch 7b"),
    ("111a", "Switch 23a"),
    ("111b", "Switch 23b"),
    ("113a", "Switch 35a"),
    ("113b", "Switch 35b"),
)
_PLANT_NUMBERS = {
    "100": "Switch 1",
    "101": "Switch 3",
    "102": "Switch 5",
    "103": "Switch 15",
    "104": "Switch 17",
    "105": "Switch 19",
    "106": "Switch 21",
    "107": "Switch 25",
    "108": "Switch 27",
    "109": "Switch 29",
    "110": "Switch 31",
    "111": "Switch 23",
    "112": "Switch 33",
    "113": "Switch 35",
    "114": "Switch 37",
    "115": "Switch 39",
    "116": "Switch 13",
    "117": "Switch 7",
    "118": "Switch 11",
    "119": "Switch 9",
}
_PROTECT_PROSE_RE = re.compile(r"(Block \d+-\d+|M2S\d+|Node:\s*\d+|DCC:\s*\d+)")
_PLANT_NUM_RE = re.compile(r"\b(1(?:0[0-9]|1[0-9]))\b")


def refresh_block_prose(comment: str) -> str:
    """Keep occupancy/stop text; swap leftover OS names and 100-series plants."""
    text = (comment or "").strip()
    if not text:
        return text
    stashed: list[str] = []

    def stash(match: re.Match[str]) -> str:
        stashed.append(match.group(0))
        return f"__HART_PROSE_{len(stashed) - 1}__"

    work = _PROTECT_PROSE_RE.sub(stash, text)
    for old, new in _PLANT_PHRASES:
        work = work.replace(old, new)
    work = _PLANT_NUM_RE.sub(lambda m: _PLANT_NUMBERS.get(m.group(1), m.group(0)), work)
    for index, original in enumerate(stashed):
        work = work.replace(f"__HART_PROSE_{index}__", original)
    return work

RENAMES = [
    RenameEntry("block", "Track Main West Brick–Plane", "Track Brick-Plane"),
    RenameEntry("block", "Track Brick-Plane", "Track Brick-Plane"),
    RenameEntry("block", "OS Switch 23a", "OS Switch 23a"),
    RenameEntry("block", "OS Switch 23b", "OS Switch 23b"),
    RenameEntry("block", "OS Switch 25", "OS Switch 25"),
    RenameEntry("block", "OS Switch 27", "OS Switch 27"),
    RenameEntry("block", "OS Switch 29", "OS Switch 29"),
    RenameEntry("block", "OS Switch 31", "OS Switch 31"),
    RenameEntry("block", "OS Switch 33", "OS Switch 33"),
    RenameEntry("block", "OS Switch 35a", "OS Switch 35a"),
    RenameEntry("block", "OS Switch 35b", "OS Switch 35b"),
    RenameEntry("block", "OS Switch 37", "OS Switch 37"),
    RenameEntry("block", "OS Switch 39", "OS Switch 39"),
    RenameEntry("block", "OS Switch 15", "OS Switch 15"),
    RenameEntry("block", "OS Switch 17", "OS Switch 17"),
    RenameEntry("block", "OS Switch 19", "OS Switch 19"),
    RenameEntry("block", "OS Switch 21", "OS Switch 21"),
    RenameEntry("block", "OS Switch 7b (Track Barn)", "OS Switch 7b"),
    RenameEntry("block", "OS Switch 7 (Track Barn)", "OS Switch 7"),
    RenameEntry("block", "OS Switch 5", "OS Switch 5"),
    RenameEntry("block", "OS Switch 1", "OS Switch 1"),
    RenameEntry("block", "OS Switch 3", "OS Switch 3"),
]
RENAMES.sort(key=lambda item: len(item.current), reverse=True)

BEAN_RE = re.compile(
    r"(<(sensor|turnout|block|layoutblock|memory|signalhead|signalmast|virtualsignalmast|route|LogixNG|ConditionalNG)\b[^>]*>)(.*?)(</\2>)",
    re.S,
)

CTC_SWITCH = {
    "1": "Switch 3",
    "2": "Switch 3 signals",
    "3": "Switch 1",
    "4": "Switch 1 signals",
    "5": "Switch 5",
    "6": "Switch 5 signals",
    "7": "Switch 7",
    "8": "Switch 7 signals",
    "9": "Switch 13",
    "10": "Switch 13 lock",
    "11": "Switch 15",
    "12": "Switch 15 lock",
    "13": "Switch 25",
    "14": "Switch 25 lock",
    "15": "Switch 27",
    "16": "Switch 27 lock",
    "17": "Switch 23",
    "18": "Switch 23 signals",
    "19": "Switch 29",
    "20": "Switch 29 lock",
    "21": "Switch 31",
    "22": "Switch 31 lock",
    "23": "Switch 33",
    "24": "Switch 33 signals",
    "25": "Switch 35",
    "26": "Switch 35 signals",
    "27": "Switch 37",
    "28": "Switch 37 signals",
    "29": "Switch 39",
    "30": "Switch 39 signals",
    "31": "Switch 9",
    "32": "Switch 9 lock",
    "33": "Switch 11",
    "34": "Switch 11 lock",
    "35": "Switch 17",
    "36": "Switch 17 lock",
    "37": "Switch 19",
    "38": "Switch 19 lock",
    "39": "Switch 21",
    "40": "Switch 21 lock",
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
    "MTT100": "Switch 1 alias",
    "MTT111": "Switch 23 alias",
    "MTT113": "Switch 35 alias",
    "MTT114": "Switch 37 alias",
    "MTT115": "Switch 39 alias",
}

MEMORY_USERNAMES = {
    "IMCURRENTTIME": "Current time",
    "IMIS:ISMEM:versionNo": "Dispatcher version",
    "IMRATEFACTOR": "Clock rate",
}

LOGIXNG_USERNAMES = {
    "IQ:AUTO:0001": "Hide windows on start",
    "IQC:AUTO:0001": "Hide WiThrottle",
    "IQC:AUTO:0002": "Hide USS CTC",
    "IQC:AUTO:0003": "Hide Dispatcher System",
    "IQC:AUTO:0004": "Hide HART Railroad under CATS",
    "IQDA:AUTO:0004": "Hide HART Railroad under CATS",
}

BLOCK_COMMENTS = {
    "Track Brick-Plane": "Track Main West between Brick and Plane; occupancy Block 4-6 / M2S405; stop",
    "Track Main West": "Main west of Brick toward East End; occupancy Block 2-1 / M2S200; stop",
    "Track Main East": "Main east of East End; occupancy Block 2-3 / M2S202; stop",
    "Track West Main Ext": "Track Main West stub west of 111; occupancy Block 1-8 / M2S107; stop",
    "Track East Main Ext": "Main east of Plane toward Track Barn; occupancy Block 4-7 / M2S406; stop",
    "Track East Lead": "South Yard lead east of 110/112 toward Princess; occupancy Block 1-7 / M2S106; stop",
    "Track McKees Rocks": "Princess balloon, Track McKees Rocks; occupancy Block 1-1 / M2S100; stop",
    "Track McKeesport": "Princess balloon, Track McKeesport; occupancy Block 1-2 / M2S101; stop",
    "OS Switch 1": "Brick CP, Switch 1; occupancy Block 4-2 / M2S401",
    "OS Switch 3": "Brick CP, Switch 3; occupancy Block 4-1 / M2S400",
    "OS Switch 5": "Plane CP, Switch 5; occupancy Block 4-5 / M2S404",
    "OS Switch 15": "South Yard, Switch 15; occupancy Block 3-2 / M2S301",
    "OS Switch 17": "South Yard, Switch 17; occupancy Block 3-3 / M2S302",
    "OS Switch 19": "South Yard, Switch 19; occupancy Block 3-5 / M2S304",
    "OS Switch 21": "South Yard, Switch 21; occupancy Block 3-7 / M2S306",
    "OS Switch 25": "East End, Switch 25; occupancy Block 12-1 / M2S1200",
    "OS Switch 27": "East End, Switch 27; occupancy Block 12-3 / M2S1202",
    "OS Switch 29": "East End, Switch 29; occupancy Block 12-5 / M2S1204",
    "OS Switch 31": "East End, Switch 31; occupancy Block 12-7 / M2S1206",
    "OS Switch 23a": "East End crossover 111 north/west leg; occupancy Block 12-4 / M2S1203",
    "OS Switch 23b": "East End crossover 111 south/east leg; occupancy Block 12-6 / M2S1205",
    "OS Switch 33": "East End, Switch 33; occupancy Block 12-8 / M2S1207",
    "OS Switch 35a": "Princess crossover 113 south/yard leg; occupancy Block 1-6 / M2S105",
    "OS Switch 35b": "Princess crossover 113 north/main leg; occupancy Block 1-5 / M2S104",
    "OS Switch 37": "Princess, Switch 37 (same detector as Track K-2); occupancy Block 1-3 / M2S102",
    "OS Switch 39": "Princess, Switch 39 (same detector as Track K-1); occupancy Block 1-4 / M2S103",
    "OS Switch 13": "Hand-throw west of South Yard 103; occupancy Block 3-1 / M2S300",
    "OS Switch 7": "Track Barn CP crossover north/west leg; occupancy Block 13-3 / M2S1302",
    "OS Switch 7b": "Track Barn CP crossover south/east leg; occupancy Block 13-4 / M2S1303",
    "OS Switch 11": "Hand-throw Engine House lead; occupancy Block 13-2 / M2S1301",
    "OS Switch 9": "Hand-throw Engine House; occupancy Block 13-8 / M2S1307",
    "Track Scale": "Plane diverging lead to Track Barn; occupancy Block 4-8 / M2S407; stop",
    "Track Barn": "Lead 117 to 116; occupancy Block 13-1 / M2S1300; stop",
    "Track S-R": "Run-through east of 103; occupancy Block 2-8 / M2S207; stop",
    "Track S-R West": "Hidden Track S-R throat (same detector as Track S-R); occupancy Block 2-8 / M2S207; not a station",
    "Track S-R East": "Hidden Track S-R throat (same detector as Track S-R); occupancy Block 2-8 / M2S207; not a station",
    "Track S-1": "South Yard body; occupancy Block 2-7 / M2S206; stop",
    "Track S-1 West": "Hidden Track S-1 throat (same detector as Track S-1); occupancy Block 2-7 / M2S206; not a station",
    "Track S-1 East": "Hidden Track S-1 throat (same detector as Track S-1); occupancy Block 2-7 / M2S206; not a station",
    "Track S-2": "South Yard body; occupancy Block 2-6 / M2S205; stop",
    "Track S-2 West": "Hidden Track S-2 throat (same detector as Track S-2); occupancy Block 2-6 / M2S205; not a station",
    "Track S-2 East": "Hidden Track S-2 throat (same detector as Track S-2); occupancy Block 2-6 / M2S205; not a station",
    "Track S-3": "South Yard body; occupancy Block 2-5 / M2S204; stop",
    "Track S-3 West": "Hidden Track S-3 throat (same detector as Track S-3); occupancy Block 2-5 / M2S204; not a station",
    "Track S-3 East": "Hidden Track S-3 throat (same detector as Track S-3); occupancy Block 2-5 / M2S204; not a station",
    "Track S-4": "South Yard body; occupancy Block 2-4 / M2S203; stop",
    "Track S-4 West": "Hidden Track S-4 throat (same detector as Track S-4); occupancy Block 2-4 / M2S203; not a station",
    "Track S-4 East": "Hidden Track S-4 throat (same detector as Track S-4); occupancy Block 2-4 / M2S203; not a station",
    "Track W-1": "Brick yard Track W-1; access Switch 3 only; occupancy Block 4-4 / M2S403; stop",
    "Track W-2": "Brick yard Track W-2; access Switch 3 only; occupancy Block 4-3 / M2S402; stop",
    "Track EH-1": "Top house track; occupancy Block 13-7 / M2S1306; stop",
    "Track EH-2": "Middle house track; occupancy Block 13-6 / M2S1305; stop",
    "Track EH-3": "Bottom house track; occupancy Block 13-5 / M2S1304; stop",
    "Track K-1": "Princess stub east of Switch 39; shares Block 1-4 with OS Switch 39; occupancy Block 1-4 / M2S103; stop",
    "Track K-2": "Princess stub east of Switch 37; shares Block 1-3 with OS Switch 37; occupancy Block 1-3 / M2S102; stop",
}

BLOCK_COMMENTS = {
    key: refresh_block_prose(value) for key, value in BLOCK_COMMENTS.items()
}

TURNOUT_COMMENTS = {
    "Switch 1": "Brick CP; MQTT M2T408; FB Switch 4-1; rests Thrown",
    "Switch 3": "Brick CP, West Yard access; MQTT M2T409; FB Switch 4-2",
    "Switch 5": "Plane CP; MQTT M2T410; FB Switch 4-3",
    "Switch 15": "South Yard ladder; MQTT M2T308; FB Switch 3-1; CTC local",
    "Switch 17": "South Yard; MQTT M2T309; FB Switch 3-2; hand-throw",
    "Switch 19": "South Yard; MQTT M2T310; FB Switch 3-3; hand-throw",
    "Switch 21": "South Yard; MQTT M2T311; FB Switch 3-4; hand-throw",
    "Switch 25": "East End; MQTT M2T1208; FB Switch 12-1",
    "Switch 27": "East End; MQTT M2T1209; FB Switch 12-2",
    "Switch 29": "East End; MQTT M2T1210; FB Switch 12-3",
    "Switch 31": "East End ladder; MQTT M2T1211; FB Switch 12-4; CTC local",
    "Switch 23": "East End crossover 111a/111b; MQTT M2T1212; FB Switch 12-5",
    "Switch 33": "East End; MQTT M2T1213; FB Switch 12-6; rests Thrown",
    "Switch 35": "Princess crossover 113a/113b; MQTT M2T108; FB Switch 1-1",
    "Switch 37": "Princess; MQTT M2T109; FB Switch 1-2; rests Thrown",
    "Switch 39": "Princess; MQTT M2T110; FB Switch 1-3; rests Thrown",
    "Switch 13": "Hand-throw west of South Yard; MQTT M2T411; CTC local",
    "Switch 7": "Track Barn CP crossover 117/117b; MQTT M2T1308; field hand-throw",
    "Switch 11": "Hand-throw Engine House lead; MQTT M2T1309",
    "Switch 9": "Hand-throw Engine House; MQTT M2T1310",
}

TURNOUT_COMMENTS = {
    key: refresh_block_prose(value.replace("OS ", "Track "))
    for key, value in TURNOUT_COMMENTS.items()
}

OCC_SENSOR = {
    "Block 1-1": "Occupancy Track McKees Rocks; MQTT M2S100",
    "Block 1-2": "Occupancy Track McKeesport; MQTT M2S101",
    "Block 1-3": "Occupancy OS Switch 37 / Track K-2; MQTT M2S102",
    "Block 1-4": "Occupancy OS Switch 39 / Track K-1; MQTT M2S103",
    "Block 1-5": "Occupancy OS Switch 35b; MQTT M2S104",
    "Block 1-6": "Occupancy OS Switch 35a; MQTT M2S105",
    "Block 1-7": "Occupancy Track East Lead; MQTT M2S106",
    "Block 1-8": "Occupancy Track West Main Ext; MQTT M2S107",
    "Block 2-1": "Occupancy Track Main West; MQTT M2S200",
    "Block 2-3": "Occupancy Track Main East; MQTT M2S202",
    "Block 2-4": "Occupancy Track S-4 (and hidden Track S-4 West/East throats); MQTT M2S203",
    "Block 2-5": "Occupancy Track S-3 (and hidden Track S-3 West/East throats); MQTT M2S204",
    "Block 2-6": "Occupancy Track S-2 (and hidden Track S-2 West/East throats); MQTT M2S205",
    "Block 2-7": "Occupancy Track S-1 (and hidden Track S-1 West/East throats); MQTT M2S206",
    "Block 2-8": "Occupancy Track S-R (and hidden Track S-R West/East throats); MQTT M2S207",
    "Block 3-1": "Occupancy OS Switch 13; MQTT M2S300",
    "Block 3-2": "Occupancy OS Switch 15; MQTT M2S301",
    "Block 3-3": "Occupancy OS Switch 17; MQTT M2S302",
    "Block 3-5": "Occupancy OS Switch 19; MQTT M2S304",
    "Block 3-7": "Occupancy OS Switch 21; MQTT M2S306",
    "Block 4-1": "Occupancy OS Switch 3; MQTT M2S400",
    "Block 4-2": "Occupancy OS Switch 1; MQTT M2S401",
    "Block 4-3": "Occupancy Track W-2; MQTT M2S402",
    "Block 4-4": "Occupancy Track W-1; MQTT M2S403",
    "Block 4-5": "Occupancy OS Switch 5; MQTT M2S404",
    "Block 4-6": "Occupancy Track Brick-Plane; MQTT M2S405",
    "Block 4-7": "Occupancy Track East Main Ext; MQTT M2S406",
    "Block 4-8": "Occupancy Track Scale; MQTT M2S407",
    "Block 12-1": "Occupancy OS Switch 25; MQTT M2S1200",
    "Block 12-3": "Occupancy OS Switch 27; MQTT M2S1202",
    "Block 12-4": "Occupancy OS Switch 23a; MQTT M2S1203",
    "Block 12-5": "Occupancy OS Switch 29; MQTT M2S1204",
    "Block 12-6": "Occupancy OS Switch 23b; MQTT M2S1205",
    "Block 12-7": "Occupancy OS Switch 31; MQTT M2S1206",
    "Block 12-8": "Occupancy OS Switch 33; MQTT M2S1207",
    "Block 13-1": "Occupancy Track Barn; MQTT M2S1300",
    "Block 13-2": "Occupancy OS Switch 11; MQTT M2S1301",
    "Block 13-3": "Occupancy OS Switch 7; MQTT M2S1302",
    "Block 13-4": "Occupancy OS Switch 7b; MQTT M2S1303",
    "Block 13-5": "Occupancy Track EH-3; MQTT M2S1304",
    "Block 13-6": "Occupancy Track EH-2; MQTT M2S1305",
    "Block 13-7": "Occupancy Track EH-1; MQTT M2S1306",
    "Block 13-8": "Occupancy OS Switch 9; MQTT M2S1307",
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


def set_user_name(body: str, user_name: str, *, replace: bool = False) -> str:
    escaped = (
        user_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    if re.search(r"<userName>.*?</userName>", body, re.S):
        if not replace:
            return body
        return re.sub(
            r"<userName>.*?</userName>",
            f"<userName>{escaped}</userName>",
            body,
            count=1,
            flags=re.S,
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


def load_device_map_comments() -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """Identity-row comments from public_name_map.csv (HART Device map)."""
    path = ROOT / "jmri/layouts/hart/data/public_name_map.csv"
    by_sys: dict[str, str] = {}
    by_user: dict[tuple[str, str], str] = {}
    if not path.is_file():
        return by_sys, by_user

    layer_kind = {
        "turnout": "turnout",
        "occupancy": "sensor",
        "fb": "sensor",
        "head": "signalhead",
        "mast": "signalmast",
        "block": "block",
    }
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            current = (row.get("current") or "").strip()
            proposed = (row.get("proposed") or "").strip()
            layer = (row.get("layer") or "").strip()
            comment = public_comment(layer, proposed, (row.get("comment") or "").strip())
            if not comment or current != proposed:
                continue
            for token in (row.get("hardware") or "").split():
                if token.startswith(("M2T", "M2S", "IH", "MTT")):
                    by_sys[token] = comment
            xml_kind = layer_kind.get(layer)
            if xml_kind:
                by_user[(xml_kind, proposed)] = comment
                if xml_kind == "signalmast":
                    by_user[("virtualsignalmast", proposed)] = comment
    return by_sys, by_user


DEVICE_MAP_COMMENTS_BY_SYS, DEVICE_MAP_COMMENTS_BY_USER = load_device_map_comments()
WIRING_HEAD_COMMENTS = load_wiring_head_comments()


def comment_for(kind: str, system_name: str, user_name: str, existing: str) -> str | None:
    if existing and re.search(r"(?:\bstop\b|not a station)", existing, re.I):
        return existing
    if kind == "signalhead":
        wired = WIRING_HEAD_COMMENTS.get(user_name)
        if wired:
            return wired
    mapped = DEVICE_MAP_COMMENTS_BY_SYS.get(system_name) or DEVICE_MAP_COMMENTS_BY_USER.get(
        (kind, user_name)
    )
    if mapped:
        if kind in {"signalmast", "virtualsignalmast"}:
            return public_comment("mast", user_name, mapped)
        return format_lcos_comment(mapped)
    if kind == "block":
        return BLOCK_COMMENTS.get(user_name)
    # LayoutBlock XSD requires <metric> before <comment>; JMRI omits metric
    # when it is the default, so a comment here fails schema validation.
    if kind == "layoutblock":
        return None
    if kind == "turnout":
        if user_name in TURNOUT_COMMENTS:
            return TURNOUT_COMMENTS[user_name]
        if system_name.startswith("IT:HART:YL:"):
            return f"Internal yard-ladder control {user_name}"
        if system_name.startswith("MTT"):
            alias = {
                "MTT100": "Switch 1; same FB as MQTT hardware (Switch 4-1)",
                "MTT111": "Switch 23; same FB as MQTT hardware (Switch 12-5)",
                "MTT113": "Switch 35; same FB as MQTT hardware (Switch 1-1)",
                "MTT114": "Switch 37; same FB as MQTT hardware (Switch 1-2)",
                "MTT115": "Switch 39; same FB as MQTT hardware (Switch 1-3)",
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
            extra = ""
            found = re.search(r"Default Reverse:.*", existing)
            if found:
                extra = f"; {found.group(0).strip()}"
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
        if "unused LCOS" in existing and user_name.startswith("unused "):
            return existing
        if user_name.startswith("unused ") or user_name.startswith("OLCB leftover"):
            return existing or user_name
        return None
    if existing:
        return None
    if kind in {"signalmast", "virtualsignalmast"}:
        return mast_protect_comment(user_name, existing) if user_name else None
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
        elif kind == "sensor":
            ctc_name = ctc_user_name(system_name)
            if ctc_name and ctc_name != user_name:
                used.discard(user_name)
                used.add(ctc_name)
                body = set_user_name(body, ctc_name, replace=True)
                user_name = ctc_name
                changed += 1
        comment = comment_for(kind, system_name, user_name, existing)
        if comment and comment != existing:
            changed += 1
            body = set_comment(body, comment)
        return open_tag + body + close_tag

    return BEAN_RE.sub(repl, text), changed


def main() -> int:
    n_map = sync_map_head_comments()
    if n_map:
        print(f"public_name_map.csv: {n_map} head comments from signal_wiring.csv")
        global DEVICE_MAP_COMMENTS_BY_SYS, DEVICE_MAP_COMMENTS_BY_USER
        DEVICE_MAP_COMMENTS_BY_SYS, DEVICE_MAP_COMMENTS_BY_USER = load_device_map_comments()
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
        ROOT / "cats/scripts/archive/west_yard/wire_hart_sheet_west_yard2.py",
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
