#!/usr/bin/env python3
"""Static Layout Editor signalling validator + SML mini-discovery.

Validates tables/new_tables.xml for JMRI native SML discovery readiness
WITHOUT launching JMRI, then simulates discovery (path-walk from every
mast to the next facing mast) and diffs the result against the CATS
oracle PAIRS in cats/scripts/apply_sml_cats_pairs.py.

Semantics are transcribed from JMRI source (LayoutTurnout.java,
PositionablePoint.java, LayoutBlockManager.getFacingBean,
LayoutEditorTools.isAtWestEndOfAnchor):

- A mast bound at turnout connection X (signalXMast) faces the external
  block connected at X and protects into the turnout: it governs trains
  ENTERING the turnout at X.
- Crossovers: A-B and C-D are straight routes (state = continuing attr,
  normally CLOSED); the diagonal is A-C on RH_XOVER, B-D on LH_XOVER
  (state = diverging); B-C / A-D are illegal. Corner blocks B/C/D
  default to A's block when unset.
- Anchor boundaries: the "eastbound" mast faces the segment whose far
  end is more west; when the boundary is primarily vertical, more NORTH
  counts as west (isAtWestEndOfAnchor). A train crossing the anchor from
  the west/north segment faces the eastbound mast.

Usage:
  python3 cats/scripts/validate_le_signalling.py            # checks + diff
  python3 cats/scripts/validate_le_signalling.py --dests    # per-mast dests
  python3 cats/scripts/validate_le_signalling.py --strict   # fail on diff
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_XML = ROOT / "tables/new_tables.xml"
DEFAULT_CSV = ROOT / "cats/data/le_signal_boundaries.csv"
ORACLE = ROOT / "cats/scripts/apply_sml_cats_pairs.py"

PORTS = "ABCD"
XOVER_TYPES = {"RH_XOVER", "LH_XOVER", "DOUBLE_XOVER"}
SIMPLE_TYPES = {"RH_TURNOUT", "LH_TURNOUT", "WYE_TURNOUT"}


@dataclass
class Turnout:
    ident: str
    ttype: str
    continuing: int
    turnout_user: str
    blocks: dict[str, str | None]
    connects: dict[str, str | None]
    masts: dict[str, str | None]
    coords: dict[str, tuple[float, float]]


@dataclass
class Segment:
    ident: str
    block: str | None
    ends: list[tuple[str, str]]  # (connect name, type)


@dataclass
class Point:
    ident: str
    ptype: str
    x: float
    y: float
    connects: list[str]
    east_mast: str | None = None
    west_mast: str | None = None


@dataclass
class Model:
    blockrouting: str | None = None
    layoutblocks: dict[str, str | None] = field(default_factory=dict)  # user -> sensor
    turnouts: dict[str, Turnout] = field(default_factory=dict)
    segments: dict[str, Segment] = field(default_factory=dict)
    points: dict[str, Point] = field(default_factory=dict)
    masts: list[str] = field(default_factory=list)  # user names
    turnout_user_by_any: dict[str, str] = field(default_factory=dict)


def parse(xml_path: Path) -> Model:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    m = Model()

    lbs = root.find("layoutblocks")
    if lbs is not None:
        m.blockrouting = lbs.get("blockrouting")
        for lb in lbs.findall("layoutblock"):
            user = lb.findtext("userName") or lb.get("userName")
            m.layoutblocks[user] = lb.get("occupancysensor")

    for t in root.iter("turnout"):
        sysname = t.findtext("systemName")
        user = t.findtext("userName")
        if sysname:
            m.turnout_user_by_any[sysname] = user or sysname
        if user:
            m.turnout_user_by_any[user] = user

    for sm in root.iter("signalmast"):
        user = sm.findtext("userName")
        if user:
            m.masts.append(user)

    le = root.find("LayoutEditor")
    if le is None:
        raise SystemExit("no LayoutEditor element found")

    for lt in le.findall("layoutturnout"):
        ident = lt.get("ident")
        blocks = {"A": lt.get("blockname")}
        blocks["B"] = lt.get("blockbname")
        blocks["C"] = lt.get("blockcname")
        blocks["D"] = lt.get("blockdname")
        connects = {p: lt.get(f"connect{p.lower()}name") for p in PORTS}
        masts = {p: lt.findtext(f"signal{p}Mast") for p in PORTS}
        coords = {}
        for p in PORTS:
            xs, ys = lt.get(f"x{p.lower()}"), lt.get(f"y{p.lower()}")
            if xs is not None and ys is not None:
                coords[p] = (float(xs), float(ys))
        tname = lt.get("turnoutname") or ""
        m.turnouts[ident] = Turnout(
            ident=ident,
            ttype=lt.get("type"),
            continuing=int(lt.get("continuing", "2")),
            turnout_user=m.turnout_user_by_any.get(tname, tname),
            blocks=blocks,
            connects=connects,
            masts=masts,
            coords=coords,
        )

    for ts in le.findall("tracksegment"):
        m.segments[ts.get("ident")] = Segment(
            ident=ts.get("ident"),
            block=ts.get("blockname"),
            ends=[
                (ts.get("connect1name"), ts.get("type1")),
                (ts.get("connect2name"), ts.get("type2")),
            ],
        )

    for pp in le.findall("positionablepoint"):
        m.points[pp.get("ident")] = Point(
            ident=pp.get("ident"),
            ptype=pp.get("type"),
            x=float(pp.get("x", "0")),
            y=float(pp.get("y", "0")),
            connects=[c for c in (pp.get("connect1name"), pp.get("connect2name")) if c],
            east_mast=pp.get("eastboundsignalmast"),
            west_mast=pp.get("westboundsignalmast"),
        )
    return m


def corner_block(t: Turnout, port: str) -> str | None:
    """JMRI defaulting: B/C/D fall back to block A."""
    return t.blocks.get(port) or t.blocks["A"]


def routes_from(t: Turnout, port: str) -> list[tuple[str, str]]:
    """Legal (exit_port, required_state) routes entering turnout at port."""
    cont = "closed" if t.continuing == 2 else "thrown"
    div = "thrown" if t.continuing == 2 else "closed"
    if t.ttype in SIMPLE_TYPES:
        if port == "A":
            return [("B", cont), ("C", div)]
        if port == "B":
            return [("A", cont)]
        if port == "C":
            return [("A", div)]
        return []
    if t.ttype == "RH_XOVER":
        table = {"A": [("B", cont), ("C", div)], "B": [("A", cont)],
                 "C": [("D", cont), ("A", div)], "D": [("C", cont)]}
    elif t.ttype == "LH_XOVER":
        table = {"A": [("B", cont)], "B": [("A", cont), ("D", div)],
                 "C": [("D", cont)], "D": [("C", cont), ("B", div)]}
    elif t.ttype == "DOUBLE_XOVER":
        table = {"A": [("B", cont), ("C", div)], "B": [("A", cont), ("D", div)],
                 "C": [("D", cont), ("A", div)], "D": [("C", cont), ("B", div)]}
    else:
        table = {}
    return table.get(port, [])


def endpoint_coords(m: Model, name: str, ctype: str) -> tuple[float, float] | None:
    if ctype == "POS_POINT":
        p = m.points.get(name)
        return (p.x, p.y) if p else None
    if ctype and ctype.startswith("TURNOUT_"):
        t = m.turnouts.get(name)
        return t.coords.get(ctype[-1]) if t else None
    return None


def far_end_coords(m: Model, seg: Segment, anchor: str) -> tuple[float, float] | None:
    for name, ctype in seg.ends:
        if not (ctype == "POS_POINT" and name == anchor):
            return endpoint_coords(m, name, ctype)
    return None


def is_west_end(m: Model, seg: Segment, other: Segment, anchor: str) -> bool:
    """Transcription of LayoutEditorTools.isAtWestEndOfAnchor."""
    c1 = far_end_coords(m, seg, anchor)
    c2 = far_end_coords(m, other, anchor)
    if c1 is None or c2 is None:
        return True
    dx, dy = c1[0] - c2[0], c1[1] - c2[1]
    if abs(dx) > 2.0 * abs(dy):
        return dx <= 0.0
    if abs(dy) > 2.0 * abs(dx):
        return dy <= 0.0
    return dx <= 0.0


def external_block(m: Model, t: Turnout, port: str) -> str | None:
    """Block of the track connected at a turnout port."""
    name = t.connects.get(port)
    if name in m.segments:
        return m.segments[name].block
    if name in m.turnouts:
        # direct turnout-to-turnout link; find which port of the peer points back
        peer = m.turnouts[name]
        for p in PORTS:
            if peer.connects.get(p) == t.ident:
                return corner_block(peer, p)
    return None


@dataclass
class MastSite:
    mast: str
    kind: str            # "turnout" | "anchor"
    ident: str
    port: str            # A-D or "east"/"west"
    facing_block: str | None
    protected_block: str | None


def mast_sites(m: Model) -> list[MastSite]:
    sites = []
    for t in m.turnouts.values():
        for p in PORTS:
            mast = t.masts.get(p)
            if mast:
                sites.append(MastSite(
                    mast=mast, kind="turnout", ident=t.ident, port=p,
                    facing_block=external_block(m, t, p),
                    protected_block=corner_block(t, p),
                ))
    for pt in m.points.values():
        if not (pt.east_mast or pt.west_mast):
            continue
        segs = [m.segments.get(c) for c in pt.connects]
        if len(segs) != 2 or None in segs:
            continue
        s1, s2 = segs
        west_seg, east_seg = (s1, s2) if is_west_end(m, s1, s2, pt.ident) else (s2, s1)
        if pt.east_mast:
            sites.append(MastSite(pt.east_mast, "anchor", pt.ident, "east",
                                  facing_block=west_seg.block, protected_block=east_seg.block))
        if pt.west_mast:
            sites.append(MastSite(pt.west_mast, "anchor", pt.ident, "west",
                                  facing_block=east_seg.block, protected_block=west_seg.block))
    return sites


@dataclass
class Dest:
    mast: str
    blocks: list[str]
    turnouts: list[tuple[str, str]]
    note: str = ""


def walk_from_site(m: Model, site: MastSite, max_hops: int = 80) -> list[Dest]:
    """Simulate a train passing the mast; find every next facing mast."""
    dests: list[Dest] = []

    def add_block(blocks: list[str], b: str | None):
        if b and (not blocks or blocks[-1] != b):
            blocks.append(b)

    def enter_segment(seg: Segment, from_name: str, blocks, tstates, visited, hops):
        """Traverse segment entered from entity `from_name`; continue past far end."""
        if hops > max_hops:
            return
        key = ("seg", seg.ident, from_name)
        if key in visited:
            return
        visited = visited | {key}
        blocks = list(blocks)
        add_block(blocks, seg.block)
        for name, ctype in seg.ends:
            if name == from_name:
                continue
            if ctype == "POS_POINT":
                pt = m.points.get(name)
                if pt is None or pt.ptype == "END_BUMPER":
                    dests.append(Dest("", blocks, sorted(tstates.items()),
                                      note="end of track"))
                    return
                other_names = [c for c in pt.connects if c != seg.ident]
                if not other_names:
                    dests.append(Dest("", blocks, sorted(tstates.items()),
                                      note="end of track"))
                    return
                other = m.segments.get(other_names[0])
                if other is None:
                    return
                # facing mast at the anchor?
                if pt.east_mast or pt.west_mast:
                    seg_is_west = is_west_end(m, seg, other, pt.ident)
                    facing = pt.east_mast if seg_is_west else pt.west_mast
                    if facing:
                        add_block(blocks, other.block)
                        dests.append(Dest(facing, blocks, sorted(tstates.items())))
                        return
                enter_segment(other, name, blocks, tstates, visited, hops + 1)
                return
            if ctype and ctype.startswith("TURNOUT_"):
                enter_turnout(m.turnouts[name], ctype[-1], blocks, tstates,
                              visited, hops + 1)
                return

    def enter_turnout(t: Turnout, port: str, blocks, tstates, visited, hops):
        if hops > max_hops:
            return
        key = ("to", t.ident, port)
        if key in visited:
            return
        visited = visited | {key}
        mast = t.masts.get(port)
        if mast:
            blocks = list(blocks)
            add_block(blocks, corner_block(t, port))
            dests.append(Dest(mast, blocks, sorted(tstates.items())))
            return
        for exit_port, state in routes_from(t, port):
            tu = t.turnout_user
            if tu in tstates and tstates[tu] != state:
                continue  # conflicting requirement on same turnout
            nts = dict(tstates)
            nts[tu] = state
            nb = list(blocks)
            add_block(nb, corner_block(t, port))
            add_block(nb, corner_block(t, exit_port))
            nxt = t.connects.get(exit_port)
            if nxt in m.segments:
                enter_segment(m.segments[nxt], t.ident, nb, nts, visited, hops + 1)
            elif nxt in m.turnouts:
                peer = m.turnouts[nxt]
                for p in PORTS:
                    if peer.connects.get(p) == t.ident:
                        enter_turnout(peer, p, nb, nts, visited, hops + 1)
                        break

    # launch: the train has just passed the mast, entering the protected side
    if site.kind == "turnout":
        t = m.turnouts[site.ident]
        for exit_port, state in routes_from(t, site.port):
            tstates = {t.turnout_user: state}
            blocks: list[str] = []
            add_block(blocks, corner_block(t, site.port))
            add_block(blocks, corner_block(t, exit_port))
            nxt = t.connects.get(exit_port)
            visited = {("to", t.ident, site.port)}
            if nxt in m.segments:
                enter_segment(m.segments[nxt], t.ident, blocks, tstates, visited, 1)
            elif nxt in m.turnouts:
                peer = m.turnouts[nxt]
                for p in PORTS:
                    if peer.connects.get(p) == t.ident:
                        enter_turnout(peer, p, blocks, tstates, visited, 1)
                        break
    else:
        pt = m.points[site.ident]
        segs = [m.segments.get(c) for c in pt.connects]
        s1, s2 = segs
        west_seg, east_seg = (s1, s2) if is_west_end(m, s1, s2, pt.ident) else (s2, s1)
        into = east_seg if site.port == "east" else west_seg
        blocks: list[str] = []
        enter_segment(into, pt.ident, blocks, {}, set(), 1)

    return dests


def load_oracle() -> list[tuple[str, str, list[str], list[tuple[str, str]]]]:
    spec = importlib.util.spec_from_file_location("apply_sml_cats_pairs", ORACLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PAIRS


def load_stored_sml(xml_path: Path) -> list[tuple[str, str, str]]:
    """(source, dest, useLayoutEditor) triples from <signalmastlogics>."""
    root = ET.parse(xml_path).getroot()
    smls = root.find("signalmastlogics")
    out = []
    if smls is None:
        return out
    for sml in smls.findall("signalmastlogic"):
        src = sml.findtext("sourceSignalMast")
        for dm in sml.findall("destinationMast"):
            out.append((src, dm.findtext("destinationSignalMast"),
                        dm.findtext("useLayoutEditor") or "?"))
    return out


def load_boundary_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--xml", type=Path, default=DEFAULT_XML)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--dests", action="store_true", help="print per-mast computed dests")
    ap.add_argument("--strict", action="store_true", help="exit 1 on oracle diff too")
    ap.add_argument("--compare-stored", action="store_true",
                    help="diff computed dests vs stored <signalmastlogics> (regression check)")
    args = ap.parse_args()

    m = parse(args.xml)
    errors: list[str] = []
    warnings: list[str] = []

    # --- static checks -------------------------------------------------
    if m.blockrouting != "yes":
        errors.append(f"layoutblocks blockrouting={m.blockrouting!r} (need 'yes')")

    geom_blocks: set[str] = set()
    for s in m.segments.values():
        if not s.block:
            errors.append(f"segment {s.ident} has no blockname")
        else:
            geom_blocks.add(s.block)
    for t in m.turnouts.values():
        if not t.blocks["A"]:
            errors.append(f"turnout {t.ident} has no blockname")
        for p in PORTS:
            b = corner_block(t, p)
            if b:
                geom_blocks.add(b)
        if t.continuing not in (2, 4):
            errors.append(f"turnout {t.ident} continuing={t.continuing} (need 2 or 4)")

    for user, sensor in m.layoutblocks.items():
        if not sensor:
            errors.append(f"layoutblock {user!r} has no occupancy sensor")
        if user not in geom_blocks:
            errors.append(f"layoutblock {user!r} not attached to any track geometry")
    for b in sorted(geom_blocks):
        if b not in m.layoutblocks:
            errors.append(f"geometry block {b!r} missing from layoutblock table")

    sites = mast_sites(m)
    bound = {}
    for s in sites:
        bound.setdefault(s.mast, []).append(s)
    for mast, ss in bound.items():
        if len(ss) > 1:
            errors.append(f"mast {mast!r} bound at {len(ss)} boundaries: "
                          + ", ".join(f"{x.ident}.{x.port}" for x in ss))
        if mast not in m.masts:
            errors.append(f"bound mast {mast!r} not in signalmast table")
    for mast in m.masts:
        if mast not in bound:
            errors.append(f"mast {mast!r} not bound to any boundary")

    for s in sites:
        if s.facing_block is None or s.protected_block is None:
            errors.append(f"mast {s.mast!r} at {s.ident}.{s.port}: unresolved "
                          f"facing={s.facing_block!r} protected={s.protected_block!r}")
        elif s.facing_block == s.protected_block:
            errors.append(f"mast {s.mast!r} at {s.ident}.{s.port}: NOT a block "
                          f"boundary (both sides {s.facing_block!r}) — discovery "
                          f"cannot use this mast")

    # CSV cross-check
    csv_rows = load_boundary_csv(args.csv)
    csv_set = set()
    for row in csv_rows:
        slot = row["slot"].strip()
        key = (row["kind"].strip(), row["ident"].strip(),
               slot.upper() if row["kind"].strip() == "turnout" else slot.lower())
        csv_set.add((key, row["mast_user_name"].strip()))
    xml_set = set()
    for s in sites:
        key = (s.kind, s.ident, s.port.upper() if s.kind == "turnout" else s.port)
        xml_set.add((key, s.mast))
    for key, mast in sorted(csv_set - xml_set):
        warnings.append(f"CSV has {key[0]} {key[1]}.{key[2]} = {mast!r} but XML differs")
    for key, mast in sorted(xml_set - csv_set):
        warnings.append(f"XML has {key[0]} {key[1]}.{key[2]} = {mast!r} but CSV differs")

    # --- mini-discovery ------------------------------------------------
    computed: dict[str, list[Dest]] = {}
    for s in sites:
        if s.facing_block == s.protected_block:
            continue
        found = walk_from_site(m, s)
        real = [d for d in found if d.mast]
        deadends = [d for d in found if not d.mast]
        computed[s.mast] = real
        if not real and deadends:
            warnings.append(f"mast {s.mast!r}: no onward mast on any route "
                            f"(ends of track: {len(deadends)}) — discovery will "
                            f"produce no pairs for this mast")

    if args.dests:
        print("=== computed dests (mini-discovery) ===")
        for mast in sorted(computed):
            for d in computed[mast]:
                tstr = ", ".join(f"{n}={st}" for n, st in d.turnouts) or "-"
                print(f"  {mast}  ->  {d.mast}")
                print(f"      blocks:   {', '.join(d.blocks)}")
                print(f"      turnouts: {tstr}")
            if not computed[mast]:
                print(f"  {mast}  ->  (none)")
        print()

    # --- stored SML diff (regression) ------------------------------------
    if args.compare_stored:
        if errors:
            print(f"=== ERRORS ({len(errors)}) ===")
            for e in errors:
                print(f"  ERROR: {e}")
        else:
            print("=== static checks: PASS ===")
        stored = load_stored_sml(args.xml)
        stored_le = {(s, d) for s, d, ule in stored if ule == "yes"}
        stored_manual = {(s, d) for s, d, ule in stored if ule != "yes"}
        computed_pairs = {(src, d.mast) for src, dests in computed.items() for d in dests}
        missing = sorted(stored_le - computed_pairs)
        unexpected = sorted(computed_pairs - stored_le - stored_manual)
        print(f"=== stored SML vs computed model ===")
        print(f"  stored: {len(stored)} dests ({len(stored_le)} useLE=yes, "
              f"{len(stored_manual)} manual)")
        for s, d in sorted(stored_manual):
            print(f"  manual (not validated by model): {s} -> {d}")
        for s, d in missing:
            print(f"  STORED-ONLY (model cannot route it): {s} -> {d}")
        for s, d in unexpected:
            print(f"  model-only (Discover did not store): {s} -> {d}")
        if not missing:
            print("  all stored useLE=yes pairs are reproduced by the model: OK")
        print()
        sys.exit(1 if (errors or missing) else 0)

    # --- oracle diff ----------------------------------------------------
    oracle = load_oracle()
    matches, criteria_diffs, unreachable, extra = [], [], [], []
    oracle_keys = set()
    for src, dst, oblocks, oturnouts in oracle:
        oracle_keys.add((src, dst))
        cands = [d for d in computed.get(src, []) if d.mast == dst]
        if not cands:
            unreachable.append((src, dst, oblocks, oturnouts))
            continue
        d = cands[0]
        ot = {(n, st) for n, st in oturnouts}
        ct = set(d.turnouts)
        ob, cb = set(oblocks), set(d.blocks)
        if ot == ct and ob <= cb:
            matches.append((src, dst))
        else:
            criteria_diffs.append((src, dst, oblocks, sorted(ot - ct), sorted(ct - ot),
                                   sorted(ob - cb), sorted(cb - ob)))
    for src, dests in computed.items():
        for d in dests:
            if (src, d.mast) not in oracle_keys:
                extra.append((src, d.mast, d.blocks, d.turnouts))

    # --- report ----------------------------------------------------------
    print(f"panel: {args.xml}")
    print(f"turnouts={len(m.turnouts)} segments={len(m.segments)} "
          f"points={len(m.points)} layoutblocks={len(m.layoutblocks)} "
          f"masts={len(m.masts)} bound_sites={len(sites)}")
    print()
    if errors:
        print(f"=== ERRORS ({len(errors)}) ===")
        for e in errors:
            print(f"  ERROR: {e}")
    else:
        print("=== static checks: PASS ===")
    if warnings:
        print(f"=== warnings ({len(warnings)}) ===")
        for w in warnings:
            print(f"  warn: {w}")
    print()
    print(f"=== oracle diff (CATS PAIRS = {len(oracle)}) ===")
    print(f"  matched (dest + criteria):        {len(matches)}")
    print(f"  matched dest, criteria differ:    {len(criteria_diffs)}")
    print(f"  NOT discoverable (oracle-only):   {len(unreachable)}")
    print(f"  discoverable but not in oracle:   {len(extra)}")
    for src, dst, ob, ot in unreachable:
        print(f"  UNREACHABLE: {src} -> {dst}")
    for src, dst, ob, missing_t, extra_t, missing_b, extra_b in criteria_diffs:
        print(f"  CRITERIA: {src} -> {dst}")
        if missing_t:
            print(f"      oracle turnouts not computed: {missing_t}")
        if extra_t:
            print(f"      computed turnouts not in oracle: {extra_t}")
        if missing_b:
            print(f"      oracle blocks not computed: {missing_b}")
        if extra_b:
            print(f"      computed extra blocks: {extra_b}")
    for src, dst, blocks, tstates in extra:
        tstr = ", ".join(f"{n}={st}" for n, st in tstates) or "-"
        print(f"  EXTRA: {src} -> {dst}  [{', '.join(blocks)}] ({tstr})")

    bad = bool(errors) or (args.strict and (unreachable or criteria_diffs))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
