#!/usr/bin/env python3
"""Traced stamps for the jobs of tools/check.sh: a job whose recorded reads are unchanged since its last pass is skipped.

    check_stamps.py current NAME [--save FILE]           exit 0 when NAME's stamp still holds (skip the job),
                                                         1 when it must run (and may record: FILE is written),
                                                         2 when NAME is not stampable now (run it, record nothing)
    check_stamps.py current-batch NAMES DIR [--why]      `current` for every job of a check.sh run, in one process:
                                                         NAMES has one job name per line; job i (from 0) gets
                                                         DIR/i.stamp (--save) and DIR/i.stamplog (--why), and
                                                         DIR/verdicts "i<TAB>0|1|2" per job once all are checked;
                                                         exit 3 and no verdicts when it cannot check them all
    check_stamps.py record  NAME FILE --trace LOG [--skipped N]
                                                         record NAME's stamp from the trace of the run that passed
                                                         (N: the skipped tests its output shows)
    check_stamps.py why     NAME                         say why NAME is not current
    check_stamps.py declared NAME                        the patterns NAME falls back to (an untraceable program)
    check_stamps.py audit-report DIR [-v]                compare the files a CHECK_AUDIT run opened with the declarations
                                                         (-v: for every job, the first two path parts
                                                         of each file it read)

check.sh runs each job under the trace hook of tools/audit/traced.py (shared with make panels): every repo file the
job's Python processes open, every file they probe and find absent, every folder they list and every subprocess they
start goes to a log. After a pass the stamp records that read set with its hashes and a key: panel_stamps.digest over
the job name, tools/check.sh and the hook, the Python and the plugin's state, what the job reads from outside the
repo (outside_state; for a job of the step manifest, tools/pipeline/checks.toml, also a digest of the entries it
runs, so an edited entry reruns that job and no other), and the output of each read-only git command it ran (run
again at compare time). The next run
skips the job only when the key and every read-set entry match, so an edit re-runs only the jobs that read the file.
A unit job whose tests skipped records them too (each test's id and reason, from the hook) in its key; what they
skipped on is an input like any other: a file or folder the trace saw, a shutil.which lookup (looked up again at
compare time), the interpreters' packages (outside_state), a git command it ran or a git ref REFS_OF names.
check.sh checks every job in one `current-batch` process before it starts any, and starts only the ones that run.
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
import importlib.util
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


def _import(name: str, path: Path):
    """The module at `path` under `name`, loaded once per process (its dataclasses look it up in sys.modules)."""
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


pm = _import("pipeline_manifest", ROOT / "tools/pipeline/manifest.py")
MANIFEST = pm.MANIFEST.relative_to(pm.ROOT)     # tools/pipeline/checks.toml, under each Checker's root

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
    # ruff (a program the trace cannot see) reads every .py and ruff.toml, and skips what .gitignore files ignore; the
    # version is requirements.txt's pin
    "ruff": ("**/*.py", "ruff.toml", "requirements.txt", ".gitignore", "**/.gitignore"),
    "portal": (*CODE, *SITE),
    # its node scripts (www/scripts/tests/*.js, build_exam_answers.js, build_play_answers.js) read only www/, and a
    # package.json on the way up from them (none today) would set how node loads them
    "unit-portal": (*CODE, "www/**/*", "docs/**/*", "ops/**/*", "package.json"),
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
    # the deploy scripts (bash, and a git clone of HEAD staged the same way) copy from jmri/, cats/, tools/ and one
    # speed-matching CSV under docs/jmri/ (tools/hosts/deploy/stage.sh); their Python reads only CODE
    "unit-hosts test_deploy_stage": ("docs/jmri/**/*",),
    # cs105_roster_sync.sh (bash) refuses when the submodule is not checked out, and the test skips on that answer
    "unit-hosts test_pi_ssh_scripts": ("external/jmri-cs105-roster-sync/**/*",),
    "unit-guards test_check_sh_tables": ("www/**/*",),
    # tools/ops/status_counts.py reads wiki/STATUS.md; its git status only compares the tree before and after
    "unit-guards test_hart_tables_writers": ("wiki/STATUS.md", "www/scripts/**/*"),
    # it lists the STL folder to check every file there is classified
    "unit-guards test_helix_stl_index": ("www/scripts/**/*", "docs/benchwork/helix/stl/**/*"),
    "unit-guards test_jmri_process_patterns": ("docs/**/*", "ops/**/*", "www/scripts/**/*"),
    # the map build draws the agent-doc lane from the wiki and docs/INDEX.md too (tools/ops/agent_docs_map.py)
    # the map build also reads .gitmodules (the submodule nodes) and lists ops/hart-ops/card_pipeline (a folder node
    # of the map, docs/pipeline-map/pipeline_map.json)
    "unit-guards test_pipeline_map": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*",
                                      "docs/INDEX.md", "ops/hart-ops/AGENTS.md", ".gitmodules",
                                      "ops/hart-ops/card_pipeline/**/*"),
    # the map and the entry files outside CODE (www/scripts/deploy_hartrailroad.sh); its output roots are in CODE
    "unit-guards test_pipeline_map_coverage": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*",
                                               "docs/INDEX.md", "ops/hart-ops/AGENTS.md"),
    # the step manifest's loader checks domains, edge sides and local nodes against the map (manifest.repo())
    "unit-guards test_pipeline_manifest": ("docs/pipeline-map/pipeline_map.json",),
    "unit-guards test_check_docs_only": ("docs/pipeline-map/pipeline_map.json",),
    "unit-guards test_agent_docs_map": ("docs/pipeline-map/**/*", "www/scripts/**/*", "wiki/**/*", "docs/INDEX.md",
                                        "ops/hart-ops/AGENTS.md", ".gitmodules"),
    # the agent-doc cells it checks are in the wiki (home.md, the decisions, pipelines, projects, STATUS.md)
    "unit-guards test_agent_docs_cells": ("wiki/**/*",),
    # check_ai_speak.DEFAULT_GLOBS (a test keeps the two the same): it lists their folders and fails a glob that
    # matches nothing
    "unit-guards test_ai_speak": ("www/ai/*.html", "www/library/*.html", "www/behind/*.html", "www/guides/*.html",
                                  "www/ap/*.html", "www/exam/index.html", "www/exam/run.html"),
    # check_public_text.py imports private_name from ops/hart-ops/card_pipeline (on sys.path)
    "unit-guards test_public_text": ("ops/hart-ops/card_pipeline/**/*",),
    # it checks wiki/STATUS.md for doubled entries and merges in a scratch repo under the repo's .gitattributes
    "unit-guards test_status_merge": ("wiki/STATUS.md", ".gitattributes"),
    # the merge drivers run under the repo's own .gitattributes in a scratch repo
    "unit-guards test_merge_pipeline_map": (".gitattributes",),
    "unit-guards test_portal_inputs": ("www/scripts/**/*",),
    "unit-guards test_publish_draft": ("docs/ops/**/*", "ops/**/*"),
    "unit-guards test_site_device_names": ("www/data/**/*", "www/scripts/**/*"),
    "unit-guards test_write_inventory": ("docs/wiring/**/*",),
    # it runs check_data_readers.py over every tracked .py (docs/, ops/ and www/ included)
    "unit-guards test_check_data_readers": ("**/*.py",),
    "unit-guards test_docs_index": ("docs/**/*",),
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


# The quick jobs tests/test_check_stamps.py runs under CHECK_AUDIT: one of each kind of folder a job tests.
AUDIT_SAMPLE = ("unit-hartlib", "unit-mimic", "unit-anyrail", "unit-cats", "unit-jmri-scripts",
                "unit-guards test_turnout_startup", "unit-hosts test_load_env", "unit-jmri test_speedmatch_distance")
# "kind test" -> the jobs it runs through a check.sh of its own (bash, untraced, so its stamp falls back to its
# declaration): it reads what their declarations name (its AuditTest checks that they cover what each read), and
# RUNS_JOBS_ALSO: .gitmodules (check.sh's start-up: worktrees.py submodules and the plugin pin check) and .gitignore
# (git check-ignore and ls-files in the sample jobs and the stamp helper). The rest of that start-up and the stamp
# helper read tools/, except portal_inputs.py (www/scripts/published-files.json and git), whose answer only names
# the portal job, which CHECK_ONLY leaves out of that run.
RUNS_JOBS: dict[str, tuple[str, ...]] = {
    "unit-guards test_check_stamps": AUDIT_SAMPLE,
}
RUNS_JOBS_ALSO = (".gitmodules", ".gitignore")


def _test_key(name: str) -> str | None:
    """"kind test" for job `name` ("unit-hosts test_deploy_gates.SomeTest" -> "unit-hosts test_deploy_gates"), or
    None for a job named by its kind alone."""
    parts = name.split(" ", 2)
    return f"{parts[0]} {parts[1].split('.')[0]}" if len(parts) > 1 else None


def declared(name: str) -> tuple[str, ...] | None:
    """The patterns job `name`'s stamp covers, or None when it is not a stampable job (a "... skipped" placeholder)."""
    pats = BY_KIND.get(name.split(" ", 1)[0])
    if pats is None or re.search(r" skipped\b", name):
        return None
    tk = _test_key(name)
    extra = EXTRA.get(tk, ()) if tk else ()
    inner = (*(p for job in RUNS_JOBS[tk] for p in _declared_job(job)), *RUNS_JOBS_ALSO) if tk in RUNS_JOBS else ()
    return tuple(dict.fromkeys((*pats, *extra, *inner, "tools/check.sh")))


def _declared_job(job: str) -> tuple[str, ...]:
    """declared(job) for a job a table names: one that is not stampable is an error in the table."""
    pats = declared(job)
    if pats is None:
        raise ValueError(f"check_stamps.RUNS_JOBS names {job!r}, which is not a stampable job")
    return pats


def check_tables() -> None:
    """The tables keyed by "kind test" name a kind in BY_KIND, and RUNS_JOBS does not nest (a job that runs a job
    that runs jobs) and names only stampable jobs. Raises ValueError."""
    for label, table in (("EXTRA", EXTRA), ("LISTED_ONLY", LISTED_ONLY), ("RUNS_JOBS", RUNS_JOBS)):
        for tk in table:
            parts = tk.split(" ")
            if len(parts) != 2 or parts[0] not in BY_KIND or not parts[1]:
                raise ValueError(f"check_stamps.{label}: {tk!r} is not \"<kind in BY_KIND> <test file>\"")
    for tk, jobs in RUNS_JOBS.items():
        for job in jobs:
            if _test_key(job) in RUNS_JOBS:
                raise ValueError(f"check_stamps.RUNS_JOBS: {tk!r} runs {job!r}, which runs jobs of its own")
            _declared_job(job)
    for job, refs in REFS_OF.items():
        if declared(job) is None:
            raise ValueError(f"check_stamps.REFS_OF: {job!r} is not a stampable job")
        unknown = [r for r in refs if r not in GIT_REFS]
        if unknown:
            raise ValueError(f"check_stamps.REFS_OF: {job!r} names {', '.join(unknown)}, not in GIT_REFS")


def _pruned(rel: str) -> bool:
    return any(rel == p or rel.startswith(p + "/") for p in PRUNE_PATHS)


def walk(patterns, root: Path = ROOT) -> list[Path]:
    """Every file under `root` the patterns name, sorted; caches, VCS data, other worktrees and the plugin left out.
    Linked folders (media/, ops/car-cards in a worktree) are walked through their links, whatever the pattern."""
    heads = set()
    for pat in patterns:
        # a literal pattern ("tools/check.sh") starts at itself, not at its folder: no walk of all of tools/ for it
        if not any(c in pat for c in "*?"):
            heads.add(pat)
            continue
        head = pat.split("*", 1)[0].split("?", 1)[0]
        heads.add(head.rsplit("/", 1)[0] if "/" in head else "")
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
    """An interpreter's real path and the names and versions of the packages it can import: for the Python running
    this (the jobs' python3), its site-packages and the user's (pip install --user); for another one (a venv), the
    site-packages under its prefix."""
    out = [os.path.realpath(python)]
    if out[0] == os.path.realpath(sys.executable):
        import site
        sites = [Path(s) for s in site.getsitepackages()]
        if site.ENABLE_USER_SITE:
            sites.append(Path(site.getusersitepackages()))
    else:
        sites = sorted(Path(python).parent.parent.glob("lib/python*/site-packages"))
    for s in sites:
        out += sorted(d.name for d in s.glob("*.dist-info"))
    return "|".join(out)


class Checker:
    """The stamp checks of one moment: one file-hash cache, and what is the same for every job then (git's answers,
    the plugin's state, the walk of a pattern set, the interpreters, the snapshot) worked out once. check.sh's
    `current-batch` checks every job with one; a single `current`, `why` or `record` makes one of its own."""

    def __init__(self, root: Path = ROOT, store: Path = STORE) -> None:
        self.root, self.store = root, store
        self.cache = HashCache(store / "filehash.json")
        self._memo: dict[tuple, object] = {}

    def _once(self, key: tuple, make):
        if key not in self._memo:
            self._memo[key] = make()
        return self._memo[key]

    def git(self, *args: str) -> str:
        return self._once(("git", args), lambda: _run("git", *args, cwd=self.root))

    def plugin(self) -> str:
        return self._once(("plugin",), lambda: ps.plugin_state(self.root))

    def unstampable(self) -> str | None:
        return self._once(("unstampable",), lambda: ps.unstampable(self.root))

    def walk(self, patterns: tuple[str, ...]) -> list[Path]:
        return self._once(("walk", patterns), lambda: walk(patterns, self.root))

    def manifest(self) -> dict[str, str]:
        """manifest.job_digests of the checkout's tools/pipeline/checks.toml (raises manifest.ManifestError)."""
        return self._once(("manifest",), lambda: pm.job_digests(self.root / MANIFEST))

    def venv(self, python: Path) -> str:
        return self._once(("venv", str(python)), lambda: venv_state(python))

    def replay(self, gits: list) -> list[str]:
        """traced.git_replay, each command run once."""
        return [self._once(("replay", tuple(cmd)), lambda cmd=cmd: traced.git_replay([cmd], str(self.root))[0])
                for cmd in gits]

    def snapshot(self, outside: str) -> str:
        return self._once(("snapshot", outside), lambda: traced.snapshot(self.root, self.plugin(), outside))


# The git refs a job's key holds besides the git commands its trace replays: the read-only checks and the portal
# build compare against them, test_redeploy_commit's deploy script (bash, untraced) stages HEAD's tree and refuses
# a commit that is not on origin/main, and its tests skip by that answer, and test_deploy_stage stages from a git clone
# of the committed HEAD (its StampNamesWhatWasShipped setUpClass, tools/hosts/tests/test_deploy_stage.py) while its
# read set hashes the working tree, so committing an edit already in the tree must rerun it (and any other commit
# reruns it too: the price of keying on HEAD).
GIT_REFS = {"head": ("rev-parse", "HEAD"), "base": ("merge-base", "HEAD", "origin/main"),
            "origin": ("rev-parse", "origin/main")}
REFS_OF: dict[str, tuple[str, ...]] = {
    "static": ("head", "base"),
    "portal": ("head", "base"),
    "unit-hosts test_redeploy_commit": ("head", "base", "origin"),
    "unit-hosts test_deploy_stage": ("head",),
}


# The environment that picks other inputs, and what tests skip on (tests/test_check_stamps.py: every variable a
# test's skip reads is here): CHECK_AUDIT (test_check_stamps inside an audit run), UPDATE_GOLDEN (golden files rewritten).
KEY_ENV = ("ANYRAIL_PLAN", "JMRI_LAYOUT", "SCHEMATIC_CACHE", "SCHEMATIC_REQUIRED", "CHECK_AUDIT", "UPDATE_GOLDEN")


def from_manifest(name: str) -> bool:
    """Whether check.sh runs job `name` from the step manifest: every stampable job but the unit tests (static, and
    each step in no group: public-text, ruff, portal)."""
    return declared(name) is not None and not name.split(" ", 1)[0].startswith("unit-")


def manifest_part(name: str, ck: Checker) -> str:
    """The key's line for a manifest job: the digest of the entries it runs. Raises manifest.ManifestError when the
    manifest cannot be read or holds no such job (check.sh then runs the job and records nothing)."""
    digests = ck.manifest()
    if name not in digests:
        raise pm.ManifestError(f"{MANIFEST.as_posix()} has no job {name!r}, which check.sh runs from it "
                               f"(its jobs: {', '.join(digests)})")
    return f"manifest={digests[name]}"


def outside_state(name: str, ck: Checker, wide: bool = False) -> str:
    """What the jobs read from outside the traced files: the private AnyRail plan, the interpreters and their
    packages, the environment that picks other inputs, the git refs REFS_OF names for the job, and for a manifest job
    the digest of its entries (manifest_part). `wide` (a job that ran an untraceable program) adds the names of the
    files git tracks or would add."""
    plan = plan_file()
    parts = [f"plan={ck.cache(plan) if plan.is_file() else 'absent'}",
             f"python3={ck.venv(Path(sys.executable))}"]
    if wide:
        parts.append("tracked=" + hashlib.sha256(ck.git("ls-files", "-co", "--exclude-standard").encode()).hexdigest())
    hops = ck.root / "ops/hart-ops/.venv/bin/python"
    if name in ("unit-hart-ops", "public-text") and hops.exists():
        parts.append(f"hops={ck.venv(hops)}")
    for ref in REFS_OF.get(name) or REFS_OF.get(_test_key(name) or "", ()):
        parts.append(f"{ref}=" + ck.git(*GIT_REFS[ref]).strip())
    if from_manifest(name):
        parts.append(manifest_part(name, ck))
    parts += [f"{k}={os.environ.get(k, '')}" for k in KEY_ENV]
    parts.append(f"euid={os.geteuid() if hasattr(os, 'geteuid') else ''}")    # test_operating skips as root
    return "\n".join(parts)


def not_stampable(name: str, ck: Checker | None = None) -> str | None:
    if declared(name) is None:
        return f"{name} is not a stampable job"
    # also while HART_TABLES is set, for every job: the unit jobs run without it
    return ck.unstampable() if ck else ps.unstampable(ROOT)


# check.sh, the loader that turns the manifest's entries into its job lines, and the hook: an edit to one reruns every
# job. tools/pipeline/checks.toml is not here: each manifest job's key holds its own entries (manifest_part).
ALWAYS = ("tools/check.sh", "tools/pipeline/manifest.py", *traced.HOOK_FILES)


def _patterns(name: str, programs: list[str]) -> tuple[str, ...]:
    """What the key hashes by pattern: check.sh and the hook, and the whole declaration after an untraceable program."""
    return (*ALWAYS, *(declared(name) or ())) if programs else ALWAYS


def skip_list(skips) -> list[list[str]]:
    """The skipped tests a stamp holds: [test id, reason] pairs, sorted, each once."""
    return [list(s) for s in sorted({(str(i), str(r)) for i, r in skips})]


def key(name: str, ck: Checker, programs: list[str], gits: list, skips=()) -> str:
    """The stamp key: job, check.sh and the hook, interpreter, plugin, outside state and git output now, for a job
    that ran an untraceable program every file its declaration names, and the tests its passing run skipped (their
    ids and reasons): what they skipped on is in the rest of the key and the read set."""
    pats = _patterns(name, programs)
    extra = (outside_state(name, ck, bool(programs)) + f"\nprograms={','.join(programs)}"
             + f"\ngit={','.join(ck.replay(gits))}")
    if skips:
        extra += "\nskips=" + json.dumps(skip_list(skips))
    return ps.digest(f"check:{name}", (), pats, ck.root, hasher=ck.cache, files=ck.walk(pats), extra=extra,
                     plugin=ck.plugin())


def _file(name: str, store: Path = STORE) -> Path:
    slug = "".join(c if c.isalnum() else "_" for c in name)[:60]
    return store / f"{slug}-{hashlib.sha256(name.encode()).hexdigest()[:10]}.json"


def why_not_current(name: str, root: Path = ROOT, store: Path = STORE, checker: Checker | None = None) -> str | None:
    """None when job `name` may be skipped, else why it must run. With no `checker`, one of its own (saved after)."""
    ck = checker or Checker(root, store)
    try:
        stamp = traced.load(_file(name, ck.store))
        if not stamp:
            return "no stamp"
        k = key(name, ck, stamp.get("programs", []), stamp.get("git", []), stamp.get("skips", []))
        return traced.mismatch(stamp, k, str(ck.root), hasher=lambda p: ck.cache(Path(p)))
    finally:
        if checker is None:
            ck.cache.save()


def is_current(name: str, root: Path = ROOT, store: Path = STORE) -> bool:
    return why_not_current(name, root, store) is None


def snapshot(name: str, root: Path = ROOT, store: Path = STORE, checker: Checker | None = None) -> str:
    """traced.snapshot with the plugin's and `name`'s outside state: saved before the job, compared at record."""
    ck = checker or Checker(root, store)
    try:
        return ck.snapshot(outside_state(name, ck, True))
    finally:
        if checker is None:
            ck.cache.save()


def verdict(name: str, ck: Checker, save: Path | None) -> tuple[int, str | None]:
    """`current`'s answer for job `name`: (0, None) when its stamp holds (skip it), (1, why) when it must run and may
    record, (2, why) when it is not stampable now (run it, record nothing). `save` gets the snapshot of a stampable
    job, taken before it runs, for `record`."""
    unstampable = not_stampable(name, ck)
    if unstampable:
        return 2, unstampable
    reason = why_not_current(name, checker=ck)
    if save:
        save.write_text(snapshot(name, checker=ck) + "\n")
    return (0, None) if reason is None else (1, reason)


class BatchError(Exception):
    """current-batch stopped: check.sh then runs every job and records none."""


def read_names(path: Path) -> list[str]:
    """The job names of a current-batch, one per line in check.sh's order (line i is job i). Raises BatchError."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise BatchError(f"cannot read the job names in {path}: {exc}") from exc
    names = text.split("\n")
    if names and names[-1] == "":
        names.pop()
    if not names:
        raise BatchError(f"{path} names no job")
    for i, name in enumerate(names):
        if not name.strip() or name != name.strip():
            raise BatchError(f"{path} line {i + 1}: {name!r} is no job name (empty, or spaces around it)")
    return names


def current_batch(names: list[str], out: Path, why: bool, root: Path = ROOT, store: Path = STORE) -> list[int]:
    """`current` for every job of one check.sh run in one process, with one Checker: job i (names[i]) gets out/i.stamp
    (the snapshot, for a stampable job) and, with `why`, out/i.stamplog ("runs: <why>"); out/verdicts gets "i<TAB>code"
    per job once all are checked (written whole or not at all). A job whose check raises gets 2 (run, record nothing),
    its stamp is dropped so its next pass records afresh, and its stamplog says why. Raises BatchError when it cannot
    check the batch at all (the folder): then no job may be skipped."""
    if not out.is_dir():
        raise BatchError(f"{out} is not a folder")
    ck = Checker(root, store)
    verdicts = []
    try:
        for i, name in enumerate(names):
            log = out / f"{i}.stamplog"
            try:
                code, reason = verdict(name, ck, out / f"{i}.stamp")
            except Exception as exc:  # noqa: BLE001 - this job runs and records nothing; its stamp is dropped
                code, why_now = 2, f"the stamp check failed: {type(exc).__name__}: {exc}; its stamp is dropped"
                _file(name, ck.store).unlink(missing_ok=True)
                (out / f"{i}.stamp").unlink(missing_ok=True)
                log.write_text(f"runs: {why_now}\n")      # printed with the job's output, --why or not
            else:
                if why and reason:
                    log.write_text(f"runs: {reason}\n")
            verdicts.append(code)
    finally:
        ck.cache.save()
    if len(verdicts) != len(names):
        raise BatchError(f"{len(verdicts)} verdicts for {len(names)} jobs")
    tmp = out / f"verdicts.{os.getpid()}.tmp"
    tmp.write_text("".join(f"{i}\t{code}\n" for i, code in enumerate(verdicts)))
    os.replace(tmp, out / "verdicts")
    return verdicts


def record(name: str, trace_log, root: Path = ROOT, store: Path = STORE, before: str | None = None,
           skipped: int = 0) -> str | None:
    """Record `name`'s stamp from `trace_log`; None when recorded, else why not (any old stamp is dropped).
    `before` is the snapshot() taken before the job: a different one now records nothing. `skipped` is the number of
    skipped tests the job's output shows: the trace must hold at least that many skips, with their ids and reasons."""
    t = traced.parse(trace_log)
    reason = traced.problem(t)
    ck = Checker(root, store)
    try:
        if reason is None and before is not None and before != snapshot(name, checker=ck):
            reason = ("HEAD, origin/main, the plugin, an interpreter, the private plan or the job's entries in "
                      "tools/pipeline/checks.toml changed while the job ran")
        if reason is None and len(t.skips) < skipped:
            reason = (f"the output shows {skipped} skipped tests and the trace holds {len(t.skips)}: which tests "
                      "skipped, and why, is not known")
        if reason is None:
            main = main_checkout(root)
            programs, gits = traced.untraced(t, str(root), (str(main),) if main else ())
            rs = traced.read_set(t, str(root))
            hashed = [p.relative_to(root).as_posix() for p in ck.walk(_patterns(name, programs))]
            late = traced.changed_since(t, rs, str(root), hashed)
            if late:
                reason = f"{late[0]} changed while the job ran"
            else:
                skips = skip_list(t.skips)
                k = key(name, ck, programs, gits, skips)
                meta = {"programs": programs, "git": gits, **({"skips": skips} if skips else {})}
                traced.save(_file(name, store), traced.make_stamp(k, t, str(root), hasher=lambda p: ck.cache(Path(p)),
                                                                  **meta))
                return None
    finally:
        ck.cache.save()
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
    tk = _test_key(name)
    listed = LISTED_ONLY.get(tk, ()) if tk else ()
    for d in sorted(dirs):
        if d in (".", "") or d in listed:
            continue
        if not any(_reaches(d, pat) for pat in pats):
            bad.append(d + "/")
    return bad


def _reaches(d: str, pat: str) -> bool:
    """Whether listing folder `d` is covered by pattern `pat`: `d` is on the way to a file it names, or inside the
    folder its wildcard spans. A file pattern ("Makefile", "wiki/STATUS.md") reaches only its parent folders, and a
    root wildcard only "**" (every folder), not "*.md" (root files)."""
    if "*" not in pat:
        return pat.startswith(d + "/")
    head = pat.split("*", 1)[0]
    if "/" not in head:
        return pat.startswith("**")
    literal = head.rsplit("/", 1)[0]
    return d == literal or d.startswith(literal + "/") or literal.startswith(d + "/")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        check_tables()
    except ValueError as exc:       # every job runs and records nothing (check.sh: an answer other than 0 or 1)
        print(f"check_stamps.py: {exc}", file=sys.stderr)
        return 2
    try:
        return _main(argv)
    except pm.ManifestError as exc:     # a manifest job's key cannot be made: it runs and records nothing
        print(f"check_stamps.py: not stamped: {exc}", file=sys.stderr)
        return 2


def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "current":
        name, save = argv[1], None
        if "--save" in argv:
            save = Path(argv[argv.index("--save") + 1])
        why = "--why" in argv              # say why it runs (a CI pull request run: check.sh CHECK_SKIP_FROM)
        ck = Checker()
        try:
            code, reason = verdict(name, ck, save)
        finally:
            ck.cache.save()
        if reason and why:
            print(f"runs: {reason}")
        return code
    if argv[:1] == ["current-batch"] and len(argv) in (3, 4) and argv[3:] in ([], ["--why"]):
        try:
            current_batch(read_names(Path(argv[1])), Path(argv[2]), why=len(argv) == 4)
        except BatchError as exc:
            print(f"check_stamps.py current-batch: {exc}", file=sys.stderr)
            return 3
        return 0
    if len(argv) == 2 and argv[0] == "why":
        print(not_stampable(argv[1]) or why_not_current(argv[1]) or "current")
        return 0
    if argv[:1] == ["record"] and len(argv) in (5, 7) and argv[3] == "--trace" and argv[5:6] in ([], ["--skipped"]):
        skipped = argv[6] if len(argv) == 7 else "0"
        if not skipped.isdigit():
            print(f"check_stamps.py record: --skipped takes a count, not {skipped!r}; not stamped")
            return 2
        if not_stampable(argv[1]) is None:
            reason = record(argv[1], argv[4], before=Path(argv[2]).read_text().strip(), skipped=int(skipped))
            if reason:
                print(f"not stamped: {reason}")
        return 0
    if len(argv) == 2 and argv[0] == "declared":
        print("\n".join(declared(argv[1]) or ()))
        return 0
    if argv[:1] == ["audit-report"] and (len(argv) == 2 or argv[2:] == ["-v"]):
        if not Path(argv[1]).is_dir():
            print(f"check_stamps.py audit-report: {argv[1]} is not a folder (CHECK_AUDIT=DIR FULL=1 tools/check.sh "
                  "writes one)", file=sys.stderr)
            return 2
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
