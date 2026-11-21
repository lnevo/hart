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
2. the staging beans of data/devices.csv: turnouts, sensors, heads, masts, blocks (lengths from block_lengths.csv) and
   layout blocks, their comments generated from the wiring columns (hartlib.tables_build.bean_comment), each section
   in JMRI's system-name order (hartlib.tables_build.base);
3. the Layout Editor build on that base (build_layout_le.build, levels all): the main and upper turnouts, blocks,
   sensors, heads, masts and the startup LogixNG from devices.csv, and the "HART Railroad" panel, which must match the
   owner-approved staging fingerprint;
4. the discovered Signal Mast Logic and mast properties, data/schematic/discovered_sml.xml, which only
   --discovered-from writes. The build stops when that file names a mast the tables no longer hold (a mast renamed
   or removed since discovery) and when a mast has no discovered logic it needs (missing_logic: every head mast is a
   source, every virtual mast a destination): run jmri/layouts/hart/scripts/run_sml_discover.sh, which first writes
   the tables without any logic (--discovery-base) and runs stock discovery on them, so a stale file never blocks
   its own repair;
5. the Digicon boot rule: the logic of every mast signal_coordinator.py takes over boots disabled (it was a deploy-time
   rewrite, disable_digicon_sml_in_tables.py, until R9c), so the hosts get exactly the committed bytes.

A PanelPro Store of tables.xml is never copied over it: make tables-pull and tables-pull-pi keep the Store in
~/JMRI_UserFiles-pulled (outside every checkout) and record it as taken; its edits go into these sources by hand
until R9d's pull splits a Store. Exit codes: 0 written or current, 1 stale (--check), 2 a source cannot make the tables, 3 the schematic-maps
plugin is missing or not at its pin (EXIT_NO_PLUGIN; --check prints SKIPPED and exits 0 instead unless
SCHEMATIC_REQUIRED=1, which the deploy sets).
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
EXIT_NO_PLUGIN = 3      # the plugin is missing or off its pin: the deploy names the fix (sync_hart_package.sh)


def generate(discovered: tuple | None = None, with_logic: bool = True, review: bool = False) -> tuple[bytes, dict]:
    """(tables bytes, counts) from the sources (module text). `discovered`: (logics, properties) to use in place of
    the discovered file's. `with_logic` False: the discovery base, with no Signal Mast Logic and no mast properties
    (the discovered file is not read). `review`: a candidate for the owner's review, its staging panel not checked
    against the approved fingerprint (build_layout_le.py --review). tb.TablesBuildError or ble.BuildError on anything
    that stops it."""
    data, _P, _names, _bands = ble.build(levels="all", as_live=True, **({"approved": None} if review else {}))
    doc = tables.loads(data)
    root = doc.root
    if doc.prolog != tb.PROLOG or doc.epilog != tb.EPILOG:
        raise tb.TablesBuildError("the Layout Editor build changed the envelope")
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
    g.add_argument("--discovery-base", action="store_true",
                   help="write tables.xml with no Signal Mast Logic, for run_sml_discover.sh to discover on; "
                        "tables.xml is then stale until --discovered-from")
    g.add_argument("--discovered-from", type=Path, metavar="STORE",
                   help="a PanelPro Store after SML discovery: its logic and mast properties replace "
                        f"{paths.rel(tb.DISCOVERED)}, then tables.xml is written")
    ap.add_argument("--review", action="store_true",
                    help="write a candidate for the owner's review although its staging panel is not the approved "
                         "one (as build_layout_le.py --review); never with --check")
    args = ap.parse_args(argv)
    if args.review and args.check:
        ap.error("--review writes a candidate; --check holds tables.xml to the approved panel")
    if not args.check:
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
            data, counts = generate(discovered, with_logic=not args.discovery_base, review=args.review)
        except (tb.TablesBuildError, ble.BuildError, devices.DevicesError) as exc:
            print(f"build_tables.py: {exc}", file=sys.stderr)
            return 2
        except OSError as exc:
            print(f"build_tables.py: {exc.filename}: {exc.strerror}", file=sys.stderr)
            return 2
    summary = ", ".join(f"{v} {k}" for k, v in counts.items())
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != data:
            print(f"STALE: {paths.rel(OUT)} is not what tools/schematic/build_tables.py writes; run it (never copy a "
                  "PanelPro Store over it: make tables-pull keeps the Store for R9d's split)", file=sys.stderr)
            return 1
        print(f"ok: {paths.rel(OUT)} current ({summary})")
        return 0
    if new_doc is not None and tb.write_discovered(new_doc, tb.DISCOVERED):
        print(f"wrote {paths.rel(tb.DISCOVERED)} from {args.discovered_from}")
    wrote = tables.loads(data, path=OUT).save(OUT)
    print(f"{'wrote' if wrote else 'unchanged'} {paths.rel(OUT)} ({summary})")
    if args.review:
        print(f"REVIEW: {paths.rel(OUT)}'s staging panel was not checked against the approved one; it is a candidate "
              "until the owner approves it (build_tables.py --check fails until then)")
    if args.discovery_base:
        print(f"NOTE: {paths.rel(OUT)} is the discovery base, with no Signal Mast Logic; it stays stale until "
              "run_sml_discover.sh finishes (build_tables.py --discovered-from)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
