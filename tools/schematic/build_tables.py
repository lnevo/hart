#!/usr/bin/env python3
"""Write jmri/layouts/hart/output/tables.xml, the file PanelPro and CATS load, from its sources (ADR-029).

    python3 tools/schematic/build_tables.py                          # write tables.xml
    python3 tools/schematic/build_tables.py --check                  # exit 1 if tables.xml is not what it writes
    python3 tools/schematic/build_tables.py --discovered-from STORE  # take the Signal Mast Logic of a discovery
                                                                     # Store (run_sml_discover.sh), then write
    python3 tools/schematic/build_tables.py --discovery-base         # write tables.xml with no Signal Mast Logic:
                                                                     # what run_sml_discover.sh runs discovery on

tables.xml is an output; nothing reads it as a source. It is, in this order:
1. the template, data/tables_template.xml: what PanelPro owns (settings, memories, the clock sensor, the "Hide windows
   on start" LogixNG), and the fixed envelope (hartlib.tables_build: no file history, "Written by" comment, clock
   time or memory values);
2. every level's beans of the device master: turnouts, sensors, heads, masts, blocks (lengths
   from block_lengths.csv) and layout blocks, each from its row's columns (its jmri_name, its bean_comment or the
   comment its wiring columns give), and the startup LogixNG that sets each virtual detector and turnout to its
   row's start, each section in JMRI's system-name order (hartlib.tables_build.base);
3. the Layout Editor build on that base (build_layout_le.build, levels all), which adds no bean: the "HART Railroad"
   panel (make panels
   checks it against the owner-approved fingerprint after this writes it: check_approved.py le-panel), then the
   three band panels after it, "Staging Level", "Main Level" and "Upper Level": copies of that panel trimmed to one
   band each, joined by edge connectors where the full panel joins two bands (band_panels.add);
4. the discovered Signal Mast Logic and mast properties, data/schematic/discovered_sml.xml, which only
   --discovered-from writes. The build stops when that file names a mast the tables no longer hold (a mast renamed
   or removed since discovery) and when a mast has no discovered logic it needs (missing_logic: every head mast is a
   source, every virtual mast a destination): run jmri/layouts/hart/scripts/run_sml_discover.sh, which first writes
   the tables without any logic (--discovery-base) and runs stock discovery on them, so a stale file never blocks
   its own repair;
5. the Digicon boot rule: the logic of every mast signal_coordinator.py takes over boots disabled (it was a deploy-time
   rewrite, disable_digicon_sml_in_tables.py, until R9c), so the hosts get exactly the committed bytes.

A PanelPro Store of tables.xml is never copied over it: make tables-pull and tables-pull-pi keep the Store in
media/pulled-stores in the main checkout (gitignored, shared by every worktree), and tools/schematic/split_store.py splits it into the template and
the device master (R9d). Exit codes: 0 written or current, 1 stale (--check), 2 a source cannot make the tables, 3 the schematic-maps
plugin is missing or not at its pin (EXIT_NO_PLUGIN; --check prints SKIPPED and exits 0 instead unless
SCHEMATIC_REQUIRED=1, which the deploy sets).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_layout_le as ble  # noqa: E402  the Layout Editor build (and hartlib on the path)
import band_panels  # noqa: E402  the three band panels copied from the built panel
import publish_draft as pd  # noqa: E402  the plugin's cache
from hartlib import devices, paths, tables  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402

OUT = paths.REPO_TABLES_XML
EXIT_NO_PLUGIN = 3      # the plugin is missing or off its pin: the deploy names the fix (sync_hart_package.sh)


def generate(discovered: tuple | None = None, with_logic: bool = True) -> tuple[bytes, dict]:
    """(tables bytes, counts) from the sources (module text). `discovered`: (logics, properties) to use in place of
    the discovered file's. `with_logic` False: the discovery base, with no Signal Mast Logic and no mast properties
    (the discovered file is not read). tb.TablesBuildError or ble.BuildError on anything that stops it."""
    data, P, _names, bands = ble.build(levels="all", as_live=True)
    doc = tables.loads(data)
    root = doc.root
    if doc.prolog != tb.PROLOG or doc.epilog != tb.EPILOG:
        raise tb.TablesBuildError("the Layout Editor build changed the envelope")
    band_panels.add(root, P, bands, ble.plugin()[1].CHROME)
    if with_logic:
        logics, props = discovered if discovered is not None else tb.read_discovered(tb.DISCOVERED)
    else:
        logics, props = [], {}
    tb.merge_discovered(root, logics, props)
    if with_logic:
        gaps = tb.missing_logic(root)
        if gaps:
            raise tb.TablesBuildError(f"{len(gaps)} mast(s) with no discovered logic they need ({', '.join(gaps)}): "
                                      "run jmri/layouts/hart/scripts/run_sml_discover.sh")
    digicon = tb.digicon_masts(root)
    flipped, already = tb.disable_digicon(root, digicon)
    tb.jmri_sort(root)          # the order a Store writes (ADR-029 gate 2)
    tb.finish(root)
    check(root)
    out = doc.tobytes()
    if tables.loads(out).tobytes() != out:
        raise tb.TablesBuildError("the generated tables do not read back to the same bytes")
    return out, {"signal mast logics": len(logics), "mast properties": len(props), "digicon masts": len(digicon),
                 "digicon destinations disabled": flipped + already}


# What SML discovery cannot see in the discovery base, left out of its digest (conservative: anything not listed here
# stays in). Discovery reads the masts and their slots, the Layout Editor track graph, the blocks, paths and layout
# blocks, and the turnouts with their feedback. It does not read a bean's comment, the user name of a sensor, memory
# or signal head, or the text and block-contents labels drawn on the panel.
DISCOVERY_BLIND_USERNAMES = ("sensors/sensor", "memories/memory", "signalheads/signalhead")
DISCOVERY_BLIND_PANEL_ELEMENTS = ("positionablelabel", "BlockContentsIcon")


# Geometry and looks, which discovery never reads: a drop-list, not a keep-list, because a keep-list that misses one
# topology attribute (a new connection, slot or block name) would hide a real change, while a drop-list that misses a
# drawing attribute only costs one needless discovery. Anything not named here stays in the digest.
DISCOVERY_BLIND_ATTRS = frozenset({
    "x", "y", "xcen", "ycen", "xa", "ya", "xb", "yb", "xc", "yc", "xd", "yd", "xscale", "yscale",
    "width", "height", "windowwidth", "windowheight", "panelwidth", "panelheight", "zoom", "scale",
    "arc", "flip", "circle", "angle", "hideConLines", "degrees", "level", "size", "style", "justification",
    "red", "green", "blue", "hasBackground", "fontFamily", "fontname", "linewidth",
    "redBackground", "greenBackground", "blueBackground", "gridSize", "gridSize2nd",
    "mainlinetrackwidth", "sidetrackwidth", "turnoutcirclesize", "turnoutbx", "turnoutcx", "turnoutwid",
    "xoverlong", "xoverhwid", "xovershort",
})
# Whole panel elements that only draw: track drawing options (colours, widths) and decoration shapes.
DISCOVERY_BLIND_DRAWING = ("layoutTrackDrawingOptions", "layoutShape")


def discovery_digest(data: bytes) -> str:
    """sha256 of the discovery base `data` without what discovery cannot see (see DISCOVERY_BLIND_*): a change that
    leaves this the same needs no new discovery on PanelPro. Coordinates, sizes, colours and fonts are dropped; the
    connections, blocks, turnout types, mast slots and mast definitions stay."""
    root = ET.fromstring(data)
    for parent in list(root.iter()):
        for child in [c for c in parent if c.tag in DISCOVERY_BLIND_DRAWING]:
            parent.remove(child)
    for el in root.iter():
        for name in list(el.attrib):
            if name in DISCOVERY_BLIND_ATTRS or (name.lower().endswith("color") and el.tag == "LayoutEditor"):
                del el.attrib[name]
    for parent in root.iter():
        for child in [c for c in parent if c.tag == "comment"]:
            parent.remove(child)
    for path in DISCOVERY_BLIND_USERNAMES:
        for bean in root.iterfind(path):
            for name in bean.findall("userName"):
                bean.remove(name)
    for panel in root.iter("LayoutEditor"):
        for child in [c for c in panel if c.tag in DISCOVERY_BLIND_PANEL_ELEMENTS]:
            panel.remove(child)
    return hashlib.sha256(ET.tostring(root, encoding="utf-8")).hexdigest()


def check(root) -> None:
    """The output's invariants: the envelope is the fixed one, no name is given twice, every row of the master that
    gives a bean (any level, assignment not none) has it in the output by its bean name (tb.bean_name), and every
    Digicon destination is disabled."""
    held = tb.envelope_items(root)
    if held:
        raise tb.TablesBuildError(f"the output holds {', '.join(held)}")
    tb.check_names(root)
    names = {tables.system_name(el) for sec in tables.elements(root) for el in tables.elements(sec)}
    want = {tb.bean_name(r.cells()) for r in devices.load() if r.level and r.assignment != "none"}
    lost = sorted(want - names)
    if lost:
        raise tb.TablesBuildError(f"beans of the device master missing from the output: {', '.join(lost[:8])}")
    still = tb.enabled_digicon(root, tb.digicon_masts(root))
    if still:
        raise tb.TablesBuildError(f"Digicon destinations still enabled: {still[:4]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="exit 1 if tables.xml is not what this writes")
    g.add_argument("--discovery-base", action="store_true",
                   help="write tables.xml with no Signal Mast Logic, for run_sml_discover.sh to discover on; "
                        "tables.xml is then stale until --discovered-from")
    g.add_argument("--base-hash", action="store_true",
                   help="print the digest of the discovery base (what --discovery-base writes, less what discovery cannot "
                        "see: discovery_digest) and write nothing: "
                        "the stamp of data/schematic/discovered_sml.stamp")
    g.add_argument("--discovered-from", type=Path, metavar="STORE",
                   help="a PanelPro Store after SML discovery: its logic and mast properties replace "
                        f"{paths.rel(tb.DISCOVERED)}, then tables.xml is written")
    args = ap.parse_args(argv)
    if not (args.check or args.base_hash):
        message = paths.check_only_message(Path(__file__).name)
        if message:
            print(f"ERROR: {message}", file=sys.stderr)
            return 1
    try:
        ble.plugin()
    except ble.BuildError as exc:
        if args.check and os.environ.get("SCHEMATIC_REQUIRED") != "1":
            print(f"SKIPPED tables check: {exc}")
            return 0
        print(f"build_tables.py: the schematic-maps plugin: {exc}", file=sys.stderr)
        return EXIT_NO_PLUGIN
    with contextlib.ExitStack() as stack:
        stack.enter_context(pd.cache_on())
        try:
            discovered = new_doc = None
            if args.discovered_from:
                new_doc = tb.discovered_from_store(tables.load(args.discovered_from).root)
                discovered = tb.read_discovered_root(new_doc, str(args.discovered_from))
            data, counts = generate(discovered, with_logic=not (args.discovery_base or args.base_hash))
        except (tb.TablesBuildError, ble.BuildError, devices.DevicesError) as exc:
            print(f"build_tables.py: {exc}", file=sys.stderr)
            return 2
        except OSError as exc:
            print(f"build_tables.py: {exc.filename}: {exc.strerror}", file=sys.stderr)
            return 2
    summary = ", ".join(f"{v} {k}" for k, v in counts.items())
    if args.base_hash:
        print(discovery_digest(data))
        return 0
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != data:
            print(f"STALE: {paths.rel(OUT)} is not what tools/schematic/build_tables.py writes; run it (never copy a "
                  "PanelPro Store over it: make tables-pull keeps the Store for split_store.py)", file=sys.stderr)
            return 1
        print(f"ok: {paths.rel(OUT)} current ({summary})")
        return 0
    if new_doc is not None and tb.write_discovered(new_doc, tb.DISCOVERED):
        print(f"wrote {paths.rel(tb.DISCOVERED)} from {args.discovered_from}")
    wrote = tables.loads(data, path=OUT).save(OUT)
    print(f"{'wrote' if wrote else 'unchanged'} {paths.rel(OUT)} ({summary})")
    if args.discovery_base:
        print(f"NOTE: {paths.rel(OUT)} is the discovery base, with no Signal Mast Logic; it stays stale until "
              "run_sml_discover.sh finishes (build_tables.py --discovered-from)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
