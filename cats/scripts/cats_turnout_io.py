"""Digicon turnout IO: switch facts → SWITCHPOINTS SELECTEDREPORT / ROUTECOMMAND.

Plant cells are ``wire_digicon.PLANT_CELLS``; the Layout Editor turnout, its
hardware, the closed and thrown legs and the invert polarity are switch facts in
jmri/layouts/hart/data/ (switches.csv, switch_legs.csv, public_name_map.csv).
This module only binds JMRI M2T addresses.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(paths.LAYOUT_SCRIPTS))

import digicon_lib as le  # noqa: E402
import layout_facts as facts  # noqa: E402

ROOT = paths.REPO_ROOT
HART_PANEL = paths.TABLES_XML


def section_tracks(sec: ET.Element) -> list[str]:
    tg = sec.find("TRACKGROUP")
    return [(t.text or "").strip() for t in tg.findall("TRACK")] if tg is not None else []


# Alias for archived West Yard sheet scripts.
_tracks = section_tracks


def _edge(sec: ET.Element, edge: str) -> ET.Element | None:
    for e in sec.findall("SEC_EDGE"):
        if e.get("EDGE") == edge:
            return e
    return None


def load_turnouts() -> dict[str, tuple[str, str]]:
    """layout_ident → (DECADDR, USER_NAME) for M2T, one per switch in switches.csv.

    The address is the switch's M2T hardware (public_name_map.csv); the user name is
    its public name, Switch N. A switch whose hardware is not an M2T turnout in
    tables.xml is skipped with a message.
    """
    m2t = {tables.system_name(t) for t in tables.turnouts(tables.read(HART_PANEL))
           if tables.system_name(t).startswith("M2T")}
    out: dict[str, tuple[str, str]] = {}
    for sw in facts.load_switches().values():
        if sw.hardware not in m2t:
            print(f"TURNOUT SKIP: {sw.le_ident} unresolved {sw.hardware or sw.turnout}", file=sys.stderr)
            continue
        out[sw.le_ident] = (sw.hardware[3:], sw.turnout)
    return out


def wire_turnouts(
    tp: ET.Element,
    turnout_by_ident: dict[str, tuple[str, str]],
    plants: dict[tuple[int, int], tuple[str, str, str]],
    invert_vs_jmri: set[str] | None = None,
) -> int:
    """Bind SELECTEDREPORT + ROUTECOMMAND on each plant SWITCHPOINTS.

    Default: NORMAL route ↔ JMRI CLOSED (close); other leg ↔ THROWN (throw).
    ``invert_vs_jmri`` is layout_idents whose CATS NORMAL (drawn through)
    is JMRI Thrown — Designer “differs from JMRI settings”: NORMAL→throw.
    SELECTEDREPORT and ROUTECOMMAND must use the same polarity — remapping
    only the report (to chase a bad MQTT retain) reverses Digicon commands.
    """
    invert = invert_vs_jmri or set()
    secs = {
        (int(s.get("X")), int(s.get("Y"))): s
        for s in tp.findall("SECTION")
        if s.find("TRACKGROUP") is not None
    }
    n = 0
    for xy, (_os, normal, ident) in plants.items():
        binding = turnout_by_ident.get(ident)
        if not binding:
            print(f"TURNOUT SKIP: plant {xy} {ident} not in CSV", file=sys.stderr)
            continue
        addr, uname = binding
        sec = secs.get(xy)
        if sec is None:
            continue
        tracks = section_tracks(sec)
        pts = le.points_edge(tracks)
        if pts is None:
            continue
        legs = [e for e in le.cell_edges(tracks) if e != pts]
        sp_edge = _edge(sec, pts)
        if sp_edge is None:
            continue
        sp = sp_edge.find("SWITCHPOINTS")
        if sp is None:
            sp = ET.SubElement(sp_edge, "SWITCHPOINTS")
        # Do not set SPUR here. Digicon Spur gates CONFLICTINGSIGNALLOCK via
        # UnlockRoute (only Normal clears it); that lock is in GUISwitchLocks and
        # blocks dispatcher throw of SW100/101 without a coded switch-unlock.
        if sp.get("SPUR") is not None:
            del sp.attrib["SPUR"]
        existing = {r.get("ROUTEID"): r for r in sp.findall("ROUTEINFO")}
        for leg in legs:
            ri = existing.get(leg)
            if ri is None:
                attrs = {"ROUTEID": leg}
                if leg == normal:
                    attrs["NORMAL"] = "true"
                ri = ET.SubElement(sp, "ROUTEINFO", attrs)
                existing[leg] = ri
            elif leg == normal:
                ri.set("NORMAL", "true")
            else:
                if "NORMAL" in ri.attrib:
                    del ri.attrib["NORMAL"]
            for child in list(ri):
                ri.remove(child)
            if ident in invert:
                pol = "throw" if leg == normal else "close"
            else:
                pol = "close" if leg == normal else "throw"
            for tag in ("SELECTEDREPORT", "ROUTECOMMAND"):
                el = ET.SubElement(ri, tag)
                ios = ET.SubElement(
                    el,
                    "IOSPEC",
                    {"DECADDR": addr, "JMRIPREFIX": "M2T", "USER_NAME": uname},
                )
                ios.text = pol
        n += 1
    return n
