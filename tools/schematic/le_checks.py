"""Mast and slot checks of the Layout Editor build: every staging mast in the one slot that resolves to its blocks
(check_device_masts) and at the ident and slot le_signal_boundaries.csv records for it (check_boundaries), the main and
upper masts in theirs."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hartlib import boundaries, paths  # noqa: E402
from le_common import BuildError, slots_module  # noqa: E402


BOUNDARIES = boundaries.PATH


def mast_band(m: dict) -> int:
    """The band index the plugin placed mast `m` on (P.masts); stops naming the mast when it has none."""
    if "band" not in m:
        raise BuildError(f"mast {m.get('mast')}: the plugin gave it no band")
    return m["band"]


def check_level_slots(P, rows: list[dict], le_mod) -> None:
    """Stop when a main or upper mast (main_upper_masts.csv) is missing from the new panel, or stands in a slot
    that JMRI does not resolve to its facing track and protected OS block (a virtual mast at a buffer stop protects
    none), or (with `leg`) on the other leg of its turnout than its continuing route makes it."""
    if not rows:
        return
    ix = slots_module().Index(le_mod.to_xml(P, "check"))
    placed = {m["mast"]: m for m in P.masts if mast_band(m) != 0}
    turnouts = {P.name(t["ident"]): t for t in P.turnouts}
    bad = []
    for r in rows:
        m = placed.get(r["mast"])
        if m is None:
            bad.append(f"{r['mast']} is not on the panel")
            continue
        ident = P.name(m["ident"])
        f, pr = ix.blocks(m["kind"], ident, m["slot"])
        if (f, list(pr)) != (r["facing"], [r["protects"]] if r["protects"] else []):     # a virtual mast: a bumper
            bad.append(f"{r['mast']} at {ident} {m['slot']} faces {f} and protects {pr}, not {r['facing']} into "
                       f"{r['protects']}")
        if r["leg"]:
            normal = "B" if turnouts[ident]["continuing"] == "2" else "C"
            if (m["slot"] == normal) != (r["leg"] == "normal"):
                bad.append(f"{r['mast']} is on leg {m['slot']} of {ident}, not its {r['leg']} leg")
    if bad:
        raise BuildError("main and upper masts not where they belong: " + "; ".join(bad))


def check_unplaced(P) -> list[str]:
    """Stop on any mast the plugin could not place; a note for each buffer-stop mast moved to a helix join."""
    if P.unplaced:
        raise BuildError("masts with no matching slot on the new panel: " +
                         "; ".join(f"{mast}: {why}" for _t, mast, why in P.unplaced))
    return [f"{mast}: {why}" for _t, mast, why in P.moved]


def turnout_facts(le: ET.Element) -> dict:
    """{ident: facts} of a panel's turnouts: its turnout name, type, continuing route (not a crossover's), the four
    leg blocks and the block of the track on each leg."""
    segs = {s.get("ident"): s.get("blockname") for s in le.findall("tracksegment")}
    out = {}
    for t in le.findall("layoutturnout"):
        legs = {L: segs.get(t.get(f"connect{L.lower()}name")) for L in "ABCD" if t.get(f"connect{L.lower()}name")}
        out[t.get("ident")] = dict(name=t.get("turnoutname"), type=t.get("type"),
                                   continuing=t.get("continuing") if "XOVER" not in t.get("type") else None,
                                   blocks=tuple(t.get(a) for a in ("blockname", "blockbname", "blockcname",
                                                                     "blockdname")), legs=legs)
    return out


def check_device_masts(P, masts: list[dict], le_mod, facts: dict | None = None) -> None:
    """The device-map path's staging mast check (no frozen ident or slot to hold the panel to): stop when a staging
    mast (`masts`, the plugin's list) is not on the panel, fits more than one slot of its kind with its blocks (the
    plugin would take the first, a guess), or a turnout mast stands on another turnout than its switch's (`facts`,
    default staging_device_map.mast_facts: the turnout the device map binds the switch by), or the plugin placed a
    staging mast `masts` does not ask for."""
    import staging_device_map as sdm
    if facts is None:
        try:
            facts = sdm.mast_facts()
        except sdm.StagingMapError as exc:
            raise BuildError(f"staging device map: {exc}") from None
    ix = slots_module().Index(le_mod.to_xml(P, "check"))
    fits = defaultdict(list)
    for c in ix.candidates():
        f, pr = ix.blocks(*c)
        fits[(c[0], f, tuple(pr))].append(c)
    placed = {}
    for m in ix.masts():
        if m["mast"] in placed:
            raise BuildError(f"mast {m['mast']} is bound in two slots of the new panel")
        placed[m["mast"]] = m
    bad = []
    asked = {m["mast"] for m in masts}
    bad += [f"{name} was not asked for" for name in sorted({m["mast"] for m in P.masts if mast_band(m) == 0} - asked)]
    for m in masts:
        got = placed.get(m["mast"])
        if got is None:
            bad.append(f"{m['mast']} is not on the panel")
            continue
        same = fits[(got["kind"], got["facing"], tuple(got["protects"]))]
        if m["kind"] == "turnout":
            want = (facts.get(m["mast"]) or {}).get("turnout")
            if got.get("turnout") != want:
                bad.append(f"{m['mast']} is on turnout {got.get('turnout')}, its switch's is {want}")
            same = [c for c in same if ix.turnouts[c[1]].get("turnoutname") == want]
        if len(same) > 1:
            bad.append(f"{m['mast']} fits {len(same)} slots ({', '.join(f'{c[1]} {c[2]}' for c in same)}): which "
                       "one is a guess")
    if bad:
        raise BuildError("staging masts not placed for certain: " + "; ".join(bad))


def check_boundaries(panel: ET.Element, path: Path = BOUNDARIES) -> None:
    """Stop unless every mast of le_signal_boundaries.csv stands on `panel` (a generated panel) in the kind of slot,
    at the ident and in the slot its row records. The anchor idents are generated, so a change to the staging drawing can renumber
    them; this stops the build then, naming each row, rather than leave the audits, apply_le_sml_facing.py and the
    boundary contract on the wrong anchor. Rewrite the named rows from the new panel."""
    placed = {m["mast"]: m for m in slots_module().Index(panel).masts()}
    bad = []
    try:
        rows = boundaries.read(path)
    except ValueError as exc:
        raise BuildError(str(exc)) from None
    for b in rows:
        name, want = b.mast, (b.kind, b.ident, b.slot)
        m = placed.get(name)
        got = (m["kind"], m["ident"], m["slot"]) if m else None
        if got != want:
            bad.append(f"{name}: recorded {' '.join(want)}, drawn {' '.join(got) if got else 'nowhere'}")
    if bad:
        raise BuildError(f"{paths.rel(path)} does not follow the drawn panel (rewrite these rows from it): "
                         + "; ".join(bad))
