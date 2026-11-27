#!/usr/bin/env python3
"""HART car workflow: one car repository feeding cards, STS and Operations Pro.

    cars.py import-legacy   Add roster cars with no photo to the repository (once)
    cars.py intake          Process new photos in ops/car-cards/incoming/
    cars.py add             Add a car with no photo by answering questions
    cars.py status          Show the queue of cars still working through the steps
    cars.py review          Stage 1: crop and read new photos, write a review sheet
    cars.py ai-notes BATCH FILE   Merge an AI reviewer's readings into the review sheet
    cars.py kind BATCH car|loco PHOTO...   Set whether photos are cars or locomotives
    cars.py fill BATCH [--set COL=VAL]   Set a column on every row, fill empty details from the best row
    cars.py sheet-import BATCH FILE   Load the review.csv downloaded from the review page
    cars.py crop BATCH [PHOTO X,Y,W,H[,ANGLE]]   Crop picker on the review page / re-cut a photo
    cars.py approve BATCH   Approve the unflagged rows of a review sheet
    cars.py records BATCH   Stage 2: write approved rows into the repository
    cars.py site            Stage 5: add new photographed cars and locos to the public gallery
    cars.py locos ...       Locomotive repository and stage 4 publish (add, set, status, publish)
    cars.py cards           Build a print .docx for every queued car without a card
    cars.py publish         Rebuild rosters, feed STS, merge into Operations Pro
    cars.py seed-copy       Rebuild the roster and refresh the STS seed copies only
    cars.py compare         Report differences between the repository and each tool
    cars.py sync            Send the repository's identity fields to the tools that differ (dry run; --apply writes)

``data/image_metadata.csv`` is the repository: one row per car, with a blank
``source_image`` until the car is photographed. ``data/car_queue.csv`` tracks
which new cars still need a card, STS or Operations Pro.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

from car_repo import (  # noqa: I001  (car_repo first: it sets HART_CAR_CARDS_ROOT before car_paths loads)
    DEPLOY_NOTE, MERGED, OPS_MERGED, PI_HOST, PI_OPS_DIR, PRINT_DIR, QUEUE, METADATA, SEED_COPIES, SEED_INPUTS,
    STS_HELPERS, as_fields, find_car, out_of_service_ids, parse_sets, read_queue, read_rows, row_id, sync_seed_copies,
    today, write_queue, write_rows,
)
from car_compare import cmd_compare
from car_fields import NOT_CARS
from car_intake import cmd_add, cmd_import_legacy, cmd_intake, stage
from car_ops_roster import merge_ops, ops_ids, ops_out_of_service
from car_paths import FINAL_DIR, CardPipelineError
from car_records import QueueItem
from car_sync import cmd_sync

__all__ = ["PI_HOST", "PI_OPS_DIR", "main"]

Command = Callable[[argparse.Namespace], int]


def cmd_locos(args: argparse.Namespace) -> int:
    import locos

    run = {"add": locos.cmd_add, "set": locos.cmd_set, "status": locos.cmd_status}
    if args.action == "publish":
        return locos.cmd_publish(args, parse_sets, FINAL_DIR)
    return run[args.action](args, parse_sets)


def cmd_status(_args: argparse.Namespace) -> int:
    from car_intake import new_photos

    rows, _ = read_rows()
    queue = read_queue()
    no_photo = [r for r in rows if not r.get("source_image")]
    print(f"Cars: {len(rows)} ({len(no_photo)} without a photo)")
    print(f"New photos waiting: {len(new_photos(rows))}")
    open_items = [q for q in queue if not (q["card_printed"] and q["sts"] and q["ops"])]
    if not open_items:
        print("Queue is empty.")
        return 0
    print(f"{'Car':<16}{'Reason':<14}{'Card':<12}{'Printed':<12}{'STS':<12}{'Ops Pro':<12}")
    for q in open_items:
        print(
            f"{q['roster_id']:<16}{q['reason']:<14}{q['card_built'] or '-':<12}"
            f"{q['card_printed'] or '-':<12}{q['sts'] or '-':<12}{q['ops'] or '-':<12}"
        )
    return 0


def mark_printed(queue: list[QueueItem], loco_queue: list[dict[str, str]]) -> int:
    """cards --mark-printed: every built, unprinted card of both queues is printed today."""
    import locos

    count = 0
    for item in queue:
        if item["card_built"] and not item["card_printed"]:
            item["card_printed"] = today()
            count += 1
    for loco_item in loco_queue:
        if loco_item.get("card_built") and not loco_item.get("card_printed"):
            loco_item["card_printed"] = today()
            count += 1
    write_queue(queue)
    if loco_queue:
        locos.write_table(locos.LOCO_QUEUE, locos.QUEUE_COLUMNS, loco_queue)
    print(f"Marked {count} cards printed.")
    return 0


def cmd_cards(args: argparse.Namespace) -> int:
    import locos

    queue = read_queue()
    loco_queue = locos.read_queue()
    if args.mark_printed:
        return mark_printed(queue, loco_queue)
    pending = [q for q in queue if not q["card_printed"]]
    loco_pending = [q for q in loco_queue if not q.get("card_printed")]
    if not pending and not loco_pending and not args.trains:
        print("No cards queued.")
        return 0

    import generate_all_cards as gen

    rows, _ = read_rows()
    roster = gen.load_roster()
    _, engines = gen.load_engine_roster()
    cards: list[gen.CardEntry] = []
    for item in pending:
        row = find_car(rows, item["roster_id"])
        if row is None:
            raise CardPipelineError(f"Queued car {item['roster_id']} is not in the repository.")
        record, image = gen.row_to_card(as_fields(row), roster, engines)
        cards.append(gen.CardEntry(record, image, as_fields(row)))
        print(f"  {record['RoadName']} {record['RoadNumber']}: {'photo' if image else 'no photo'}")
    loco_rows = {r["roster_id"]: r for r in locos.read_locos()}
    for loco_item in loco_pending:
        loco = loco_rows.get(loco_item["roster_id"])
        if loco is None:
            raise CardPipelineError(f"Queued loco {loco_item['roster_id']} is not in the locomotive repository.")
        card, engine = locos.card_row(loco)
        engines = {**engines, (loco["road_name"], loco["road_number"]): engine}
        record, image = gen.row_to_card(card, roster, engines)
        cards.append(gen.CardEntry(record, image, card))
        print(f"  {record['RoadName']} {record['RoadNumber']} (loco): {'photo' if image else 'no photo'}")
    if args.trains:
        import train_cards

        # train_cards gives (fields, None, {}) tuples in CardEntry's order, typed as plain dicts.
        trains = cast("list[gen.CardEntry]", train_cards.train_cards())
        cards.extend(trains)
        print(f"  + {len(trains)} train cards")
    PRINT_DIR.mkdir(parents=True, exist_ok=True)
    gen.OUTPUT = PRINT_DIR / f"HART_New_Car_Cards_{today()}.docx"
    gen.generate(cards)
    for item in pending:
        item["card_built"] = today()
    for loco_item in loco_pending:
        loco_item["card_built"] = today()
    write_queue(queue)
    if loco_queue:
        locos.write_table(locos.LOCO_QUEUE, locos.QUEUE_COLUMNS, loco_queue)
    print(f"Wrote {gen.OUTPUT}. After printing, run: cars.py cards --mark-printed")
    return 0


def publish_gate(args: argparse.Namespace) -> None:
    """Stop before anything is changed unless the stage 3 checks pass (ADR-018)."""
    import intake_stages
    import publish_gate as gate

    sys.path.insert(0, str(STS_HELPERS / "lib"))
    from sts_paths import backups_dir

    problems = gate.run_gate(
        batch_root=intake_stages.BATCH_ROOT,
        tracked=[METADATA, QUEUE],
        ops_local=OPS_MERGED.parent,
        pi_host=PI_HOST,
        pi_dir=PI_OPS_DIR,
        backups_dir=backups_dir(),
        only=bool(args.only),
        skip=args.skip_check,
    )
    if problems:
        raise CardPipelineError("\n".join(["Publish stopped:", *(f"  {line}" for line in problems)]))


def cmd_seed_copy(_args: argparse.Namespace) -> int:
    """Rebuild the merged roster as publish does, then refresh the STS seed copies only."""
    from build_car_roster_sor import main as build_roster

    build_roster()
    sync_seed_copies(SEED_INPUTS, SEED_COPIES)
    return 0


def is_chosen(item: QueueItem, only: list[str] | None) -> bool:
    """With --only, the rest of the queue is left exactly as it is."""
    return not only or item["roster_id"] in only


def publish_to_sts(queue: list[QueueItem], for_sts: list[QueueItem]) -> list[str]:
    """Add the chosen cars to STS (they stay queued when it fails), then sync the out-of-service flags.

    Returns one line per STS step that exited non-zero; an empty list means both steps passed.
    """
    failed: list[str] = []
    if for_sts:
        ids = [q["roster_id"] for q in for_sts]
        result = subprocess.run(
            [sys.executable, str(STS_HELPERS / "tools/add_hart_cars.py"), *ids],
            check=False,
        )
        if result.returncode:
            failed.append(
                f"add_hart_cars.py exited {result.returncode}; these cars stay queued for STS: {' '.join(ids)}"
            )
        else:
            for item in for_sts:
                item["sts"] = today()
            write_queue(queue)

    result = subprocess.run(
        [sys.executable, str(STS_HELPERS / "tools/sync_hart_status.py")], check=False
    )
    if result.returncode:
        failed.append(f"sync_hart_status.py (out-of-service sync) exited {result.returncode}")
    return failed


def publish_to_ops(queue: list[QueueItem], only: list[str] | None, live: Path) -> None:
    """Merge the chosen cars and the out-of-service flags into the Operations Pro roster, when either changed."""
    for_ops = [q["roster_id"] for q in queue if not q["ops"] and is_chosen(q, only)]
    rows, _ = read_rows()
    out = out_of_service_ids(rows)
    flags_differ = live.is_file() and ops_out_of_service(live) != out
    if for_ops or flags_differ:
        added = merge_ops(live, for_ops, MERGED, out_of_service=out)
        for item in queue:
            if not item["ops"] and is_chosen(item, only):
                item["ops"] = today()
        write_queue(queue)
        print(f"Added {len(added)} cars to {OPS_MERGED}; {len(out)} out of service")
        print(DEPLOY_NOTE)


def cmd_publish(args: argparse.Namespace) -> int:
    """Rebuild the rosters, refresh the STS seed copies, then send the queued cars to STS and Operations Pro.

    The Operations Pro merge runs even when an STS step fails; the failure is raised after it, naming the step.
    """
    from build_car_roster_sor import main as build_roster

    publish_gate(args)
    build_roster()
    queue = read_queue()
    if args.only:
        unknown = [i for i in args.only if i not in {q["roster_id"] for q in queue}]
        if unknown:
            raise CardPipelineError(f"Not in the queue: {' '.join(unknown)}")
    sync_seed_copies(SEED_INPUTS, SEED_COPIES)
    sts_failed = publish_to_sts(queue, [q for q in queue if not q["sts"] and is_chosen(q, args.only)])
    publish_to_ops(queue, args.only, Path(args.ops_live))
    if sts_failed:
        raise CardPipelineError("\n".join(["Publish: STS step failed:", *(f"  {line}" for line in sts_failed)]))
    return 0


def cmd_service(args: argparse.Namespace) -> int:
    """Record a car as out of or back in service. Publish carries it to STS and Operations Pro."""
    rows, columns = read_rows()
    if "out_of_service" not in columns:
        columns.append("out_of_service")
    for roster_id in args.roster_ids:
        matches = [r for r in rows if row_id(r) == roster_id]
        if not matches:
            raise CardPipelineError(f"{roster_id} is not in the repository.")
        for row in matches:
            row["out_of_service"] = "yes" if args.state == "out" else ""
    write_rows(rows, columns)
    print(f"Marked {args.state} of service: {' '.join(args.roster_ids)}. Run publish to send it.")
    return 0


def cmd_fix_ops(args: argparse.Namespace) -> int:
    """Bring the Operations Pro roster up to the repository. Leaves STS and the queue alone."""
    from build_car_roster_sor import main as build_roster

    build_roster()
    rows, _ = read_rows()
    live = Path(args.ops_live)
    wanted = sorted(
        row_id(r) for r in rows
        if row_id(r) and (r.get("car_type") or "") not in NOT_CARS
    )
    unknown = sorted(ops_ids(live) - {row_id(r) for r in rows})
    added = merge_ops(live, wanted, MERGED, out_of_service_ids(rows))
    print(f"Added {len(added)}: {' '.join(added)}")
    if unknown:
        # fix-ops renames nothing: a car kept under a wrong id would now sit beside its added right id.
        print(f"Not in the repository, left as they are (check each by hand): {' '.join(unknown)}")
    print(DEPLOY_NOTE)
    return 0


def add_repository_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """import-legacy, intake and add: cars into the repository."""
    sub.add_parser("import-legacy").set_defaults(run=cmd_import_legacy)
    for name, run in (("intake", cmd_intake), ("add", cmd_add)):
        p = sub.add_parser(name)
        p.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
        p.add_argument("--yes", action="store_true", help="Do not ask questions")
        p.set_defaults(run=run)


def add_stage_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """The intake stages: review, ai-notes, kind, approve, fill, sheet-import, crop, records, site and locos."""
    p = sub.add_parser("review")
    p.add_argument("--batch", help="Batch name (default: today's date)")
    p.set_defaults(run=stage("intake_stages", "cmd_review"))
    p = sub.add_parser("ai-notes")
    p.add_argument("batch")
    p.add_argument("file", help="JSON: {photo: {marks, number, type, note}}")
    p.set_defaults(run=stage("intake_stages", "cmd_ai_notes"))
    p = sub.add_parser("kind")
    p.add_argument("batch")
    p.add_argument("kind", choices=["car", "loco"])
    p.add_argument("photos", nargs="+")
    p.set_defaults(run=stage("intake_stages", "cmd_kind"))
    p = sub.add_parser("approve")
    p.add_argument("batch")
    p.add_argument("--no-ai", action="store_true", help="Approve without the AI review step")
    p.set_defaults(run=stage("intake_stages", "cmd_approve"))
    p = sub.add_parser("fill")
    p.add_argument("batch")
    p.add_argument("--set", action="append", metavar="COLUMN=VALUE", help="Set a column on every row")
    p.set_defaults(run=stage("intake_stages", "cmd_fill"))
    p = sub.add_parser("sheet-import")
    p.add_argument("batch")
    p.add_argument("file", help="review.csv downloaded from the review page")
    p.set_defaults(run=stage("intake_stages", "cmd_sheet_import"))
    p = sub.add_parser("crop", help="Crop picker on the review page, or re-cut one photo")
    p.add_argument("batch")
    p.add_argument("photo", nargs="?")
    p.add_argument("box", nargs="?", metavar="X,Y,W,H[,ANGLE]")
    p.add_argument("--refresh", action="store_true", help="Rebuild the picker views")
    p.set_defaults(run=stage("crop_picker", "cmd_crop"))
    p = sub.add_parser("records")
    p.add_argument("batch")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--allow-pending", action="store_true", help="Record approved rows while others wait")
    p.set_defaults(run=stage("intake_stages", "cmd_records"))
    p = sub.add_parser("site")
    p.add_argument("--apply", action="store_true", help="Write the entries (default: show them)")
    p.set_defaults(run=stage("site_gallery", "cmd_site"))
    p = sub.add_parser("locos")
    p.add_argument("action", choices=["add", "set", "status", "publish"])
    p.add_argument("roster_id", nargs="?")
    p.add_argument("fields", nargs="*", metavar="FIELD=VALUE")
    p.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(run=cmd_locos)


def add_queue_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """status, cards, service, publish, fix-ops and seed-copy."""
    sub.add_parser("status").set_defaults(run=cmd_status)
    p = sub.add_parser("cards")
    p.add_argument("--mark-printed", action="store_true")
    p.add_argument("--trains", action="store_true",
                   help="append the train cards (D749, NVL, CK1, Route 23, OCS-1, EXTRA)")
    p.set_defaults(run=cmd_cards)
    p = sub.add_parser("service")
    p.add_argument("state", choices=["out", "in"])
    p.add_argument("roster_ids", nargs="+")
    p.set_defaults(run=cmd_service)
    p = sub.add_parser("publish")
    p.add_argument("--ops-live", default=str(OPS_MERGED))
    p.add_argument("--only", nargs="+", metavar="ROSTER_ID",
                   help="Publish just these queued cars (testing one at a time)")
    p.add_argument("--skip-check", action="append", default=[], metavar="NAME",
                   help="Skip a gate check: batches, committed, pi or backup")
    p.set_defaults(run=cmd_publish)
    p = sub.add_parser("fix-ops")
    p.add_argument("--ops-live", default=str(OPS_MERGED))
    p.set_defaults(run=cmd_fix_ops)
    sub.add_parser("seed-copy").set_defaults(run=cmd_seed_copy)


def add_tool_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """compare and sync: the repository against each tool."""
    p = sub.add_parser("compare")
    p.add_argument("--ops-live", default=str(OPS_MERGED))
    p.add_argument("--all", action="store_true", help="List every field difference, not the first 20")
    p.add_argument("--live-sts", action="store_true",
                   help="Also read the live STS cars over its API (GET only; refused while the operating flag is set)")
    p.add_argument("--sts-url", metavar="URL",
                   help="STS API base URL for this run, e.g. http://RPi-JMRI.local:8980/sts/api/v1 "
                        "(else STS_API_URL, else the Mac UAT)")
    p.set_defaults(run=cmd_compare)
    p = sub.add_parser("sync", help="Send the repository's identity fields to the tools that differ")
    p.add_argument("--ops-live", default=str(OPS_MERGED))
    p.add_argument("--apply", action="store_true", help="Write the changes (default: show them); the STS seed copies are replaced wholesale, as seed-copy does")
    p.add_argument("--live-sts", action="store_true", help="Include the live STS (with --apply, also needs --sts-url)")
    p.add_argument("--sts-url", metavar="URL", help="STS API base URL for this run")
    p.set_defaults(run=cmd_sync)


def build_parser() -> argparse.ArgumentParser:
    """Every bin/cars command, in the order --help lists them."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    add_repository_commands(sub)
    add_stage_commands(sub)
    add_queue_commands(sub)
    add_tool_commands(sub)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run: Command = args.run
    try:
        return run(args)
    except CardPipelineError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
