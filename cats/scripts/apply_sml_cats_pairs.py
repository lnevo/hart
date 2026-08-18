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
- Princess South McKeesport / K-2 -> 111a rows are geometrically impossible
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
        "Plane East East Main Ext",
        "West Yard West East Main Ext",
        ["East Main Ext"],
        [],
    ),
    (
        "West Yard West East Main Ext",
        "Plane East East Main Ext",
        ["East Main Ext"],
        [],
    ),
    (
        "West Yard West East Main Ext",
        "East End South OS 112",
        ["OS 117b (West Yard)", "Main East"],
        [("Switch 117", "closed")],
    ),
    (
        "West Yard West East Main Ext",
        "West Yard West OS 117",
        ["OS 117 (West Yard)"],
        [("Switch 117", "thrown")],
    ),
    (
        "West Yard East OS 117b",
        "Plane East East Main Ext",
        ["East Main Ext"],
        [("Switch 117", "closed")],
    ),
    (
        "Plane East OS 102",
        "West Yard West OS 117",
        ["Yard T1"],
        [("Switch 102", "thrown")],
    ),
    (
        "West Yard West OS 117",
        "West Yard East Yard T6",
        ["OS 117 (West Yard)", "Yard T6"],
        [("Switch 117", "closed")],
    ),
    (
        "Brick East Main West",
        "West Yard West East Main Ext",
        ["OS 102 (Plane)", "East Main Ext"],
        [("Switch 100", "thrown"), ("Switch 102", "closed")],
    ),
    (
        "Brick East Main West",
        "West Yard West OS 117",
        ["OS 102 (Plane)", "Yard T1"],
        [("Switch 100", "thrown"), ("Switch 102", "thrown")],
    ),
    (
        "East End East OS 111a",
        "Brick East Main West",
        ["Main West"],
        [("Switch 111", "closed")],
    ),
    (
        "East End East Lead",
        "West Yard East OS 117b",
        ["OS 112 (East End)", "Main East"],
        [("Switch 112", "thrown")],
    ),
    (
        "East End South OS 112",
        "Princess West OS 113a",
        ["East Lead"],
        [("Switch 112", "thrown")],
    ),
    (
        "East End South OS 110",
        "Princess West OS 113a",
        ["OS 110 (East End)", "East Lead"],
        [("Switch 110", "thrown"), ("Switch 112", "closed")],
    ),
    (
        "East End West Main West",
        "Princess West OS 113b",
        ["West Main Ext"],
        [("Switch 111", "closed")],
    ),
    (
        "East End West Yard Track 1",
        "Princess West OS 113a",
        ["Yard Track 1", "East Lead"],
        [("Switch 111", "closed"), ("Switch 112", "closed")],
    ),
    (
        "West Yard East Yard T6",
        "West Yard West OS 117",
        ["Yard T6", "OS 117 (West Yard)"],
        [("Switch 117", "closed")],
    ),
    (
        "West Yard East Yard T6",
        "Plane East OS 102",
        ["Yard T6", "Yard T1"],
        [("Switch 117", "thrown")],
    ),
    # 114/115 C homes face west. Dest 111a (113 closed) or East Lead (113 thrown).
    (
        "Princess North McKees Rocks",
        "East End East OS 111a",
        ["OS 115 (Princess)", "West Main Ext"],
        [("Switch 115", "thrown"), ("Switch 113", "closed")],
    ),
    (
        "Princess North McKees Rocks",
        "East End East Lead",
        ["OS 115 (Princess)", "East Lead"],
        [("Switch 115", "thrown"), ("Switch 113", "thrown")],
    ),
    (
        "Princess South McKeesport",
        "East End East OS 111a",
        ["OS 114 (Princess)", "West Main Ext"],
        [("Switch 114", "thrown"), ("Switch 113", "closed")],
    ),
    (
        "Princess South McKeesport",
        "East End East Lead",
        ["OS 114 (Princess)", "East Lead"],
        [("Switch 114", "thrown"), ("Switch 113", "thrown")],
    ),
    (
        "Princess East K-1",
        "East End East OS 111a",
        ["OS 115 (Princess)", "West Main Ext"],
        [("Switch 115", "closed"), ("Switch 113", "closed")],
    ),
    (
        "Princess East K-1",
        "East End East Lead",
        ["OS 115 (Princess)", "East Lead"],
        [("Switch 115", "closed"), ("Switch 113", "thrown")],
    ),
    (
        "Princess East K-2",
        "East End East OS 111a",
        ["OS 114 (Princess)", "West Main Ext"],
        [("Switch 114", "closed"), ("Switch 113", "closed")],
    ),
    (
        "Princess East K-2",
        "East End East Lead",
        ["OS 114 (Princess)", "East Lead"],
        [("Switch 114", "closed"), ("Switch 113", "thrown")],
    ),
    (
        "Princess West OS 113b",
        "Princess East McKees Rocks",
        ["OS 113b (Princess)", "OS 115 (Princess)"],
        [("Switch 113", "closed"), ("Switch 115", "thrown")],
    ),
    (
        "Princess West OS 113b",
        "Princess East K-1",
        ["OS 113b (Princess)", "OS 115 (Princess)"],
        [("Switch 113", "closed"), ("Switch 115", "closed")],
    ),
    (
        "Princess West OS 113a",
        "Princess East McKeesport",
        ["OS 113a (Princess)", "OS 114 (Princess)"],
        [("Switch 113", "closed"), ("Switch 114", "thrown")],
    ),
    (
        "Princess West OS 113a",
        "Princess East K-2",
        ["OS 113a (Princess)", "OS 114 (Princess)"],
        [("Switch 113", "closed"), ("Switch 114", "closed")],
    ),
    # Balloon: dest each other. Rocks includes McKees Rocks so occupy → Stop.
    # McKeesport has no intermediate — dest Stop → Slow Clear / Restricting.
    (
        "Princess East McKeesport",
        "Princess East McKees Rocks",
        [],
        [],
    ),
    (
        "Princess East McKees Rocks",
        "Princess East McKeesport",
        ["McKees Rocks"],
        [],
    ),
    (
        "Brick West Yard 1",
        "East End West Main West",
        ["West Yard 1", "OS 101 (Brick)", "Main West"],
        [("Switch 101", "closed")],
    ),
    (
        "Brick West Yard 2",
        "East End West Main West",
        ["West Yard 2", "OS 101 (Brick)", "Main West"],
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
