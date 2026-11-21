#!/usr/bin/env python3
"""Stamps for the jobs of tools/check.sh: a job whose stamp equals its last pass is skipped on a local run.

    check_stamps.py current NAME [--save FILE]   exit 0 when NAME's stamp equals the recorded one (skip the job),
                                                 1 when it must run (the stamp it would record goes to FILE),
                                                 2 when NAME is not stampable now (run it, record nothing)
    check_stamps.py record  NAME FILE            record the stamp saved in FILE (check.sh does it after the job passed)
    check_stamps.py declared NAME                the patterns NAME's stamp covers
    check_stamps.py audit-report DIR             compare the files a CHECK_AUDIT run opened with the declarations

A stamp is panel_stamps.digest over the job name, tools/check.sh itself, the Python and the plugin's state, and every
file the job's declaration names (`declared`). It is taken before the job starts and recorded after it passed, so a file
edited while the job ran leaves the next run to repeat it. Nothing is skipped or recorded while HART_TABLES is set or
the schematic plugin is not at its pinned commit (panel_stamps.unstampable), and check.sh never asks when CI is set or
FULL=1. Stamps hold content hashes, not paths, so they sit in one per-user folder (<main checkout>/.cache/hart/check-stamps, gitignored, or
CHECK_STAMPS_DIR) that every worktree and `make remote` run shares; a file hash is reused while its size and mtime stay.

The risk is an input a declaration misses. tests/test_check_stamps.py runs check.sh under CHECK_AUDIT for the quick
jobs: tools/audit/stamp_audit/sitecustomize.py logs every repo file the job's Python processes open or list, and the test
fails for any the declaration does not cover. `CHECK_AUDIT=DIR FULL=1 tools/check.sh` then `audit-report DIR` does it for
every job (unit-hosts test_live_paths fails there: it finds the hook an unlisted builder input). What the hook cannot see: a non-Python subprocess (git, bash) and the plugin's files (covered by its commit).
Declarations are wide on purpose: a job names whole folders, so a new file in them can never be missed.
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
                                      "docs/INDEX.md"),
    # the map and the entry files outside CODE (www/scripts/deploy_hartrailroad.sh); its output roots are in CODE
    "unit-guards test_pipeline_map_coverage": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*",
                                               "docs/INDEX.md"),
    "unit-guards test_agent_docs_map": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*", "docs/INDEX.md"),
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


def outside_state(name: str, root: Path, cache: "HashCache") -> str:
    """What the jobs read from outside the declared files: the private AnyRail plan, the interpreters and their
    packages, the files git tracks (names only: a git-reading check follows a file being added or removed), the
    environment that picks other inputs, and, for the checks that read git history, HEAD and the merge base."""
    plan = plan_file()
    parts = [f"plan={cache(plan) if plan.is_file() else 'absent'}",
             f"python3={venv_state(Path(sys.executable))}",
             "tracked=" + hashlib.sha256(_run("git", "ls-files", "-co", "--exclude-standard", cwd=root).encode()).hexdigest()]
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


def stamp(name: str, root: Path = ROOT, store: Path = STORE) -> str:
    pats = declared(name)
    assert pats is not None
    cache = HashCache(store / "filehash.json")
    try:
        return ps.digest(f"check:{name}", (), pats, root, hasher=cache, files=walk(pats, root),
                         extra=outside_state(name, root, cache))
    finally:
        cache.save()


def _file(name: str, store: Path = STORE) -> Path:
    slug = "".join(c if c.isalnum() else "_" for c in name)[:60]
    return store / f"{slug}-{hashlib.sha256(name.encode()).hexdigest()[:10]}.sha256"


def is_current(name: str, root: Path = ROOT, store: Path = STORE) -> tuple[bool, str]:
    s = stamp(name, root, store)
    f = _file(name, store)
    return f.is_file() and f.read_text().strip() == s, s


def record(name: str, stamp_text: str, store: Path = STORE) -> None:
    store.mkdir(parents=True, exist_ok=True)
    _file(name, store).write_text(stamp_text.strip() + "\n")


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
        ok, s = is_current(name)
        if save:
            save.write_text(s + "\n")
        return 0 if ok else 1
    if len(argv) == 3 and argv[0] == "record":
        if not_stampable(argv[1]) is None:
            record(argv[1], Path(argv[2]).read_text())
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
