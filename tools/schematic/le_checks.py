"""Mast and slot checks of the Layout Editor build: every live staging mast in the slot that resolves to its blocks,
the main and upper masts in theirs, and the live turnouts' legs kept."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hartlib import paths  # noqa: E402
from le_common import BuildError, read_csv, slots_module  # noqa: E402
from le_names import swap_legs, swapped_idents  # noqa: E402


BOUNDARIES = paths.LAYOUT_DATA / "le_signal_boundaries.csv"


def check_swapped_slots(path: Path = BOUNDARIES) -> None:
    """Stop when le_signal_boundaries.csv's generated_slot column and LEGS_SWAPPED disagree: every turnout row on a
    swapped switch's leg B or C gives the other letter as its generated_slot, and no other row gives one (the
    audits and apply_le_sml_facing.py read the column; this build reads LEGS_SWAPPED)."""
    swapped = swapped_idents()
    bad = []
    for row in read_csv(path):
        slot, gen = row["slot"].strip(), (row.get("generated_slot") or "").strip()
        swaps = row["kind"].strip() == "turnout" and row["ident"].strip() in swapped and slot in ("B", "C")
        want = "BC".replace(slot, "") if swaps else ""
        if gen != want:
            bad.append(f"{row['ident']} {slot} ({row['mast_user_name']}): generated_slot {gen or 'empty'}, "
                       f"LEGS_SWAPPED gives {want or 'empty'}")
    if bad:
        raise BuildError(f"{paths.rel(path)} and LEGS_SWAPPED disagree: " + "; ".join(bad))


def check_slots(P, masts: list[dict], le_mod) -> None:
    """Stop when a staging mast could have gone in more than one slot of the new panel (the plugin would take the
    first), a turnout mast is on another turnout than live, or a mast stands in another slot (ident and slot) than
    masts.csv gives, so a hand edit of those columns takes effect or fails (`masts`: masts.csv's rows)."""
    slots = slots_module()
    ix = slots.Index(le_mod.to_xml(P, "check"))
    alias = P.name          # the XML holds the idents as written; the Panel's lookups keep the generated ones
    staging = {alias(t["ident"]) for t in P.turnouts if t["band"] == 0} | \
        {alias(k) for k, p in P.points.items() if p["band"] == 0}
    fits = defaultdict(list)
    for c in ix.candidates():
        if c[1] in staging:
            f, pr = ix.blocks(*c)
            fits[(c[0], f, tuple(pr))].append(c)
    want = {m["mast"]: m for m in masts}
    swapped = swapped_idents()
    moved = {mast for _t, mast, _why in P.moved}       # a bumper mast at a helix join (all-levels trial): elsewhere
    bad = []
    for m in P.masts:
        if mast_band(m) != 0:           # main and upper: check_level_slots
            continue
        name = m["mast"]
        if name not in want:
            bad.append(f"{name} was not asked for")
            continue
        placed = (alias(m["ident"]), m["slot"])
        slot = want[name]["slot"]
        if want[name]["kind"] == "turnout" and want[name]["ident"] in swapped and slot in "BC":
            slot = "BC".replace(slot, "")          # LEGS_SWAPPED: the mast moves with its leg
        frozen = (want[name]["ident"], slot)
        if name not in moved and placed != frozen:
            bad.append(f"{name} stands at {placed[0]} {placed[1]}, masts.csv says {frozen[0]} {frozen[1]}")
        f, pr = ix.blocks(m["kind"], alias(m["ident"]), m["slot"])
        same = fits[(m["kind"], f, tuple(pr))]
        if want[name]["kind"] == "turnout":
            here = ix.turnouts[alias(m["ident"])].get("turnoutname")
            if here != want[name]["turnout"]:
                bad.append(f"{name} is on turnout {here}, live on {want[name]['turnout']}")
            same = [c for c in same if ix.turnouts[c[1]].get("turnoutname") == want[name]["turnout"]]
        if len(same) > 1:
            bad.append(f"{name} fits {len(same)} slots ({', '.join(f'{c[1]} {c[2]}' for c in same)}): which one is a "
                       "guess")
    if bad:
        raise BuildError("staging masts not placed for certain: " + "; ".join(bad))


def mast_band(m: dict) -> int:
    """The band index the plugin placed mast `m` on (P.masts); stops naming the mast when it has none."""
    if "band" not in m:
        raise BuildError(f"mast {m.get('mast')}: the plugin gave it no band")
    return m["band"]


def check_level_slots(P, rows: list[dict], le_mod) -> None:
    """Stop when a main or upper mast (main_upper_masts.csv) is missing from the new panel, or stands in a slot
    that JMRI does not resolve to its facing track and protected OS block, or (with `leg`) on the other leg of its
    turnout than its continuing route makes it."""
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
        if (f, list(pr)) != (r["facing"], [r["protects"]]):
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
    """{ident: facts} of a panel's turnouts as check_live_turnouts compares them (le_inputs.Inputs.turnout_facts)."""
    segs = {s.get("ident"): s.get("blockname") for s in le.findall("tracksegment")}
    out = {}
    for t in le.findall("layoutturnout"):
        legs = {L: segs.get(t.get(f"connect{L.lower()}name")) for L in "ABCD" if t.get(f"connect{L.lower()}name")}
        out[t.get("ident")] = dict(name=t.get("turnoutname"), type=t.get("type"),
                                   continuing=t.get("continuing") if "XOVER" not in t.get("type") else None,
                                   blocks=tuple(t.get(a) for a in ("blockname", "blockbname", "blockcname",
                                                                     "blockdname")), legs=legs)
    return out


def check_live_turnouts(gen_le: ET.Element, inputs, swapped: set | None = None) -> None:
    """Stop unless each staging turnout keeps its live ident, name, type, continuing route, leg blocks and the block
    of the track on each leg, as turnouts.csv and tracks.csv hold them (leg letters are what the boundaries
    contract, switch_legs.csv and CATS key on); a turnout in `swapped` (default: the LEGS_SWAPPED ones) with its
    legs B and C swapped (swap_legs)."""
    live, gen = inputs.turnout_facts(), turnout_facts(gen_le)
    swapped = swapped_idents() if swapped is None else swapped
    live = {i: swap_legs(f) if i in swapped else f for i, f in live.items()}
    bad = []
    for ident, want in sorted(live.items()):
        got = gen.get(ident)
        if got is None:
            bad.append(f"{ident} ({want['name']}) is not on the new panel")
            continue
        for k in want:
            if got[k] != want[k]:
                bad.append(f"{ident} ({want['name']}) {k}: live {want[k]}, new {got[k]}")
    if bad:
        raise BuildError("staging turnouts differ from the live panel: " + "; ".join(bad))
