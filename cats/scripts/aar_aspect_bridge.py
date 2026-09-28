#!/usr/bin/env python3
"""Bridge Digicon R-code templates to JMRI basic-enhanced aspect names.

CATS stock templates call setAspect("R281"|…). Homes are
basic-enhanced two-searchlight-high and dwarfs are one-searchlight-low.
Flashing aspects (Advanced Approach, Diverging Advanced Approach) are disabled
on the masts, so setAspect may only request Clear, Approach, Stop, Diverging
Clear, and Diverging Approach (dwarfs: Clear, Approach, Stop). HOLD_ONLY panels
need AppearanceKey values that match those enabled names so Digicon can paint
from SML. Do not alias RES_* to Approach on 2-head templates: CATS reverse
lookup is first-match, and RES_NORM sits before R285 (Approach would paint as
Restricting). Aspect names with spaces cannot be XML attribute names.

HOLD_ONLY (ABS-RO / CTC SML): map every aspect SML can post onto a unique
IndicationNames row whose ICON class is the closest one-disc ABS action
(CLEAR=green proceed, APPROACH=yellow caution, STOP=red). CATS cannot draw
two searchlights; unused CATS rows get a same-ICON fallback so they cannot
steal a match.

When CATS drives aspects (no HOLD_ONLY), request only those enabled names.

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

# CATS IndicationName → basic-enhanced aspect (setAspect) when CATS drives the mast.
# Enabled two-head aspects: Clear G/R, Approach Y/R, Diverging Clear R/G,
# Diverging Approach R/Y, Stop R/R. Y/G and Y/Y have no enabled aspect.
_REMAP_2 = {
    "R281": "Clear",
    "R281B": "Clear",
    "R282": "Approach",
    "R284": "Approach",
    "RES_NORM": "Diverging Approach",
    "ADV_NORM": "Clear",
    "R285": "Approach",
    "R281C": "Clear",
    "C412": "Clear",
    "C413": "Clear",
    "C414": "Clear",
    "RES_LIM": "Diverging Approach",
    "ADV_LIM": "Clear",
    "R281D": "Approach",
    "R283": "Diverging Clear",
    "C417": "Diverging Clear",
    "R283A": "Diverging Clear",
    "R283B": "Diverging Clear",
    "RES_MED": "Diverging Approach",
    "ADV_MED": "Diverging Clear",
    "R286": "Diverging Approach",
    "R287": "Diverging Clear",
    "C422": "Diverging Clear",
    "C423": "Diverging Clear",
    "C424": "Diverging Clear",
    "RES_SLO": "Diverging Approach",
    "ADV_SLO": "Approach",
    "R288": "Diverging Approach",
    "R292": "Stop",
    "R291": "Stop",
}

# one-searchlight-low: Clear / Approach / Stop.
_REMAP_1 = {
    key: (
        "Stop"
        if key in ("R291", "R292")
        else "Approach"
        if key.startswith("RES_") or key.startswith("ADV_") or key in ("R285", "R281D", "R286", "R288")
        else "Clear"
    )
    for key in _REMAP_2
}

# HOLD_ONLY listen map: unique JMRI names on the ICON that matches ABS action.
# Every value MUST be an enabled basic-enhanced aspect on that mast type.
# CATS Block.startUp → PhysicalSignal.refresh() calls setAspect(AppearanceKey)
# even when HOLD_ONLY; a disabled or unknown name aborts Screen.init and freezes
# occupancy / turnout listeners.
#
# two-searchlight-high, flash aspects disabled: Clear G/R, Approach Y/R,
# Diverging Clear R/G, Diverging Approach R/Y, Stop R/R.
_REMAP_2_LISTEN_ASPECTS = {
    "R281": "Clear",
    "R283": "Diverging Clear",
    "R285": "Approach",
    "RES_NORM": "Diverging Approach",
    "R292": "Stop",
}

# one-searchlight-low: Clear / Approach / Stop. No Diverging aspects.
_REMAP_1_LISTEN_ASPECTS = {
    "R281": "Clear",
    "R285": "Approach",
    "R292": "Stop",
}

# Fallback per ICON so unused CATS rows cannot crash setAspect, and cannot
# steal first-match from the unique names above.
_VALID_2 = {
    "CLEAR": "Clear",
    "APPROACH": "Approach",
    "RESTRICTING": "Diverging Approach",
    "STOP": "Stop",
}
_VALID_1 = {
    "CLEAR": "Clear",
    "APPROACH": "Approach",
    "RESTRICTING": "Stop",
    "STOP": "Stop",
}

_PAINT_1 = {
    "Clear": "green",
    "Approach": "yellow",
    "Stop": "red",
}

_PAINT_2 = {
    "Clear": "green|red",
    "Approach": "yellow|red",
    "Diverging Clear": "red|green",
    "Diverging Approach": "red|yellow",
    "Stop": "red|red",
}

_PAINT_3 = {
    "Clear": "green|red|red",
    "Approach": "yellow|red|red",
    "Diverging Clear": "red|green|red",
    "Diverging Approach": "red|yellow|red",
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
    "Approach",
    "Diverging Clear",
    "Diverging Approach",
    "Stop",
}
_ALLOWED_1 = {"Clear", "Approach", "Stop"}

_LISTEN_2_ICON = {
    "Clear": "CLEAR",
    "Diverging Clear": "CLEAR",
    "Approach": "APPROACH",
    "Diverging Approach": "RESTRICTING",
    "Stop": "STOP",
}

_LISTEN_1_ICON = {
    "Clear": "CLEAR",
    "Approach": "APPROACH",
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
