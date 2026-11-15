#!/usr/bin/env python3
"""Build a Layout Editor panel of all three levels that looks like the schematic (C3, ADR-023).

    python3 tools/schematic/build_layout_le.py           # write the trial tables file
    python3 tools/schematic/build_layout_le.py --check   # fail if the trial file is stale

Writes jmri/layouts/hart/output/trial/tables_layout.xml: the live tables.xml unchanged, plus one new Layout
Editor panel, PANEL_NAME, and the internal turnouts, blocks and layout blocks the main and upper levels need. The
live tables.xml is only read. The panel is the schematic-maps plugin's `le` drawing of the solved schematic bands
(the inputs of publish_draft.py): straight rows, rounded bends, half-circle turnbacks, helix circles, names on the
drawing. Staging, main and upper are stacked as on the sheet.

Names:
- Staging binds to the live objects, so the panel can replace "HART Railroad" at the cut-over: each schematic
  switch is the live Layout Editor turnout that switches.csv names (its turnout name and OS blocks as the live panel
  has them; switches 7, 23 and 35 are one single crossover each), and each schematic track takes the blocks of the
  live track between the same two switches, in order (a turnback's two tracks split them by track name). The
  normal leg is switch_legs.csv's closed leg. No staging object is created; the build stops if a name is missing.
- Main and upper use placeholders: turnouts "Switch <number>" (internal IT:HART:C3: system names, so nothing
  commands field hardware), blocks "Track <plan edge id>" and "OS Switch <number>" (the track between the A and B
  halves of one number is that number's OS block). No sensors and no masts.

The plugin is the pinned submodule, or SCHEMATIC_PLUGIN (as publish_draft.py).
"""
from __future__ import annotations

import argparse
import copy
import csv
import functools
import importlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
from hartlib import paths, tables  # noqa: E402

TRIAL = paths.LAYOUT_OUTPUT / "trial" / "tables_layout.xml"
PANEL_NAME = "Layout (generated)"
TEMPLATE_PANEL = "HART Railroad"     # the live panel: staging's names, and the attributes the new panel copies
SWITCHES = paths.LAYOUT_DATA / "switches.csv"
SWITCH_LEGS = paths.LAYOUT_DATA / "switch_legs.csv"
STAGING = "Staging"                  # band key (first word of the band title) bound to the live objects

TURNOUT_SYS = "IT:HART:C3:"          # internal turnouts: nothing reaches the field
BLOCK_SYS = "IB:C3:"
LAYOUT_BLOCK_FIRST = 1001            # ILB1001 up; the live file stops well below
COMMENT = "Placeholder from the schematic (C3 trial, build_layout_le.py)"


class BuildError(RuntimeError):
    pass


@functools.lru_cache(maxsize=None)
def plugin():
    """The plugin's modules: sheet, le, core (found and checked once)."""
    try:
        folder = pd.plugin()
    except SystemExit as exc:
        raise BuildError(str(exc.code)) from None
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    return (importlib.import_module("schematic.sheet"), importlib.import_module("schematic.le"),
            importlib.import_module("schematic.core"))


def band_key(title: str) -> str:
    return (title or "").split()[0] if title else ""


def bare(label: str) -> str:
    return (label or "").rstrip("*")


# ---------------------------------------------------------------- the live staging panel

def live_chains(le: ET.Element) -> list[dict]:
    """Every track between two turnout legs or a leg and an end bumper on the live panel: its two ends
    [(ident, leg letter) or ("END", bumper ident)] and its blocks in order from the first end (repeats folded)."""
    segs = {s.get("ident"): s for s in le.findall("tracksegment")}
    pts = {p.get("ident"): p for p in le.findall("positionablepoint")}
    turnouts = {t.get("ident") for t in le.findall("layoutturnout")}
    out, seen = [], set()
    for t in le.findall("layoutturnout"):
        for leg in "abcd":
            first = t.get(f"connect{leg}name")
            if not first:
                continue
            start = (t.get("ident"), f"TURNOUT_{leg.upper()}")
            here, seg, blocks = start, first, []
            for _ in range(len(segs) + 1):
                s = segs.get(seg)
                if s is None:
                    raise BuildError(f"live panel: {here[0]} connects to {seg!r}, which is no track segment")
                if not blocks or blocks[-1] != s.get("blockname"):
                    blocks.append(s.get("blockname"))
                ends = [(s.get("connect1name"), s.get("type1")), (s.get("connect2name"), s.get("type2"))]
                other = ends[1] if ends[0] == here else ends[0]
                if other[1] in ("TURNOUT_A", "TURNOUT_B", "TURNOUT_C", "TURNOUT_D") and other[0] in turnouts:
                    end = (other[0], other[1][-1])
                    break
                p = pts.get(other[0]) if other[1] == "POS_POINT" else None
                if p is None or p.get("type") not in ("ANCHOR", "END_BUMPER"):
                    raise BuildError(f"live panel: track {s.get('ident')} reaches {other[0]} ({other[1]}"
                                     f"{', ' + p.get('type') if p is not None else ''}), which this build does not "
                                     "follow (only turnouts, anchors and end bumpers)")
                if p.get("type") == "END_BUMPER":
                    end = ("END", other[0])
                    break
                here, seg = other, (p.get("connect2name") if p.get("connect1name") == seg else p.get("connect1name"))
            else:
                raise BuildError(f"live panel: the track from {start[0]} leg {leg.upper()} never ends")
            a = (start[0], start[1][-1])
            key = tuple(sorted((a, end)))
            if key not in seen:
                seen.add(key)
                out.append(dict(ends=[a, end], blocks=blocks))
    return out


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def crossover_strands(band) -> set:
    """Tracks joining two switches of one number C to C: inside a single crossover, as the plugin draws it."""
    nodes = band["nodes"]
    out = set()
    for sid, s in band["strands"].items():
        (u, pu), (v, pv) = s["src"], s["dst"]
        if u != v and pu == pv == "C" and nodes[u]["kind"] == nodes[v]["kind"] == "switch" and \
                nodes[u].get("label") and nodes[u]["label"] == nodes[v]["label"]:
            out.add(sid)
    return out


def runs(band, skip=()):
    """Tracks joined through turnbacks: [(start (node, port), [(strand id, reversed)], end (node, port))]."""
    nodes, strands = band["nodes"], band["strands"]
    turn = lambda n: nodes[n]["kind"].startswith("turn")      # noqa: E731
    done, out = set(), []

    def beyond(cur, node):
        nxt = next((k for k in strands if k != cur and node in (strands[k]["src"][0], strands[k]["dst"][0])), None)
        if nxt is None:
            raise BuildError(f"turnback {node}: only track {cur} reaches it")
        return nxt

    for sid in sorted(strands):
        if sid in done or sid in skip:
            continue
        # walk back to a terminal end, then forward
        cur, rev = sid, False
        for _ in range(len(strands) + 1):
            head = strands[cur]["dst"] if rev else strands[cur]["src"]
            if not turn(head[0]):
                break
            nxt = beyond(cur, head[0])
            rev = strands[nxt]["src"][0] == head[0]
            cur = nxt
        else:
            raise BuildError(f"track {sid}: a closed loop of turnbacks with no switch or end")
        start = strands[cur]["dst"] if rev else strands[cur]["src"]
        chain = []
        for _ in range(len(strands)):
            chain.append((cur, rev))
            done.add(cur)
            tail = strands[cur]["src"] if rev else strands[cur]["dst"]
            if not turn(tail[0]):
                break
            cur = beyond(cur, tail[0])
            rev = strands[cur]["dst"][0] == tail[0]
        out.append((tuple(start), chain, tuple(tail)))
    return out


def orient(chain: dict, start_label: str, what: str):
    """(blocks, ends) of a live track, in order from the end at `start_label`. A track with one label at both ends
    (a reversing track, or two end bumpers) has no order to read; it stops unless its blocks read the same both
    ways."""
    if chain["labels"][0] == chain["labels"][1]:
        if chain["blocks"] != chain["blocks"][::-1]:
            raise BuildError(f"staging track {what}: both ends at {chain['labels'][0]}, so its blocks cannot be put "
                             "in order")
        return list(chain["blocks"]), list(chain["ends"])
    if start_label == chain["labels"][0]:
        return list(chain["blocks"]), list(chain["ends"])
    return chain["blocks"][::-1], chain["ends"][::-1]


def share_blocks(blocks: list[str], chain, strands) -> dict:
    """{strand id: [block, ...] from its src to its dst} for a run of tracks with the live blocks in run order.
    A block named after a strand's track goes with it ("Track K-2 West" is track K-2, unless a track is named
    "K-2 West"); the others with the strand of the block before (or after, at the start)."""
    names = [strands[sid]["name"] for sid, _ in chain]
    owner = []
    for b in blocks:
        name = b.removeprefix("Track ")
        hit = [i for i, n in enumerate(names) if n and n == name] or \
            [i for i, n in enumerate(names) if n and n == re.sub(r" (East|West)$", "", name)]
        owner.append(hit[0] if hit else None)
    for i in range(len(owner)):
        if owner[i] is None and i and owner[i - 1] is not None:
            owner[i] = owner[i - 1]
    for i in reversed(range(len(owner))):
        if owner[i] is None:
            owner[i] = owner[i + 1] if i + 1 < len(owner) and owner[i + 1] is not None else 0
    out = {}
    for k, (sid, rev) in enumerate(chain):
        mine = [b for b, o in zip(blocks, owner) if o == k]
        if not mine:        # a track with no block of its own: the one it meets
            before = [b for b, o in zip(blocks, owner) if o < k]
            mine = [before[-1] if before else blocks[0]]
        out[sid] = mine[::-1] if rev else mine
    return out


def staging_names(band, live_le: ET.Element, tidy) -> dict:
    """The plugin's names for the staging band, bound to the live panel (see the module text)."""
    nodes, strands = band["nodes"], band["strands"]
    label_of = {r["le_ident"]: r["switch"] for r in read_csv(SWITCHES)}
    lts = {t.get("ident"): t for t in live_le.findall("layoutturnout")}
    chains = live_chains(live_le)

    def end_label(e):
        return "END" if e[0] == "END" else label_of.get(e[0])

    for c in chains:
        c["labels"] = [end_label(e) for e in c["ends"]]
        if None in c["labels"]:
            raise BuildError(f"live turnout {c['ends']} is not in switches.csv")
    far = {}                    # (live ident, leg) -> label at the other end of its track
    for c in chains:
        for i in (0, 1):
            if c["ends"][i][0] != "END":
                far[c["ends"][i]] = c["labels"][1 - i]

    def node_label(n):
        d = nodes[n]
        if d["kind"] == "end":
            return "END"
        return bare(d.get("label"))

    names = dict(turnouts={}, os={}, normal={}, blocks={})
    inner = crossover_strands(band)
    used = set()
    run_far = {}                # (node, port) -> label at the other end of its run
    far_block = {}              # (node, port) -> block of the live turnout leg at the other end of its run

    def leg_block(e):
        if e[0] == "END":
            return None
        lt = lts[e[0]]
        return lt.get(f"block{e[1].lower()}name" if e[1] != "A" else "blockname") or lt.get("blockname")

    for start, chain, end in runs(band, inner):
        want = sorted((node_label(start[0]), node_label(end[0])))
        cands = [i for i, c in enumerate(chains) if sorted(c["labels"]) == want and i not in used]
        if len(cands) > 1:
            mine = {t for sid, _ in chain if strands[sid]["name"] for t in tidy([strands[sid]["name"]])}
            cands = [i for i in cands if mine & {t for b in tidy(chains[i]["blocks"])
                                                 for t in (b, re.sub(r" (East|West)$", "", b))}]
        if len(cands) != 1:
            raise BuildError(f"staging track {' + '.join(s for s, _ in chain)} ({want[0]} to {want[1]}): "
                             f"{len(cands)} live tracks match")
        used.add(cands[0])
        c = chains[cands[0]]
        blocks, ends = orient(c, node_label(start[0]), " + ".join(s for s, _ in chain))
        run_far[start] = node_label(end[0])
        run_far[end] = node_label(start[0])
        far_block[start], far_block[end] = leg_block(ends[1]), leg_block(ends[0])
        names["blocks"].update(share_blocks(blocks, chain, strands))
    missing = [i for i in range(len(chains)) if i not in used]
    if missing:
        raise BuildError("live staging tracks with no schematic track: " +
                         "; ".join(f"{chains[i]['labels']} {chains[i]['blocks']}" for i in missing))

    # switches: the live turnout, its OS blocks, and the normal leg
    closed = {r["os_block"]: r["closed_leg"] for r in read_csv(SWITCH_LEGS)}
    for n, d in sorted(nodes.items()):
        if d["kind"] not in ("switch", "dx"):
            continue
        ident = next((i for i, lab in label_of.items() if lab == bare(d["label"])), None)
        if ident not in lts:
            raise BuildError(f"staging switch {d['label']}: no live Layout Editor turnout in switches.csv")
        lt = lts[ident]
        names["turnouts"][n] = lt.get("turnoutname")
        if "XOVER" in (lt.get("type") or ""):
            mine = {run_far[(n, p)] for p in "AB"}
            ab = {far.get((ident, "A")), far.get((ident, "B"))}
            cd = {far.get((ident, "C")), far.get((ident, "D"))}
            if mine == ab and mine != cd:
                names["os"][n] = lt.get("blockname")
            elif mine == cd and mine != ab:
                names["os"][n] = lt.get("blockcname") or lt.get("blockname")
            else:
                raise BuildError(f"staging switch {d['label']}: cannot tell which half of crossover {ident} it is")
            continue
        names["os"][n] = lt.get("blockname")
        want = closed.get(lt.get("blockname"))
        if want is None:
            raise BuildError(f"staging switch {d['label']}: {lt.get('blockname')} is not in switch_legs.csv")
        legs = []
        for p in "BC":
            sid = d["ins"].get(p) or d["outs"].get(p)
            seq = names["blocks"][sid] if tuple(strands[sid]["src"]) == (n, p) else names["blocks"][sid][::-1]
            first = next((b for b in seq if b != lt.get("blockname")), None)
            if first is None:           # the track is all this switch's OS: the block past it is the next switch's
                first = far_block[(n, p)]
            if first == want or re.sub(r" (East|West)$", "", first or "") == want:    # "Track S-4 West" is S-4
                legs.append(p)
        if len(legs) != 1:
            raise BuildError(f"staging switch {d['label']}: closed leg {want} is on {len(legs)} of its legs")
        names["normal"][n] = legs[0]
    return names


# ---------------------------------------------------------------- main and upper placeholders

def placeholder_names(bands, le_mod) -> tuple[dict, dict]:
    """({band key: names}, {block: length mm}) for every band but staging."""
    joined = le_mod.partners(bands)
    out, lengths, counted = {}, defaultdict(float), set()
    for bi, (title, band, _) in enumerate(bands):
        key = band_key(title)
        if key == STAGING:
            continue
        nodes, strands = band["nodes"], band["strands"]
        names = dict(turnouts={}, os={}, blocks={})
        for n, d in sorted(nodes.items()):
            if d["kind"] in ("switch", "dx"):
                names["turnouts"][n] = f"Switch {bare(d['label'])}"
                names["os"][n] = "OS Switch " + re.sub(r"[AB]$", "", bare(d["label"]))
        for start, chain, end in runs(band):
            labels = []
            for n, _ in (start, end):
                if nodes[n].get("sub") == "link" and (bi, n) in joined:      # the far side of the connector
                    bj, m = joined[(bi, n)]
                    other = bands[bj][1]
                    sid = next(iter(list(other["nodes"][m]["ins"].values()) + list(other["nodes"][m]["outs"].values())))
                    s = other["strands"][sid]
                    n2 = s["dst"][0] if s["src"][0] == m else s["src"][0]
                    labels.append(bare(other["nodes"][n2].get("label")))
                else:
                    labels.append(bare(nodes[n].get("label")) if nodes[n]["kind"] in ("switch", "dx") else "")
            a, b = labels
            halves = (a and b and a[-1:] in "AB" and b[-1:] in "AB" and a[:-1] == b[:-1] and a[:-1].isdigit())
            for sid, _ in chain:
                s = strands[sid]
                edge = s["edge"]
                if any(nodes[x[0]].get("sub") == "link" for x in (s["src"], s["dst"])):
                    edge = re.sub(r"(?<=\d)[xy]$", "", edge)
                block = f"OS Switch {a[:-1]}" if halves else f"Track {edge}"
                names["blocks"][sid] = [block]
                # a turnback's two tracks each carry their whole edge's length (count it once); a connector or
                # helix cut leaves a piece on each band (e36x, e36y): count both
                if (block, s["edge"]) not in counted:
                    counted.add((block, s["edge"]))
                    lengths[block] += s["cm"] * 10
        for n in names["os"].values():
            lengths[n] += 0.0
        out[key] = names
    return out, dict(lengths)


# ---------------------------------------------------------------- tables

def place(parent: ET.Element, new: list[ET.Element], depth: int, after: ET.Element | None = None) -> None:
    """Insert `new` into `parent` after `after` (default: at the end), indented as JMRI writes."""
    kids = list(parent)
    idx = kids.index(after) + 1 if after is not None else len(kids)
    prev = kids[idx - 1] if idx else None
    pad = "\n" + "  " * depth
    tail = prev.tail if prev is not None else parent.text
    for k, el in enumerate(new):
        ET.indent(el, space="  ", level=depth)
        parent.insert(idx + k, el)
        el.tail = pad
    if new:
        if prev is not None:
            prev.tail = pad
        else:
            parent.text = pad
        new[-1].tail = tail


def bean(tag: str, attrs: dict, sysname: str, user: str, *children) -> ET.Element:
    el = ET.Element(tag, attrs)
    ET.SubElement(el, "systemName").text = sysname
    ET.SubElement(el, "userName").text = user
    for t, v in children:
        ET.SubElement(el, t).text = v
    return el


def r1(v: float) -> str:
    return f"{round(v, 1):.1f}"


def block_sort(name: str):
    kind = 0 if name.startswith("OS ") else 1
    tail = name.split(" ")[-1].split("+")[0]
    digits = "".join(c for c in tail if c.isdigit())
    return (kind, int(digits or 0), name)


def build(live_path: Path = paths.TABLES_XML, bands=None):
    """(trial tables bytes, the plugin's Panel, {band key: names}, bands)."""
    sheet, le_mod, core = plugin()
    if bands is None:
        built = sheet.build([(json.loads((pd.GRAPHS / g).read_text(encoding="utf-8")), n) for g, n in pd.INPUTS],
                            str(pd.DATA))
        bands, page = built.bands, built.opts
    else:
        page = bands[-1][2]
    keys = [band_key(t) for t, _, _ in bands]
    if STAGING not in keys:
        raise BuildError(f"no {STAGING} band in the schematic (bands: {', '.join(keys)})")
    doc = tables.load(live_path)
    root = doc.root
    if any(le.get("name") == PANEL_NAME for le in tables.layout_editors(root)):
        raise BuildError(f"{live_path} already has a panel named {PANEL_NAME}")
    template = tables.layout_editor(root, TEMPLATE_PANEL)
    if template is None:
        raise BuildError(f"no live panel named {TEMPLATE_PANEL}")

    names, lengths = placeholder_names(bands, le_mod)
    names[STAGING] = staging_names(bands[keys.index(STAGING)][1], template, core.tidy)
    try:
        P = le_mod.panel(bands, names, page=page)
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from None

    # staging: every name must already be live
    staging_turnouts = set(names[STAGING]["turnouts"].values())
    staging_blocks = set(names[STAGING]["os"].values()) | {b for v in names[STAGING]["blocks"].values() for b in v}
    live_turnouts = tables.by_any_name(tables.turnouts(root))
    live_lb = {tables.user_name(b) for b in tables.layout_blocks(root)}
    missing = sorted(t for t in staging_turnouts if t not in live_turnouts) + \
        sorted(b for b in staging_blocks if b not in live_lb)
    if missing:
        raise BuildError(f"staging names not in the live tables: {missing}")

    # main and upper: new placeholder turnouts and blocks
    new_turnouts = sorted({t for k, v in names.items() if k != STAGING for t in v["turnouts"].values()},
                          key=lambda s: block_sort("OS " + s))
    new_blocks = sorted((b for b in P.blocks if b not in staging_blocks), key=block_sort)
    if set(new_blocks) - set(lengths):
        raise BuildError(f"blocks with no source: {sorted(set(new_blocks) - set(lengths))}")
    taken_users = {tables.user_name(b) for b in tables.turnouts(root) + tables.blocks(root, full=False)
                   + tables.layout_blocks(root)}
    taken_sys = {tables.system_name(b) for b in tables.turnouts(root) + tables.blocks(root, full=False)
                 + tables.layout_blocks(root)}
    turnout_sys = {t: TURNOUT_SYS + t.split(" ", 1)[1] for t in new_turnouts}
    block_sys = {b: f"{BLOCK_SYS}{i:04d}" for i, b in enumerate(new_blocks, 1)}
    lb_sys = {b: f"ILB{LAYOUT_BLOCK_FIRST + i}" for i, b in enumerate(new_blocks)}
    new_users = new_turnouts + new_blocks
    new_sys = list(turnout_sys.values()) + list(block_sys.values()) + list(lb_sys.values())
    clash = sorted((set(new_users) & taken_users) | (set(new_sys) & taken_sys))
    if clash or len(set(new_users)) != len(new_users) or len(set(new_sys)) != len(new_sys):
        raise BuildError(f"names collide: {clash}")

    internal = next(s for s in root.findall("turnouts") if "InternalTurnoutManager" in (s.get("class") or ""))
    place(internal, [bean("turnout", {"feedback": "DIRECT", "inverted": "false", "automate": "Off"}, turnout_sys[t],
                          t, ("comment", COMMENT)) for t in new_turnouts], 2)
    blocks_el = root.find("blocks")
    short = tables.blocks(root, full=False)
    if not short:
        raise BuildError("the live tables have no names-only block pass to add to")
    last_short = short[-1]
    place(blocks_el, [bean("block", {"systemName": block_sys[b]}, block_sys[b], b) for b in new_blocks], 2, last_short)
    place(blocks_el, [bean("block", {"systemName": block_sys[b], "length": r1(lengths[b]), "curve": "0"},
                           block_sys[b], b, ("comment", COMMENT), ("permissive", "no")) for b in new_blocks], 2)
    place(root.find("layoutblocks"),
          [bean("layoutblock", {"systemName": lb_sys[b], "occupiedsense": "2", "trackcolor": "gray",
                                "occupiedcolor": "red", "extracolor": "white"}, lb_sys[b], b) for b in new_blocks], 2)

    attrs = dict(template.attrib)
    attrs.update(scrollable="both", editable="yes", autoblkgenerate="no")
    panel_el = le_mod.to_xml(P, PANEL_NAME, attrs, copy.deepcopy(template.find("layoutTrackDrawingOptions")))
    place(root, [panel_el], 1, tables.layout_editors(root)[-1])
    return doc.tobytes(), P, names, bands


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="regenerate in memory and fail if the trial file differs")
    ap.add_argument("--out", type=Path, default=TRIAL, help="where to write (default: the trial file)")
    args = ap.parse_args(argv)
    try:
        data, P, _names, _bands = build()
    except BuildError as exc:
        print(f"ERROR: {exc}")
        return 1
    _, le_mod, _ = plugin()
    summary = f"panel {PANEL_NAME!r}: {le_mod.summary(P)}"
    if args.check:
        if not args.out.exists() or args.out.read_bytes() != data:
            print(f"STALE: {paths.rel(args.out)}; run {paths.rel(Path(__file__))}")
            return 1
        print(f"ok: {paths.rel(args.out)} is current ({summary})")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tables.loads(data, path=args.out).save(args.out)
    print(f"wrote {paths.rel(args.out)}: {summary}")
    for line in P.log:
        print(f"  note: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
