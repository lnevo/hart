#!/usr/bin/env python3
"""Traced stamps for the jobs of tools/check.sh: a job whose recorded reads are unchanged since its last pass is skipped.

    check_stamps.py current NAME [--save FILE]           exit 0 when NAME's stamp still holds (skip the job),
                                                         1 when it must run (and may record: FILE is written),
                                                         2 when NAME is not stampable now (run it, record nothing)
    check_stamps.py record  NAME FILE --trace LOG        record NAME's stamp from the trace of the run that passed
    check_stamps.py why     NAME                         say why NAME is not current
    check_stamps.py declared NAME                        the patterns NAME falls back to (an untraceable program)
    check_stamps.py audit-report DIR                     compare the files a CHECK_AUDIT run opened with the declarations

check.sh runs each job under the trace hook of tools/audit/traced.py (shared with make panels): every repo file the
job's Python processes open, every file they probe and find absent, every folder they list and every subprocess they
start goes to a log. After a pass the stamp records that read set with its hashes and a key: panel_stamps.digest over
the job name, tools/check.sh and the hook, the Python and the plugin's state, what the job reads from outside the
repo (outside_state), and the output of each read-only git command it ran (run again at compare time). The next run
skips the job only when the key and every read-set entry match, so an edit re-runs only the jobs that read the file.
A job that ran a program the hook cannot see (bash, a writing git, a Python child with the hook dropped) inside the
checkout falls back to its declaration (`declared`, wide on purpose: whole folders) as well, as before the traces.
Nothing is skipped or recorded while HART_TABLES is set or the schematic plugin is not at its pinned commit
(panel_stamps.unstampable), for a trace that is missing or short of a Python process, or when a file the job read
changed while it ran; check.sh never skips when CI is set, FULL=1 or CHECK_AUDIT (FULL=1 still records). Stamps hold
content hashes and repo-relative paths, so they sit in one per-user folder (<main checkout>/.cache/hart/check-stamps,
gitignored, or CHECK_STAMPS_DIR) that every worktree and `make remote` run shares; a file hash is reused while its
size and mtime stay.

tests/test_check_stamps.py checks that a recorded read set holds everything an independent audit hook
(tools/audit/stamp_audit/sitecustomize.py, CHECK_AUDIT) saw the same jobs open or list. What neither hook can see:
the plugin's files (covered by its commit).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "schematic"))
import panel_stamps as ps  # noqa: E402

traced = ps.traced
sys.path[:0] = [str(ROOT / "tools/hartlib/src")]
from hartlib.paths import cache_dir, main_checkout  # noqa: E402

STORE = Path(os.environ.get("CHECK_STAMPS_DIR") or cache_dir("check-stamps", ROOT))
PRUNE = {".git", ".cache", "__pycache__", "node_modules", ".venv", "venv", ".pages-dist", ".mypy_cache", ".pytest_cache"}
PRUNE_PATHS = {".claude/worktrees", "external/model-railroad-skills"}     # the plugin is stamped by its commit
LITTER = (".DS_Store", ".pyc")

# Folder groups. TOOLS is the code and its tests; LAYOUT the shared source and generated data every build reads.
TOOLS = ("tools/**/*",)
LAYOUT = ("jmri/**/*", "cats/**/*")
REPO_FILES = ("Makefile", "AGENTS.md", "requirements.txt", ".github/**/*", ".githooks/**/*", ".claude/**/*",
              ".cursor/**/*", ".vscode/**/*")
CODE = (*TOOLS, *LAYOUT, *REPO_FILES)       # what a unit job reads unless it says more
SITE = ("www/**/*", "ops/**/*", "docs/**/*", "wiki/**/*", "media/**/*", "archive/**/*", "external/**/*")
EVERYTHING = ("**/*",)

# job-name prefix -> patterns (tools/check.sh is always added). Each unit job names everything the audit saw it read
# (tools/audit/tests/test_check_stamps.py; `CHECK_AUDIT=DIR FULL=1 tools/check.sh`, then `check_stamps.py audit-report DIR`
# for every job), widened to whole folders so a new file there is covered.
BY_KIND: dict[str, tuple[str, ...]] = {
    "static": EVERYTHING,
    "public-text": EVERYTHING,
    "portal": (*CODE, *SITE),
    "unit-portal": (*CODE, *SITE),
    "unit-hart-ops": (*CODE, *SITE),
    "unit-schematic": (*CODE, "docs/ops/**/*", "wiki/pipelines/**/*", "www/crew/**/*", "www/data/**/*", "ops/**/*"),
    "unit-anyrail": (*CODE, "www/build/**/*", "docs/**/*"),
    "unit-hartlib": (*CODE, "**/*.py"),             # test_devices_one_path reads every tracked .py
    "unit-mimic": CODE,
    "unit-cats": CODE,
    "unit-jmri-scripts": CODE,
    "unit-jmri": CODE,
    "unit-hosts": CODE,
    "unit-guards": CODE,
}
# "kind test" (the test file, before any ".Class") -> patterns added to its kind's: the test files that read the
# site, the docs or the wiki. Every other file reads only code and data.
EXTRA: dict[str, tuple[str, ...]] = {
    "unit-guards test_name_copies": EVERYTHING,
    "unit-hosts test_deploy_stage": EVERYTHING,
    "unit-guards test_check_sh_tables": ("www/**/*",),
    "unit-guards test_hart_tables_writers": ("wiki/**/*", "www/scripts/**/*"),
    "unit-guards test_helix_stl_index": ("www/scripts/**/*",),
    "unit-guards test_jmri_process_patterns": ("docs/**/*", "ops/**/*", "www/scripts/**/*"),
    # the map build draws the agent-doc lane from the wiki and docs/INDEX.md too (tools/ops/agent_docs_map.py)
    "unit-guards test_pipeline_map": ("docs/pipeline-map/**/*", "www/library/**/*", "www/scripts/**/*", "wiki/**/*",
                                      "docs/INDEX.md", "ops/hart-ops/AGENTS.md"),
    # the map and the entry files outside CODE (www/scripts/deploy_hartrailroad.sh); its output roots are in CODE
    "unit-guards test_pipeline_map_coverage": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*",
                                               "docs/INDEX.md", "ops/hart-ops/AGENTS.md"),
    "unit-guards test_agent_docs_map": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*", "docs/INDEX.md",
                                        "ops/hart-ops/AGENTS.md"),
    # the merge drivers run under the repo's own .gitattributes in a scratch repo
    "unit-guards test_merge_pipeline_map": (".gitattributes",),
    "unit-guards test_portal_inputs": ("www/scripts/**/*",),
    "unit-guards test_publish_draft": ("docs/ops/**/*", "ops/**/*"),
    "unit-guards test_site_device_names": ("www/data/**/*", "www/scripts/**/*"),
    "unit-guards test_write_inventory": ("docs/wiring/**/*",),
    "unit-guards test_docs_index": ("docs/**/*",),
    "unit-guards test_check_stamps": EVERYTHING,
    "unit-hosts test_live_paths": ("docs/**/*",),
    "unit-hosts test_host_copies": ("ops/**/*",),
    "unit-hosts test_pull_tables": ("ops/**/*",),
    "unit-jmri test_infer_block_lengths": ("docs/jmri/**/*",),
    "unit-jmri test_speedmatch": ("docs/jmri/**/*",),
    "unit-jmri test_speedmatch_dashboard": ("docs/jmri/**/*",),
    "unit-jmri test_speedmatch_distance": ("docs/jmri/**/*",),
    "unit-jmri test_speedmatch_publish_live": ("docs/jmri/**/*",),
    "unit-jmri test_speedmatch_site_export": ("docs/jmri/**/*", "www/ai/**/*"),
}


# "kind test" -> folders the job only lists (a bare exists-or-not look; no file in them is read), left out of the stamp.
LISTED_ONLY: dict[str, tuple[str, ...]] = {
    "unit-hosts test_deploy_preflight": ("www",),
}


def declared(name: str) -> tuple[str, ...] | None:
    """The patterns job `name`'s stamp covers, or None when it is not a stampable job (a "... skipped" placeholder)."""
    parts = name.split(" ", 2)
    pats = BY_KIND.get(parts[0])
    if pats is None or re.search(r" skipped\b", name):
        return None
    extra = EXTRA.get(f"{parts[0]} {parts[1].split('.')[0]}", ()) if len(parts) > 1 else ()
    return (*pats, *extra, "tools/check.sh")


def _pruned(rel: str) -> bool:
    return any(rel == p or rel.startswith(p + "/") for p in PRUNE_PATHS)


def walk(patterns, root: Path = ROOT) -> list[Path]:
    """Every file under `root` the patterns name, sorted; caches, VCS data, other worktrees and the plugin left out.
    Linked folders (media/, ops/car-cards in a worktree) are walked through their links, whatever the pattern."""
    heads = set()
    for pat in patterns:
        head = pat.split("*", 1)[0]
        heads.add(head.rsplit("/", 1)[0] if "/" in head else ("" if "*" in pat else pat))
    found: set[Path] = set()
    starts = {h for h in heads if not any(h != o and (h + "/").startswith(o + "/") for o in heads if o)}
    seen: set[str] = set()                          # real paths of the folders walked: a link back up ends there
    for start in sorted(starts):
        base = root / start
        if base.is_file():
            walked = [(str(base.parent), [], [base.name])]
        else:
            walked = os.walk(base, followlinks=True)
        for dirpath, dirnames, filenames in walked:
            seen.add(os.path.realpath(dirpath))
            rel_dir = Path(dirpath).relative_to(root).as_posix()
            rel_dir = "" if rel_dir == "." else rel_dir
            dirnames[:] = [d for d in dirnames
                           if d not in PRUNE and not _pruned(f"{rel_dir}/{d}".lstrip("/"))
                           and os.path.realpath(os.path.join(dirpath, d)) not in seen]
            for f in filenames:
                if f.endswith(LITTER) or f == ".DS_Store":
                    continue
                rel = f"{rel_dir}/{f}".lstrip("/")
                if any(ps._glob_match(rel, pat) for pat in patterns):
                    p = root / rel
                    if p.is_file():
                        found.add(p)
    return sorted(found)


class HashCache:
    """sha256 of files, reused while a file's size and mtime stay; shared by the jobs through one JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.dirty = False
        try:
            self.data = json.loads(path.read_text())
        except (OSError, ValueError):
            self.data = {}

    def __call__(self, p: Path) -> str:
        st = p.stat()
        hit = self.data.get(str(p))
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            return hit[2]
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        self.data[str(p)] = [st.st_mtime_ns, st.st_size, sha]
        self.dirty = True
        return sha

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self.data))
        os.replace(tmp, self.path)


def plan_file() -> Path:
    """The AnyRail plan levels_svg.py and plan_lengths.py read (private, never in the repo)."""
    return Path(os.environ.get("ANYRAIL_PLAN") or Path.home() / "Documents/Layout/Lee Nevo Design Version 5.3c.any")


def _run(*cmd: str, cwd: Path) -> str:
    try:
        done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return done.stdout if done.returncode == 0 else f"failed:{done.returncode}"


def venv_state(python: Path) -> str:
    """An interpreter's real path and the names and versions of the packages in its site-packages."""
    out = [os.path.realpath(python)]
    prefix = Path(python).parent.parent
    for site in sorted(prefix.glob("lib/python*/site-packages")):
        out += sorted(d.name for d in site.glob("*.dist-info"))
    return "|".join(out)


def outside_state(name: str, root: Path, cache: "HashCache", wide: bool = False) -> str:
    """What the jobs read from outside the traced files: the private AnyRail plan, the interpreters and their
    packages, the environment that picks other inputs, and, for the checks that read git history, HEAD and the merge
    base. `wide` (a job that ran an untraceable program) adds the names of the files git tracks or would add."""
    plan = plan_file()
    parts = [f"plan={cache(plan) if plan.is_file() else 'absent'}",
             f"python3={venv_state(Path(sys.executable))}"]
    if wide:
        parts.append("tracked=" + hashlib.sha256(
            _run("git", "ls-files", "-co", "--exclude-standard", cwd=root).encode()).hexdigest())
    hops = root / "ops/hart-ops/.venv/bin/python"
    if name in ("unit-hart-ops", "public-text") and hops.exists():
        parts.append(f"hops={venv_state(hops)}")
    if name in ("static", "portal"):
        parts.append("head=" + _run("git", "rev-parse", "HEAD", cwd=root).strip())
        parts.append("base=" + _run("git", "merge-base", "HEAD", "origin/main", cwd=root).strip())
    parts += [f"{k}={os.environ.get(k, '')}" for k in ("ANYRAIL_PLAN", "JMRI_LAYOUT", "SCHEMATIC_CACHE", "SCHEMATIC_REQUIRED")]
    return "\n".join(parts)


def not_stampable(name: str) -> str | None:
    if declared(name) is None:
        return f"{name} is not a stampable job"
    return ps.unstampable(ROOT)         # also while HART_TABLES is set, for every job: the unit jobs run without it


ALWAYS = ("tools/check.sh", *traced.HOOK_FILES)


def _patterns(name: str, programs: list[str]) -> tuple[str, ...]:
    """What the key hashes by pattern: check.sh and the hook, and the whole declaration after an untraceable program."""
    return (*ALWAYS, *(declared(name) or ())) if programs else ALWAYS


def key(name: str, root: Path, cache: "HashCache", programs: list[str], gits: list) -> str:
    """The stamp key: job, check.sh and the hook, interpreter, plugin, outside state and git output now, and, for a job
    that ran an untraceable program, every file its declaration names."""
    pats = _patterns(name, programs)
    extra = (outside_state(name, root, cache, bool(programs)) + f"\nprograms={','.join(programs)}"
             + f"\ngit={','.join(traced.git_replay(gits, str(root)))}")
    return ps.digest(f"check:{name}", (), pats, root, hasher=cache, files=walk(pats, root), extra=extra)


def _file(name: str, store: Path = STORE) -> Path:
    slug = "".join(c if c.isalnum() else "_" for c in name)[:60]
    return store / f"{slug}-{hashlib.sha256(name.encode()).hexdigest()[:10]}.json"


def why_not_current(name: str, root: Path = ROOT, store: Path = STORE) -> str | None:
    """None when job `name` may be skipped, else why it must run."""
    stamp = traced.load(_file(name, store))
    if not stamp:
        return "no stamp"
    cache = HashCache(store / "filehash.json")
    try:
        k = key(name, root, cache, stamp.get("programs", []), stamp.get("git", []))
        return traced.mismatch(stamp, k, str(root), hasher=lambda p: cache(Path(p)))
    finally:
        cache.save()


def is_current(name: str, root: Path = ROOT, store: Path = STORE) -> bool:
    return why_not_current(name, root, store) is None


def snapshot(name: str, root: Path = ROOT, store: Path = STORE) -> str:
    """traced.snapshot with the plugin's and `name`'s outside state: saved before the job, compared at record."""
    cache = HashCache(store / "filehash.json")
    try:
        return traced.snapshot(root, ps.plugin_state(root), outside_state(name, root, cache, True))
    finally:
        cache.save()


def record(name: str, trace_log, root: Path = ROOT, store: Path = STORE, before: str | None = None) -> str | None:
    """Record `name`'s stamp from `trace_log`; None when recorded, else why not (any old stamp is dropped).
    `before` is the snapshot() taken before the job: a different one now records nothing."""
    t = traced.parse(trace_log)
    reason = traced.problem(t)
    if reason is None and before is not None and before != snapshot(name, root, store):
        reason = "HEAD, origin/main, the plugin, an interpreter or the private plan changed while the job ran"
    if reason is None:
        main = main_checkout(root)
        programs, gits = traced.untraced(t, str(root), (str(main),) if main else ())
        rs = traced.read_set(t, str(root))
        cache = HashCache(store / "filehash.json")
        try:
            hashed = [p.relative_to(root).as_posix() for p in walk(_patterns(name, programs), root)]
            late = traced.changed_since(t, rs, str(root), hashed)
            if late:
                reason = f"{late[0]} changed while the job ran"
            else:
                k = key(name, root, cache, programs, gits)
                traced.save(_file(name, store), traced.make_stamp(k, t, str(root), hasher=lambda p: cache(Path(p)),
                                                                  programs=programs, git=gits))
                return None
        finally:
            cache.save()
    _file(name, store).unlink(missing_ok=True)
    return reason


# ---- the audit ----

def read_audit(folder: Path) -> dict[str, tuple[set[str], set[str]]]:
    """job name -> (files read, folders listed), from a CHECK_AUDIT folder: N.name and N.log per job."""
    jobs = {}
    for namef in sorted(folder.glob("*.name")):
        files, dirs = set(), set()
        logf = namef.with_suffix(".log")
        if logf.is_file():
            for line in logf.read_text(errors="replace").splitlines():
                kind, _, rel = line.partition("\t")
                if not rel or rel.startswith(("<", ".git/", ".venv/")) or rel in (".git", ".venv") \
                        or "__pycache__" in rel.split("/") or rel.endswith(LITTER):
                    continue
                if _pruned(rel):
                    continue
                (files if kind == "r" else dirs).add(rel)
        jobs[namef.read_text().strip()] = (files, dirs)
    return jobs


def uncovered(name: str, files: set[str], dirs: set[str]) -> list[str]:
    pats = declared(name)
    assert pats is not None
    # the shared build cache (<main checkout>/.cache/, hartlib.paths.cache_dir) is keyed on real inputs: no input itself
    files = {f for f in files if not f.startswith(".cache/")}
    dirs = {d for d in dirs if d != ".cache" and not d.startswith(".cache/")}
    bad = [f for f in sorted(files) if not any(ps._glob_match(f, p) for p in pats)]
    parts = name.split(" ", 2)
    listed = LISTED_ONLY.get(f"{parts[0]} {parts[1].split('.')[0]}", ()) if len(parts) > 1 else ()
    for d in sorted(dirs):
        if d in (".", "") or d in listed:
            continue
        reach = False
        for pat in pats:
            head = pat.split("*", 1)[0]
            literal = head.rsplit("/", 1)[0] if "/" in head else ""
            if d == literal or d.startswith(literal + "/") or literal.startswith(d + "/") or literal == "":
                reach = True
                break
        if not reach:
            bad.append(d + "/")
    return bad


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) >= 2 and argv[0] == "current":
        name, save = argv[1], None
        if "--save" in argv:
            save = Path(argv[argv.index("--save") + 1])
        if not_stampable(name):
            return 2
        ok = is_current(name)
        if save:
            save.write_text(snapshot(name) + "\n")
        return 0 if ok else 1
    if len(argv) == 2 and argv[0] == "why":
        print(not_stampable(argv[1]) or why_not_current(argv[1]) or "current")
        return 0
    if len(argv) == 5 and argv[0] == "record" and argv[3] == "--trace":
        if not_stampable(argv[1]) is None:
            reason = record(argv[1], argv[4], before=Path(argv[2]).read_text().strip())
            if reason:
                print(f"not stamped: {reason}")
        return 0
    if len(argv) == 2 and argv[0] == "declared":
        print("\n".join(declared(argv[1]) or ()))
        return 0
    if len(argv) == 2 and argv[0] == "audit-report":
        rc = 0
        for name, (files, dirs) in read_audit(Path(argv[1])).items():
            if declared(name) is None:
                continue
            bad = uncovered(name, files, dirs)
            tops = sorted({"/".join(f.split("/")[:2]) for f in files})
            print(f"{name}: {len(files)} files read{' ; UNCOVERED ' + ', '.join(bad[:20]) if bad else ''}")
            if "-v" in argv or bad:
                print("    reads:", ", ".join(tops))
            rc |= bool(bad)
        return rc
    print(__doc__.split("\n\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
