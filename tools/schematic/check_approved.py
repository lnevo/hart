"""check_approved.py [--check] [key ...]  |  check_approved.py --approve (key ... | --all)

Check the owner-approved built outputs against their fingerprints (tools/schematic/approval.py): the three-level
"HART Railroad" Layout Editor panel in tables.xml and the CATS desks. Exit 1 naming each output that drifted.
--approve records outputs as approved, only the ones named (or all of them with --all); run it only after the owner
has approved them. Keys: le-panel (the live tables.xml), le-candidate (the cut-over candidate; checked only when
named), cats-ctc, cats-abs. Checking with no key covers every output but le-candidate.
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
    ap.add_argument("--approve", action="store_true", help="record the named outputs as approved")
    ap.add_argument("--all", action="store_true", help="with --approve: every output but le-candidate")
    ap.add_argument("--check", action="store_true", help="the default; accepted so build_panels.sh can pass it")
    ap.add_argument("keys", nargs="*", metavar="key", help=", ".join(keys))
    args = ap.parse_args(argv)
    unknown = [k for k in args.keys if k not in keys]
    if unknown:
        ap.error(f"unknown output {unknown[0]!r}; choose from {', '.join(keys)}")
    if args.all and not args.approve:
        ap.error("--all goes with --approve")
    if args.approve and args.check:
        ap.error("--approve and --check are different jobs")
    if args.approve and args.all == bool(args.keys):
        ap.error("--approve takes the outputs to approve (" + ", ".join(keys) + ") or --all, not both and not neither")
    defaults = [o for o in approval.OUTPUTS if o.default]
    chosen = [keys[k] for k in args.keys] or defaults
    bad = 0
    for out in chosen:
        try:
            if args.approve:
                print(f"approving {out.key}: {out.what} from {approval.paths.rel(out.source)}")
                approval.approve(out)
                print(f"  wrote {approval.paths.rel(out.approved)}")
            else:
                approval.check(out)
                print(f"{out.key}: matches the approved fingerprint")
        except approval.ApprovalError as exc:
            print(f"ERROR {exc}", file=sys.stderr)
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
