#!/usr/bin/env python3
"""RETIRED workaround — kept only as the historical CATS-pairs oracle.

SML is now native: the Layout Editor panel defects that blocked Discover
were fixed (see cats/scripts/validate_le_signalling.py and
cats/docs/SIGNAL_FACING.md), Discover generates the pairs with
useLayoutEditor=yes, and they are stored in tables/new_tables.xml. The
startup Jython twin was removed from the Mac and Pi profiles.

PAIRS below is the CATS-derived list this workaround used to apply. It is
imported by validate_le_signalling.py as a historical comparison oracle.
Known defects in PAIRS (why it is only historical):
- opposing-face pairs (Plane EME <-> Barn D, the OS 117 plant pairs) that
  SML never models; replaced by true next-mast-down-the-line pairs
- 114LB / K-2 -> 111a rows are geometrically impossible
  (LH crossover 113 cannot route bottom-east to top-west)
- balloon A48 rows had source/dest direction swapped

Running this script would OVERWRITE the native SML — it now refuses
without --force-legacy.
"""

from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEW_TABLES = ROOT / "tables/new_tables.xml"
SYNC_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
JYTHON = ROOT / "jmri/layouts/hart/scripts/apply_sml_cats_pairs.py"

# source, dest, blocks (must be unoccupied), turnouts [(userName, closed|thrown)]
# Turnout polarity: TURNOUT_STATE_SOURCES.md / SIGNAL_FACING.md.
PAIRS: list[tuple[str, str, list[str], list[tuple[str, str]]]] = [
    # South line: Plane EME ↔ Barn D across East Main Ext (not East End Main West).
    (
        "102LB",
        "117RB",
        ["East Main Ext"],
        [],
    ),
    (
        "117RB",
        "102LB",
        ["East Main Ext"],
        [],
    ),
    (
        "117RB",
        "112R",
        ["OS 117b", "Main East"],
        [("Switch 117", "closed")],
    ),
    (
        "117RB",
        "117RA",
        ["OS 117"],
        [("Switch 117", "thrown")],
    ),
    (
        "117LA",
        "102LB",
        ["East Main Ext"],
        [("Switch 117", "closed")],
    ),
    (
        "102LA",
        "117RA",
        ["Scale"],
        [("Switch 102", "thrown")],
    ),
    (
        "117RA",
        "117LB",
        ["OS 117", "Barn"],
        [("Switch 117", "closed")],
    ),
    (
        "100L",
        "117RB",
        ["OS 102", "East Main Ext"],
        [("Switch 100", "thrown"), ("Switch 102", "closed")],
    ),
    (
        "100L",
        "117RA",
        ["OS 102", "Scale"],
        [("Switch 100", "thrown"), ("Switch 102", "thrown")],
    ),
    (
        "111L",
        "100L",
        ["Main West"],
        [("Switch 111", "closed")],
    ),
    (
        "112L",
        "117LA",
        ["OS 112", "Main East"],
        [("Switch 112", "thrown")],
    ),
    (
        "112R",
        "113RB",
        ["East Lead"],
        [("Switch 112", "thrown")],
    ),
    (
        "110R",
        "113RB",
        ["OS 110", "East Lead"],
        [("Switch 110", "thrown"), ("Switch 112", "closed")],
    ),
    (
        "111RA",
        "113RA",
        ["West Main Ext"],
        [("Switch 111", "closed")],
    ),
    (
        "111RB",
        "113RB",
        ["S-1", "East Lead"],
        [("Switch 111", "closed"), ("Switch 112", "closed")],
    ),
    (
        "117LB",
        "117RA",
        ["Barn", "OS 117"],
        [("Switch 117", "closed")],
    ),
    (
        "117LB",
        "102LA",
        ["Barn", "Scale"],
        [("Switch 117", "thrown")],
    ),
    # 114/115 C homes face west. Dest 111a (113 closed) or East Lead (113 thrown).
    (
        "115LB",
        "111L",
        ["OS 115", "West Main Ext"],
        [("Switch 115", "thrown"), ("Switch 113", "closed")],
    ),
    (
        "115LB",
        "112L",
        ["OS 115", "East Lead"],
        [("Switch 115", "thrown"), ("Switch 113", "thrown")],
    ),
    (
        "114LB",
        "111L",
        ["OS 114", "West Main Ext"],
        [("Switch 114", "thrown"), ("Switch 113", "closed")],
    ),
    (
        "114LB",
        "112L",
        ["OS 114", "East Lead"],
        [("Switch 114", "thrown"), ("Switch 113", "thrown")],
    ),
    (
        "115LA",
        "111L",
        ["OS 115", "West Main Ext"],
        [("Switch 115", "closed"), ("Switch 113", "closed")],
    ),
    (
        "115LA",
        "112L",
        ["OS 115", "East Lead"],
        [("Switch 115", "closed"), ("Switch 113", "thrown")],
    ),
    (
        "114LA",
        "111L",
        ["OS 114", "West Main Ext"],
        [("Switch 114", "closed"), ("Switch 113", "closed")],
    ),
    (
        "114LA",
        "112L",
        ["OS 114", "East Lead"],
        [("Switch 114", "closed"), ("Switch 113", "thrown")],
    ),
    (
        "113RA",
        "120L",
        ["OS 113b", "OS 115"],
        [("Switch 113", "closed"), ("Switch 115", "thrown")],
    ),
    (
        "113RA",
        "115LA",
        ["OS 113b", "OS 115"],
        [("Switch 113", "closed"), ("Switch 115", "closed")],
    ),
    (
        "113RB",
        "120R",
        ["OS 113a", "OS 114"],
        [("Switch 113", "closed"), ("Switch 114", "thrown")],
    ),
    (
        "113RB",
        "114LA",
        ["OS 113a", "OS 114"],
        [("Switch 113", "closed"), ("Switch 114", "closed")],
    ),
    # Balloon: dest each other across A48. Adjacent CPs — no intermediate
    # occupancy. (Old shared 1-1/1-2 circuit stuffed McKees Rocks onto
    # 120L→120R so either track occupied Stopped both; sensors are independent now.)
    (
        "120R",
        "120L",
        [],
        [],
    ),
    (
        "120L",
        "120R",
        [],
        [],
    ),
    (
        "101RA",
        "111RA",
        ["W-1", "OS 101", "Main West"],
        [("Switch 101", "closed")],
    ),
    (
        "101RB",
        "111RA",
        ["W-2", "OS 101", "Main West"],
        [("Switch 101", "thrown")],
    ),
]


def _dest_xml(dest: str, blocks: list[str], turnouts: list[tuple[str, str]]) -> str:
    lines = [
        f'      <destinationMast destination="{dest}">',
        f"        <destinationSignalMast>{dest}</destinationSignalMast>",
        "        <comment>CATS dest; stored occupancy/turnouts (useLayoutEditor=no)</comment>",
        "        <enabled>yes</enabled>",
        "        <allowAutoMaticSignalMastGeneration>no</allowAutoMaticSignalMastGeneration>",
        "        <useLayoutEditor>no</useLayoutEditor>",
        "        <useLayoutEditorTurnouts>no</useLayoutEditorTurnouts>",
        "        <useLayoutEditorBlocks>no</useLayoutEditorBlocks>",
        "        <lockTurnouts>no</lockTurnouts>",
    ]
    if blocks:
        lines.append("        <blocks>")
        for name in blocks:
            lines.append("          <block>")
            lines.append(f"            <blockName>{name}</blockName>")
            lines.append("            <blockState>unoccupied</blockState>")
            lines.append("          </block>")
        lines.append("        </blocks>")
    if turnouts:
        lines.append("        <turnouts>")
        for name, state in turnouts:
            lines.append("          <turnout>")
            lines.append(f"            <turnoutName>{name}</turnoutName>")
            lines.append(f"            <turnoutState>{state}</turnoutState>")
            lines.append("          </turnout>")
        lines.append("        </turnouts>")
    lines.append("      </destinationMast>")
    return "\n".join(lines)


def signalmastlogics_xml() -> str:
    by_src: dict[str, list[tuple[str, list[str], list[tuple[str, str]]]]] = defaultdict(list)
    for src, dest, blocks, turnouts in PAIRS:
        by_src[src].append((dest, blocks, turnouts))
    chunks = [
        '  <signalmastlogics class="jmri.managers.configurexml.DefaultSignalMastLogicManagerXml">',
        "    <logicDelay>500</logicDelay>",
    ]
    for src in by_src:
        chunks.append(f'    <signalmastlogic source="{src}">')
        chunks.append(f"      <sourceSignalMast>{src}</sourceSignalMast>")
        for dest, blocks, turnouts in by_src[src]:
            chunks.append(_dest_xml(dest, blocks, turnouts))
        chunks.append("    </signalmastlogic>")
    chunks.append("  </signalmastlogics>")
    return "\n".join(chunks)


def replace_signalmastlogics(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.find("<signalmastlogics")
    end = text.find("</signalmastlogics>")
    if start < 0 or end < 0:
        raise SystemExit(f"no signalmastlogics in {path}")
    end += len("</signalmastlogics>")
    path.write_text(text[:start] + signalmastlogics_xml() + text[end:], encoding="utf-8")


def jython_script() -> str:
    pair_lines = []
    for src, dest, blocks, turnouts in PAIRS:
        b = ", ".join('"%s"' % x for x in blocks)
        t = ", ".join('("%s", "%s")' % (n, s) for n, s in turnouts)
        pair_lines.append('    ("%s", "%s", [%s], [%s]),' % (src, dest, b, t))
    pairs_blob = "\n".join(pair_lines)
    return '''# JMRI jython — apply CATS-matching SML dests in the running JVM.
#
# Generated by cats/scripts/apply_sml_cats_pairs.py. Safe to re-run.
# Must run on the Swing thread AFTER Layout Editor exists. XML SML load
# calls initialise() before the panel, so dests are already "init" with
# Discover pathfinding. Re-adding the dest is what actually enables it.
# CATS ABS must stay unbound; do not setAspect on these masts.

import jmri
from java.lang import Thread, Runnable
from java.util import Hashtable
from javax.swing import SwingUtilities
from jmri import Block, Turnout, InstanceManager
from jmri.jmrit.display.layoutEditor import LayoutBlockManager

smm = InstanceManager.getDefault(jmri.SignalMastManager)
smlm = InstanceManager.getDefault(jmri.SignalMastLogicManager)
bm = InstanceManager.getDefault(jmri.BlockManager)
tm = InstanceManager.turnoutManagerInstance()
nbhm = InstanceManager.getDefault(jmri.NamedBeanHandleManager)
lbm = InstanceManager.getDefault(LayoutBlockManager)

PAIRS = [
%s
]


def _mast(name):
    m = smm.getSignalMast(name)
    if m is None:
        print("apply_sml_cats_pairs: missing mast", name)
    return m


def _apply(src_name, dest_name, blocks, turnouts):
    src = _mast(src_name)
    dest = _mast(dest_name)
    if src is None or dest is None:
        return False
    logic = smlm.newSignalMastLogic(src)
    try:
        if dest in logic.getDestinationList():
            logic.removeDestination(dest)
    except Exception as e:
        print("apply_sml_cats_pairs: remove", src_name, dest_name, e)
    logic.setDestinationMast(dest)
    logic.setEnabled(dest)
    logic.allowAutoMaticSignalMastGeneration(False, dest)
    try:
        logic.useLayoutEditorDetails(False, False, dest)
    except Exception as e:
        print("apply_sml_cats_pairs: useLayoutEditorDetails", src_name, e)
    try:
        logic.useLayoutEditor(False, dest)
    except Exception as e:
        print("apply_sml_cats_pairs: useLayoutEditor(false)", src_name, e)
        return False
    blist = Hashtable()
    for bname in blocks:
        blk = bm.getBlock(bname)
        if blk is None:
            print("apply_sml_cats_pairs: missing block", bname)
            continue
        blist.put(blk, Block.UNOCCUPIED)
    logic.setBlocks(blist, dest)
    tlist = Hashtable()
    for tname, state in turnouts:
        to = tm.getTurnout(tname)
        if to is None:
            print("apply_sml_cats_pairs: missing turnout", tname)
            continue
        value = Turnout.THROWN if state == "thrown" else Turnout.CLOSED
        tlist.put(nbhm.getNamedBeanHandle(tname, to), value)
    logic.setTurnouts(tlist, dest)
    try:
        logic.useLayoutEditor(False, dest)
    except Exception:
        pass
    using_le = True
    try:
        using_le = logic.useLayoutEditor(dest)
    except Exception:
        pass
    if using_le:
        print("apply_sml_cats_pairs: STILL useLayoutEditor", src_name, "->", dest_name)
        return False
    return True


def _run():
    n = 0
    fail = 0
    for src, dest, blocks, turnouts in PAIRS:
        if _apply(src, dest, blocks, turnouts):
            n += 1
        else:
            fail += 1
    print("apply_sml_cats_pairs: applied", n, "dests, failed", fail)


class _Apply(Runnable):
    def run(self):
        try:
            _run()
        except Exception:
            import traceback
            traceback.print_exc()


class _Wait(Runnable):
    def run(self):
        Thread.sleep(10000)
        SwingUtilities.invokeLater(_Apply())


if lbm.routingStablised():
    print("apply_sml_cats_pairs: routing settled, apply on EDT")
    SwingUtilities.invokeLater(_Apply())
else:
    t = Thread(_Wait())
    t.setDaemon(True)
    t.setName("apply_sml_cats_pairs")
    t.start()
    print("apply_sml_cats_pairs: will apply on EDT in 10s")
''' % pairs_blob


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jython-only", action="store_true")
    ap.add_argument("--force-legacy", action="store_true",
                    help="really overwrite native SML with the legacy hand pairs")
    args = ap.parse_args()
    if not args.force_legacy:
        raise SystemExit(
            "apply_sml_cats_pairs.py is retired: SML is native (Discover) now.\n"
            "This would overwrite tables/new_tables.xml SML with the legacy hand\n"
            "pairs. Use --force-legacy only to reproduce the old workaround."
        )
    JYTHON.write_text(jython_script(), encoding="utf-8")
    print("wrote", JYTHON.relative_to(ROOT))
    if args.jython_only:
        return
    replace_signalmastlogics(NEW_TABLES)
    shutil.copy2(NEW_TABLES, SYNC_TABLES)
    print("updated", NEW_TABLES.relative_to(ROOT))
    print("copied", SYNC_TABLES.relative_to(ROOT))
    print("%d dest pairs" % len(PAIRS))


if __name__ == "__main__":
    main()
