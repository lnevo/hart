#!/usr/bin/env python3
"""Add JMRI Entry/Exit (NX) sensors on CTC masts for HART Railroad.

Creates ISNX:<mast> internals, binds them to the same turnout/point legs as
the mast, and places a small click target on the approach rail into the switch.

Does not generate pairs — run discover_nx.py in PanelPro for that.
Does not touch USS paneleditor or Dispatcher System MoveTo icons.

Modes (--mode):
  sml   (default) NX throws turnouts and uses SML. No Hold, no block
        reserve. LE turnout circles still work. Default AAR aspects.
  lock  Full interlock: Hold at Stop until a route is clicked, reserve
        the path. CATS CTC and USS Logic off while this is on.

Switch later: python3 apply_nx_layer.py --mode lock && deploy.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULTS = [
    ROOT / "jmri/layouts/hart/output/tables.xml",
    ROOT / "tables/new_tables.xml",
]

# CTC plant only (100–115 / 117). Not 116/118/119 or yard stubs.
CTC_MASTS = {
    "Mast 2L": "Brick east main westbound; lever 4 Left",
    "Mast 4RA": "Brick Track W-1 dwarf eastbound; lever 2 Right",
    "Mast 4RB": "Brick Track W-2 dwarf eastbound; lever 2 Right",
    "Mast 6LA": "Plane, Track Scale westbound; lever 6 Left",
    "Mast 6LB": "Plane, Track East Main Ext westbound; lever 6 Left",
    "Mast 8RA": "Track Barn, yard eastbound; lever 8 Right",
    "Mast 8RB": "Track Barn, Track East Main Ext eastbound; lever 8 Right",
    "Mast 8LA": "Track Barn, Track East Main Ext westbound; lever 8 Left",
    "Mast 8LB": "Track Barn, Track Barn dwarf westbound; lever 8 Left",
    "Mast 24RA": "East End, Track Main West eastbound; lever 18 Right",
    "Mast 24RB": "East End, Track S-R dwarf eastbound; lever 18 Right",
    "Mast 24L": "East End, Track 23a westbound; lever 18 Left",
    "Mast 32R": "East End, Track 31 dwarf eastbound; lever 20 Right",
    "Mast 34R": "East End, Track Main East eastbound; lever 24 Right",
    "Mast 34L": "East End lead westbound; lever 24 Left",
    "Mast 36RA": "Princess, Track Main West eastbound; lever 26 Right",
    "Mast 36RB": "Princess, Track East Lead eastbound; lever 26 Right",
    "Mast 2036": "Princess, Track McKeesport dwarf eastbound; lever 28 Right",
    "Mast 38LA": "Princess, Track K-2 dwarf westbound; lever 28 Left",
    "Mast 38LB": "Princess, Track McKeesport westbound; lever 28 Left",
    "Mast 2035": "Princess, Track McKees Rocks dwarf eastbound; lever 30 Right",
    "Mast 40LA": "Princess, Track K-1 dwarf westbound; lever 30 Left",
    "Mast 40LB": "Princess, Track McKees Rocks westbound; lever 30 Left",
}

INTERNAL_CLOSE = "  </sensors>\n  <turnouts class=\"jmri.jmrix.openlcb.configurexml.OlcbTurnoutManagerXml\">"
ENTRYEXIT_OPEN = (
    '  <entryexitpairs class="jmri.jmrit.entryexit.configurexml.EntryExitPairsXml">'
)
ABS_YES = "    <abssignalmode>yes</abssignalmode>"
GEOGRAPHIC_PANEL_NAMES = ("HART Railroad", "HART", "My Layout")
LAYOUT_EDITOR_PREFIX = (
    '<LayoutEditor class="jmri.jmrit.display.layoutEditor.configurexml.LayoutEditorXml" name="'
)
NEXT_PANEL_START = '<LayoutEditor class="jmri.jmrit.display.layoutEditor.configurexml.LayoutEditorXml" name="Dispatcher System"'
MAST_ICON_RE = re.compile(
    r'<signalmasticon signalmast="([^"]+)" x="([^"]+)" y="([^"]+)"[^>]*degrees="([^"]+)"'
)
TURNOUT_RE = re.compile(r"<layoutturnout\b[^>]*>.*?</layoutturnout>", re.S)
POINT_RE = re.compile(r"<positionablepoint\b[^>]*/>")
SENSOR_SYS_RE = re.compile(r"<systemName>(ISNX:[^<]+)</systemName>")


def user_name(mast: str) -> str:
    return f"NX {mast}"


def system_name(mast: str) -> str:
    return f"ISNX:{mast}"


def sensor_xml(mast: str) -> str:
    note = CTC_MASTS[mast]
    return (
        "    <sensor inverted=\"false\">\n"
        f"      <systemName>{system_name(mast)}</systemName>\n"
        f"      <userName>{user_name(mast)}</userName>\n"
        f"      <comment>Entry/Exit at mast {mast}; {note}. "
        "Full interlock. CATS CTC and USS Logic off while NX is in use.</comment>\n"
        "    </sensor>\n"
    )


# 21×21 USS lamp, centered on the approach rail into the switch (not the
# frog, not the mast heads). y = rail − 10. Paired A/B ends share x.
NX_ICON_POSITIONS: dict[str, tuple[int, int]] = {
    "Mast 2L": (382, 242),    # Track Main West into 100, left of the mast cluster
    "Mast 4RA": (198, 242),   # Track W-1, even with 100 / 111 / 113
    "Mast 4RB": (198, 293),   # Track W-2, left+up off the rail
    "Mast 6LA": (374, 305),   # Track Scale into 102
    "Mast 6LB": (378, 353),   # Track East Main Ext into 102
    "Mast 8RA": (462, 305),   # Track Scale into 117
    "Mast 8LB": (548, 305),   # Track Barn into 117; same X as Mast 8LA
    "Mast 8RB": (445, 353),   # Track East Main Ext into 117; same Y as NX Mast 6LB
    "Mast 8LA": (548, 353),   # Track Main East into 117
    "Mast 24RA": (1095, 242),  # Track Main West into 111
    "Mast 24RB": (1095, 305),  # Track S-R into 111 (aligned with Mast 24RA)
    "Mast 24L": (1248, 242),   # same X as NX Mast 32R
    "Mast 32R": (1248, 335),   # Track 29 ladder, left of the diagonal
    "Mast 34R": (1312, 338),   # Track Main East, left of the diagonal
    "Mast 34L": (1407, 305),   # Track East Lead into 112
    "Mast 36RA": (1465, 242),  # Track West Main Ext into 113
    "Mast 36RB": (1465, 305),  # Track East Lead into 113
    "Mast 38LA": (1675, 305),  # Track K-2 stub toward the balloon
    "Mast 38LB": (1695, 367),  # Track McKeesport bezier
    "Mast 40LA": (1675, 242),  # Track K-1 stub toward the balloon
    "Mast 40LB": (1695, 162),  # Rocks bezier; same X as Mast 38LB
    "Mast 2035": (1826, 245),   # Rocks arc; same X as Mast 2036
    "Mast 2036": (1826, 291),   # Track McKeesport arc; same X as Mast 2035
}

# Mast shifts so heads clear the approach lamps and share Mast 2L's height.
MAST_ALIGN: dict[str, tuple[int, int]] = {
    "Mast 6LA": (366, 290),
    "Mast 6LB": (366, 338),
    "Mast 8RA": (445, 327),
    "Mast 8LB": (552, 290),
    "Mast 8RB": (445, 374),
    "Mast 8LA": (529, 341),
    "Mast 32R": (1265, 349),
    "Mast 2035": (1848, 245),
    "Mast 2036": (1804, 291),
    "Mast 40LB": (1608, 185),
    "Mast 24L": (1248, 218),
    "Mast 24RA": (1095, 263),
    "Mast 24RB": (1095, 326),
    "Mast 34L": (1392, 289),
    "Mast 36RA": (1465, 264),
    "Mast 36RB": (1465, 325),
    "Mast 40LA": (1665, 222),
    "Mast 38LA": (1665, 285),
}

# USS lamps, not the 10px circuit squares used by Dispatcher MoveInProgress.
NX_ICON_INNER = (
    '      <active url="program:resources/icons/USS/sensor/green-on.gif" '
    'degrees="0" scale="1.0">\n'
    "        <rotation>0</rotation>\n"
    "      </active>\n"
    '      <inactive url="program:resources/icons/USS/sensor/white-off.gif" '
    'degrees="0" scale="1.0">\n'
    "        <rotation>0</rotation>\n"
    "      </inactive>\n"
    '      <unknown url="program:resources/icons/USS/sensor/white-off.gif" '
    'degrees="0" scale="1.0">\n'
    "        <rotation>0</rotation>\n"
    "      </unknown>\n"
    '      <inconsistent url="program:resources/icons/USS/sensor/white-off.gif" '
    'degrees="0" scale="1.0">\n'
    "        <rotation>0</rotation>\n"
    "      </inconsistent>\n"
    "      <iconmaps />\n"
)
NX_ICON_RE = re.compile(
    r'(<sensoricon sensor="NX [^"]+"[^>]*>).*?(</sensoricon>)',
    re.S,
)


def icon_xml(mast: str, x: int, y: int) -> str:
    return (
        f'    <sensoricon sensor="{user_name(mast)}" x="{x}" y="{y}" level="11" '
        'forcecontroloff="false" hidden="no" positionable="true" showtooltip="true" '
        'editable="false" momentary="false" icon="yes" '
        'class="jmri.jmrit.display.configurexml.SensorIconXml">\n'
        f"{NX_ICON_INNER}"
        "    </sensoricon>\n"
    )


def restyle_icons(panel: str) -> tuple[str, int]:
    changed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        body = f"{match.group(1)}\n{NX_ICON_INNER}    {match.group(2)}"
        if body != match.group(0):
            changed += 1
        return body

    return NX_ICON_RE.sub(repl, panel), changed


def nx_xy(mast: str, x: float, y: float, degrees: float) -> tuple[int, int]:
    """Approach-rail lamp, or a facing-side fallback for an unknown mast."""
    if mast in NX_ICON_POSITIONS:
        return NX_ICON_POSITIONS[mast]
    d = int(degrees) % 360
    along = 28
    if 45 <= d <= 135:
        return int(round(x - along)), int(round(y + 2))
    if 225 <= d <= 315:
        return int(round(x + along)), int(round(y + 2))
    if 135 < d < 225:
        return int(round(x + 2)), int(round(y - along))
    return int(round(x + 2)), int(round(y + along))


def align_masts(panel: str) -> tuple[str, int]:
    changed = 0
    for mast, (x, y) in MAST_ALIGN.items():
        pattern = rf'(<signalmasticon signalmast="{re.escape(mast)}" x=")[^"]+(" y=")[^"]+"'

        def repl(match: re.Match[str], x: int = x, y: int = y) -> str:
            nonlocal changed
            updated = f"{match.group(1)}{x}{match.group(2)}{y}\""
            if updated != match.group(0):
                changed += 1
            return updated

        panel, n = re.subn(pattern, repl, panel, count=1)
        if n == 0:
            continue
    return panel, changed


def reposition_icons(panel: str) -> tuple[str, int]:
    masts: dict[str, tuple[float, float, float]] = {}
    for match in MAST_ICON_RE.finditer(panel):
        masts[match.group(1)] = (
            float(match.group(2)),
            float(match.group(3)),
            float(match.group(4)),
        )
    changed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        name = match.group(1)
        mast = name[3:]
        if mast not in masts and mast not in NX_ICON_POSITIONS:
            return match.group(0)
        x, y, degrees = masts.get(mast, (0.0, 0.0, 0.0))
        ix, iy = nx_xy(mast, x, y, degrees)
        updated = f'<sensoricon sensor="{name}" x="{ix}" y="{iy}"'
        if updated != match.group(0):
            changed += 1
        return updated

    return re.sub(r'<sensoricon sensor="(NX [^"]+)" x="[^"]+" y="[^"]+"', repl, panel), changed


def insert_internal_sensors(text: str) -> tuple[str, int]:
    if INTERNAL_CLOSE not in text:
        raise SystemExit("internal sensor table close not found")
    existing = set(SENSOR_SYS_RE.findall(text))
    chunks = []
    for mast in CTC_MASTS:
        if system_name(mast) not in existing:
            chunks.append(sensor_xml(mast))
    if not chunks:
        return text, 0
    return text.replace(INTERNAL_CLOSE, "".join(chunks) + INTERNAL_CLOSE, 1), len(chunks)


def patch_turnout(xml: str) -> str:
    for letter in "ABCD":
        mast_m = re.search(rf"<signal{letter}Mast>([^<]+)</signal{letter}Mast>", xml)
        if not mast_m:
            continue
        mast = mast_m.group(1)
        if mast not in CTC_MASTS or re.search(rf"<sensor{letter}>", xml):
            continue
        xml = xml.replace(
            f"</signal{letter}Mast>",
            f"</signal{letter}Mast>\n      <sensor{letter}>{user_name(mast)}</sensor{letter}>",
            1,
        )
    return xml


def patch_point(xml: str) -> str:
    if "eastboundsignalmast=" not in xml and "westboundsignalmast=" not in xml:
        return xml
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', xml))
    east_mast = attrs.get("eastboundsignalmast")
    west_mast = attrs.get("westboundsignalmast")
    extra = []
    if east_mast in CTC_MASTS and "eastboundsensor" not in attrs:
        extra.append(f'eastboundsensor="{user_name(east_mast)}"')
    if west_mast in CTC_MASTS and "westboundsensor" not in attrs:
        extra.append(f'westboundsensor="{user_name(west_mast)}"')
    if not extra:
        return xml
    return xml.replace(" class=", " " + " ".join(extra) + " class=", 1)


def insert_icons(panel: str) -> tuple[str, int]:
    present = set(re.findall(r'<sensoricon sensor="(NX [^"]+)"', panel))
    last = None
    for match in MAST_ICON_RE.finditer(panel):
        last = match
    if last is None:
        raise SystemExit("HART Railroad has no signalmasticon rows")
    chunks = []
    for match in MAST_ICON_RE.finditer(panel):
        mast, x, y, degrees = match.group(1), float(match.group(2)), float(match.group(3)), float(match.group(4))
        if mast not in CTC_MASTS or user_name(mast) in present:
            continue
        ix, iy = nx_xy(mast, x, y, degrees)
        chunks.append(icon_xml(mast, ix, iy))
    if not chunks:
        return panel, 0
    insert_at = last.end()
    # signalmasticon may be self-closing or have a closing tag on the same line
    if panel[insert_at:insert_at + 2] != "\n":
        nl = panel.find("\n", insert_at)
        insert_at = nl + 1 if nl >= 0 else insert_at
    return panel[:insert_at] + "".join(chunks) + panel[insert_at:], len(chunks)


def apply_panel(panel: str) -> tuple[str, dict[str, int]]:
    counts = {"turnouts": 0, "points": 0}

    def turnout_sub(match: re.Match[str]) -> str:
        patched = patch_turnout(match.group(0))
        if patched != match.group(0):
            counts["turnouts"] += 1
        return patched

    def point_sub(match: re.Match[str]) -> str:
        patched = patch_point(match.group(0))
        if patched != match.group(0):
            counts["points"] += 1
        return patched

    panel = TURNOUT_RE.sub(turnout_sub, panel)
    panel = POINT_RE.sub(point_sub, panel)
    panel, aligned = align_masts(panel)
    panel, icons = insert_icons(panel)
    panel, restyled = restyle_icons(panel)
    panel, moved = reposition_icons(panel)
    counts["aligned"] = aligned
    counts["icons"] = icons
    counts["restyled"] = restyled
    counts["moved"] = moved
    return panel, counts


NXTYPE_SML = "signalmastlogic"
NXTYPE_LOCK = "fullinterlocking"


def set_abs_mode(text: str, enabled: bool) -> tuple[str, int]:
    has_yes = bool(re.search(r"<abssignalmode>\s*yes\s*</abssignalmode>", text))
    if enabled:
        if has_yes:
            return text, 0
        if "<abssignalmode>" in text:
            updated, n = re.subn(
                r"<abssignalmode>.*?</abssignalmode>",
                "<abssignalmode>yes</abssignalmode>",
                text,
                count=1,
                flags=re.S,
            )
            return updated, n
        if ENTRYEXIT_OPEN not in text:
            return text, 0
        return text.replace(ENTRYEXIT_OPEN, ENTRYEXIT_OPEN + "\n" + ABS_YES, 1), 1
    updated, n = re.subn(
        r"\n?[ \t]*<abssignalmode>.*?</abssignalmode>\n?",
        "\n",
        text,
        count=1,
        flags=re.S,
    )
    return updated, n


def set_pair_type(text: str, nx_type: str) -> tuple[str, int]:
    if ENTRYEXIT_OPEN not in text:
        return text, 0
    updated, n = re.subn(r'nxType="[^"]+"', f'nxType="{nx_type}"', text)
    return updated, n


def apply_text(text: str, mode: str = "sml") -> tuple[str, dict[str, int]]:
    if mode not in ("sml", "lock"):
        raise SystemExit(f"unknown NX mode {mode!r}")
    text, sensors = insert_internal_sensors(text)
    end = text.find(NEXT_PANEL_START)
    start = -1
    for name in GEOGRAPHIC_PANEL_NAMES:
        found = text.find(LAYOUT_EDITOR_PREFIX + name + '"')
        if found >= 0:
            start = found
            break
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("HART Railroad / Dispatcher System panel bounds not found")
    panel, counts = apply_panel(text[start:end])
    text = text[:start] + panel + text[end:]
    lock = mode == "lock"
    text, abs_mode = set_abs_mode(text, enabled=not lock)
    text, ntype = set_pair_type(text, NXTYPE_LOCK if lock else NXTYPE_SML)
    counts["sensors"] = sensors
    counts["abs_mode"] = abs_mode
    counts["nx_type"] = ntype
    counts["mode"] = mode
    return text, counts


def apply_file(path: Path, mode: str = "sml") -> dict[str, int]:
    original = path.read_text(encoding="utf-8")
    updated, counts = apply_text(original, mode=mode)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--mode",
        choices=("sml", "lock"),
        default="sml",
        help="sml = turnout + SML now; lock = full interlock Hold",
    )
    ap.add_argument("paths", nargs="*", type=Path, default=DEFAULTS)
    args = ap.parse_args()
    for path in args.paths:
        if not path.is_file():
            print(f"skip missing {path}", file=sys.stderr)
            continue
        counts = apply_file(path, mode=args.mode)
        print(
            f"{path}: mode={counts.get('mode')} sensors+{counts['sensors']} "
            f"turnouts+{counts['turnouts']} points+{counts['points']} "
            f"aligned+{counts.get('aligned', 0)} "
            f"icons+{counts['icons']} restyled+{counts.get('restyled', 0)} "
            f"moved+{counts.get('moved', 0)} abs+{counts.get('abs_mode', 0)} "
            f"nxtype+{counts.get('nx_type', 0)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
