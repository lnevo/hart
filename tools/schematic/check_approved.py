"""check_approved.py [--check | --approve] [key ...]

Check the owner-approved built outputs against their fingerprints (tools/schematic/approval.py): the three-level
"HART Railroad" Layout Editor panel in tables.xml and the CATS desks. Exit 1 naming each output that drifted.
--approve records the current outputs as approved; run it only after the owner has approved them.
Keys: le-panel, cats-ctc, cats-abs (default: all).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import approval  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    keys = {o.key: o for o in approval.OUTPUTS}
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--approve", action="store_true", help="record the current outputs as approved")
    ap.add_argument("--check", action="store_true", help="the default; accepted so build_panels.sh can pass it")
    ap.add_argument("keys", nargs="*", metavar="key", help=", ".join(keys))
    args = ap.parse_args(argv)
    unknown = [k for k in args.keys if k not in keys]
    if unknown:
        ap.error(f"unknown output {unknown[0]!r}; choose from {', '.join(keys)}")
    chosen = [keys[k] for k in args.keys] or list(approval.OUTPUTS)
    bad = 0
    for out in chosen:
        try:
            if args.approve:
                approval.approve(out)
                print(f"approved {out.key}: {approval.paths.rel(out.approved)}")
            else:
                approval.check(out)
                print(f"{out.key}: matches the approved fingerprint")
        except approval.ApprovalError as exc:
            print(f"ERROR {exc}", file=sys.stderr)
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
