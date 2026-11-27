#!/usr/bin/env python3
"""Check that the Digicon masts' Signal Mast Logic is stored disabled in a tables file.

Digicon field masts (their heads wired in jmri/layouts/hart/data/wiring.csv, on wired LCOS heads) boot with SML Enabled=no so JMRI
does not run ABS until signal_coordinator.py takes Digicon control. Non-Digicon sources are left alone.

Since R9c (ADR-029) the generator applies the rule: tools/schematic/build_tables.py writes tables.xml with these
destinations disabled (hartlib.tables_sml.disable_digicon), and the deploy ships the committed bytes. This script
checks a tables file (--check, tools/check.sh), reports (--dry-run), or, with --panel, applies the rule to another
tables file in place (the parked Stage 1 repair, run_panelpro_stage1.sh). It never rewrites the generated tables.xml:
run tools/schematic/build_tables.py instead.

Usage:
  python3 jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py --check
  python3 jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py --dry-run --panel path/to/tables.xml
  python3 jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py --panel path/to/other_tables.xml
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402
from hartlib import tables_sml as sml  # noqa: E402

ROOT = paths.REPO_ROOT
WIRING = paths.WIRING
NEW_TABLES = paths.TABLES_XML


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--panel", type=Path, default=NEW_TABLES,
                    help="tables XML to check or patch (default: jmri/layouts/hart/output/tables.xml)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="report counts only; do not write")
    g.add_argument("--check", action="store_true",
                   help="fail if any Digicon (MQTT) SML destination is still Enabled=yes; do not write")
    args = ap.parse_args(argv)
    if not (args.check or args.dry_run):
        paths.exit_if_overridden(Path(__file__).name)
        if os.path.realpath(args.panel) == os.path.realpath(paths.REPO_TABLES_XML):
            print("tables.xml is generated (R9c): tools/schematic/build_tables.py applies the Digicon rule; "
                  "this script only patches another tables file", file=sys.stderr)
            return 2
    try:
        doc = tables.load(args.panel)
        digicon = sml.digicon_masts(doc.root, WIRING)
        rel = paths.rel(args.panel)
        if args.check:
            pairs = sml.enabled_digicon(doc.root, digicon)
            if pairs:
                print(f"ERROR: {rel} has {len(pairs)} Digicon SML destination(s) Enabled=yes (MQTT masts must boot "
                      "disabled): " + ", ".join(f"{s} -> {d}" for s, d in pairs[:24])
                      + "; run tools/schematic/build_tables.py", file=sys.stderr)
                return 1
            print(f"ok: {rel} Digicon SML destinations Enabled=no (masts={len(digicon)})")
            return 0
        flipped, already = sml.disable_digicon(doc.root, digicon)
    except OSError as exc:
        print(f"missing tables file: {args.panel} ({exc.strerror})", file=sys.stderr)
        return 1
    except sml.TablesBuildError as exc:
        print(f"disable_digicon_sml_in_tables.py: {exc}", file=sys.stderr)
        return 2
    print(f"digicon masts={len(digicon)}  flipped yes->no={flipped}  already no={already}")
    if args.dry_run:
        return 0
    print(f"wrote {rel}" if doc.save() else "no changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
