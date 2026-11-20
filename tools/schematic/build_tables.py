#!/usr/bin/env python3
"""Write jmri/layouts/hart/output/tables.xml, the file PanelPro and CATS load, from its sources (ADR-029).

    python3 tools/schematic/build_tables.py                          # write tables.xml
    python3 tools/schematic/build_tables.py --check                  # exit 1 if tables.xml is not what it writes
    python3 tools/schematic/build_tables.py --discovered-from STORE  # take the Signal Mast Logic of a discovery
                                                                     # Store (run_sml_discover.sh), then write

tables.xml is an output; nothing reads it as a source. It is, in this order:
1. the template, data/tables_template.xml: what PanelPro owns (settings, memories, the clock sensor, the "Hide windows
   on start" LogixNG), and the fixed envelope (hartlib.tables_build: no file history, "Written by" comment, clock
   time or memory values);
2. the staging beans of data/devices.csv: turnouts, sensors, heads, masts, blocks (lengths from block_lengths.csv) and
   layout blocks, their comments generated from the wiring columns (hartlib.tables_build.bean_comment), each section
   in JMRI's system-name order (hartlib.tables_build.base);
3. the Layout Editor build on that base (build_layout_le.build, levels all): the main and upper turnouts, blocks,
   sensors, heads, masts and the startup LogixNG from devices.csv, and the "HART Railroad" panel, which must match the
   owner-approved staging fingerprint;
4. the discovered Signal Mast Logic and mast properties, data/schematic/discovered_sml.xml, which only
   --discovered-from writes;
5. the Digicon boot rule: the logic of every mast signal_coordinator.py takes over boots disabled (it was a deploy-time
   rewrite, disable_digicon_sml_in_tables.py, until R9c), so the hosts get exactly the committed bytes.

A PanelPro Store of tables.xml does not come back by hand: make tables-pull splits it into these sources. Prints
SKIPPED (exit 0) with --check when the schematic-maps plugin is not checked out, unless SCHEMATIC_REQUIRED=1.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_layout_le as ble  # noqa: E402  the Layout Editor build (and hartlib on the path)
import publish_draft as pd  # noqa: E402  the plugin's cache
from hartlib import devices, paths, tables  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402

OUT = paths.REPO_TABLES_XML


def generate(discovered: tuple | None = None) -> tuple[bytes, dict]:
    """(tables bytes, counts) from the sources (module text). `discovered`: (logics, properties) to use in place of
    the discovered file's. tb.TablesBuildError or ble.BuildError on anything that stops it."""
    data, _P, _names, _bands = ble.build(levels="all", as_live=True)
    doc = tables.loads(data)
    root = doc.root
    if doc.prolog != tb.PROLOG or doc.epilog != tb.EPILOG:
        raise tb.TablesBuildError("the Layout Editor build changed the envelope")
    logics, props = discovered if discovered is not None else tb.read_discovered(tb.DISCOVERED)
    tb.merge_discovered(root, logics, props)
    digicon = tb.digicon_masts(root)
    flipped, already = tb.disable_digicon(root, digicon)
    tb.finish(root)
    check(root)
    out = doc.tobytes()
    if tables.loads(out).tobytes() != out:
        raise tb.TablesBuildError("the generated tables do not read back to the same bytes")
    return out, {"signal mast logics": len(logics), "mast properties": len(props), "digicon masts": len(digicon),
                 "digicon destinations disabled": flipped + already}


def check(root) -> None:
    """The output's invariants: the envelope is the fixed one, no name is given twice, every staging bean of the
    master is in it once, and every Digicon destination is disabled."""
    held = tb.envelope_items(root)
    if held:
        raise tb.TablesBuildError(f"the output holds {', '.join(held)}")
    tb.check_names(root)
    names = {tables.system_name(el) for sec in tables.elements(root) for el in tables.elements(sec)}
    want = {r["jmri_name"] if r["layer"] != "turnout" else r["system_name"] for r in devices.load()
            if r["level"] in tb.GENERATED_LEVELS and r["assignment"] != "none"}
    lost = sorted(want - names)
    if lost:
        raise tb.TablesBuildError(f"staging beans of devices.csv missing from the output: {', '.join(lost[:8])}")
    still = tb.enabled_digicon(root, tb.digicon_masts(root))
    if still:
        raise tb.TablesBuildError(f"Digicon destinations still enabled: {still[:4]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="exit 1 if tables.xml is not what this writes")
    g.add_argument("--discovered-from", type=Path, metavar="STORE",
                   help="a PanelPro Store after SML discovery: its logic and mast properties replace "
                        f"{paths.rel(tb.DISCOVERED)}, then tables.xml is written")
    args = ap.parse_args(argv)
    if not args.check:
        message = paths.check_only_message(Path(__file__).name)
        if message:
            print(f"ERROR: {message}", file=sys.stderr)
            return 1
    try:
        ble.plugin()
    except ble.BuildError as exc:
        if args.check:
            print(f"SKIPPED tables check: {exc}")
            return 1 if os.environ.get("SCHEMATIC_REQUIRED") == "1" else 0
        print(f"build_tables.py: {exc}", file=sys.stderr)
        return 2
    with contextlib.ExitStack() as stack:
        stack.enter_context(pd.cache_on())
        try:
            discovered = new_doc = None
            if args.discovered_from:
                new_doc = tb.discovered_from_store(tables.load(args.discovered_from).root)
                discovered = tb.read_discovered_root(new_doc, str(args.discovered_from))
            data, counts = generate(discovered)
        except (tb.TablesBuildError, ble.BuildError, devices.DevicesError) as exc:
            print(f"build_tables.py: {exc}", file=sys.stderr)
            return 2
        except OSError as exc:
            print(f"build_tables.py: {exc.filename}: {exc.strerror}", file=sys.stderr)
            return 2
    summary = ", ".join(f"{v} {k}" for k, v in counts.items())
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != data:
            print(f"STALE: {paths.rel(OUT)} is not what tools/schematic/build_tables.py writes; run it (a PanelPro "
                  "Store comes back through make tables-pull, never by hand)", file=sys.stderr)
            return 1
        print(f"ok: {paths.rel(OUT)} current ({summary})")
        return 0
    if new_doc is not None and tb.write_discovered(new_doc, tb.DISCOVERED):
        print(f"wrote {paths.rel(tb.DISCOVERED)} from {args.discovered_from}")
    wrote = tables.loads(data, path=OUT).save(OUT)
    print(f"{'wrote' if wrote else 'unchanged'} {paths.rel(OUT)} ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
