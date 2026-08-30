"""Digicon turnout IO: CSV → SWITCHPOINTS SELECTEDREPORT / ROUTECOMMAND.

Live SoR for plant cells and invert polarity is ``wire_hart_master4.py``
``PLANTS`` / ``INVERT_VS_JMRI``. This module only binds JMRI M2T addresses.
"""
from __future__ import annotations

import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_hart_digicon_from_le as le  # noqa: E402

TURNOUT_CSV = ROOT / "cats/data/turnout_bindings.csv"
HART_PANEL = ROOT / "jmri/layouts/hart/output/hart_prod.xml"


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
    """layout_ident → (DECADDR, USER_NAME) for M2T."""
    by_user: dict[str, str] = {}
    root = ET.parse(HART_PANEL).getroot()
    for t in root.iter("turnout"):
        sn = (t.findtext("systemName") or t.get("systemName") or "").strip()
        un = (t.findtext("userName") or "").strip()
        if sn.startswith("M2T") and un:
            by_user[un] = sn[3:]
            by_user[sn] = sn[3:]
    out: dict[str, tuple[str, str]] = {}
    with TURNOUT_CSV.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ident = row["layout_ident"].strip()
            key = row["turnout_user_or_system"].strip()
            addr = by_user.get(key)
            if not addr and key.startswith("M2T"):
                addr = key[3:]
            if not addr:
                print(f"TURNOUT SKIP: {ident} unresolved {key}", file=sys.stderr)
                continue
            uname = key
            for u, a in by_user.items():
                if a == addr and u.startswith("Switch"):
                    uname = u
                    break
            out[ident] = (addr, uname)
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
