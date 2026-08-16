#!/usr/bin/env python3
"""Inject S-1…S-5 yard-ladder Digicon buttons wired to JMRI Routes.

Left of each S-n: west-yard lead (116) + south ladder to that track.
Right of each S-n: east lead (112/111) + east ladder to that track.

Row map (see LEFT_ROUTES / RIGHT_ROUTES):
  S-1  west/east lead thru S-1
  S-2  103/104  ·  109/110
  S-3  103–105  ·  108–110
  S-4  103–106  ·  107–110  (106/107 reverse)
  S-5  same as S-4 with 106/107 NORMAL (CLOSED)

Buttons sit in the same SECTION row as each S-n label (X±1). Digicon BUTTON
has no SIGLOCATION — with FIT_TO_GRID=false the icon paints from the cell
top-left, so the lamp is baked into a canvas that must fit *inside* one grid
cell (taller canvases spill into the next row: S-5 appeared on Main East and
ate clicks). Idle=dark, active=green.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANEL = ROOT / "cats/panels/HART_Master_ABS.xml"
TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
NEW_TABLES = ROOT / "tables/new_tables.xml"
# Pi live load is preference:tables.xml → /home/pi/JMRI_UserFiles/tables.xml
# (preference: is NOT the profile dir on the Pi). Deploy TABLES there.
BTN_DIR = ROOT / "cats/resources/buttons"
# Lamp-only icons on a ~grid-cell canvas (placement = where the disc sits).
LAMP_LEFT_IDLE = BTN_DIR / "lamp_left_idle.png"
LAMP_LEFT_ACTIVE = BTN_DIR / "lamp_left_active.png"
LAMP_RIGHT_IDLE = BTN_DIR / "lamp_right_idle.png"
LAMP_RIGHT_ACTIVE = BTN_DIR / "lamp_right_active.png"
# Same row as S-n labels — hit-test cell == visual row.
BUTTON_Y_OFFSET = 0
# Master ABS cells render ~30px tall. Canvas = cell height; lamp flush to bottom.
CELL_W, CELL_H = 30, 30
LAMP = 12
LAMP_BOTTOM_PAD = 0
LAMP_SIDE_PAD = 2
TRACK_ORDER = ("S-1", "S-2", "S-3", "S-4", "S-5")


def _indicator_sys(side: str, track: str) -> str:
    """Internal turnout Digicon shows (white=THROWN); also triggers the route."""
    n = track.split("-")[1]
    letter = "L" if side == "left" else "R"
    return f"IT:HART:YL:{letter}{n}"


def _indicator_user(side: str, track: str) -> str:
    return f"Yard ladder {('L' if side == 'left' else 'R')} {track}"


def _indicator_outputs(side: str, track: str) -> list[tuple[str, str]]:
    """Light this row's button; extinguish the other four on the same side."""
    out: list[tuple[str, str]] = []
    for t in TRACK_ORDER:
        sn = _indicator_sys(side, t)
        out.append((sn, "THROWN" if t == track else "CLOSED"))
    return out


# Digicon NORMAL = JMRI CLOSED. Path sense from hart_prod LayoutTurnout continuing
# (continuing=CLOSED → connect B). Yard leads: 116 tip→103; 112/111→OS110.
#
# Row 1 (S-1): west lead / east lead thru to S-1
# Row 2 (S-2): 103/104  and  109/110  (+ leads)
# Row 3 (S-3): 103/104/105  and  108/109/110  (+ leads)
# Row 4 (S-4): 103–106  and  107–110  (+ leads); 106/107 reverse of NORMAL
# Row 5 (S-5): same as row 4 but 106/107 NORMAL (CLOSED)
LEFT_ROUTES: dict[str, list[tuple[str, str]]] = {
    # 116 NORMAL (CLOSED) for all west ladder routes. Unused peels NORMAL.
    "S-1": [
        ("M2T411", "CLOSED"),  # 116 NORMAL
        ("M2T308", "CLOSED"),  # 103 → S-1
        ("M2T309", "CLOSED"),  # 104 NORMAL
        ("M2T310", "CLOSED"),  # 105 NORMAL
        ("M2T311", "CLOSED"),  # 106 NORMAL
    ],
    "S-2": [
        ("M2T411", "CLOSED"),  # 116 NORMAL
        ("M2T308", "THROWN"),  # 103 down
        ("M2T309", "THROWN"),  # 104 → S-2
        ("M2T310", "CLOSED"),  # 105 NORMAL
        ("M2T311", "CLOSED"),  # 106 NORMAL
    ],
    "S-3": [
        ("M2T411", "CLOSED"),  # 116 NORMAL
        ("M2T308", "THROWN"),  # 103
        ("M2T309", "CLOSED"),  # 104 continue
        ("M2T310", "THROWN"),  # 105 → S-3
        ("M2T311", "CLOSED"),  # 106 NORMAL
    ],
    "S-4": [
        ("M2T411", "CLOSED"),  # 116 NORMAL
        ("M2T308", "THROWN"),  # 103
        ("M2T309", "CLOSED"),  # 104
        ("M2T310", "CLOSED"),  # 105 continue
        ("M2T311", "THROWN"),  # 106 → S-4
    ],
    "S-5": [
        ("M2T411", "CLOSED"),  # 116 NORMAL
        ("M2T308", "THROWN"),
        ("M2T309", "CLOSED"),
        ("M2T310", "CLOSED"),
        ("M2T311", "CLOSED"),  # 106 NORMAL → S-5
    ],
}

RIGHT_ROUTES: dict[str, list[tuple[str, str]]] = {
    # 112 = M2T1213 CLOSED (Digicon NORMAL→OS110). 111 only on S-1.
    # Unused peels NORMAL so only one YT thrown.
    "S-1": [
        ("M2T1213", "CLOSED"),  # 112 NORMAL → OS110
        ("M2T1212", "CLOSED"),  # 111 NORMAL (S-1 only)
        ("M2T1211", "CLOSED"),  # 110 stay (S-1)
        ("M2T1210", "CLOSED"),  # 109 NORMAL
        ("M2T1209", "CLOSED"),  # 108 NORMAL
        ("M2T1208", "CLOSED"),  # 107 NORMAL
    ],
    "S-2": [
        ("M2T1213", "CLOSED"),  # 112
        ("M2T1211", "THROWN"),  # 110 down
        ("M2T1210", "THROWN"),  # 109 → S-2
        ("M2T1209", "CLOSED"),  # 108 NORMAL
        ("M2T1208", "CLOSED"),  # 107 NORMAL
    ],
    "S-3": [
        ("M2T1213", "CLOSED"),  # 112
        ("M2T1211", "THROWN"),  # 110
        ("M2T1210", "CLOSED"),  # 109 continue
        ("M2T1209", "THROWN"),  # 108 → S-3
        ("M2T1208", "CLOSED"),  # 107 NORMAL
    ],
    "S-4": [
        ("M2T1213", "CLOSED"),  # 112
        ("M2T1211", "THROWN"),  # 110
        ("M2T1210", "CLOSED"),  # 109
        ("M2T1209", "CLOSED"),  # 108 continue
        ("M2T1208", "THROWN"),  # 107 → S-4
    ],
    "S-5": [
        ("M2T1213", "CLOSED"),  # 112
        ("M2T1211", "THROWN"),  # 110
        ("M2T1210", "CLOSED"),  # 109
        ("M2T1209", "CLOSED"),  # 108
        ("M2T1208", "CLOSED"),  # 107 NORMAL → S-5
    ],
}

# IO:AUTO:02xx reserved for yard ladder routes
ROUTE_IDS = {
    ("left", "S-1"): "IO:AUTO:0201",
    ("left", "S-2"): "IO:AUTO:0202",
    ("left", "S-3"): "IO:AUTO:0203",
    ("left", "S-4"): "IO:AUTO:0204",
    ("left", "S-5"): "IO:AUTO:0205",
    ("right", "S-1"): "IO:AUTO:0206",
    ("right", "S-2"): "IO:AUTO:0207",
    ("right", "S-3"): "IO:AUTO:0208",
    ("right", "S-4"): "IO:AUTO:0209",
    ("right", "S-5"): "IO:AUTO:0210",
}

MARKER = "hart-yard-ladder-buttons"


def _build_lamp_low_icons() -> None:
    """Cell-sized canvases; disc at LOWCENT, biased toward the S-n label."""
    from PIL import Image, ImageDraw

    BTN_DIR.mkdir(parents=True, exist_ok=True)

    def lamp(fill: tuple[int, int, int, int], rim: tuple[int, int, int, int]) -> Image.Image:
        im = Image.new("RGBA", (LAMP, LAMP), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((0, 0, LAMP - 1, LAMP - 1), fill=fill, outline=rim)
        d.ellipse((2, 2, 5, 5), fill=(255, 255, 255, 90))
        return im

    idle = lamp((36, 36, 40, 255), (70, 70, 78, 255))  # dark = idle
    active = lamp((28, 170, 62, 255), (90, 230, 120, 255))  # green = route active

    def place(src: Image.Image, side: str) -> Image.Image:
        canvas = Image.new("RGBA", (CELL_W, CELL_H), (0, 0, 0, 0))
        bw, bh = src.size
        # Low-center inside this cell only (no spill into row below).
        cy = CELL_H - bh - LAMP_BOTTOM_PAD
        if side == "left":
            cx = (CELL_W - bw) // 2
        else:
            # Bias toward S-n label.
            cx = LAMP_SIDE_PAD
        canvas.alpha_composite(src, (cx, cy))
        return canvas

    place(idle, "left").save(LAMP_LEFT_IDLE)
    place(active, "left").save(LAMP_LEFT_ACTIVE)
    place(idle, "right").save(LAMP_RIGHT_IDLE)
    place(active, "right").save(LAMP_RIGHT_ACTIVE)


def _route_user(side: str, track: str) -> str:
    return f"{'Left' if side == 'left' else 'Right'} {track} ladder"


def _ensure_teemast(root: ET.Element) -> None:
    """Appearance → Tee Base. Presence of <TEEMAST/> toggles default-off → on."""
    if root.find("TEEMAST") is None:
        # Place near other appearance counters / LINE
        idx = 0
        for i, child in enumerate(list(root)):
            if child.tag in ("LINE", "COUNTER", "TEEMAST"):
                idx = i + 1
        root.insert(idx, ET.Element("TEEMAST"))


def _ensure_jmri_route_prefix(root: ET.Element) -> None:
    for el in root.findall("JMRINAME"):
        if el.get("JMRIPREFIX") == "IO" and el.get("XMLTYPE") == "Route":
            break
    else:
        idx = 0
        for i, child in enumerate(list(root)):
            if child.tag == "JMRINAME":
                idx = i + 1
        el = ET.Element(
            "JMRINAME",
            {"JMRIPREFIX": "IO", "XMLTYPE": "Route"},
        )
        el.text = "jmri.managers.DefaultRouteManager"
        root.insert(idx, el)

    for el in root.findall("JMRINAME"):
        if el.get("JMRIPREFIX") == "IT" and el.get("XMLTYPE") == "Turnout":
            return
    idx = 0
    for i, child in enumerate(list(root)):
        if child.tag == "JMRINAME":
            idx = i + 1
    el = ET.Element(
        "JMRINAME",
        {"JMRIPREFIX": "IT", "XMLTYPE": "Turnout"},
    )
    el.text = "jmri.managers.InternalTurnoutManager"
    root.insert(idx, el)


def _strip_panel_previous(root: ET.Element) -> None:
    for el in list(root.findall("IOSPECCHAIN")):
        un = el.get("USER_NAME") or ""
        dec = el.get("DECADDR") or ""
        if un.startswith(("Left S-", "Right S-", "Yard ladder ")) or (
            dec.isdigit() and 201 <= int(dec) <= 210
        ):
            root.remove(el)
    for sec in root.iter("SECTION"):
        for btn in list(sec.findall("BUTTON")):
            if btn.get("COMMENT") == MARKER:
                sec.remove(btn)
                continue
            trig = btn.find("TRIGGER/IOSPEC")
            if trig is None:
                continue
            un = trig.get("USER_NAME") or ""
            if un.startswith(("Left S-", "Right S-")) and "ladder" in un:
                sec.remove(btn)
            if un.startswith("Yard ladder "):
                sec.remove(btn)


def _button(side: str, track: str, idle: Path, active: Path) -> ET.Element:
    # Wire to internal turnout: Digicon shows ALTERNATE (white) when THROWN.
    # Throwing the IT also triggers the JMRI Route (controlTurnout).
    sysname = _indicator_sys(side, track)
    uname = _indicator_user(side, track)
    dec = sysname[len("IT") :]
    btn = ET.Element(
        "BUTTON",
        {
            "PRIMARY": str(idle),
            "ALTERNATE": str(active),
            "DELAY": "0",
            "STATUS": "false",
            "FIT_TO_GRID": "false",
            "COMMENT": MARKER,
        },
    )
    trig = ET.SubElement(btn, "TRIGGER")
    ios = ET.SubElement(
        trig,
        "IOSPEC",
        {
            "DECADDR": dec,
            "JMRIPREFIX": "IT",
            "USER_NAME": uname,
        },
    )
    # Digicon: click while Primary (red) runs sendUndoCommand(). With text
    # "close", undo = throw → IT goes THROWN → route controlTurnout fires.
    # (text "throw" made the first click close the IT and skip the route.)
    ios.text = "close"
    return btn


def _find_label_cells(root: ET.Element) -> dict[str, tuple[int, int]]:
    parent = {c: p for p in root.iter() for c in p}
    out: dict[str, tuple[int, int]] = {}
    for sn in root.iter("SEC_NAME"):
        name = sn.get("NAME") or ""
        if name not in LEFT_ROUTES:
            continue
        sec = parent[sn]
        while sec is not None and sec.tag != "SECTION":
            sec = parent.get(sec)
        if sec is None:
            continue
        out[name] = (int(sec.get("X")), int(sec.get("Y")))
    return out


def apply_panel(panel: Path) -> None:
    tree = ET.parse(panel)
    root = tree.getroot()
    _strip_panel_previous(root)
    _ensure_teemast(root)
    _ensure_jmri_route_prefix(root)

    labels = _find_label_cells(root)
    missing = [t for t in LEFT_ROUTES if t not in labels]
    if missing:
        raise SystemExit(f"Missing SEC_NAME labels: {missing}")

    secs = {(s.get("X"), s.get("Y")): s for s in root.iter("SECTION")}

    def _place(action: str, x: int, by: int) -> None:
        left_sec = secs.get((str(x - 1), str(by)))
        right_sec = secs.get((str(x + 1), str(by)))
        if left_sec is None or right_sec is None:
            raise SystemExit(f"{action}: missing side cells at y={by}")
        left_sec.insert(0, _button("left", action, LAMP_LEFT_IDLE, LAMP_LEFT_ACTIVE))
        right_sec.insert(
            0, _button("right", action, LAMP_RIGHT_IDLE, LAMP_RIGHT_ACTIVE)
        )
        print(
            f"{action}: left@({x-1},{by})→{_indicator_user('left', action)}  "
            f"right@({x+1},{by})→{_indicator_user('right', action)}"
        )

    # One button pair per S-n label row; route name matches that track.
    for track in TRACK_ORDER:
        x, y = labels[track]
        _place(track, x, y + BUTTON_Y_OFFSET)

    # Barn lower-right signal → LOWRIGHT
    for ps in root.iter("PANELSIGNAL"):
        # find enclosing SECSIGNAL text
        pass
    parent = {c: p for p in root.iter() for c in p}
    for ss in root.iter("SECSIGNAL"):
        name = (ss.text or "").strip().split("\n")[0].strip()
        if name != "West Yard East OS 117b":
            continue
        ps = ss.find("PANELSIGNAL")
        if ps is not None:
            ps.set("SIGLOCATION", "LOWRIGHT")
            print("Barn lower-right signal → LOWRIGHT")

    tree.write(panel, encoding="UTF-8", xml_declaration=True)
    print(f"Wrote {panel}")


def _strip_table_routes(routes_el: ET.Element) -> None:
    for route in list(routes_el.findall("route")):
        un = ""
        for child in route:
            if child.tag == "userName":
                un = child.text or ""
        sn_el = route.find("systemName")
        sn = sn_el.text if sn_el is not None else ""
        if un.startswith(("Left S-", "Right S-")) and "ladder" in un:
            routes_el.remove(route)
        elif sn and sn.startswith("IO:AUTO:02"):
            routes_el.remove(route)


def _strip_indicator_turnouts(turnouts_el: ET.Element) -> None:
    for t in list(turnouts_el.findall("turnout")):
        sn = t.findtext("systemName") or ""
        un = t.findtext("userName") or ""
        if sn.startswith("IT:HART:YL:") or un.startswith("Yard ladder "):
            turnouts_el.remove(t)


def _make_indicator_turnout(sysname: str, user: str) -> ET.Element:
    t = ET.Element(
        "turnout", {"feedback": "DIRECT", "inverted": "false", "automate": "Off"}
    )
    sn = ET.SubElement(t, "systemName")
    sn.text = sysname
    un = ET.SubElement(t, "userName")
    un.text = user
    return t


def _make_route(
    sysname: str,
    user: str,
    outputs: list[tuple[str, str]],
    control_turnout: str,
) -> ET.Element:
    route = ET.Element(
        "route",
        {
            "userName": user,
            "controlTurnout": control_turnout,
            "controlTurnoutState": "THROWN",
        },
    )
    sn = ET.SubElement(route, "systemName")
    sn.text = sysname
    un = ET.SubElement(route, "userName")
    un.text = user
    for to_sys, state in outputs:
        ET.SubElement(
            route,
            "routeOutputTurnout",
            {"systemName": to_sys, "state": state},
        )
    return route


def apply_tables(path: Path) -> None:
    if not path.is_file():
        print(f"skip missing tables: {path}")
        return
    tree = ET.parse(path)
    root = tree.getroot()
    turnouts_el = None
    for el in root.findall("turnouts"):
        cls = el.get("class") or ""
        if "InternalTurnoutManager" in cls:
            turnouts_el = el
            break
    if turnouts_el is None:
        turnouts_el = ET.SubElement(
            root,
            "turnouts",
            {
                "class": "jmri.jmrix.internal.configurexml.InternalTurnoutManagerXml"
            },
        )
    _strip_indicator_turnouts(turnouts_el)
    # Also strip from any other turnout lists (legacy mis-inserts).
    for el in root.findall("turnouts"):
        if el is not turnouts_el:
            _strip_indicator_turnouts(el)
    for side in ("left", "right"):
        for track in TRACK_ORDER:
            turnouts_el.append(
                _make_indicator_turnout(
                    _indicator_sys(side, track), _indicator_user(side, track)
                )
            )

    routes_el = root.find("routes")
    if routes_el is None:
        routes_el = ET.SubElement(
            root,
            "routes",
            {"class": "jmri.managers.configurexml.DefaultRouteManagerXml"},
        )
    _strip_table_routes(routes_el)
    for track, outs in LEFT_ROUTES.items():
        control = _indicator_sys("left", track)
        routes_el.append(
            _make_route(
                ROUTE_IDS[("left", track)],
                _route_user("left", track),
                outs + _indicator_outputs("left", track),
                control,
            )
        )
    for track, outs in RIGHT_ROUTES.items():
        control = _indicator_sys("right", track)
        routes_el.append(
            _make_route(
                ROUTE_IDS[("right", track)],
                _route_user("right", track),
                outs + _indicator_outputs("right", track),
                control,
            )
        )
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    print(f"Wrote 10 ladder routes + indicators → {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "panel",
        nargs="*",
        type=Path,
        default=[
            DEFAULT_PANEL,
            ROOT / "cats/panels/HART_Master.xml",
        ],
    )
    ap.add_argument("--skip-tables", action="store_true")
    args = ap.parse_args()
    _build_lamp_low_icons()
    for p in (
        LAMP_LEFT_IDLE,
        LAMP_LEFT_ACTIVE,
        LAMP_RIGHT_IDLE,
        LAMP_RIGHT_ACTIVE,
    ):
        if not p.is_file():
            raise SystemExit(f"Missing lamp button icon: {p}")
    if not args.skip_tables:
        apply_tables(TABLES)
        apply_tables(NEW_TABLES)
    panels = args.panel if args.panel else [DEFAULT_PANEL]
    for panel in panels:
        apply_panel(panel.resolve())


if __name__ == "__main__":
    main()
