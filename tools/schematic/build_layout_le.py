#!/usr/bin/env python3
"""Build a Layout Editor panel of all three levels that looks like the schematic (C3, ADR-023).

    python3 tools/schematic/build_layout_le.py           # write the trial tables file
    python3 tools/schematic/build_layout_le.py --check   # fail if the trial file is stale
    python3 tools/schematic/build_layout_le.py --as-live                   # the cut-over candidate, all three levels
    python3 tools/schematic/build_layout_le.py --as-live --review          # the same, staging not yet approved
    python3 tools/schematic/build_layout_le.py --levels staging --as-live   # staging alone (the candidate's base)
    python3 tools/schematic/build_layout_le.py --freeze [--tables FILE]     # one-shot: re-read the frozen inputs

Frozen inputs (Phase 3b, owner requirement 2026-11-15). Everything the build used to read off the hand-drawn "HART
Railroad" panel (its turnouts, tracks and their blocks, the idents kept, the Entry/Exit sensors, the masts, the
overlay of icons and labels, the panel's attributes) was read once into
jmri/layouts/hart/data/schematic/staging_le/ (le_inputs.py, le_overlay.py). The build reads only those files, the
schematic and the tables' beans; it reads no panel. So the candidate is the same file whether the tables hold the
hand-drawn panel, the generated one (after the cut-over) or none. Edit the frozen files, not a panel. `--freeze`
re-reads them from a hand-drawn panel (it refuses a generated one) and checks they rebuild the same candidate;
it is not part of the normal build. "Live" below means the railroad's objects and the hand-drawn panel as frozen.

Three levels (owner, 2026-11-16). `--as-live` (levels all) writes the cut-over candidate
jmri/layouts/hart/output/trial/tables_cutover.xml: first the staging candidate below (--levels staging --as-live, drawn
at staging's own fit widened by STRETCH, so the three-level panel has the window's shape; check_aspect), then
all three bands at that candidate's grid (no fitting: the panel is larger than the FIT window, which stays FIT;
zoom to fit), each band's labels placed in rounds of their own (the plugin's labels_by_band, so staging's do not
depend on the levels below), staging against the left edge (the plugin's band_align) and the main level below everything the
staging candidate holds (the band gap grows by what the overlay adds under staging), the frame items and status
cluster tied to the staging band's track. check_staging_unchanged then stops unless the staging candidate is in it
unchanged: every bean, every other panel, every staging element, but the main and upper objects and the helix joins
(the staging helix tracks run on to the main level, so their end bumpers become anchors and Masts 38RA and 40RA stand
there, protecting Track 135-H2 and Track 135-H1). Main and upper take the device map's names (device_names; a
crossover's two halves are one turnout, drawn as one single crossover on one level, or as two Layout Editor
turnouts on one turnout for 129 and 135, whose halves stand on two levels), on internal system names; their track
names are the device map's block names without "Track ", one per block, left out where there is no room
(names_last); one block contents icon per block at 12 px (staging keeps 13; LEVEL_LE_LABELS). No masts, sensors or icons for them.

Staging alone (owner approved 2026-11-15). `--levels staging` draws the staging band alone: its helix
tracks end at end bumpers as live, so every mast resolves exactly as live (no helix-entrance exception), its rows
STAGING_ROW px apart, and no main or upper object is added to the tables. With `--as-live` it writes
jmri/layouts/hart/output/trial/tables_cutover_staging.xml: the tables with the "HART Railroad" panel replaced, in its
place (or put before the first Layout Editor panel when there is none), by the generated one under the same name and
the frozen panel attributes (editable, scrollable, colours,
turnout sizes, autoblkgenerate), sized by FIT and opening at 0, 0 so the window fits the display; the "Dispatcher
System" panel and everything else unchanged. In it the staging turnouts, boundary anchors, end bumpers and the
track segment of each one-segment block keep their live idents (the plugin's `idents`), each turnout keeps its
live leg letters, type and continuing route (`leg_b`: a switch whose drawn diverging leg is live leg B is drawn
that way), the Entry/Exit sensors go back in their live slots (same ident and slot, checked to resolve to the same
blocks), and le_overlay.py carries the live icons and region captions across (Phase 2), around the switch
numbers, track names, station captions and block contents icons the plugin generates (owner, 2026-11-15). The
panel carries the hidden generated-panel label (hartlib.tables.GENERATED_PANEL_MARKER, Phase 3):
polish_hart_layout_editor.py, reconcile_dispatcher_stations.py, the audit and the other scripts that pin the
hand-drawn panel's pixels read it and take positions from the panel itself (wiki/projects/schematic-maps-handoff.md,
cut-over runbook).

Writes jmri/layouts/hart/output/trial/tables_layout.xml: the live tables.xml unchanged, plus one new Layout
Editor panel, PANEL_NAME, and the internal turnouts, blocks and layout blocks the main and upper levels need. The
live tables.xml is only read. The panel is the schematic-maps plugin's `le` drawing of the solved schematic bands
(the inputs of publish_draft.py): straight rows, rounded bends, half-circle turnbacks, helix circles, names on the
drawing. Staging, main and upper are stacked as on the sheet.

Names:
- Staging binds to the live objects, so the panel can replace "HART Railroad" at the cut-over: each schematic
  switch is the live Layout Editor turnout that switches.csv names (its turnout name and OS blocks as the live panel
  has them; switches 7, 23 and 35 are one single crossover each), and each schematic track takes the blocks of the
  live track between the same two switches, in order (a turnback's two tracks split them by track name), drawn at
  their measured lengths (staging `track_lengths_in`), so each short throat block (S-1 West, S-1 East, East Lead
  East, K-1 West) sits at its own end of its track, by its ladder. The
  normal leg is switch_legs.csv's closed leg. No staging object is created; the build stops if a name is missing.
- Staging masts: every mast the live panel binds in a slot goes in the slot of the new panel that JMRI resolves to
  the same facing and protected blocks, and the same kind of slot (anchor, end bumper or turnout leg), so Signal
  Mast Logic discovery and the Dispatcher System read the same boundaries from either panel (the plugin's slots.py
  holds JMRI's rules). Its icon goes on the right-hand side of the train it governs, hidden as the live icon is.
  Staging's helix joins carry the next level's block ("joins": "other"), so the helix entrance anchor is a block
  boundary: a live buffer-stop mast whose track the new panel runs on through the helix (Mast 38RA, 40RA) stands
  there, facing the same block and protecting the helix run (the live buffer stop protects nothing). Any mast with
  no matching slot stops the build, and so does a mast that two slots of the new panel would fit (a turnout mast
  must also land on the live turnout).
- Main and upper: the drawing's placeholders (turnouts "Switch <number>", blocks "Track <plan edge id>" and "OS
  Switch <number>", the track between the A and B halves of one number being that number's OS block) mapped to
  the device map's user names by its trial_name column, on internal IT:HART:C3: and IB:C3: system names, so nothing
  commands field hardware. No sensors and no masts.

Size: the panel opens at 100% zoom in a FIT pixel window (the plugin's `fit` scales the grid; label fonts keep their
size).

The trial is for looking at only. Both panels bind the same staging masts in one tables file. JMRI's mast lookups
(LayoutBlockManager, DefaultSignalMastLogic) walk the Layout Editor panels in title order and take the first panel
that has the mast, so "HART Railroad" answers before "Layout (generated)"; but Layout Block routing merges the block
connections of every loaded panel, so the trial adds the helix joins (McKeesport and McKees Rocks to the next
levels' placeholder blocks) to the routing graph, and 38RA and 40RA resolve differently on the two panels. So with
the trial loaded do not run Signal Mast Logic discovery, Dispatcher System Stage 1 or Entry/Exit generation, and do
not Store. At the cut-over the live panel goes and the generated one alone carries the masts. This script never
writes the live tables.xml or anything in the JMRI profile (main() refuses such an --out).

The plugin is the pinned submodule, or SCHEMATIC_PLUGIN (as publish_draft.py).
"""
from __future__ import annotations

import argparse
import copy
import csv
import functools
import hashlib
import importlib
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import le_inputs  # noqa: E402  the frozen staging facts (jmri/layouts/hart/data/schematic/staging_le/)
import publish_draft as pd  # noqa: E402  DATA, GRAPHS, INPUTS, hartlib paths and the pinned plugin
from hartlib import paths, tables  # noqa: E402

TRIAL = paths.LAYOUT_OUTPUT / "trial" / "tables_layout.xml"
CUTOVER = paths.LAYOUT_OUTPUT / "trial" / "tables_cutover.xml"                    # all three levels (the candidate)
CUTOVER_STAGING = paths.LAYOUT_OUTPUT / "trial" / "tables_cutover_staging.xml"    # staging alone (the guard's base)
TRIAL_STAGING = paths.LAYOUT_OUTPUT / "trial" / "tables_layout_staging.xml"
LEVELS = ("all", "staging")
PANEL_NAME = "Layout (generated)"
TEMPLATE_PANEL = le_inputs.PANEL     # the panel the cut-over candidate replaces (its inputs are frozen in le_inputs)
SWITCHES = paths.LAYOUT_DATA / "switches.csv"
SWITCH_LEGS = paths.LAYOUT_DATA / "switch_legs.csv"
DEVICE_MAP = pd.DATA / "device_map_main_upper.csv"   # main and upper names (trial_name: the drawing's placeholder)
# The staging candidate's panel as the owner approved it: a hash per element (approved_fingerprint), so a plugin bump
# or an overlay edit that changes the approved staging panel stops both cut-over builds. Refreshed only by
# --approve-staging, after the owner approves the new panel in PanelPro.
APPROVED = pd.DATA / "approved_staging.sha256"
APPROVED_NOTE = ("# The staging cut-over candidate's \"HART Railroad\" panel as approved by the owner in PanelPro on {date}\n"
                 "# (build_layout_le.py --approve-staging; checked by --levels staging --as-live and --as-live). One line\n"
                 "# per element, in panel order: its sha256 (attributes sorted, layout whitespace dropped) and what it\n"
                 "# is; the first line is the panel's own attributes, the last the whole panel's hash.\n")
STAGING = "Staging"                  # band key (first word of the band title) bound to the live objects

TURNOUT_SYS = "IT:HART:C3:"          # internal turnouts: nothing reaches the field
BLOCK_SYS = "IB:C3:"
LAYOUT_BLOCK_FIRST = 1001            # ILB1001 up; the live file stops well below
COMMENT = "Main and upper level, internal until the import (device map name; build_layout_le.py)"
# The window the panel opens in at 100% zoom on the owner's 1900 x 1200 display (the plugin fits the panel inside
# it less Layout Editor's 18 x 60 px frame allowance). Width: the whole 1900, so the panel is at most 1882 (the
# live panel's window is 1882 wide). Height: 1200 less the macOS menu bar (37 px on a notched display, 25 else)
# and 23 px spare for the Dock's edge is 1140; the 60 px allowance covers the title bar (28 px) and the thin edit
# toolbar, leaving the panel at most 1080.
FIT = (1900, 1140)
# Staging alone fills the window's width long before its height, so its rows may be as far apart as the live
# panel's yard tracks (about 47 px), leaving room between them for the live panel's icons and labels.
STAGING_ROW = 48
# The cut-over candidates' grid (owner, 2026-11-16). Staging's own fit to the window (the grid's scale across and down
# when the staging band alone is fitted into FIT at STAGING_ROW, found by the plugin's fit in each staging cut-over
# build and kept as P.staging_fit) widened by STRETCH, so that the three-level
# panel has the shape of the window's panel area (FIT less Layout Editor's frame, about 1.74 wide to 1 high) and
# fills it when zoomed to fit. Rows, their spacing and the band gap do not change. The build stops when the panel's
# shape drifts more than ASPECT_TOLERANCE from the window's (check_aspect names the factor that would fit it).
STRETCH = 1.307
ASPECT_TOLERANCE = 0.03
# The plugin's label layer (schematic/le_labels.py): switch numbers as the hand-drawn panel wrote them ("SW-13",
# 13 px bold), block contents icons on with the plugin's reserve; given to every band through the page options.
# The all-levels trial (viewing only) has no block contents icons (owner, 2026-11-16), and its switch numbers at the
# plugin's 9 px: three bands in one window leave no room for 13 px ones (SW-29 fits nowhere). Staging keeps both.
LE_LABELS = {"switch_prefix": "SW-", "switch_size": 13}
TRIAL_LE_LABELS = dict(LE_LABELS, switch_size=9, block_contents=False)
# Main and upper at staging's grid (the three-level candidate): denser than staging, so every block's contents icon
# comes first and a track name with no room is left out (logged; the plugin's names_last), and the icons are 12 px,
# the short reserve still tried before none (owner, 2026-11-16): at 13 px three have no clean spot at any reserve.
LEVEL_LE_LABELS = {"names_last": True, "block_contents_size": 12}


class BuildError(le_inputs.InputsError):
    """A build that cannot go on; main() also stops on le_inputs.InputsError (a frozen file of the wrong shape)."""


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


@functools.lru_cache(maxsize=None)
def schematic():
    """(bands, page options) of the solved schematic (the inputs of publish_draft.py), solved once per run."""
    sheet = plugin()[0]
    built = pd.solved_sheet(sheet)
    return built.bands, built.opts


def overlay_mod():
    """tools/schematic/le_overlay.py: the live panel's icons and labels carried onto the new one."""
    import le_overlay
    return le_overlay


def slots_module():
    plugin()
    return importlib.import_module("schematic.slots")


def band_key(title: str) -> str:
    return (title or "").split()[0] if title else ""


def bare(label: str) -> str:
    return (label or "").rstrip("*")


# ---------------------------------------------------------------- staging, from the frozen inputs (le_inputs.py)

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


def staging_names(band, inputs, tidy) -> dict:
    """The plugin's names for the staging band, bound to the live objects through the frozen inputs (see the module
    text)."""
    nodes, strands = band["nodes"], band["strands"]
    label_of = {r["le_ident"]: r["switch"] for r in read_csv(SWITCHES)}
    lts = {t["ident"]: t for t in inputs.turnouts}
    chains = copy.deepcopy(inputs.chains)

    def end_label(e):
        return "END" if e[0] == "END" else label_of.get(e[0])

    for c in chains:
        c["labels"] = [end_label(e) for e in c["ends"]]
        if None in c["labels"]:
            raise BuildError(f"frozen track {c['ends']}: a turnout of it is not in switches.csv")
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

    names = dict(turnouts={}, os={}, normal={}, blocks={}, leg_b={})
    idents = {}                 # switch node -> live turnout ident
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
        raise BuildError("frozen staging tracks (tracks.csv) with no schematic track: " +
                         "; ".join(f"{chains[i]['labels']} {chains[i]['blocks']}" for i in missing))

    # switches: the live turnout, its OS blocks, and the normal leg
    closed = {r["os_block"]: r["closed_leg"] for r in read_csv(SWITCH_LEGS)}
    for n, d in sorted(nodes.items()):
        if d["kind"] not in ("switch", "dx"):
            continue
        ident = next((i for i, lab in label_of.items() if lab == bare(d["label"])), None)
        if ident not in lts:
            raise BuildError(f"staging switch {d['label']}: switches.csv's Layout Editor turnout {ident} is not in "
                             "the frozen turnouts.csv")
        lt = lts[ident]
        names["turnouts"][n] = lt.get("turnoutname")
        idents[n] = ident
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
        legs, first = [], {}
        for p in "BC":
            sid = d["ins"].get(p) or d["outs"].get(p)
            seq = names["blocks"][sid] if tuple(strands[sid]["src"]) == (n, p) else names["blocks"][sid][::-1]
            first[p] = next((b for b in seq if b != lt.get("blockname")), None)
            if first[p] is None:        # the track is all this switch's OS: the block past it is the next switch's
                first[p] = far_block[(n, p)]
            if first[p] == want or re.sub(r" (East|West)$", "", first[p] or "") == want:   # "Track S-4 West" is S-4
                legs.append(p)
        if len(legs) != 1:
            raise BuildError(f"staging switch {d['label']}: closed leg {want} is on {len(legs)} of its legs")
        names["normal"][n] = legs[0]
        # the band leg that is the live Layout Editor leg B: the one whose first block is live leg B's
        live_b = live_leg_first(chains, lts, ident, "B")
        if live_b is None or None in first.values():
            raise BuildError(f"staging switch {d['label']}: no block past live {ident} leg B ({live_b}) or past "
                             f"drawn leg B ({first['B']}) or C ({first['C']}), so leg B cannot be matched")
        track = lambda b: re.sub(r" (East|West)$", "", b)      # noqa: E731  "Track S-4 West" is S-4, as above
        on_b = [p for p in "BC" if first[p] == live_b] or [p for p in "BC" if track(first[p]) == track(live_b)]
        if len(on_b) != 1:
            raise BuildError(f"staging switch {d['label']}: live {ident} leg B reaches {live_b}, which "
                             f"{'both' if on_b else 'neither'} of its drawn legs B ({first['B']}) and C "
                             f"({first['C']}) reach first")
        names["leg_b"][n] = on_b[0] if bare(d["label"]) not in LEGS_SWAPPED else "BC".replace(on_b[0], "")
    names["idents"] = dict(turnouts=idents, boundaries=copy.deepcopy(inputs.boundaries), ends=dict(inputs.ends),
                           segments=dict(inputs.segments))
    return names


# Staging switches whose generated turnout swaps the live leg letters B and C (and so its continuing route): JMRI
# draws a plain turnout's leg A in line with leg B, so a switch whose live leg B is the diverging track on the sheet
# can be drawn as the sheet has it only with that track on leg C (owner, 2026-11-16). A mast on such a leg moves to
# the other letter with it (le_signal_boundaries.csv's generated_slot); the blocks stay.
LEGS_SWAPPED = {"13": "Barn on leg C, so 15-13-11 is drawn level as on the sheet (owner, 2026-11-16)"}


def swapped_idents() -> set:
    """The live Layout Editor idents of the LEGS_SWAPPED switches (switches.csv)."""
    idents = {r["switch"]: r["le_ident"] for r in read_csv(SWITCHES)}
    missing = sorted(set(LEGS_SWAPPED) - set(idents))
    if missing:
        raise BuildError(f"LEGS_SWAPPED names switches switches.csv does not have: {missing}")
    return {idents[k] for k in LEGS_SWAPPED}


def swap_legs(facts: dict) -> dict:
    """A turnout's facts (turnout_facts) with legs B and C swapped, as LEGS_SWAPPED draws it: the other hand (the
    straight leg is now B) and the continuing route on the other letter."""
    legs = dict(facts["legs"])
    legs["B"], legs["C"] = facts["legs"].get("C"), facts["legs"].get("B")
    a, b, c, d = facts["blocks"]
    hand = {"RH_TURNOUT": "LH_TURNOUT", "LH_TURNOUT": "RH_TURNOUT"}
    return dict(facts, legs={k: v for k, v in legs.items() if v is not None}, blocks=(a, c, b, d),
                type=hand.get(facts["type"], facts["type"]),
                continuing={"2": "4", "4": "2"}.get(facts["continuing"], facts["continuing"]))


def live_leg_first(chains: list[dict], lts: dict, ident: str, leg: str) -> str | None:
    """The first block past a live turnout's own block along its leg (the block of the turnout leg at the far end,
    when the whole track is in this turnout's block). `chains`: tracks.csv's tracks; `lts`: turnouts.csv's rows."""
    own = lts[ident].get("blockname")
    for c in chains:
        for i in (0, 1):
            if tuple(c["ends"][i]) == (ident, leg):
                seq = c["blocks"] if i == 0 else c["blocks"][::-1]
                got = next((b for b in seq if b != own), None)
                if got is not None:
                    return got
                far = c["ends"][1 - i]
                if far[0] == "END":
                    return None
                t = lts[far[0]]
                return (t.get(f"block{far[1].lower()}name") if far[1] != "A" else None) or t.get("blockname")
    raise BuildError(f"frozen tracks: turnout {ident} leg {leg} reaches no track")


def staging_lengths(opts: dict, names: dict) -> dict:
    """{block: inches} for each staging block the schematic draws whose track has a measured length (layer 1
    `track_lengths_in`, by track name: block "Track S-1 West" is track "S-1 West"), so a track with several blocks
    is cut at their real shares: a short throat block (S-1 West, East Lead East, K-1 West) sits at its own end."""
    measured = opts.get("track_lengths_in") or {}
    if not isinstance(measured, dict):
        raise BuildError("staging track_lengths_in must be an object of track name: inches")
    used = {b for v in names["blocks"].values() for b in v}
    out = {}
    for track, inches in sorted(measured.items()):
        if isinstance(inches, bool) or not isinstance(inches, (int, float)) or not inches > 0:
            raise BuildError(f"staging track_lengths_in: {track!r} has length {inches!r}, not inches above zero")
        if f"Track {track}" not in used:
            raise BuildError(f"staging track_lengths_in: no drawn staging track has the block 'Track {track}' "
                             "(renamed or misspelt?)")
        out[f"Track {track}"] = float(inches)
    # A track that also holds an OS block (the Scale track ends in OS Switch 7) has no measured length for it, so
    # it is drawn with equal blocks as before; its track's length is left out rather than logged on every build.
    for blocks in names["blocks"].values():
        if any(b.startswith("OS ") for b in blocks):
            for b in blocks:
                out.pop(b, None)
    return out


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


def plugin_masts(masts: list[dict]) -> list[dict]:
    """The plugin's mast list for staging from masts.csv's rows: each mast with the facing block, protected blocks
    and kind of slot it must resolve to, its icon size and hidden flag; an end bumper mast may stand at a helix join
    instead (the all-levels trial runs its track on)."""
    out = []
    for m in masts:
        entry = dict(mast=m["mast"], facing=m["facing"], protects=list(m["protects"]), kind=m["kind"],
                     hidden=m["hidden"], icon=list(m["icon"]))
        if m["kind"] == "end bumper":
            entry["or_join"] = True
        out.append(entry)
    return sorted(out, key=lambda m: m["mast"])


def check_unplaced(P) -> list[str]:
    """Stop on any mast the plugin could not place; a note for each buffer-stop mast moved to a helix join."""
    if P.unplaced:
        raise BuildError("staging masts with no matching slot on the new panel: " +
                         "; ".join(f"{mast}: {why}" for _t, mast, why in P.unplaced))
    return [f"{mast}: {why}" for _t, mast, why in P.moved]


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


def device_names(path: Path = DEVICE_MAP) -> dict:
    """{placeholder: device-map user name} for the main and upper turnouts and blocks: each turnout or block row's
    `trial_name` (comma separated: a crossover's two halves are one turnout, "Switch 101A, Switch 101B" -> "Switch
    101") is the placeholder placeholder_names gives. Stops on a row with no trial name, a trial name given twice, a
    turnout not named "Switch <n>" or a block not named "Track ..." or "OS Switch <n>"."""
    try:
        rows = read_csv(path)
    except OSError as exc:
        raise BuildError(f"cannot read the device map {path}: {exc}") from None
    need = {"layer", "user_name", "trial_name"}
    if rows and not need <= set(rows[0]):
        raise BuildError(f"{paths.rel(path)}: columns {sorted(rows[0])} lack {sorted(need - set(rows[0]))}")
    out, bad = {}, []
    for i, r in enumerate(rows, 2):
        if r["layer"] not in ("turnout", "block"):
            continue
        user = (r["user_name"] or "").strip()
        if r["layer"] == "turnout" and user.startswith("DCC "):
            continue                    # the LCC alias of a turnout: not a panel object
        form = r"Switch \d+" if r["layer"] == "turnout" else r"(Track \S.*|OS Switch \d+)"
        if not re.fullmatch(form, user):
            bad.append(f"line {i}: {r['layer']} {user!r} is not named {form}")
            continue
        # a trailing "*" marks a switch the plan's label carries one on (223, owner-confirmed hand); the drawing's
        # placeholder is the bare name, as placeholder_names writes it
        trial = [bare(t.strip()) for t in (r["trial_name"] or "").split(",") if t.strip()]
        if not trial:
            bad.append(f"line {i}: {user} has no trial_name")
        for t in trial:
            if t in out:
                bad.append(f"line {i}: trial_name {t} is given to {out[t]} and {user}")
            out[t] = user
    if bad:
        raise BuildError(f"{paths.rel(path)}: " + "; ".join(bad))
    if not out:
        raise BuildError(f"{paths.rel(path)}: no turnout or block rows")
    return out


def level_names(bands, le_mod, device: dict | None = None) -> tuple[dict, dict]:
    """placeholder_names with every placeholder replaced by its device-map name (device_names): ({band key: names},
    {block: length mm}). Stops on a placeholder the device map does not name, or a device-map name the drawing does
    not use."""
    device = device_names() if device is None else device
    names, lengths = placeholder_names(bands, le_mod)
    used, missing = set(), set()

    def to(ph):
        if ph not in device:
            missing.add(ph)
            return ph
        used.add(ph)
        return device[ph]

    out = {}
    for key, nm in names.items():
        out[key] = dict(turnouts={n: to(t) for n, t in nm["turnouts"].items()},
                        os={n: to(b) for n, b in nm["os"].items()},
                        blocks={sid: [to(b) for b in v] for sid, v in nm["blocks"].items()})
    out_len = defaultdict(float)
    for ph, mm in lengths.items():
        out_len[to(ph)] += mm
    if missing:
        raise BuildError(f"main and upper placeholders {paths.rel(DEVICE_MAP)} names nowhere: {sorted(missing)}")
    unused = sorted(set(device) - used)
    if unused:
        raise BuildError(f"{paths.rel(DEVICE_MAP)} trial names the drawing does not have: {unused}")
    return out, dict(out_len)


def shared_turnouts(names: dict) -> None:
    """Give each main and upper band's names the turnouts it shares with another band (`shared_turnouts`): a
    crossover whose halves stand on two levels (the helix-top 129 and 135) is one device-map turnout drawn as two
    Layout Editor turnouts, which JMRI throws together."""
    bands_of = defaultdict(set)
    for key, nm in names.items():
        if key != STAGING:
            for t in nm["turnouts"].values():
                bands_of[t].add(key)
    for key, nm in names.items():
        if key != STAGING:
            nm["shared_turnouts"] = sorted(t for t in set(nm["turnouts"].values()) if len(bands_of[t]) > 1)


# Track names on the cut-over candidates that stand on one centre x (owner, 2026-11-16): South Yard's, in the middle
# of the yard between its ladders (the plugin's name_columns)
NAME_COLUMNS = [["S-R", "S-1", "S-2", "S-3", "S-4"]]


# Station clusters that step along one slope (owner, 2026-11-16): the engine house's buttons, one row apart. Each after
# the second is placed again at the x the first two's step gives it (the plugin's extra "x"), its y the plugin's.
STATION_STEPS = [["Track EH-1", "Track EH-2", "Track EH-3"]]


def cluster_steps(P, groups) -> dict:
    """{station block: x} for the clusters after the second of each group (STATION_STEPS): the first's x plus n
    times the first step, from the boxes the plugin placed (P.extras). Stops on a group member it placed none for."""
    boxes = {e["id"]: e["box"] for e in getattr(P, "extras", ())}
    out = {}
    for group in groups:
        missing = [g for g in group if g not in boxes]
        if missing:
            raise BuildError(f"station steps: the plugin placed no cluster for {missing}")
        x0, step = boxes[group[0]][0], boxes[group[1]][0] - boxes[group[0]][0]
        out.update({g: round(x0 + k * step) for k, g in enumerate(group[2:], 2)})
    return out


def with_x(extras: dict, xs: dict) -> dict:
    """`extras` ({"extras": [...]}) with each station cluster in `xs` placed at that x (the plugin's extra "x")."""
    return {"extras": [dict(e, x=xs[e["id"]]) if e["id"] in xs else e for e in extras.get("extras", [])]}


def staging_columns(bands):
    """`bands` with the staging band's le_labels giving NAME_COLUMNS (a copy of its options)."""
    out = []
    for title, band, opts in bands:
        if band_key(title) == STAGING:
            if "le_labels" in (opts or {}):
                raise BuildError(f"{title}: its preferences already hold le_labels; HART sets them here")
            opts = dict(opts or {}, le_labels={"name_columns": [list(g) for g in NAME_COLUMNS]})
        out.append((title, band, opts))
    return out


def named_bands(bands, names: dict):
    """A copy of `bands` in which each main and upper track block is named on one of its tracks (the longest; its
    name the block's without "Track "), so the plugin's label layer writes the device-map track names there; every
    other main and upper track is unnamed, but a helix track keeps its plan name (McKees Rocks, McKeesport): the
    plugin joins the helix ends of two levels by that name (le.partners), so it is the label there too. Staging is
    left as it is."""
    out = []
    for title, band, opts in bands:
        key = band_key(title)
        if key == STAGING:
            out.append((title, band, opts))
            continue
        band = copy.deepcopy(band)
        nodes = band["nodes"]
        # a crossover's two halves on this band ("101A", "101B" joined C to C), one device-map turnout: labelled by
        # its number, so the plugin draws them as one single crossover, as staging's 7, 23 and 35
        for s in band["strands"].values():
            (u, pu), (v, pv) = s["src"], s["dst"]
            a, b = (bare(nodes[x].get("label")) for x in (u, v))
            if u != v and pu == pv == "C" and nodes[u]["kind"] == nodes[v]["kind"] == "switch" and \
                    re.fullmatch(r"\d+[AB]", a or "") and a[:-1] == b[:-1] and a != b:
                if names[key]["turnouts"].get(u) != names[key]["turnouts"].get(v):
                    raise BuildError(f"{title}: switches {a} and {b} are joined as a crossover but the device map "
                                     f"gives them two turnouts")
                nodes[u]["label"] = nodes[v]["label"] = a[:-1]
        by_block = defaultdict(list)
        for sid, blocks in names[key]["blocks"].items():
            if len(blocks) != 1:
                raise BuildError(f"{title}: track {sid} has blocks {blocks}, not one")
            if blocks[0].startswith("Track "):
                by_block[blocks[0]].append(sid)
        helix = {sid for sid, s in band["strands"].items()
                 if any(nodes[e[0]].get("sub") == "helix" for e in (s["src"], s["dst"]))}
        for sid, s in band["strands"].items():
            if sid not in helix:        # a helix track keeps its plan name: le.partners joins the levels by it
                s["name"] = ""
        for block, sids in by_block.items():
            if helix & set(sids):
                continue
            best = max(sids, key=lambda k: (band["strands"][k]["cm"], k))
            band["strands"][best]["name"] = block.removeprefix("Track ")
        if "le_labels" in (opts or {}):
            raise BuildError(f"{title}: its preferences already hold le_labels; HART sets them here (LEVEL_LE_LABELS)")
        out.append((title, band, dict(opts or {}, le_labels=dict(LEVEL_LE_LABELS))))
    return out


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


def joined_ends(bands, staging: dict, le_mod) -> set:
    """The blocks of the staging tracks that end at a helix or connector join to another drawn band."""
    band = bands[0][1]
    out = set()
    for (bi, n), _other in le_mod.partners(bands).items():
        if bi != 0:
            continue
        d = band["nodes"][n]
        sid = next(iter(list(d["ins"].values()) + list(d["outs"].values())))
        blocks = staging["blocks"][sid]
        out.add(blocks[0] if band["strands"][sid]["src"][0] == n else blocks[-1])
    return out


def bind_sensors(gen_le: ET.Element, sensors: list[dict]) -> int:
    """Bind each Entry/Exit sensor of sensors.csv in the same slot of the new panel: the same ident and slot, since
    staging keeps the live idents and leg letters. Stops unless that slot is there and resolves to the same facing
    and protected blocks as frozen. Returns how many."""
    gen_ix = slots_module().Index(gen_le)
    bad = []
    for row in sorted(sensors, key=lambda r: (r["ident"], r["slot"])):
        ident, slot, sensor, kind = row["ident"], row["slot"], row["sensor"], row["kind"]
        have = gen_ix.turnouts if kind == "turnout" else gen_ix.points
        if ident not in have:
            bad.append(f"{sensor}: live {kind} {ident} is not on the new panel")
            continue
        want_type = "END_BUMPER" if kind == "end bumper" else "ANCHOR"
        if kind != "turnout" and have[ident].get("type") != want_type:
            bad.append(f"{sensor}: {ident} is a {have[ident].get('type')} on the new panel, live a {want_type}")
            continue
        if kind == "turnout" and not have[ident].get(f"connect{slot.lower()}name"):
            bad.append(f"{sensor}: turnout {ident} has no leg {slot} on the new panel")
            continue
        want, got = (row["facing"], list(row["protects"])), tuple(gen_ix.blocks(kind, ident, slot))
        if want != (got[0], list(got[1])):
            bad.append(f"{sensor}: {ident} {slot} faces {got[0]} and protects {got[1]} on the new panel, live "
                       f"{want[0]} and {want[1]}")
            continue
        if kind == "turnout":
            el = ET.SubElement(have[ident], f"sensor{slot}")
            el.text = sensor
        else:
            have[ident].set(f"{slot}boundsensor", sensor)
    if bad:
        raise BuildError("Entry/Exit sensors not placed for certain: " + "; ".join(bad))
    return len(sensors)


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


def replace(parent: ET.Element, old: ET.Element, new: ET.Element, depth: int) -> None:
    """Put `new` where `old` stands in `parent`, indented as JMRI writes."""
    idx = list(parent).index(old)
    ET.indent(new, space="  ", level=depth)
    new.tail = old.tail
    parent.remove(old)
    parent.insert(idx, new)


def build(live_path: Path = paths.TABLES_XML, bands=None, levels: str = "all", as_live: bool = False, inputs=None,
          freeze_from: ET.Element | None = None, approved: Path | None = APPROVED):
    """(tables bytes, the plugin's Panel, {band key: names}, bands). `levels` "all" draws every band, main and upper
    under the device map's names (level_names) and their objects added to the tables; "staging" draws staging alone, its
    helix ends as end bumpers as live, and adds no table object. `as_live` writes a cut-over candidate: the "HART
    Railroad" panel of the tables (hand-drawn or generated) replaced by the new one, or the new one put before the
    first Layout Editor panel when the tables have none, under the frozen name and attributes; with "all", drawn at
    the staging candidate's grid and checked to hold it unchanged (check_staging_unchanged; module text). Without
    `as_live`, "all" is the viewing trial beside the live panel, fitted into the FIT window. The staging facts come
    from `inputs` (default: the frozen files, le_inputs.load()); nothing is read from a panel in the tables.
    `freeze_from` (--freeze only, with `as_live`): the hand-drawn panel whose overlay le_overlay.freeze reads into
    inputs.overlay before it is carried. `approved`: the fingerprint the staging candidate's panel must match
    (check_approved; None skips it, for --approve-staging and tests that change the inputs)."""
    if levels not in LEVELS:
        raise BuildError(f"levels must be one of {', '.join(LEVELS)}, not {levels!r}")
    if freeze_from is not None and not (as_live and levels == "staging"):
        raise BuildError("the overlay is frozen from the staging cut-over build (--levels staging --as-live)")
    if inputs is None:
        inputs = le_inputs.load()
    _sheet, le_mod, core = plugin()
    if bands is None:
        bands, page = schematic()
    else:
        page = bands[-1][2]
    base = None             # the three-level candidate: the staging candidate it must hold unchanged, and its grid
    if as_live and levels == "all":
        base = build(live_path, bands, "staging", True, inputs, approved=approved)
    keys = [band_key(t) for t, _, _ in bands]
    if STAGING not in keys:
        raise BuildError(f"no {STAGING} band in the schematic (bands: {', '.join(keys)})")
    if levels == "staging":
        bands = [bands[keys.index(STAGING)]]
        keys = [STAGING]
    if band_key(bands[0][0]) != STAGING:
        raise BuildError(f"the first band is {bands[0][0]!r}, not {STAGING}")
    doc = tables.load(live_path)
    root = doc.root
    panel_name = inputs.panel_name if as_live else PANEL_NAME
    if not as_live and any(le.get("name") == PANEL_NAME for le in tables.layout_editors(root)):
        raise BuildError(f"{live_path} already has a panel named {PANEL_NAME}")
    if not tables.layout_editors(root):
        raise BuildError(f"{live_path} has no Layout Editor panel to put the new one beside")

    names, lengths = level_names(bands, le_mod) if levels == "all" else ({}, {})
    shared_turnouts(names)
    names[STAGING] = staging_names(bands[0][1], inputs, core.tidy)
    # a live segment ident JMRI cannot find as a segment by name (F46-W-0: LayoutEditorFindItems.findObjectByName
    # reads only T... and F<n>-S-<n>; such names load, but the Check menu and connection menus miss them) is not
    # carried over: that segment takes a generated ident (noted)
    segs = names[STAGING]["idents"]["segments"]
    unfindable = sorted(i for i in segs.values() if le_mod.jmri_kind(i) != "segment")
    names[STAGING]["idents"]["segments"] = {b: i for b, i in segs.items() if i not in unfindable}
    names[STAGING]["masts"] = plugin_masts(inputs.masts)
    system = tables.mast_system_names(root)
    absent = sorted(m["mast"] for m in inputs.masts if m["mast"] not in system)
    if absent:
        raise BuildError(f"masts.csv names masts that are not in the signal mast table: {absent}")
    if levels == "all":
        names[STAGING]["joins"] = "other"
        # a staging track that runs on through a helix join has no end bumper here: its live bumper's ident goes
        names[STAGING]["idents"]["ends"] = {b: i for b, i in names[STAGING]["idents"]["ends"].items()
                                            if b not in joined_ends(bands, names[STAGING], le_mod)}
    names[STAGING]["lengths"] = staging_lengths(bands[0][2], names[STAGING])
    if "le_labels" in page:
        raise BuildError("the schematic's page options already hold le_labels; HART sets them here (LE_LABELS)")
    page = dict(page, le_labels=dict(TRIAL_LE_LABELS if levels == "all" and not as_live else LE_LABELS))  # a copy
    extras = {}
    if as_live:         # the station clusters, placed by the plugin's label layer (le_overlay.station_extras)
        ov = overlay_mod()
        try:
            clusters = ov.panel_station_clusters(freeze_from) if freeze_from is not None else \
                ov.station_clusters(inputs.overlay)
            extras = {"extras": ov.station_extras(clusters)}
        except ov.OverlayError as exc:
            raise BuildError(f"overlay: {exc}") from None
    try:
        if base is not None:        # staging's own grid, so staging is drawn as in its candidate; no fitting
            scale = base[1].scale
            if page.get("band_align"):
                raise BuildError("the schematic's page options hold band_align; HART sets it for the panel here")
            # staging against the left edge, where it stands drawn alone, however wide the other levels are; its
            # labels placed as when it is drawn alone (labels_by_band); and the gaps between the levels as small as
            # is clean (owner, 2026-11-16; band_gap): each level's title TITLE_CLEAR px below the lowest thing of
            # the level above, which for staging is everything its candidate holds (its status cluster stands in
            # the gap). The main level's lowest label is known only once it is drawn: drawn twice
            S = base[1]
            gaps = [band_gap(max(le_mod.extent(S)[3], S.overlay["bottom"]), S.band_boxes[0][3], le_mod),
                    le_mod.BAND_GAP]
            # every single crossover at staging's angle (one grid column across), however each level is stretched
            stepped = with_x(extras, S.station_x)       # the station clusters where staging's candidate has them
            draw = lambda g: le_mod.panel(staging_columns(named_bands(bands, names)), names,  # noqa: E731
                                          cell=le_mod.CELL * scale[0], row=STAGING_ROW * scale[1],
                                          page=dict(page, band_align={STAGING: "left"}), gap=g, labels_by_band=True,
                                          crossover_run=le_mod.CELL * scale[0], **stepped)
            P = draw(gaps)
            if len(P.band_boxes) > 2:
                gaps[1:] = [band_gap(le_mod.extent(P, bi)[3], P.band_boxes[bi][3], le_mod)
                            for bi in range(1, len(P.band_boxes) - 1)]
                P = draw(gaps)
            P.scale, P.fit, P.gaps = scale, None, gaps
        elif as_live:               # the staging candidate: the cut-over grid, no fitting (it scrolls in FIT)
            fitted = le_mod.panel(bands, names, page=page, fit=FIT, row=STAGING_ROW, **extras).scale
            scale = (fitted[0] * STRETCH, fitted[1])
            draw = lambda e: le_mod.panel(staging_columns(bands), names, cell=le_mod.CELL * scale[0],  # noqa: E731
                                          row=STAGING_ROW * scale[1], page=page, **e)
            P = draw(extras)
            xs = cluster_steps(P, STATION_STEPS) if extras else {}
            if xs:                  # again, with the stepped clusters placed at their x (STATION_STEPS)
                P = draw(with_x(extras, xs))
            P.scale, P.fit, P.staging_fit, P.station_x = scale, None, fitted, xs
        else:
            rows = {"row": STAGING_ROW} if levels == "staging" else {}
            drawn = named_bands(bands, names) if levels == "all" else bands
            P = le_mod.panel(drawn, names, page=page, fit=FIT, **rows, **extras)
    except core.SchematicError as exc:
        raise BuildError(f"schematic le: {exc}") from None
    P.mast_notes = check_unplaced(P)
    if unfindable:
        P.log.append(f"live segment idents JMRI does not find as segments, so not reused: {', '.join(unfindable)}")
    check_slots(P, inputs.masts, le_mod)
    check_live_turnouts(le_mod.to_xml(P, "check"), inputs)

    # staging: every name must already be live
    staging_turnouts = set(names[STAGING]["turnouts"].values())
    staging_blocks = set(names[STAGING]["os"].values()) | {b for v in names[STAGING]["blocks"].values() for b in v}
    live_turnouts = tables.by_any_name(tables.turnouts(root))
    live_lb = {tables.user_name(b) for b in tables.layout_blocks(root)}
    missing = sorted(t for t in staging_turnouts if t not in live_turnouts) + \
        sorted(b for b in staging_blocks if b not in live_lb)
    if missing:
        raise BuildError(f"staging names not in the live tables: {missing}")
    if levels == "staging" and set(P.blocks) - staging_blocks:
        raise BuildError(f"the staging panel draws blocks that are not live: {sorted(set(P.blocks) - staging_blocks)}")
    if levels == "all":
        add_level_objects(root, P, names, lengths, staging_blocks)

    if as_live:
        panel_el = le_mod.to_xml(P, panel_name, dict(inputs.attrs), copy.deepcopy(inputs.drawing_options))
        P.sensors_bound = bind_sensors(panel_el, inputs.sensors)
        ov = overlay_mod()
        try:
            if freeze_from is not None:
                inputs.overlay = ov.freeze(freeze_from, panel_el, root, le_mod, slots_module(), inputs.note,
                                           LE_LABELS["switch_prefix"])
            P.overlay = ov.carry(inputs.overlay, panel_el, P, le_mod, slots_module(), FIT,
                                 LE_LABELS["switch_prefix"], frame_blocks=staging_blocks)
        except ov.OverlayError as exc:
            raise BuildError(f"overlay: {exc}") from None
        # a panel larger than its window (the cut-over grid: staging alone is wider, three levels wider and taller)
        # scrolls both ways, so nothing on it is out of reach at 100% zoom; the frozen attribute says "none"
        w, h = P.overlay["size"]
        if w + le_mod.CHROME[0] > FIT[0] or h + le_mod.CHROME[1] > FIT[1]:
            panel_el.set("scrollable", "both")
        # the marker that tells polish_hart_layout_editor.py and the other hand-pixel scripts to leave positions alone
        opts = panel_el.find("layoutTrackDrawingOptions")
        panel_el.insert(list(panel_el).index(opts) + 1 if opts is not None else 0, tables.generated_marker_label())
        if levels == "staging" and approved is not None:
            check_approved(panel_el, approved)
        old = tables.layout_editor(root, panel_name)
        if old is not None:
            replace(root, old, panel_el, 1)
        else:
            insert_first_panel(root, panel_el, 1)
        if base is not None:
            P.staging_same = check_staging_unchanged(base, doc.tobytes(), P, panel_name)
            P.staging_data = base[0]
            check_aspect(P.overlay["size"], le_mod.CHROME)
    else:
        attrs = dict(inputs.attrs)
        attrs.update(scrollable="both", editable="yes", autoblkgenerate="no")
        panel_el = le_mod.to_xml(P, panel_name, attrs, copy.deepcopy(inputs.drawing_options))
        place(root, [panel_el], 1, tables.layout_editors(root)[-1])
    return doc.tobytes(), P, names, bands


# px between the lowest thing of one level (labels, readouts, carried items) and the next level's title
TITLE_CLEAR = 8


def band_gap(lowest: float, box_bottom: float, le_mod) -> float:
    """The gap the plugin leaves below a band whose box (P.band_boxes) ends at `box_bottom` and whose lowest drawn
    thing ends at `lowest`, so the next band's title stands TITLE_CLEAR px below it (the title is drawn TITLE_GAP
    above the next band's box, less 4 px)."""
    return math.ceil(max(0.0, lowest - box_bottom) + le_mod.TITLE_GAP - 4 + TITLE_CLEAR)


def check_aspect(size, chrome, fit=FIT, stretch=STRETCH, tolerance=ASPECT_TOLERANCE) -> None:
    """Stop unless the panel `size` (width, height) has the shape of the `fit` window's panel area (fit less
    `chrome`) within `tolerance`, naming the STRETCH that would give it (the panel's width grows about in step)."""
    want = (fit[0] - chrome[0]) / (fit[1] - chrome[1])
    got = size[0] / size[1]
    if abs(got / want - 1) > tolerance:
        raise BuildError(f"the panel is {size[0]}x{size[1]} px, {got:.3f} wide to 1 high; the {fit[0]}x{fit[1]} "
                         f"window's panel area is {want:.3f}: set STRETCH to about {stretch * want / got:.3f} "
                         f"(now {stretch})")


def canon_sorted(el: ET.Element) -> str:
    """An element as text with each element's attributes in name order and no layout whitespace."""
    e = copy.deepcopy(el)
    for c in e.iter():
        c.attrib = dict(sorted(c.attrib.items()))
        c.tail = None
        c.text = (c.text or "").strip() or None
    return ET.tostring(e, encoding="unicode")


def element_label(el: ET.Element, index: int) -> str:
    """What a panel element is, for a message: its tag and name (ident, mast, text, block, sensor, turnout)."""
    name = next((el.get(a) for a in ("ident", "signalmast", "text", "blockcontents", "sensor", "turnout") if el.get(a)),
                f"#{index}")
    return f"{el.tag} {name}"


def approved_fingerprint(panel_el: ET.Element) -> list[tuple[str, str]]:
    """[(sha256, what)]: the panel's own attributes, then each element in order, then the whole panel."""
    head = ET.Element(panel_el.tag, panel_el.attrib)
    out = [(hashlib.sha256(canon_sorted(head).encode()).hexdigest(), f"LayoutEditor {panel_el.get('name')}")]
    out += [(hashlib.sha256(canon_sorted(el).encode()).hexdigest(), element_label(el, i))
            for i, el in enumerate(panel_el)]
    out.append((hashlib.sha256(canon_sorted(panel_el).encode()).hexdigest(), "panel"))
    return out


def write_approved(panel_el: ET.Element, path: Path = APPROVED, date: str | None = None) -> None:
    """Write the staging panel's fingerprint (approved_fingerprint) to `path` (--approve-staging)."""
    import datetime
    lines = [f"{h} {what}" for h, what in approved_fingerprint(panel_el)]
    try:
        path.write_text(APPROVED_NOTE.format(date=date or datetime.date.today().isoformat()) + "\n".join(lines) + "\n",
                        encoding="utf-8")
    except OSError as exc:
        raise BuildError(f"cannot write {path}: {exc}") from None


def read_approved(path: Path = APPROVED) -> list[tuple[str, str]]:
    """The approved fingerprint's [(sha256, what)]; stops on a missing file or a line of the wrong shape."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BuildError(f"cannot read the approved staging fingerprint {paths.rel(path)}: {exc}; after the owner "
                         "approves the staging panel, run build_layout_le.py --approve-staging") from None
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        m = re.fullmatch(r"([0-9a-f]{64}) (\S.*)", line)
        if not m:
            raise BuildError(f"{paths.rel(path)} line {n}: not '<sha256> <what>'")
        out.append((m.group(1), m.group(2)))
    if len(out) < 2 or out[-1][1] != "panel":
        raise BuildError(f"{paths.rel(path)}: no panel hash on its last line")
    return out


def check_approved(panel_el: ET.Element, path: Path = APPROVED) -> None:
    """Stop with BuildError unless the staging candidate's panel is the one the owner approved (`path`), naming the
    first element that differs."""
    want, got = read_approved(path), approved_fingerprint(panel_el)
    if want[-1] == got[-1]:
        return
    for i, (w, g) in enumerate(zip(want, got)):
        if w != g:
            raise BuildError(f"the staging panel is not the one the owner approved ({paths.rel(path)}): element {i} "
                             f"is {g[1]}, approved {w[1]}" + (" (changed)" if w[1] == g[1] else ""))
    raise BuildError(f"the staging panel is not the one the owner approved ({paths.rel(path)}): it has "
                     f"{len(got) - 2} elements, approved {len(want) - 2}")


def canon(el: ET.Element) -> str:
    """An element as text without layout whitespace: what must match between the two candidates."""
    e = copy.deepcopy(el)
    for c in e.iter():
        c.tail = None
        if c.text is not None and not c.text.strip():
            c.text = None
    return ET.tostring(e, encoding="unicode")


def is_level_bean(el: ET.Element) -> bool:
    """A turnout, block or layout block add_level_objects adds (by its internal system name)."""
    sysname = (el.findtext("systemName") or el.get("systemName") or "").strip()
    if el.tag == "turnout":
        return sysname.startswith(TURNOUT_SYS)
    if el.tag == "block":
        return sysname.startswith(BLOCK_SYS)
    if el.tag == "layoutblock":
        return sysname.startswith("ILB") and sysname[3:].isdigit() and int(sysname[3:]) >= LAYOUT_BLOCK_FIRST
    return False


def level_items(P, panel_el: ET.Element) -> set:
    """ids of the panel elements that belong to main and upper, by the plugin's own band of each: their turnouts,
    points, track segments (and the hidden helix and connector joins, drawn with no band), circles, labels (band
    titles have no band either: every one but staging's) and block contents icons. The plugin writes its labels and
    block contents icons in P.labels and P.bcis order, before the carried items, so the n-th of each on the panel is
    the n-th of the plugin's (checked by text and block)."""
    mine = {P.name(t["ident"]) for t in P.turnouts if t["band"] != 0} | \
        {P.name(k) for k, p in P.points.items() if p["band"] != 0} | \
        {P.name(s["ident"]) for s in P.segments if s.get("band") != 0} | \
        {P.name(sh["ident"]) for sh in P.shapes if sh["band"] != 0}
    staging_title = next((i for i, lb in enumerate(P.labels) if lb.get("kind") == "title"), None)
    if staging_title is None:
        raise BuildError("staging guard: the plugin wrote no band title")
    labels = [el for el in panel_el.findall("positionablelabel")
              if not (el.get("hidden") == "yes" and el.get("text") == tables.GENERATED_PANEL_MARKER)]
    bcis = panel_el.findall("BlockContentsIcon")
    if len(labels) < len(P.labels) or len(bcis) != len(P.bcis):
        raise BuildError(f"staging guard: the panel holds {len(labels)} labels and {len(bcis)} block contents icons, "
                         f"the plugin wrote {len(P.labels)} and {len(P.bcis)}")
    out = {id(el) for el in panel_el if el.get("ident") in mine}
    for i, (el, lb) in enumerate(zip(labels, P.labels)):
        if el.get("text") != lb["text"]:
            raise BuildError(f"staging guard: label {i} on the panel reads {el.get('text')!r}, the plugin wrote "
                             f"{lb['text']!r}")
        if lb["band"] != 0 and i != staging_title:
            out.add(id(el))
    for el, b in zip(bcis, P.bcis):
        if el.get("blockcontents") != b["block"]:
            raise BuildError(f"staging guard: a block contents icon on the panel is {el.get('blockcontents')}, the "
                             f"plugin wrote {b['block']}")
        if b["band"] != 0:
            out.add(id(el))
    return out


# What the three-level candidate may change on the staging candidate's panel (owner, 2026-11-16): its size, and
# what the helix joins change: the staging helix tracks run on to the main level instead of ending at a buffer stop,
# so each of their end bumpers becomes an anchor where the hidden join starts (same place, same mast slot), and the
# track segment reaching it is reconnected to it (helix_join_changes). Masts 38RA and 40RA stay in that slot, so
# their icons do not change.
PANEL_SIZE_ATTRS = ("panelheight", "windowheight", "panelwidth", "windowwidth")


def helix_join_changes(missing: list, extra: list, new_le: ET.Element, P, ends: set, joins: set) -> list[str]:
    """Take out of `missing` (staging-candidate elements not in the three-level panel) and `extra` (the reverse) the
    changes the helix joins make, and only those: a staging end bumper in `ends` that the three-level panel draws as
    an anchor in `joins` at the same place, with the same attributes but its ident, its type ANCHOR and one more
    connection, a hidden join segment (P.joins) starting there; and a track segment that ends at that bumper, with
    the same attributes but that connection, now the anchor. Returns them as notes; anything else stays."""
    notes = []
    segs = {el.get("ident"): el for el in new_le.findall("tracksegment")}
    join_segs = {P.name(i) for i in P.joins}
    anchors = {(el.get("x"), el.get("y")): el for el in extra
               if el.tag == "positionablepoint" and el.get("ident") in joins}
    rename = {}
    for old in [el for el in missing if el.tag == "positionablepoint" and el.get("ident") in ends]:
        new = anchors.get((old.get("x"), old.get("y")))
        if new is None or len(old) or len(new):
            continue
        added = {k: v for k, v in new.attrib.items() if k not in old.attrib}
        want = dict(old.attrib, ident=new.get("ident"), type="ANCHOR")
        seg = segs.get(added.get("connect2name"))
        if set(added) != {"connect2name"} or old.get("type") != "END_BUMPER" or \
                {k: new.get(k) for k in want} != want or seg is None or seg.get("ident") not in join_segs or \
                seg.get("hidden") != "yes" or new.get("ident") not in (seg.get("connect1name"), seg.get("connect2name")):
            continue
        rename[old.get("ident")] = new.get("ident")
        missing.remove(old)
        extra.remove(new)
        notes.append(f"end bumper {old.get('ident')} -> anchor {new.get('ident')} (hidden join {seg.get('ident')} to "
                     f"{seg.get('blockname')}" + (f", {old.get('eastboundsignalmast') or old.get('westboundsignalmast')}"
                                                  if old.get("eastboundsignalmast") or old.get("westboundsignalmast")
                                                  else "") + ")")
    by_ident = {el.get("ident"): el for el in extra if el.tag == "tracksegment"}
    for old in [el for el in missing if el.tag == "tracksegment"]:
        at = [k for k in ("connect1name", "connect2name") if old.get(k) in rename]
        new = by_ident.get(old.get("ident"))
        if len(at) != 1 or new is None or len(old) != len(new) or \
                any(canon_sorted(a) != canon_sorted(b) for a, b in zip(old, new)):
            continue
        if dict(new.attrib) != dict(old.attrib, **{at[0]: rename[old.get(at[0])]}):
            continue
        missing.remove(old)
        extra.remove(new)
        notes.append(f"track segment {old.get('ident')} {at[0]} {old.get(at[0])} -> {new.get(at[0])}")
    return notes


def check_staging_unchanged(base, data: bytes, P, panel_name: str) -> list[str]:
    """Stop with BuildError unless the three-level candidate `data` holds the staging candidate (`base`: build()'s
    result for --levels staging --as-live) unchanged: every bean, every other panel and every element of the staging
    panel (track, mast icons, labels, block contents icons, carried items), but the main and upper objects added
    (level_items), the panel size (PANEL_SIZE_ATTRS) and the helix-join changes the owner accepted
    (helix_join_changes). Returns those helix-join changes, as notes."""
    S = base[1]
    old_root, new_root = tables.loads(base[0]).root, tables.loads(data).root
    bad = []
    if [c.tag for c in old_root] != [c.tag for c in new_root]:
        raise BuildError("staging guard: the top-level sections of the two candidates differ")
    for old, new in zip(old_root, new_root):
        if old.tag == "LayoutEditor" and old.get("name") == panel_name:
            continue
        if old.attrib != new.attrib:
            bad.append(f"<{old.tag}> attributes differ")
        kept = [canon(c) for c in new if not is_level_bean(c)]
        if kept != [canon(c) for c in old]:
            bad.append(f"<{old.tag} {old.get('class') or old.get('name') or ''}> differs beyond the added main and "
                       "upper beans")
    old_le, new_le = tables.layout_editor(old_root, panel_name), tables.layout_editor(new_root, panel_name)
    for k in sorted(set(old_le.attrib) | set(new_le.attrib)):
        if old_le.get(k) != new_le.get(k) and k not in PANEL_SIZE_ATTRS:
            bad.append(f"panel attribute {k}: {old_le.get(k)} -> {new_le.get(k)}")
    ends = {S.name(k) for k, p in S.points.items() if p["type"] == "END_BUMPER"} - \
        {P.name(k) for k, p in P.points.items() if p["type"] == "END_BUMPER"}
    joins = {P.name(i) for (b, i) in P.join_ends if b == 0}     # the staging anchors the hidden joins start at
    level = level_items(P, new_le)
    old_els = defaultdict(list)
    for el in old_le:
        old_els[canon(el)].append(el)
    extra = []
    for el in new_le:
        if id(el) in level:
            continue
        got = old_els.get(canon(el))
        if got:
            got.pop()
        else:
            extra.append(el)
    missing = [el for v in old_els.values() for el in v]
    notes = helix_join_changes(missing, extra, new_le, P, ends, joins)
    if len(notes) != 2 * len(ends):
        bad.append(f"{len(ends)} staging end bumpers ({', '.join(sorted(ends))}) are joined to the next level, but "
                   f"only these helix-join changes are as expected: {notes}")
    for i, el in enumerate(missing + extra):
        bad.append(f"{element_label(el, i)} {'gone or changed' if el in missing else 'new or changed'}")
    if bad:
        raise BuildError("staging guard: the three-level candidate changes the approved staging panel: " +
                         "; ".join(bad[:20]) + (f" (and {len(bad) - 20} more)" if len(bad) > 20 else ""))
    return notes


def insert_first_panel(root: ET.Element, new: ET.Element, depth: int) -> None:
    """Put `new` before the first Layout Editor panel of `root` (where the hand-drawn panel stood, before the
    Dispatcher System panel), indented as JMRI writes."""
    first = tables.layout_editors(root)[0]
    idx = list(root).index(first)
    ET.indent(new, space="  ", level=depth)
    new.tail = root[idx - 1].tail if idx else root.text
    root.insert(idx, new)


def add_level_objects(root: ET.Element, P, names: dict, lengths: dict, staging_blocks: set) -> None:
    """Main and upper: their turnouts, blocks and layout blocks in the tables, under the device-map user names
    (level_names) on internal system names (TURNOUT_SYS, BLOCK_SYS, ILB from LAYOUT_BLOCK_FIRST), so nothing reaches
    MQTT or the field."""
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


def live_target(out: Path) -> bool:
    """True when `out` is the live tables.xml or lies in the JMRI profile (by path or through a link)."""
    real = Path(os.path.realpath(out))
    # the checkout's own file, whatever HART_TABLES points TABLES_XML at
    if real in (Path(os.path.realpath(paths.REPO_TABLES_XML)), Path(os.path.realpath(paths.TABLES_XML))):
        return True
    profile = Path(os.path.realpath(paths.JMRI_USER_FILES))
    return real == profile or profile in real.parents


SIGNAL_GRAPH = "staging.json"      # the plan graph in inputs/ the signal reader matches staging's masts on


def freeze(tables_path: Path = paths.TABLES_XML, folder: Path = le_inputs.FOLDER, date: str | None = None) -> list:
    """Read every staging input off the hand-drawn panel in `tables_path` into the frozen files in `folder`, once
    (le_inputs.py): its turnouts, tracks, kept idents, Entry/Exit sensors, masts (with their schematic runs, by the
    plugin's signal reader, as build_signals.py read them before) and overlay (le_overlay.freeze), and its
    attributes. Refuses a generated panel. The files are written to a new folder beside `folder` first; the cut-over
    candidate is rebuilt from them there and must be byte for byte the one built from the panel, and the signals the
    reader's. Only then do they replace `folder` (each step a rename); on any failure `folder` is left as it was.
    Every failure is a BuildError (or le_inputs.InputsError). Returns the files written."""
    import datetime
    import shutil
    import tempfile

    try:
        root = tables.read(tables_path)
    except (OSError, ET.ParseError, ValueError) as exc:
        raise BuildError(f"cannot read {tables_path}: {exc}") from None
    live_le = tables.layout_editor(root, TEMPLATE_PANEL)
    if live_le is None:
        raise BuildError(f"{tables_path} has no {TEMPLATE_PANEL!r} panel to freeze")
    if tables.generated_panel(live_le):
        raise BuildError(f"the {TEMPLATE_PANEL!r} panel in {tables_path} is a generated one (it holds the "
                         "generated-panel marker): the inputs are frozen from the hand-drawn panel only")
    plugin()
    reader = importlib.import_module("schematic.signal_reader")
    layers = importlib.import_module("schematic.layers")
    panel_reader = importlib.import_module("schematic.panel_reader")
    try:
        overrides = layers.load("staging", str(pd.DATA), preferences=False)
        graph = json.loads((pd.GRAPHS / SIGNAL_GRAPH).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:        # a missing or unparsable layer file or plan graph
        raise BuildError(f"cannot read the staging plan overrides or {SIGNAL_GRAPH}: {exc}") from None
    try:
        signals = reader.read(str(tables_path), graph, overrides, panel_reader.load_numbers(str(SWITCHES)),
                              panel_reader.load_lengths(str(paths.LAYOUT_DATA / "block_lengths.csv")),
                              TEMPLATE_PANEL)
    except Exception as exc:        # the plugin's own errors (PlanError and others): named, not a traceback
        raise BuildError(f"signal reader on {tables_path}: {type(exc).__name__}: {exc}") from None
    try:
        source = paths.rel(Path(tables_path))
    except ValueError:
        source = Path(tables_path).name
    note = le_inputs.NOTE.format(panel=TEMPLATE_PANEL, source=source,
                                 date=date or datetime.date.today().isoformat())
    inputs = le_inputs.from_live(root, live_le, slots_module(), signals, overrides.get("mast_prefix", ""), note)
    # the freeze compares two builds with each other; whether the owner approved that panel is the cut-over's check
    data = build(tables_path, levels="staging", as_live=True, inputs=inputs, freeze_from=live_le, approved=None)[0]
    folder = Path(folder)
    try:
        folder.parent.mkdir(parents=True, exist_ok=True)
        fresh = Path(tempfile.mkdtemp(prefix=f".{folder.name}.new.", dir=folder.parent))
    except OSError as exc:
        raise BuildError(f"cannot make a folder beside {folder}: {exc}") from None
    try:
        written = le_inputs.write(inputs, fresh)
        again = le_inputs.load(fresh)
        if le_inputs.signal_rows(again.masts) != signals["signals"]:
            raise BuildError("the written masts.csv does not give back the signal reader's runs")
        if build(tables_path, levels="staging", as_live=True, inputs=again, approved=None)[0] != data:
            raise BuildError("the written files do not rebuild the panel built from the hand-drawn one")
        old = None
        if folder.exists():
            old = Path(tempfile.mkdtemp(prefix=f".{folder.name}.old.", dir=folder.parent)) / folder.name
            folder.rename(old)
        try:
            fresh.rename(folder)
        except OSError:
            if old is not None:
                old.rename(folder)          # put the committed files back
            raise
        if old is not None:
            shutil.rmtree(old.parent)
    except OSError as exc:
        raise BuildError(f"cannot put the frozen files in {folder}: {exc}") from None
    finally:
        if fresh.exists():
            shutil.rmtree(fresh)
    return [folder / p.name for p in written]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="regenerate in memory and fail if the file differs")
    ap.add_argument("--levels", choices=LEVELS, default=None,
                    help="all: every band, main and upper under the device map's names (default); staging: staging "
                         "alone")
    ap.add_argument("--as-live", action="store_true",
                    help="write the cut-over candidate: the live panel replaced by the new one; with --levels all "
                         "(the default) all three levels at staging's grid (tables_cutover.xml), with --levels "
                         "staging staging alone (tables_cutover_staging.xml)")
    ap.add_argument("--out", type=Path, help="where to write (default: the trial file for these options: "
                    "tables_layout.xml, tables_layout_staging.xml, tables_cutover.xml or "
                    "tables_cutover_staging.xml)")
    ap.add_argument("--tables", type=Path, help="the tables file to build on (default: this checkout's); with "
                    "--freeze, the tables holding the hand-drawn panel")
    ap.add_argument("--freeze", action="store_true",
                    help="one-shot: read the staging inputs off the hand-drawn panel into the frozen files "
                         f"({paths.rel(le_inputs.FOLDER)}), then check they rebuild the same candidate")
    ap.add_argument("--freeze-to", type=Path,
                    help="with --freeze: the folder to write (default: the frozen files' own)")
    ap.add_argument("--review", action="store_true",
                    help="with --as-live: write the candidate for the owner to review although its staging panel is "
                         f"not the approved one ({paths.rel(APPROVED)} is not checked; the run says so)")
    ap.add_argument("--approve-staging", action="store_true",
                    help="after the owner approves the staging panel in PanelPro: record its fingerprint in "
                         f"{paths.rel(APPROVED)}, which both cut-over builds then check")
    args = ap.parse_args(argv)
    if not args.check:          # --freeze writes the committed frozen files: refused with HART_TABLES as any write
        message = paths.check_only_message(Path(__file__).name)
        if message:
            print(f"ERROR: {message}")
            return 1
    if args.approve_staging:
        if args.check or args.freeze or args.freeze_to or args.as_live or args.out or args.levels is not None \
                or args.review:
            print("ERROR: --approve-staging takes only --tables")
            return 1
        try:
            where = {} if args.tables is None else {"live_path": args.tables}
            data = build(levels="staging", as_live=True, approved=None, **where)[0]
            write_approved(tables.layout_editor(tables.loads(data).root, TEMPLATE_PANEL))
        except le_inputs.InputsError as exc:
            print(f"ERROR: {exc}")
            return 1
        print(f"wrote {paths.rel(APPROVED)}: the staging panel as the owner approved it")
        return 0
    if args.freeze:
        if args.check or args.as_live or args.out or args.levels is not None or args.review:
            print("ERROR: --freeze takes only --tables and --freeze-to")
            return 1
        try:
            written = freeze(args.tables or paths.TABLES_XML, args.freeze_to or le_inputs.FOLDER)
        except le_inputs.InputsError as exc:
            print(f"ERROR: {exc}")
            return 1
        for p in written:
            print(f"wrote {p}")
        print("ok: the written files rebuild the same cut-over candidate")
        return 0
    if args.freeze_to is not None:
        print("ERROR: --freeze-to goes with --freeze")
        return 1
    if args.review and not args.as_live:
        print("ERROR: --review goes with --as-live")
        return 1
    levels = args.levels or "all"
    out = args.out or default_out(levels, args.as_live)
    if live_target(out):
        print(f"ERROR: {out} is the live tables or in the JMRI profile; the trial is for viewing only and is "
              "written beside them, never over them")
        return 1
    try:
        where = {} if args.tables is None else {"live_path": args.tables}
        if args.review:
            where["approved"] = None
        data, P, _names, _bands = build(levels=levels, as_live=args.as_live, **where)
    except le_inputs.InputsError as exc:
        print(f"ERROR: {exc}")
        return 1
    _, le_mod, _ = plugin()
    summary = f"panel {(TEMPLATE_PANEL if args.as_live else PANEL_NAME)!r}: {le_mod.summary(P)}"
    # the three-level candidate writes the staging candidate it holds beside it (tables_cutover_staging.xml)
    files = [(out, data)]
    if getattr(P, "staging_data", None) is not None:
        files.append((staging_out(out), P.staging_data))
    if args.check:
        stale = [f for f, d in files if not f.exists() or f.read_bytes() != d]
        if stale:
            print(f"STALE: {', '.join(paths.rel(f) for f in stale)}; run {paths.rel(Path(__file__))}")
            return 1
        print(f"ok: {', '.join(paths.rel(f) for f, _d in files)} current ({summary})")
        return 0
    for f, d in files:
        if live_target(f):
            print(f"ERROR: {f} is the live tables or in the JMRI profile")
            return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    for f, d in files:
        tables.loads(d, path=f).save(f)
    print(f"wrote {paths.rel(out)}: {summary}")
    if args.review:
        print(f"  REVIEW: the staging panel was not checked against the approved one ({paths.rel(APPROVED)}); it is "
              "UNAPPROVED until the owner approves it in PanelPro and --approve-staging records it")
    if len(files) > 1:
        print(f"wrote {paths.rel(files[1][0])}: the staging candidate it holds")
    moved = {f"{t}: mast {m}: {why}" for t, m, why in P.moved}       # the plugin's own log line for each
    for line in P.log:
        if line not in moved:
            print(f"  note: {line}")
    for line in P.mast_notes:
        print(f"  mast at a helix join: {line}")
    for line in overlay_lines(getattr(P, "overlay", None)):
        print(f"  overlay: {line}")
    if getattr(P, "gaps", None):
        print(f"  gaps between the levels: {', '.join(f'{g:g}' for g in P.gaps)} px; grid {P.scale[0]:.4f} x "
              f"{P.scale[1]:.4f} (STRETCH {STRETCH})")
    same = getattr(P, "staging_same", None)
    if same is not None:
        print(f"  staging guard: the {'(unapproved) ' if args.review else 'approved '}staging candidate is held "
              "unchanged but for the helix joins:")
        for line in same:
            print(f"    {line}")
    return 0


def staging_out(out: Path) -> Path:
    """Where the three-level candidate `out` writes the staging candidate it holds: tables_cutover.xml ->
    tables_cutover_staging.xml (CUTOVER_STAGING)."""
    return out.with_name(f"{out.stem}_staging{out.suffix}")


def default_out(levels: str, as_live: bool) -> Path:
    """The trial file for these options, so --check always compares like with like."""
    if as_live:
        return CUTOVER_STAGING if levels == "staging" else CUTOVER
    return TRIAL_STAGING if levels == "staging" else TRIAL


def overlay_lines(report) -> list[str]:
    """The overlay report (le_overlay.carry) as printed lines; none without one."""
    if not report:
        return []
    ov = overlay_mod()
    kinds = defaultdict(int)
    for r in report["records"]:
        kinds[r["anchor"].split(" ", 1)[0] if r["anchor"].startswith("group") else r["anchor"]] += 1
    out = [f"{len(report['records'])} live items carried ({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))})"
           f"; panel {report['size'][0]}x{report['size'][1]} px",
           "placed around the generated " + (", ".join(f"{v} {k if k.endswith('s') else k + 's'}"
                                                       for k, v in sorted(report["generated"].items())) or "nothing") +
           "; left to the generator: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in report["dropped"].items()
                                                   if k in ov.GIVEN) +
           "; not carried: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in report["dropped"].items()
                                         if k in ov.NOT_CARRIED)]
    out += report["notes"]
    if report["unchained"]:
        out.append("blocks whose track is not one run (an item's share read against its pieces in order): "
                   + ", ".join(report["unchained"]))
    far = sorted(report["records"], key=lambda r: -r["nudged"])[:5]
    out.append("nudged furthest: " + ", ".join(f"{r['item']} {r['nudged']:g} px" for r in far))
    return out


if __name__ == "__main__":
    sys.exit(main())
