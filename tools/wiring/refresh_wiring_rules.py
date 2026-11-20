"""refresh_wiring_docs: the fixed rename tables and plant facts the refresh applies to the imported workbooks.

Data only (plus the compiled upper-deck token list built from it); the sheet steps live in refresh_wiring_cells,
refresh_wiring_inventory and refresh_wiring_signals, and refresh_wiring_docs.py is the entry point.
"""
from __future__ import annotations

import re


BLOCK_IN_NOTES = re.compile(r"Block\s+(\d+-\d+)")


# v84 sequential enclosure IDs → C{radio Address} (D{Address} for helix DCC).
# Imported v84 snapshot keeps the old labels; refresh remaps every cell.
LEGACY_NODE_IDS: dict[str, str] = {
    "C1": "C1",
    "C2": "C12",
    "C3": "C2",
    "C4": "C3",
    "C5": "C13",
    "C6": "C4",
    "C7": "C11",
    "C8": "C21",
    "C9": "C22",
    "C10": "C32",
    "C11": "C23",
    "C12": "C14",
    "C13": "C24",
    "D1": "D5",
}
NODE_ID_TOKEN = re.compile(r"(?<![A-Za-z0-9])([CD]\d+)(?![0-9])")
DISC_SORT = {"T": 0, "S": 1, "B": 2}

# v84 "renamed for linear6" concatenated radio/100 onto upper-deck SW1xx plant
# IDs (SW127 → Switch 1127, SW138 → Switch 10038). Restore SW*. Do not write
# "Switch 127" — that is CTC East End Switch 27.
MANGLED_SWITCH_FIXES: list[tuple[str, str]] = [
    ("Switch 1125,Switch 1126,139,Switch 10040", "SW125, SW126, SW139, SW140"),
    ("Switch 1121,Switch 1123", "SW121, SW123"),
    ("SW,120,Switch 1122", "SW120, SW122"),
    ("Switch 10041,Switch 10042", "SW141, SW142"),
    ("Switch 10050", "SW150"),
    ("Switch 10049", "SW149"),
    ("Switch 10048", "SW148"),
    ("Switch 10047", "SW147"),
    ("Switch 10046", "SW146"),
    ("Switch 10045", "SW145"),
    ("Switch 10044", "SW144"),
    ("Switch 10043", "SW143"),
    ("Switch 10042", "SW142"),
    ("Switch 10041", "SW141"),
    ("Switch 10040", "SW140"),
    ("Switch 10038", "SW138"),
    ("Switch 1129", "SW129"),
    ("Switch 1127", "SW127"),
    ("Switch 1126", "SW126"),
    ("Switch 1125", "SW125"),
    ("Switch 1124", "SW124"),
    ("Switch 1123", "SW123"),
    ("Switch 1122", "SW122"),
    ("Switch 1121", "SW121"),
]

# v84 DCC Switch 100–119 → live CTC numbers (ADR-005). Longest first so
# Switch 113a becomes Switch 35a. Do not emit "Switch 127" (that is SW127).
DCC_SWITCH_TO_CTC: list[tuple[str, str]] = [
    ("Switch 119", "Switch 9"),
    ("Switch 118", "Switch 11"),
    ("Switch 117", "Switch 7"),
    ("Switch 116", "Switch 13"),
    ("Switch 115", "Switch 39"),
    ("Switch 114", "Switch 37"),
    ("Switch 113", "Switch 35"),
    ("Switch 112", "Switch 33"),
    ("Switch 111", "Switch 23"),
    ("Switch 110", "Switch 31"),
    ("Switch 109", "Switch 29"),
    ("Switch 108", "Switch 27"),
    ("Switch 107", "Switch 25"),
    ("Switch 106", "Switch 21"),
    ("Switch 105", "Switch 19"),
    ("Switch 104", "Switch 17"),
    ("Switch 103", "Switch 15"),
    ("Switch 102", "Switch 5"),
    ("Switch 101", "Switch 3"),
    ("Switch 100", "Switch 1"),
]

# Pre-linear6 SW1–SW18 / SCX* tokens still on the Nodes summary columns.
# Digit-bounded so SW12 does not eat SW124.
_SW_TOKEN_CTC: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<![A-Za-z0-9])SCXB(?![A-Za-z0-9])"), "Switch 35"),
    (re.compile(r"(?<![A-Za-z0-9])SCXA(?![A-Za-z0-9])"), "Switch 23"),
    (re.compile(r"(?<![A-Za-z0-9])SW18(?![0-9])"), "Switch 39"),
    (re.compile(r"(?<![A-Za-z0-9])SW17(?![0-9])"), "Switch 37"),
    (re.compile(r"(?<![A-Za-z0-9])SW13(?![0-9])"), "Switch 13"),
    (re.compile(r"(?<![A-Za-z0-9])SW12(?![0-9])"), "Switch 23"),
    (re.compile(r"(?<![A-Za-z0-9])SW11(?![0-9])"), "Switch 31"),
    (re.compile(r"(?<![A-Za-z0-9])SW10(?![0-9])"), "Switch 29"),
    (re.compile(r"(?<![A-Za-z0-9])SW9(?![0-9])"), "Switch 27"),
    (re.compile(r"(?<![A-Za-z0-9])SW8(?![0-9])"), "Switch 25"),
    (re.compile(r"(?<![A-Za-z0-9])SW7(?![0-9])"), "Switch 21"),
    (re.compile(r"(?<![A-Za-z0-9])SW6(?![0-9])"), "Switch 19"),
    (re.compile(r"(?<![A-Za-z0-9])SW5(?![0-9])"), "Switch 17"),
    (re.compile(r"(?<![A-Za-z0-9])SW4(?![0-9])"), "Switch 15"),
    (re.compile(r"(?<![A-Za-z0-9])SW3(?![0-9])"), "Switch 5"),
    (re.compile(r"(?<![A-Za-z0-9])SW2(?![0-9])"), "Switch 3"),
    (re.compile(r"(?<![A-Za-z0-9])SW1(?![0-9])"), "Switch 1"),
]
HEAD_MAST_RE = re.compile(r"^Head (\S+)")
LED_NAME_RE = re.compile(r"^S\d+-\d+")
RGB_LED_RE = re.compile(r"^(S([4-6])-(\d+))\s+([GYR])$")

# Upper deck continues the lower-deck odd-switch / even-signal pattern from 61/62.
# CP4 (helix) first, then CP5 (north), then CP6 (peninsula/west). v8 column order
# inside each CP. Compound plants keep a/b/c/d on the physical machines.
UPPER_SWITCH_NUM: dict[str, str] = {
    "NIX": "Switch 61",
    "SW127": "Switch 63",
    "SW138": "Switch 65",
    "SW129": "Switch 67",
    "DJE": "Switch 69",
    "DJW": "Switch 71",
    "SW124": "Switch 73",
    "CBX": "Switch 75",
    "SW143": "Switch 77",
    "SW144": "Switch 79",
    "SW145": "Switch 81",
    "SW146": "Switch 83",
    "SW147": "Switch 85",
    "SW148": "Switch 87",
    "SW149": "Switch 89",
    "SW150": "Switch 91",
    "SW125": "Switch 61a",
    "SW126": "Switch 61b",
    "SW139": "Switch 61c",
    "SW140": "Switch 61d",
    "SW121": "Switch 69a",
    "SW123": "Switch 69b",
    "SW120": "Switch 71a",
    "SW122": "Switch 71b",
    "SW141": "Switch 75a",
    "SW142": "Switch 75b",
}

# Planned RGB head → even mast id (switch+1, L/R/A/B like 24L / 36RA).
UPPER_HEAD_NAME: dict[str, str] = {
    "S4-6": "62L",
    "S4-3": "64L",
    "S4-1": "64R",
    "S4-4": "66RA",
    "S4-5": "66RB",
    "S4-2": "68L",
    "S4-7": "68R",
    "S5-1": "70L",
    "S5-5": "70RA",
    "S5-6": "70RB",
    "S5-2": "72L",
    "S5-3": "74L",
    "S5-4": "74RA",
    "S5-7": "74RB",
    "S6-1": "76L",
    "S6-2": "76R",
    "S6-3": "78L",
    "S6-6": "78R",
    "S6-4": "78RA",
    "S6-5": "78RB",
    "S6-10": "82L",
    "S6-11": "84RA",
    "S6-12": "84RB",
    "S6-13": "86L",
    "S6-7": "88L",
    "S6-8": "88R",
    "S6-9": "88RA",
    "S6-14": "90L",
    "S6-15": "92L",
}

# v8 heads that are clearly extra discs on an existing plant (not a new mast).
V8_MAST_HINT: dict[str, str] = {
    "S4-4": "Switch 65 (with 66RB)",
    "S4-5": "Switch 65 (with 66RA)",
    "S5-6": "Switch 69 reverse",
    "S5-7": "Switch 73 reverse",
}

UPPER_TURNOUT_CP: dict[str, str] = {
    "SW127": "CP4 (Helix - Upper)",
    "SW129": "CP4 (Helix - Upper)",
    "SW138": "CP4 (Helix - Upper)",
    "NIX": "CP4 (Helix - Upper)",
    "SW124": "CP5 (North - Upper)",
    "DJE": "CP5 (North - Upper)",
    "DJW": "CP5 (North - Upper)",
    "CBX": "CP6 (Peninsula - Upper)",
    "SW143": "CP6 (West - Upper)",
    "SW144": "CP6 (West - Upper)",
    "SW145": "CP6 (West - Upper)",
    "SW146": "CP6 (West - Upper)",
    "SW147": "CP6 (West - Upper)",
    "SW148": "CP6 (Peninsula - Upper)",
    "SW149": "CP6 (Peninsula - Upper)",
    "SW150": "CP6 (Peninsula - Upper)",
}


def _build_upper_name_tokens() -> list[tuple[re.Pattern[str], str]]:
    """Longest-first regexes: S6-15 before S6-1, SW150 before SW124, NIX last."""
    out: list[tuple[re.Pattern[str], str]] = []
    for old, new in sorted(
        UPPER_HEAD_NAME.items(), key=lambda kv: (-len(kv[0]), kv[0])
    ):
        out.append(
            (re.compile(rf"(?<!was )(?<![A-Za-z0-9]){re.escape(old)}(?![0-9])"), new)
        )
    for old, new in sorted(
        UPPER_SWITCH_NUM.items(), key=lambda kv: (-len(kv[0]), kv[0])
    ):
        out.append(
            (re.compile(rf"(?<![A-Za-z0-9]){re.escape(old)}(?![A-Za-z0-9])"), new)
        )
    return out


_UPPER_NAME_TOKENS = _build_upper_name_tokens()

RETIRED_S3_TURNOUTS = ("Switch 15", "Switch 17", "Switch 19", "Switch 21")
RETIRED_S2_TURNOUTS = ("Switch 25", "Switch 27", "Switch 29")
TURNOUT_SIGNAL_COLS = (
    "Entry Signal",
    "Entry Signal R Port",
    "Entry Signal Y Port",
    "Entry Signal G Port",
    "Normal Exit Signal",
    "Normal Exit R Port",
    "Normal Exit Y Port",
    "Normal Exit G Port",
    "Reverse Exit Signal",
    "Reverse Exit R Port",
    "Reverse Exit Y Port",
    "Reverse Exit G Port",
)


# TurnoutSummary: one 3-pin head per face. R/Y/G columns are lamp colors again.
# Ports use C{radio Address} (Plane/Brick C4, East End 24 on C2 / 34 on C12).
TURNOUT_DIGICON: dict[str, dict[str, object]] = {
    "Switch 100": {
        "entry": "2L",
        "entry_ports": ("C4-OU3-1", "C4-OU3-2", "C4-OU3-3"),
        "normal": None,
        "reverse": None,
    },
    "Switch 101": {
        "entry": None,
        "normal": "4RA",
        "normal_ports": ("C4-OU4-1", "C4-OU4-2", "C4-OU4-3"),
        "reverse": "4RB",
        "reverse_ports": ("C4-OU4-4", "C4-OU4-5", "C4-OU4-6"),
    },
    "Switch 102": {
        "entry": "6LA",
        "entry_ports": ("C4-OU2-7", "C4-OU3-8", "C4-OU3-7"),
        "normal": None,
        "reverse": "6LB",
        "reverse_ports": ("C4-OU2-1", "C4-OU2-2", "C4-OU2-3"),
    },
    "Switch 111": {
        "entry": "24L",
        "entry_ports": ("C2-OU2-1", "C2-OU2-2", "C2-OU2-3"),
        "normal": "24RA",
        "normal_ports": ("C2-OU1-1", "C2-OU1-2", "C2-OU1-3"),
        "reverse": "24RB",
        "reverse_ports": ("C2-OU3-6", "C2-OU3-7", "C2-OU3-8"),
    },
    "Switch 110": {
        "entry": "32R",
        "entry_ports": ("C12-OU2-7", "C12-OU3-8", "C12-OU3-7"),
        "normal": None,
        "reverse": None,
    },
    "Switch 112": {
        "entry": "34L",
        "entry_ports": ("C12-OU2-1", "C12-OU2-2", "C12-OU2-3"),
        "normal": None,
        "reverse": "34R",
        "reverse_ports": ("C12-OU3-1", "C12-OU3-2", "C12-OU3-3"),
    },
    "Switch 113": {
        "entry": "36RA",
        "entry_ports": ("C1-OU2-1", "C1-OU2-2", "C1-OU2-3"),
        "normal": None,
        "reverse": "36RB",
        "reverse_ports": ("C1-OU3-1", "C1-OU3-2", "C1-OU3-3"),
    },
    "Switch 114": {
        "entry": "2036",
        "entry_ports": ("C11-OU3-4", "C11-OU3-5", "C11-OU3-6"),
        "normal": "38LB",
        "normal_ports": ("C1-OU4-1", "C1-OU4-2", "C1-OU4-3"),
        "reverse": "38LA",
        "reverse_ports": ("C1-OU3-7", "C1-OU3-8", "C1-OU2-7"),
    },
    "Switch 115": {
        "entry": "2035",
        "entry_ports": ("C11-OU3-7", "C11-OU3-8", "C11-OU2-7"),
        "normal": "40LB",
        "normal_ports": ("C11-OU2-1", "C11-OU2-2", "C11-OU2-3"),
        "reverse": "40LA",
        "reverse_ports": ("C11-OU3-1", "C11-OU3-2", "C11-OU3-3"),
    },
    "Switch 117": {
        "entry": "8RA",
        "entry_ports": ("C13-OU1-1", "C13-OU1-2", "C13-OU1-3"),
        "normal": "8LA",
        "normal_ports": ("C13-OU3-1", "C13-OU3-2", "C13-OU3-3"),
        "reverse": "8LB / 8RB",
        "reverse_ports": ("C13-OU3-7", "C13-OU3-8", "C13-OU4-7"),
    },
}


# New 5V DNOU8: C1 Princess 38, C4 Brick west 4R, C13 Barn 8RB.
# C2 west-24 and C11/C12 use existing 5V boards (no new OU4).
NEW_5V_OU4 = ("C1", "C4", "C13")


# Princess sheet / all_logic column order (asbuilt v1).
PRINCESS_LOGIC_HEADERS = [
    "Control_Point",
    "Location",
    "Signal",
    "Signal_Block",
    "Route_From",
    "Route_To",
    "Block1",
    "Block2",
    "Next_Signal",
    "SW100",
    "SW101",
    "SW102",
    "SW117",
    "SW111",
    "SW110",
    "SW112",
    "SW113",
    "SW114",
    "SW115",
    "B1",
    "B2",
    "BO_Rule",
    "BO_Aspect",
    "MQTT_Out",
    "Notes",
]

# Clear / Approach / Stop occupancy flags (B1 = stop, B2 = approach).
_DWARF_ASPECTS = (
    (None, None, "R281", "Clear", "Green"),
    (None, "X", "R285", "Approach", "Yellow"),
    ("X", None, "R292", "Stop", "Red"),
)
