#!/usr/bin/env python3
"""Bridge Digicon R-code templates to JMRI C&O-1980 aspect names.

CATS stock templates call setAspect("R281"|…). C&O-1980 CO-33-hi homes expect
Clear / Approach Medium / Medium Clear / Approach Slow / Approach / Restricting /
Stop; dwarfs expect Slow Clear / Restricting / Stop. HOLD_ONLY panels also
need AppearanceKey values that match those JMRI aspect names so Digicon can
paint from SML. Do not alias RES_* to Approach on 2-head templates: CATS reverse
lookup is first-match, and RES_NORM sits before R285 (Approach would paint as
Restricting). Aspect names with spaces cannot be XML attribute names.

HOLD_ONLY (ABS-RO / CTC SML): map every AAR name SML can post onto a unique
IndicationNames row whose ICON class is the closest one-disc ABS action
(CLEAR=green proceed, APPROACH=yellow caution, STOP=red). CATS cannot draw
two searchlights; unused CATS rows get non-JMRI placeholders so they cannot
steal a match.

When CATS drives aspects (no HOLD_ONLY), keep the collapsed ladder so setAspect
only requests Clear / Approach / Stop (or Slow Clear / Restricting / Stop).

Idempotent: re-running refreshes remap + paint keys without duplicating templates.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# CATS IndicationNames order + ICON class (cats.layout.items.AspectMap).
# First AppearanceKey value equal to JMRI getAspect() wins.
_INDICATION_ORDER = (
    "R281",
    "R281B",
    "R282",
    "R284",
    "RES_NORM",
    "ADV_NORM",
    "R285",
    "R281C",
    "C412",
    "C413",
    "C414",
    "RES_LIM",
    "ADV_LIM",
    "R281D",
    "R283",
    "C417",
    "R283A",
    "R283B",
    "RES_MED",
    "ADV_MED",
    "R286",
    "R287",
    "C422",
    "C423",
    "C424",
    "RES_SLO",
    "ADV_SLO",
    "R288",
    "R291",
    "R292",
)

_ICON = {
    "R281": "CLEAR",
    "R281B": "CLEAR",
    "R282": "CLEAR",
    "R284": "CLEAR",
    "RES_NORM": "RESTRICTING",
    "ADV_NORM": "APPROACH",
    "R285": "APPROACH",
    "R281C": "CLEAR",
    "C412": "CLEAR",
    "C413": "CLEAR",
    "C414": "CLEAR",
    "RES_LIM": "RESTRICTING",
    "ADV_LIM": "APPROACH",
    "R281D": "APPROACH",
    "R283": "CLEAR",
    "C417": "CLEAR",
    "R283A": "CLEAR",
    "R283B": "CLEAR",
    "RES_MED": "RESTRICTING",
    "ADV_MED": "APPROACH",
    "R286": "APPROACH",
    "R287": "CLEAR",
    "C422": "CLEAR",
    "C423": "CLEAR",
    "C424": "CLEAR",
    "RES_SLO": "RESTRICTING",
    "ADV_SLO": "APPROACH",
    "R288": "APPROACH",
    "R291": "STOP",
    "R292": "STOP",
}

# CATS IndicationName → C&O-1980 aspect (setAspect) when CATS drives the mast.
# CO-33-hi has Restricting (R/Y); RES_* can request it. There is no Medium
# Approach appearance on this mast type (that lamp pair is Restricting).
_REMAP_2 = {
    "R281": "Clear",
    "R281B": "Clear",
    "R282": "Approach Medium",
    "R284": "Approach Slow",
    "RES_NORM": "Restricting",
    "ADV_NORM": "Clear",
    "R285": "Approach",
    "R281C": "Clear",
    "C412": "Clear",
    "C413": "Clear",
    "C414": "Clear",
    "RES_LIM": "Restricting",
    "ADV_LIM": "Clear",
    "R281D": "Approach",
    "R283": "Medium Clear",
    "C417": "Medium Clear",
    "R283A": "Medium Clear",
    "R283B": "Medium Clear",
    "RES_MED": "Restricting",
    "ADV_MED": "Medium Clear",
    "R286": "Restricting",
    "R287": "Medium Clear",
    "C422": "Medium Clear",
    "C423": "Medium Clear",
    "C424": "Medium Clear",
    "RES_SLO": "Restricting",
    "ADV_SLO": "Approach Slow",
    "R288": "Restricting",
    "R292": "Stop",
    "R291": "Stop",
}

# CO-3-dwarf: Slow Clear / Restricting / Stop (no Clear/Approach).
_REMAP_1 = {
    key: (
        "Stop"
        if key in ("R291", "R292")
        else "Restricting"
        if key.startswith("RES_") or key in ("R285", "R281D", "R286", "R288")
        else "Slow Clear"
    )
    for key in _REMAP_2
}

# HOLD_ONLY listen map: unique JMRI names on the ICON that matches ABS action.
# Every value MUST be a valid (and enabled) C&O-1980 aspect on that mast type.
# CATS Block.startUp → PhysicalSignal.refresh() calls setAspect(AppearanceKey)
# even when HOLD_ONLY; placeholders like _RES_NORM abort Screen.init and freeze
# occupancy / turnout listeners.
#
# CO-33-hi: Clear G/R, Approach Medium Y/G, Medium Clear R/G, Approach Slow Y/Y,
# Approach Y/R, Restricting R/Y, Stop R/R. R286 (Medium Approach in AAR) is the
# same lamp pair as Restricting here.
_REMAP_2_LISTEN_ASPECTS = {
    "R281": "Clear",
    "R282": "Approach Medium",
    "R283": "Medium Clear",
    "R284": "Approach Slow",
    "R285": "Approach",
    "RES_NORM": "Restricting",
    "R292": "Stop",
}

# CO-3-dwarf: Slow Clear / Restricting / Stop.
_REMAP_1_LISTEN_ASPECTS = {
    "R281": "Slow Clear",
    "R285": "Restricting",
    "R292": "Stop",
}

# Fallback per ICON so unused CATS rows cannot crash setAspect, and cannot
# steal first-match from the unique names above.
_VALID_2 = {
    "CLEAR": "Clear",
    "APPROACH": "Approach",
    "RESTRICTING": "Restricting",
    "STOP": "Stop",
}
_VALID_1 = {
    "CLEAR": "Slow Clear",
    "APPROACH": "Slow Clear",
    "RESTRICTING": "Stop",
    "STOP": "Stop",
}

_PAINT_1 = {
    "Clear": "green",
    "Slow Clear": "green",
    "Approach": "yellow",
    "Stop": "red",
    "Restricting": "yellow",
}

_PAINT_2 = {
    "Clear": "green|red",
    "Approach Medium": "yellow|green",
    "Medium Clear": "red|green",
    "Approach Slow": "yellow|yellow",
    "Approach": "yellow|red",
    "Restricting": "red|yellow",
    "Stop": "red|red",
}

_PAINT_3 = {
    "Clear": "green|red|red",
    "Approach": "yellow|red|red",
    "Restricting": "yellow|red|red",
    "Stop": "red|red|red",
}


def _fill_listen(
    aspects: dict[str, str], fallback: dict[str, str]
) -> dict[str, str]:
    """Every IndicationName gets a valid mast aspect; unused rows use same-ICON fallback."""
    out = {key: fallback[_ICON[key]] for key in _INDICATION_ORDER}
    out.update(aspects)
    return out


_REMAP_2_LISTEN = _fill_listen(_REMAP_2_LISTEN_ASPECTS, _VALID_2)
_REMAP_1_LISTEN = _fill_listen(_REMAP_1_LISTEN_ASPECTS, _VALID_1)

_ALLOWED_2 = {
    "Clear",
    "Approach Medium",
    "Medium Clear",
    "Approach Slow",
    "Approach",
    "Restricting",
    "Stop",
}
_ALLOWED_1 = {"Slow Clear", "Restricting", "Stop"}

_LISTEN_2_ICON = {
    "Clear": "CLEAR",
    "Approach Medium": "CLEAR",
    "Medium Clear": "CLEAR",
    "Approach Slow": "CLEAR",
    "Approach": "APPROACH",
    "Restricting": "RESTRICTING",
    "Stop": "STOP",
}

_LISTEN_1_ICON = {
    "Slow Clear": "CLEAR",
    "Restricting": "APPROACH",
    "Stop": "STOP",
}


def _first_key(remap: dict[str, str], aspect: str) -> str | None:
    for key in _INDICATION_ORDER:
        if remap.get(key) == aspect:
            return key
    return None


def _validate_listen_remap(
    remap: dict[str, str],
    expected_icon: dict[str, str],
    allowed: set[str],
) -> None:
    bad = sorted({val for val in remap.values() if val not in allowed})
    if bad:
        raise RuntimeError(f"AAR listen map has invalid mast aspects: {bad}")
    for aspect, icon in expected_icon.items():
        key = _first_key(remap, aspect)
        if key is None:
            raise RuntimeError(f"AAR listen map missing {aspect!r}")
        got = _ICON[key]
        # Stop fallback on RES_* is RESTRICTING (same red as STOP) for dwarfs.
        if aspect == "Stop" and got in ("STOP", "RESTRICTING"):
            continue
        if got != icon:
            raise RuntimeError(
                f"AAR listen map {aspect!r} hits {key} ICON {got}, expected {icon}"
            )


_validate_listen_remap(_REMAP_2_LISTEN, _LISTEN_2_ICON, _ALLOWED_2)
_validate_listen_remap(_REMAP_1_LISTEN, _LISTEN_1_ICON, _ALLOWED_1)


def _paint_for_heads(heads: int) -> dict[str, str]:
    if heads <= 1:
        return _PAINT_1
    if heads == 2:
        return _PAINT_2
    return _PAINT_3


def apply_aar_bridge(root: ET.Element, *, hold_only: bool | None = None) -> None:
    """Stamp AAR remaps + paint keys on every SIGNALTEMPLATE / ASPECTMAP.

    hold_only: True/False set HOLD_ONLY on every ASPECTMAP; None leaves it alone.
    True also uses the unique listen map so every SML aspect paints.
    """
    n_tmpl = 0
    n_maps = 0
    listen = hold_only is True
    for tmpl in root.iter("SIGNALTEMPLATE"):
        heads = int(tmpl.get("TEMPLATEHEADS") or "1")
        if listen:
            remap = _REMAP_1_LISTEN if heads <= 1 else _REMAP_2_LISTEN
        else:
            remap = _REMAP_1 if heads <= 1 else _REMAP_2
        for key, val in remap.items():
            tmpl.set(key, val)
        n_tmpl += 1
        for am in tmpl.findall("ASPECTMAP"):
            if hold_only is True:
                am.set("HOLD_ONLY", "true")
            elif hold_only is False:
                if "HOLD_ONLY" in am.attrib:
                    del am.attrib["HOLD_ONLY"]
            # ASPECTMAP only allows IndicationNames + HOLD_ONLY. Clear/Approach/
            # Stop/Restricting as attributes make CATS print "cannot have a
            # Stop attribute" and abort Screen.init (occupancy freeze).
            allowed = set(_INDICATION_ORDER) | {"HOLD_ONLY"}
            for key in list(am.attrib):
                if key not in allowed:
                    del am.attrib[key]
            paint = _paint_for_heads(heads)
            for key, aspect in remap.items():
                color = paint.get(aspect)
                if color is not None:
                    am.set(key, color)
            n_maps += 1
    print(f"AAR bridge: {n_tmpl} SIGNALTEMPLATE remaps, {n_maps} ASPECTMAP paint keys")


def apply_file(path: Path, *, hold_only: bool | None = None) -> None:
    tree = ET.parse(path)
    apply_aar_bridge(tree.getroot(), hold_only=hold_only)
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    print(f"wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("panels", nargs="+", type=Path, help="Digicon XML files")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--hold-only", action="store_true", help="Set HOLD_ONLY=true on ASPECTMAPs")
    g.add_argument("--no-hold-only", action="store_true", help="Remove HOLD_ONLY")
    args = ap.parse_args()
    hold: bool | None
    if args.hold_only:
        hold = True
    elif args.no_hold_only:
        hold = False
    else:
        hold = None
    for p in args.panels:
        if not p.is_file():
            raise SystemExit(f"Missing {p}")
        apply_file(p, hold_only=hold)


if __name__ == "__main__":
    main()
