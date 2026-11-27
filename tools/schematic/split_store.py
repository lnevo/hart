#!/usr/bin/env python3
"""Split a pulled PanelPro Store back into the sources of tables.xml (ADR-029, R9d; design in
archive/history/wiki/projects/project-health-handoff.md, "R9d redesign"). make tables-pull-pi and tables-pull keep the Store and
name this command; run it in a task worktree (make wt TOPIC=...).

    python3 tools/schematic/split_store.py STORE                   # the report: what is kept, reviewed, dropped
    python3 tools/schematic/split_store.py STORE --show D1         # one item as a diff (repo against Store)
    python3 tools/schematic/split_store.py STORE --apply --plan FP [--merge D1,C2] [--drop K3]

The report lists every item the owner changed (hartlib.store_split): KEPT items go into the template, CLASH and
DEVICE items wait for the owner's merge or drop (the agent asks in chat, in batches), DROPPED items are the build's
and the repo wins. --apply takes the plan's fingerprint from the report, so the ids mean what the owner saw: it
writes data/tables_template.xml and the merged devices_field.csv cells, rebuilds tables.xml (build_tables.py), checks the
rebuild gives what the plan promised (store_split.verify) and records the Store in data/store_splits.csv, which is
what lets the next deploy replace the host's file (ADR-029: a Store counts as taken once its split is on the branch
deployed). On any failure every file is put back. It stops before commit: the files to commit are printed.

The base is what the host had before the session, named in STORE.base (the pull writes it from
tools/hosts/pi/tables_base.sh): "deploy SHA COMMIT" (that commit's committed tables.xml, which must have that hash),
"store SHA" (an earlier Store in the same folder) or "none". When a deploy's commit is missing or shipped another
file, a kept file in the same folder with the deploy's hash is used. --base FILE names a tables file instead; with no
base every template change is reviewed.

Exit codes: 0 report printed, or applied; 1 the apply failed and was undone (the reason is printed); 2 it cannot run
(a file that cannot be read, a stale tables.xml, the main checkout, uncommitted files, a plan that changed).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hartlib" / "src"))
from hartlib import devices, paths  # noqa: E402
from hartlib import store_split as ss  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402

ROOT = paths.REPO_ROOT if hasattr(paths, "REPO_ROOT") else Path(__file__).resolve().parents[2]
TABLES_REL = "jmri/layouts/hart/output/tables.xml"
TABLES = ROOT / TABLES_REL
TEMPLATE = ROOT / "jmri/layouts/hart/data/tables_template.xml"
DEVICE_FILES = devices.Files.here()    # the master: the split reads the merged view, writes the field file alone
DEVICES = devices.FIELD                 # devices_field.csv: the owner's file, the one device file a split writes
SPLITS = ROOT / "jmri/layouts/hart/data/store_splits.csv"
SPLIT_COLUMNS = ("store_sha256", "host", "store_file", "base", "plan", "split_date")
WRITES = (TEMPLATE, DEVICES, TABLES, SPLITS)
BUILD = ROOT / "tools/schematic/build_tables.py"


class Stop(Exception):
    """The split cannot run (exit 2)."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=check)


def build_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "HART_TABLES"}
    env["SCHEMATIC_REQUIRED"] = "1"
    return env


# ---------------------------------------------------------------- the base


def read_base(store: Path, base_file: Path | None, no_base: bool) -> tuple[bytes | None, str]:
    """(the base's bytes or None, what it is, for the report and store_splits.csv)."""
    if no_base:
        return None, "none (--no-base)"
    if base_file is not None:
        return _read(base_file), f"file {base_file.name}"
    note = store.with_name(store.name + ".base")
    if not note.exists():
        return None, f"none ({note.name} is missing)"
    words = note.read_text(encoding="utf-8").split()
    if not words or words[0] == "none":
        return None, "none (the host had no deploy stamp)"
    kind, sha = words[0], words[1] if len(words) > 1 else ""
    commit = words[2] if len(words) > 2 else ""
    why = ""
    if kind == "deploy" and commit:
        if git("cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode != 0:
            git("fetch", "-q", "origin", check=False)
        got = git("show", f"{commit}:{TABLES_REL}", check=False)
        if got.returncode != 0:
            why = f"commit {commit[:10]} or its tables.xml is not in this repository"
        elif sha256(got.stdout) != sha:
            why = f"the deploy of {commit[:10]} shipped another file than its committed tables.xml"
        else:
            return got.stdout, f"deploy {commit[:10]}"
    if kind in ("deploy", "store") and sha:
        # A kept file with the base's hash: an earlier Store, or (for a deploy that shipped an uncommitted file) a
        # copy of what was shipped.
        for f in sorted(store.parent.glob("*.xml")):
            if f != store and sha256(f.read_bytes()) == sha:
                return f.read_bytes(), f"store {f.name}" + (f" ({why}; this kept file has its hash)" if why else "")
        return None, f"none ({why + '; ' if why else ''}no kept file in {store.parent} has the base's hash {sha[:12]})"
    raise Stop(f"{note}: not 'deploy SHA COMMIT', 'store SHA' or 'none'")


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise Stop(f"{path}: cannot read it ({exc.strerror})") from exc


# ---------------------------------------------------------------- the plan


def make_plan(store_path: Path, args) -> tuple[ss.Plan, dict]:
    check = subprocess.run([sys.executable, str(BUILD), "--check"], cwd=ROOT, env=build_env(),
                           capture_output=True, text=True)
    if check.returncode != 0:
        raise Stop("this checkout's tables.xml is not what its sources give (build_tables.py --check): "
                   + (check.stdout + check.stderr).strip()[-400:])
    store_bytes = _read(store_path)
    base_bytes, base_what = read_base(store_path, args.base, args.no_base)
    repo_bytes = _read(TABLES)
    try:
        template_doc = tb.read_template(TEMPLATE)
        rows = [r.cells() for r in devices.load(DEVICE_FILES)]
        roots = dict(
            base=ss.normalised(base_bytes, "the base") if base_bytes is not None else None,
            repo=ss.normalised(repo_bytes, "tables.xml"),
            store=ss.normalised(store_bytes, store_path.name),
            template=ss.normalised(template_doc.tobytes(), "the template"),
        )
        p = ss.plan(roots["base"], roots["repo"], roots["store"], roots["template"], rows)
    except (ss.SplitError, tb.TablesBuildError, devices.DevicesError) as exc:
        raise Stop(str(exc)) from exc
    return p, dict(roots=roots, rows=rows, template_doc=template_doc, base_what=base_what,
                   store_sha=sha256(store_bytes))


def ids(text: str) -> frozenset[str]:
    return frozenset(x.strip().upper() for x in (text or "").split(",") if x.strip())


# ---------------------------------------------------------------- apply


def refuse_place() -> None:
    common = Path(git("rev-parse", "--git-common-dir").stdout.decode().strip())
    own = Path(git("rev-parse", "--git-dir").stdout.decode().strip())
    if not common.is_absolute():
        common = ROOT / common
    if not own.is_absolute():
        own = ROOT / own
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.decode().strip()
    if common.resolve() == own.resolve() or branch == "main":
        raise Stop("the split writes only in a task worktree, never the main checkout or branch main: "
                   "make wt TOPIC=store-split, then run it there")
    dirty = git("status", "--porcelain", "--", *(str(p.relative_to(ROOT)) for p in WRITES)).stdout.decode().strip()
    if dirty:
        raise Stop(f"uncommitted changes to the files the split writes; commit or undo them first:\n{dirty}")


def apply(store_path: Path, p: ss.Plan, ctx: dict, choices: ss.Choices) -> int:
    saved = {f: (f.read_bytes() if f.exists() else None) for f in WRITES}

    def undo(why: list[str]) -> int:
        for f, data in saved.items():
            if data is None:
                f.unlink(missing_ok=True)
            else:
                f.write_bytes(data)
        print("Not applied; every file is as it was:", file=sys.stderr)
        for line in why:
            print(f"  {line}", file=sys.stderr)
        return 1

    try:
        changes = ss.template_changes(p, choices)
        doc = ss.new_template(ctx["template_doc"], ctx["roots"]["store"], changes, p.by_content)
        edits = ss.device_edits(p, choices)
        rows = ss.edited_rows(devices.field_rows(DEVICE_FILES), edits)      # by key, never by place
        devices.merge(devices.generated_rows(DEVICE_FILES), rows, (devices.GENERATED_FILE, devices.FIELD_FILE))
    except (ss.SplitError, devices.DevicesError) as exc:
        return undo([str(exc)])
    try:
        TEMPLATE.write_bytes(doc.tobytes())
        tb.read_template(TEMPLATE)
        if edits:
            devices.write_field(rows, DEVICE_FILES.but(field=DEVICES))
    except devices.DevicesError as exc:
        return undo([f"the new {DEVICES.name}: {exc}"])
    except (tb.TablesBuildError, OSError) as exc:
        return undo([f"the new template: {exc}"])
    built = subprocess.run([sys.executable, str(BUILD)], cwd=ROOT, env=build_env(), capture_output=True, text=True)
    if built.returncode != 0:
        hint = (["A merged rename often needs the names that follow it changed too (a turnout's FB rows, a block's "
                 "length row, the discovered logic): drop that merge, or rename by hand across the sources."]
                if any(i.part == "userName" for i in p.of(ss.DEVICE) if i.id in choices.merge) else [])
        return undo(["build_tables.py refused the new sources:",
                     *(built.stdout + built.stderr).strip().splitlines()[-12:], *hint])
    try:
        rebuilt = ss.normalised(TABLES.read_bytes(), "the rebuilt tables.xml")
        template_now = ss.normalised(tb.read_template(TEMPLATE).tobytes(), "the new template")
    except (ss.SplitError, tb.TablesBuildError) as exc:
        return undo([str(exc)])
    bad = ss.verify(p, choices, ctx["roots"]["repo"], rebuilt, template_now)
    if bad:
        return undo(["the rebuild does not give what the plan promised:", *bad[:20]])
    try:
        record(store_path, ctx, p)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        return undo([f"{SPLITS.name} could not be written: {exc!r}"])
    merged = sorted(choices.merge)
    print(f"Applied plan {p.fingerprint}: {len(changes)} template change(s), {len(edits)} {DEVICES.name} change(s)"
          + (f" (merged {', '.join(merged)})" if merged else "") + "; tables.xml rebuilt and checked.")
    written = [f for f in WRITES if (f.read_bytes() if f.exists() else None) != saved[f]]
    print("Commit these (nothing is committed yet):")
    for f in written:
        print(f"  {f.relative_to(ROOT)}")
    if edits:
        print(f"{DEVICES.name} changed: run make panels CHECK=1 (make panels when it reports stale outputs), and "
              "make panelpro-test before the deploy.")
    print("Once merged, the next deploy replaces the host's tables.xml with the generated one (store_splits.csv).")
    return 0


def record(store_path: Path, ctx: dict, p: ss.Plan) -> None:
    host = store_path.name.split("-", 1)[0] if store_path.name.startswith(("pi-", "mac-")) else "unknown"
    rows = []
    if SPLITS.exists():
        rows = list(csv.DictReader(io.StringIO(SPLITS.read_text(encoding="utf-8"))))
    rows = [r for r in rows if r["store_sha256"] != ctx["store_sha"]]
    rows.append(dict(store_sha256=ctx["store_sha"], host=host, store_file=store_path.name, base=ctx["base_what"],
                     plan=p.fingerprint, split_date=dt.date.today().isoformat()))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(SPLIT_COLUMNS), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    SPLITS.write_text(buf.getvalue(), encoding="utf-8")


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("store", type=Path, help="the kept Store (media/pulled-stores/pi-....xml)")
    ap.add_argument("--base", type=Path, help="a tables file to use as the base, in place of STORE.base")
    ap.add_argument("--no-base", action="store_true", help="split with no base: every template change is reviewed")
    ap.add_argument("--show", metavar="ID", help="print one item as a diff")
    ap.add_argument("--verbose", action="store_true", help="say where each KEPT item goes too")
    ap.add_argument("--apply", action="store_true", help="write the split (needs --plan)")
    ap.add_argument("--plan", metavar="FP", help="the plan fingerprint the report printed")
    ap.add_argument("--merge", default="", help="CLASH and DEVICE ids to merge, comma-separated; the rest are dropped")
    ap.add_argument("--drop", default="", help="KEPT ids to leave out of the template, comma-separated")
    args = ap.parse_args(argv)
    try:
        if args.apply:
            refuse_place()
        p, ctx = make_plan(args.store, args)
        print(f"Store {args.store.name}, base: {ctx['base_what']}", flush=True)
        if args.show:
            item = p.by_id().get(args.show.upper())
            if item is None:
                raise Stop(f"no item {args.show} in plan {p.fingerprint}")
            print(f"{item.id} {item.where}: {item.what}\n{item.note}")
            print("\n".join(ss.show(item)) or "(no text difference after normalising)")
            return 0
        if not args.apply:
            print("\n".join(ss.report(p, verbose=args.verbose)))
            print(f"\nApply: python3 tools/schematic/split_store.py {args.store} --apply --plan {p.fingerprint}"
                  " --merge <C and D ids> [--drop <K ids>]")
            return 0
        if args.plan != p.fingerprint:
            raise Stop(f"the plan is {p.fingerprint}, not {args.plan}: the Store, base or repo changed since the "
                       "report; review the new report")
        choices = ss.Choices(merge=ids(args.merge), drop=ids(args.drop))
        try:
            ss.check_choices(p, choices)
        except ss.SplitError as exc:
            raise Stop(str(exc)) from exc
        return apply(args.store, p, ctx, choices)
    except Stop as exc:
        print(f"split_store: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
