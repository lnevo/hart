#!/usr/bin/env python3
"""Add JMRI Entry/Exit (NX) sensors on CTC masts for HART Railroad.

Creates ISNX:* internals (frozen CTC numbers, see nx_contract.py) and binds
them to the same turnout/point legs as the mast. Entry/Exit is parked
(hartlib.parked); this serves its unparking.

Does not generate pairs — run discover_nx.py in PanelPro for that.
Does not touch USS paneleditor or Dispatcher System MoveTo icons.

SML-mode NX (the live desk) throws from Signal Mast Logic auto-turnouts when
a dest exists. Those lists are computed at runtime (useLayoutEditor=yes);
they are not stored in tables.xml. Digicon dests boot Enabled=no. Do not
enable them in the stored tables.

Modes (--mode):
  sml   (default) NX throws turnouts and uses SML. No Hold, no block
        reserve. LE turnout circles still work. Default AAR aspects.
  lock  Full interlock: Hold at Stop until a route is clicked, reserve
        the path. CATS CTC and USS Logic off while this is on.

Switch later: python3 apply_nx_layer.py --mode lock && deploy.

A mast whose NX sensor is already bound somewhere on the panel (a turnout leg's
<sensorX> or an anchor's east/westboundsensor) gets no second binding.

The main panel must be a generated one (build_layout_le.py --as-live; it holds
the hidden hartlib.tables.GENERATED_PANEL_MARKER label). It shows no NX sensor
icon (owner, 2026-11-16): the sensors bound in the mast slots are what Entry/Exit
discovery and the pairs use, so no icon is added or moved.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from nx_contract import (
    ISNX_SYSTEM,
    NXTYPE_SML,
    nx_system_name,
    nx_user_name,
)

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402

DEFAULTS = [paths.TABLES_XML]

# CTC plant only (100–115 / 117). Not 116/118/119 or yard stubs.
CTC_MASTS = {
    "Mast 2L": "Brick east main westbound; lever 4 Left",
    "Mast 4RA": "Brick Track W-1 dwarf eastbound; lever 2 Right",
    "Mast 4RB": "Brick Track W-2 dwarf eastbound; lever 2 Right",
    "Mast 6LA": "Plane, Track Scale westbound; lever 6 Left",
    "Mast 6LB": "Plane, Track East Ext westbound; lever 6 Left",
    "Mast 8RA": "Track Barn, yard eastbound; lever 8 Right",
    "Mast 8RB": "Track Barn, Track East Ext eastbound; lever 8 Right",
    "Mast 8LA": "Track Barn, Track East Ext westbound; lever 8 Left",
    "Mast 8LB": "Track Barn, Track Barn dwarf westbound; lever 8 Left",
    "Mast 24RA": "East End, Track Main West eastbound; lever 18 Right",
    "Mast 24RB": "East End, Track S-R dwarf eastbound; lever 18 Right",
    "Mast 24L": "East End, OS Switch 23a westbound; lever 18 Left",
    "Mast 32R": "East End, OS Switch 31 dwarf eastbound; lever 20 Right",
    "Mast 34R": "East End, Track Main East eastbound; lever 24 Right",
    "Mast 34L": "East End lead westbound; lever 24 Left",
    "Mast 36RA": "Princess, Track Main West eastbound; lever 26 Right",
    "Mast 36RB": "Princess, Track East Lead eastbound; lever 26 Right",
    "Mast 2036": "Princess, Track K-2 dwarf eastbound; lever 28 Right",
    "Mast 38LA": "Princess, Track McKeesport westbound home, two-head; lever 28 Left",
    "Mast 38LB": "Princess, Track K-2 dwarf westbound; lever 28 Left",
    "Mast 2035": "Princess, Track K-1 dwarf eastbound; lever 30 Right",
    "Mast 40LA": "Princess, Track McKees Rocks westbound home, two-head; lever 30 Left",
    "Mast 40LB": "Princess, Track K-1 dwarf westbound; lever 30 Left",
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
PANEL_END = "</LayoutEditor>"
TURNOUT_RE = re.compile(r"<layoutturnout\b[^>]*>.*?</layoutturnout>", re.S)
POINT_RE = re.compile(r"<positionablepoint\b[^>]*/>")
SENSOR_SYS_RE = re.compile(r"<systemName>(ISNX:[^<]+)</systemName>")
SENSOR_USER_RE = re.compile(r"<userName>(NX [^<]+)</userName>")


def user_name(mast: str) -> str:
    return nx_user_name(mast)


def system_name(mast: str) -> str:
    return nx_system_name(mast)


def sensor_comment(mast: str, mode: str) -> str:
    note = CTC_MASTS[mast]
    if mode == "lock":
        extra = "Full interlock. CATS CTC and USS Logic off while NX is in use."
        return f"Entry/Exit at mast {mast}; {note}. {extra}"
    return note


def sensor_xml(mast: str, mode: str = "sml") -> str:
    return (
        "    <sensor inverted=\"false\">\n"
        f"      <systemName>{system_name(mast)}</systemName>\n"
        f"      <userName>{user_name(mast)}</userName>\n"
        f"      <comment>{sensor_comment(mast, mode)}</comment>\n"
        "    </sensor>\n"
    )


def insert_internal_sensors(text: str, mode: str = "sml") -> tuple[str, int]:
    if INTERNAL_CLOSE not in text:
        raise SystemExit("internal sensor table close not found")
    existing_sys = set(SENSOR_SYS_RE.findall(text))
    existing_user = set(SENSOR_USER_RE.findall(text))
    chunks = []
    for mast in CTC_MASTS:
        if system_name(mast) in existing_sys or user_name(mast) in existing_user:
            continue
        chunks.append(sensor_xml(mast, mode))
    if not chunks:
        return text, 0
    return text.replace(INTERNAL_CLOSE, "".join(chunks) + INTERNAL_CLOSE, 1), len(chunks)


def refresh_sensor_comments(text: str, mode: str) -> tuple[str, int]:
    changed = 0
    for mast in CTC_MASTS:
        comment = sensor_comment(mast, mode)
        pattern = (
            rf"(<systemName>{re.escape(system_name(mast))}</systemName>\s*"
            rf"<userName>{re.escape(user_name(mast))}</userName>\s*"
            rf"<comment>)([^<]*)(</comment>)"
        )

        def repl(match: re.Match[str], comment: str = comment) -> str:
            nonlocal changed
            if match.group(2) != comment:
                changed += 1
            return f"{match.group(1)}{comment}{match.group(3)}"

        text, _n = re.subn(pattern, repl, text, count=1)
    return text, changed


def bound_nx_sensors(panel: str) -> set[str]:
    """NX sensor user names already bound in a slot on the panel (turnout legs and anchors)."""
    legs = re.findall(r"<sensor[ABCD]>(NX [^<]+)</sensor[ABCD]>", panel)
    points = re.findall(r'(?:east|west)boundsensor="(NX [^"]+)"', panel)
    return set(legs) | set(points)


def patch_turnout(xml: str, bound: set[str] | None = None) -> str:
    """Bind each CTC mast's NX sensor on this turnout's legs; `bound` (sensors already bound anywhere on the
    panel) gains each one bound here, so no sensor is bound twice."""
    bound = set() if bound is None else bound
    for letter in "ABCD":
        mast_m = re.search(rf"<signal{letter}Mast>([^<]+)</signal{letter}Mast>", xml)
        if not mast_m:
            continue
        mast = mast_m.group(1)
        if mast not in CTC_MASTS or re.search(rf"<sensor{letter}>", xml) or user_name(mast) in bound:
            continue
        xml = xml.replace(
            f"</signal{letter}Mast>",
            f"</signal{letter}Mast>\n      <sensor{letter}>{user_name(mast)}</sensor{letter}>",
            1,
        )
        bound.add(user_name(mast))
    return xml


def patch_point(xml: str, bound: set[str] | None = None) -> str:
    """As patch_turnout, for an anchor's east and west bound slots."""
    bound = set() if bound is None else bound
    if "eastboundsignalmast=" not in xml and "westboundsignalmast=" not in xml:
        return xml
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', xml))
    east_mast = attrs.get("eastboundsignalmast")
    west_mast = attrs.get("westboundsignalmast")
    extra = []
    if east_mast in CTC_MASTS and "eastboundsensor" not in attrs and user_name(east_mast) not in bound:
        extra.append(f'eastboundsensor="{user_name(east_mast)}"')
        bound.add(user_name(east_mast))
    if west_mast in CTC_MASTS and "westboundsensor" not in attrs and user_name(west_mast) not in bound:
        extra.append(f'westboundsensor="{user_name(west_mast)}"')
        bound.add(user_name(west_mast))
    if not extra:
        return xml
    return xml.replace(" class=", " " + " ".join(extra) + " class=", 1)


def apply_panel(panel: str) -> tuple[str, dict[str, int]]:
    """Bind each CTC mast's NX sensor in its mast's slot on the main panel's text `panel`."""
    counts = {"turnouts": 0, "points": 0}
    bound = bound_nx_sensors(panel)     # grows as sensors are bound: turnout legs first, then anchors

    def turnout_sub(match: re.Match[str]) -> str:
        patched = patch_turnout(match.group(0), bound)
        if patched != match.group(0):
            counts["turnouts"] += 1
        return patched

    def point_sub(match: re.Match[str]) -> str:
        patched = patch_point(match.group(0), bound)
        if patched != match.group(0):
            counts["points"] += 1
        return patched

    panel = TURNOUT_RE.sub(turnout_sub, panel)
    panel = POINT_RE.sub(point_sub, panel)
    return panel, counts


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
    missing = set(CTC_MASTS) - set(ISNX_SYSTEM)
    extra = set(ISNX_SYSTEM) - set(CTC_MASTS)
    if missing or extra:
        raise SystemExit(f"CTC_MASTS / ISNX_SYSTEM mismatch missing={sorted(missing)} extra={sorted(extra)}")
    text, sensors = insert_internal_sensors(text, mode)
    text, comments = refresh_sensor_comments(text, mode)
    try:
        generated = tables.generated_panel(tables.layout_editor(tables.loads(text.encode("utf-8")).root))
    except (ValueError, ET.ParseError) as exc:
        raise SystemExit(f"cannot read the main Layout Editor panel: {exc}") from None
    if not generated:
        raise SystemExit("the main Layout Editor panel is not a generated one (build_layout_le.py --as-live)")
    start = next((found for name in GEOGRAPHIC_PANEL_NAMES
                  if (found := text.find(LAYOUT_EDITOR_PREFIX + name + '"')) >= 0), -1)
    end = text.find(PANEL_END, start) if start >= 0 else -1
    if end < 0:
        raise SystemExit("the main Layout Editor panel's bounds are not found in the text")
    panel, counts = apply_panel(text[start:end])
    text = text[:start] + panel + text[end:]
    lock = mode == "lock"
    text, abs_mode = set_abs_mode(text, enabled=not lock)
    text, ntype = set_pair_type(text, NXTYPE_LOCK if lock else NXTYPE_SML)
    counts["sensors"] = sensors
    counts["comments"] = comments
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
    paths.exit_if_overridden(Path(__file__).name)
    for path in args.paths:
        if not path.is_file():
            print(f"skip missing {path}", file=sys.stderr)
            continue
        counts = apply_file(path, mode=args.mode)
        print(
            f"{path}: mode={counts.get('mode')} sensors+{counts['sensors']} "
            f"comments~{counts.get('comments', 0)} "
            f"turnouts+{counts['turnouts']} points+{counts['points']} "
            f"abs+{counts.get('abs_mode', 0)} "
            f"nxtype+{counts.get('nx_type', 0)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
