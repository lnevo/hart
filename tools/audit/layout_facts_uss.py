"""The USS CTC part of tools/audit/check_layout_facts.py: the code buttons in tables.xml (check_ctc_buttons) and the
USS panel, in ctc/GUIObjects.xml and in tables.xml, against switches.csv and the board's grid (check_uss_panel)."""
from __future__ import annotations

import functools
import re
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from hartlib import occupancy_bindings
from layout_facts_base import Report, facts
from layout_facts_tables import Tables

LEVER_X0, LEVER_PITCH, LEVER_INSET = 12, 65, 8      # a lever's x on the USS panel: LEVER_X0 + PITCH * slot + INSET
CREAM = 'red="220" green="220" blue="180"'           # the colour of a USS panel track label


def occupancy_sensors(device_map: Path) -> dict[str, str]:
    """{block name: occupancy sensor} of the CATS desks' blocks in the master at `device_map` (occupancy_bindings)."""
    return {row["block_user_name"]: row["occupancy_sensor_user_name"]
            for row in occupancy_bindings.rows(device_map)}


def _button_text(cb: ET.Element, tag: str) -> str:
    """The stripped text of a code button's child `tag` ("" when it has none)."""
    return (cb.findtext(tag) or "").strip()


def check_ctc_buttons(switches: dict[int, facts.Switch], t: Tables, occ: dict[str, str], r: Report) -> None:
    """One code button per switch, working its turnout with its OS blocks' sensors, its lever and signal levers."""
    buttons: dict[str, Callable[[str], str]] = {}
    for cb in t.root.iter("ctcCodeButtonData"):
        text_of = functools.partial(_button_text, cb)
        buttons[text_of("SWDI_ExternalTurnout")] = text_of
    for sw in switches.values():
        n = f"Switch {sw.number}"
        get = buttons.pop(sw.turnout, None)
        if get is None:
            r.add(f"uss:{n}", f"{n}: no USS CTC code button works {sw.turnout} in tables.xml")
            continue
        os_sensors = tuple(s for s in (get("OSSectionOccupiedExternalSensor"),
                                       get("OSSectionOccupiedExternalSensor2")) if s)
        want = tuple(occ.get(os_name, "?") for os_name in sw.os_blocks)     # "?": an OS block with no sensor
        if os_sensors != want:
            r.add(f"uss:{n}", f"{n}: CTC code button OS sensors {os_sensors}; switches.csv "
                              f"OS blocks {sw.os_blocks} report on {want}")
        lever = t.sensor_system.get(get("SWDL_InternalSensor"), "")
        if lever != f"IS{sw.ctc_is}:LEVER":
            r.add(f"uss:{n}", f"{n}: CTC lever is {get('SWDL_InternalSensor')} ({lever}), "
                              f"switches.csv says IS{sw.ctc_is}:LEVER")
        if (get("SIDL_Enabled") == "true") != sw.ctc_signals:
            r.add(f"uss:{n}", f"{n}: CTC signal levers SIDL_Enabled={get('SIDL_Enabled')}, "
                              f"switches.csv ctc_signals={'yes' if sw.ctc_signals else 'no'}")
    for turnout in buttons:
        r.add(f"uss:{turnout}", f"tables.xml has a USS CTC code button for {turnout}, not in switches.csv")


def uss_panel(text: str) -> str:
    """The <paneleditor> element of a USS panel file's text ("" when it has none)."""
    m = re.search(r"<paneleditor\b.*?</paneleditor>", text, re.S)
    return m.group(0) if m else ""


def _check_levers_and_dots(label: str, pe: str, switches: dict[int, facts.Switch], r: Report) -> None:
    """Each switch's lever in its column, and one points dot showing Normal on its NORMAL leg."""
    levers = {int(k): int(x) for k, x in re.findall(r'<sensoricon sensor="IS(\d+):LEVER" x="(\d+)"', pe)}
    dots = Counter(re.findall(r'<turnouticon turnout="([^"]+)"', pe))
    closed_url = dict(re.findall(r'<turnouticon turnout="([^"]+)"[^>]*>\s*<icons>\s*<closed url="([^"]+)"', pe))
    for sw in switches.values():
        n = f"Switch {sw.number}"
        x = levers.get(sw.ctc_is)
        want_x = LEVER_X0 + LEVER_PITCH * sw.uss_slot + LEVER_INSET
        if x != want_x:
            r.add(f"uss:{n}", f"{n}: {label} lever IS{sw.ctc_is}:LEVER at x={x}, "
                              f"column {sw.uss_slot} for plate {sw.number} is x={want_x}")
        if dots[sw.turnout] != 1:
            r.add(f"uss:{n}", f"{n}: {label} draws {dots[sw.turnout]} points dots for {sw.turnout}, expected 1")
            continue
        swapped = closed_url.get(sw.turnout, "").endswith("pts-thrown.gif")
        if swapped != sw.cats_inverted:
            r.add(f"uss-dot:{n}", f"{n}: {label} points dot shows Normal when {'thrown' if swapped else 'closed'}; "
                                  f"switches.csv cats_inverted={'yes' if sw.cats_inverted else 'no'} (Normal is the "
                                  f"{'thrown' if sw.cats_inverted else 'closed'} leg)")


def _track(name: str) -> str:
    return name.removeprefix("Track ")


def check_uss_panel(label: str, pe: str, switches: dict[int, facts.Switch], gen: ModuleType,
                    cells: dict, r: Report) -> None:
    """A USS panel (`pe`, its <paneleditor> text) against switches.csv, and its track jewels and labels against a
    fresh build from the board grid `cells` (uss_board_cells.csv) by `gen` (gen_ctc_track_plan)."""
    _check_levers_and_dots(label, pe, switches, r)
    _t, _tracks, lamps, texts = gen.build_geometry(cells)
    want_lamps = Counter((s, x, y, tip) for s, x, y, tip in lamps)
    have_lamps = Counter((s, int(x), int(y), tip) for s, x, y, tip in re.findall(
        r'<sensoricon sensor="(BS [^"]+)" x="(-?\d+)" y="(-?\d+)"[^>]*>\s*<tooltip>([^<]*)</tooltip>', pe))
    want_text = Counter((txt, x, y) for x, y, txt, _size, col in texts
                        if col == gen.CREAM)
    have_text = Counter((txt, int(x), int(y)) for x, y, txt in re.findall(
        r'<positionablelabel x="(-?\d+)" y="(-?\d+)"[^>]*text="([^"]*)"[^>]*' + CREAM, pe))
    for s, x, y, tip in want_lamps - have_lamps:
        r.add(f"uss-diagram:{_track(tip)}", f"{_track(tip)}: the CATS desk puts jewel {s} ({tip}) at "
                                            f"({x},{y}); {label} does not")
    for s, x, y, tip in have_lamps - want_lamps:
        r.add(f"uss-diagram:{_track(tip)}", f"{_track(tip)}: {label} draws jewel {s} ({tip}) at ({x},{y}); "
                                            f"the CATS desk does not")
    for txt, x, y in want_text - have_text:
        r.add(f"uss-diagram:{_track(txt)}", f"{_track(txt)}: the CATS desk labels ({x},{y}) {txt!r}; {label} does not")
    for txt, x, y in have_text - want_text:
        r.add(f"uss-diagram:{_track(txt)}", f"{_track(txt)}: {label} labels ({x},{y}) {txt!r}; the CATS desk does not")
