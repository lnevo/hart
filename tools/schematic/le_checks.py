"""Mast and slot checks of the Layout Editor build: every mast of every level in the one slot that resolves to its
blocks, on its switch's turnout and leg (check_masts, with mast_turnouts)."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from le_common import BuildError, slots_module  # noqa: E402
from hartlib import level_masts as level_masts_lib  # noqa: E402  main_upper_masts.csv's virtual masts


def mast_turnouts(rows: list[dict], facts: dict | None = None) -> dict[str, tuple[str, str | None, str]]:
    """{mast: (the mast file that lists it, the turnout name the panel binds its switch by or None, its kind of slot
    there)} of every mast of both mast files, the turnout from each file's `switch`: staging_masts.csv's through the
    device map's turnout row (`facts`, default staging_device_map.mast_facts: its jmri_name), main_upper_masts.csv's
    (`rows`, read_level_masts) as the device map's turnout user name, "Switch <switch>" (le_names.level_names names
    those turnouts by it). Only a turnout mast has a switch; a virtual mast is an end bumper one. Stops on a mast both
    files list."""
    import staging_device_map as sdm
    if facts is None:
        try:
            facts = sdm.mast_facts()
        except sdm.StagingMapError as exc:
            raise BuildError(f"staging device map: {exc}") from None
    out = {mast: ("staging_masts.csv", f["turnout"] if f["kind"] == "turnout" else None, f["kind"])
           for mast, f in facts.items()}
    both = sorted(set(facts) & {r["mast"] for r in rows})
    if both:
        raise BuildError(f"staging_masts.csv and main_upper_masts.csv both list {', '.join(both)}")
    for r in rows:      # as le_names.level_masts gives each its kind of slot
        if level_masts_lib.is_level_virtual(r["system_name"]):
            out[r["mast"]] = ("main_upper_masts.csv", None, "end bumper")
        elif r["switch"]:
            out[r["mast"]] = ("main_upper_masts.csv", f"Switch {r['switch']}", "turnout")
        else:
            out[r["mast"]] = ("main_upper_masts.csv", None, "anchor")
    return out


def check_masts(P, masts: dict[str, list[dict]], le_mod, turnouts: dict[str, str]) -> None:
    """Every level's masts against the new panel (`masts`: {band key: the plugin's masts of that band, each with its
    kind of slot, facing and protected blocks and, for one of two masts on one turnout, its `leg`}). Stop when a mast
    is not on the panel or is bound in two slots; stands in a slot of another kind, or one JMRI does not resolve to
    its facing and protected blocks (a virtual mast at a buffer stop protects none); fits more than one slot of its
    kind with its blocks (on its switch's turnout and its leg, for a turnout mast: the plugin would take the first, a
    guess); stands on another turnout than its switch's (`turnouts`: mast_turnouts) or on the other leg than its
    `leg`; or when the plugin placed a mast no band asks for. One check for every level: no frozen ident or slot
    holds the panel."""
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
    asked, bad = {}, []
    for key, band_masts in masts.items():
        for m in band_masts:
            if m["mast"] in asked:
                bad.append(f"{m['mast']} is asked for on {asked[m['mast']][0]} and {key}")
            asked[m["mast"]] = (key, m)
    bad += [f"{name} was not asked for" for name in sorted(set(placed) - set(asked))]
    for name, (key, m) in asked.items():
        got = placed.get(name)
        if got is None:
            bad.append(f"{name} ({key}) is not on the panel")
            continue
        where = f"{name} ({key}) at {got['ident']} {got['slot']}"
        if (got["facing"], list(got["protects"])) != (m["facing"], list(m["protects"])):
            bad.append(f"{where} faces {got['facing']} and protects {got['protects']}, not {m['facing']} into "
                       f"{m['protects']}")
        if got["kind"] != m["kind"]:        # its turnout, leg and other slots mean nothing in a slot of another kind
            bad.append(f"{where} is in a {got['kind']} slot, not a {m['kind']} one")
            continue
        same = fits[(got["kind"], got["facing"], tuple(got["protects"]))]
        if m["kind"] == "turnout":
            source, want, kind = turnouts.get(name, (None, None, None))
            if source is None:
                bad.append(f"{name} ({key}) is a turnout mast on the panel, but neither staging_masts.csv nor "
                           "main_upper_masts.csv lists it (mast_turnouts)")
            elif want is None:
                bad.append(f"{name} ({key}) is a turnout mast on the panel, but {source} gives it no switch (a {kind} "
                           "mast there)")
            elif got.get("turnout") != want:
                bad.append(f"{name} ({key}) is on turnout {got.get('turnout')}, its switch's is {want} ({source})")
            same = [c for c in same if ix.turnouts[c[1]].get("turnoutname") == want]
        if m.get("leg"):                    # a turnout mast (the plugin allows a leg on no other kind)
            def normal(c):
                return "B" if ix.turnouts[c[1]].get("continuing") == "2" else "C"
            if got["slot"] not in ("B", "C"):
                bad.append(f"{name} ({key}) has leg {m['leg']} but stands on leg {got['slot']} of {got['ident']}, "
                           "not B or C")
            elif (got["slot"] == normal((got["kind"], got["ident"]))) != (m["leg"] == "normal"):
                bad.append(f"{name} ({key}) is on leg {got['slot']} of {got['ident']}, not its {m['leg']} leg")
            same = [c for c in same if c[2] in ("B", "C") and (c[2] == normal(c)) == (m["leg"] == "normal")]
        if len(same) > 1:
            bad.append(f"{name} ({key}) fits {len(same)} slots ({', '.join(f'{c[1]} {c[2]}' for c in same)}): which "
                       "one is a guess")
    if bad:
        raise BuildError("masts not placed for certain: " + "; ".join(bad))


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
