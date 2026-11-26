#!/usr/bin/env python3
"""After an edit to the tables or the signal files, run the quick checks from tools/check.sh.

PostToolUse hook for Edit, Write and MultiEdit. A failing check exits 2 with its output on
stderr, which Claude sees. The table checks are the steps marked after_edit in the step
manifest, tools/pipeline/checks.toml (ADR-037), read from the edited file's checkout without
git or the map check; a manifest that does not load stops the hook with exit 2 and the reason,
as it stops check.sh (a worktree from before the marks takes them from this hook's checkout). They take about a second together. The unit-jmri job
(about 14 s) runs after an edit to a data file (tables.xml, the signal CSVs). After an edit
to a script it is replaced by the test files that name that script (matching_tests), each
well under a second; a script no test file names gets the whole unit-jmri job, and the hook
says so. The checks share a 20 s budget: a check it leaves too little time for, or one that runs
past it (unit-jmri under load), is not a failure; the hook says "not run in the edit hook (over
the 20 s budget; check.sh runs it)" on a line of its own, on stderr and in Claude's context. The slow parts of check.sh (portal build, the other unit suites) stay in
./tools/check.sh and CI. Edits made by Bash scripts (sed, a table generator) do not pass
through this hook and are not caught.

Every edited .py file of the checkout also gets pyflakes (ruff's F rules, ruff.toml) through
tools/audit/check_ruff.py, check.sh's ruff job, on that one file. Findings block like a failed
check; when ruff cannot run (not installed, another version than requirements.txt pins) the
hook says so on one line and does not block.
"""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import time

WATCHED = re.compile(
    r"(^|/)(jmri/layouts/hart/output/tables\.xml"
    r"|jmri/layouts/hart/data/schematic/(staging|main_upper)_masts\.csv"
    r"|jmri/layouts/hart/output/signal_head_plan\.csv"
    r"|jmri/scripts/(signal_coordinator|sml_[a-z_]+)\.py)$"  # the script and the sibling modules it loads
)
MANIFEST_PY = "tools/pipeline/manifest.py"
HOME = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the checkout holding this hook
# A unit-test job of tools/check.sh, so not a manifest step (ADR-037 point 4); test_guards checks check.sh has it.
UNIT_JMRI = "unit-jmri"
UNIT_JMRI_ARGV = ["python3", "-m", "unittest", "discover", "-b", "-q", "-s", "jmri/layouts/hart/scripts/tests"]
SIBLING = re.compile(r"(?<=jmri/scripts/)sml_[a-z_]+\.py$")
# Folders whose test files are searched for the edited script's name; each is a unit job in tools/check.sh.
TEST_DIRS = ["jmri/layouts/hart/scripts/tests", "jmri/scripts/tests", "cats/scripts/tests"]
RUFF_CHECK = "tools/audit/check_ruff.py"
BUDGET = 20.0
MIN_LEFT = 5.0
# A check the budget leaves no time for, or one that runs past it, is not run here: never a failure, never silent
OVER_BUDGET = "check_after_edit: {name}: not run in the edit hook (over the {budget:.0f} s budget; check.sh runs it)"


class MatchError(Exception):
    """The test files could not be searched, so the hook cannot tell which ones match."""


class ManifestLoadError(Exception):
    """The step manifest could not be read, so the hook cannot tell which checks to run."""


class NotMarked(ManifestLoadError):
    """The checkout has no manifest.py, or marks no step after_edit: a branch from before the marks."""


def manifest_checks(root, manifest_file=None):
    """(name, argv) of each step of root's checks.toml marked after_edit, in file order.

    Loads root's tools/pipeline/manifest.py by path (in sys.modules before it runs, for its dataclasses) and reads
    the file with its read(): TOML only, no git and no map, so the hook stays quick. The full check of every field
    is `manifest.py check`, which check.sh runs first. ManifestLoadError when it cannot load, a marked step has no
    usable name or command, or no step is marked: never a hook that quietly checks nothing.
    """
    script = os.path.join(root, MANIFEST_PY)
    name = "hart_after_edit_manifest"
    if not os.path.isfile(script):
        raise NotMarked(f"{root} has no {MANIFEST_PY}")
    here = os.path.realpath(os.path.dirname(script))
    for part in [k for k, m in sys.modules.items() if k.startswith("manifest_")   # parts of another checkout's
                 and os.path.dirname(os.path.realpath(getattr(m, "__file__", None) or here)) != here]:
        del sys.modules[part]   # manifest.py imports its parts by name: a fallback load must not get the first's
    try:
        spec = importlib.util.spec_from_file_location(name, script)
        if spec is None:
            raise ImportError(f"no loader for {script}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        data, shown = module.read(module.MANIFEST if manifest_file is None else pathlib.Path(manifest_file))
    except (Exception, SystemExit) as err:  # a broken manifest is a failure to see, not a reason to pass
        sys.modules.pop(name, None)
        raise ManifestLoadError(f"{MANIFEST_PY} did not load the step manifest: {err}") from err
    steps = data.get("step")
    if not isinstance(steps, list) or not all(isinstance(s, dict) for s in steps):
        raise ManifestLoadError(f"{shown}: no [[step]] tables")
    out = []
    for entry in steps:
        if entry.get("after_edit") is not True:
            continue
        step, cmd = entry.get("name"), entry.get("cmd")
        if not (isinstance(step, str) and step and isinstance(cmd, list) and cmd
                and all(isinstance(w, str) and w and w != "{python}" for w in cmd)):
            raise ManifestLoadError(f"{shown}: step {step!r} is marked after_edit but its name or cmd will not run "
                                    f"here (manifest.py check names the problem)")
        out.append((step, list(cmd)))
    if not out:
        raise NotMarked(f"{shown}: no step is marked after_edit")
    return out


def quick_checks(root):
    """The checks for an edit to a watched file: the manifest's after_edit steps, then the whole unit-jmri job.

    A worktree branched before the after_edit marks (NotMarked) takes them from the checkout that holds this hook,
    and says so; a manifest that is there but broken stops the hook."""
    try:
        checks = manifest_checks(root)
    except NotMarked as err:
        if os.path.realpath(HOME) == os.path.realpath(root):
            raise
        checks = manifest_checks(HOME)
        print(f"check_after_edit: {err}; ran the checks {HOME}'s manifest marks after_edit", file=sys.stderr)
    return checks + [(UNIT_JMRI, UNIT_JMRI_ARGV)]


def matching_tests(root, script):
    """The test files under TEST_DIRS that name the script's module, as paths relative to root.

    A test file matches when its text holds the module name (the file name without .py) as a
    whole word: an import, a path it loads, or a list of scripts it checks. No table to keep.
    """
    stem = os.path.splitext(os.path.basename(script))[0]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stem):
        raise MatchError(f"{os.path.basename(script)} is not a module name; cannot search the tests for it")
    word = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(stem) + r"(?![A-Za-z0-9_])")
    found, searched = [], 0
    for folder in TEST_DIRS:
        full = os.path.join(root, folder)
        if not os.path.isdir(full):
            continue
        for name in sorted(os.listdir(full)):
            if not (name.startswith("test") and name.endswith(".py")):
                continue
            searched += 1
            try:
                with open(os.path.join(full, name), encoding="utf-8") as handle:
                    text = handle.read()
            except (OSError, UnicodeDecodeError) as err:
                raise MatchError(f"cannot read {folder}/{name}: {err}") from err
            if word.search(text):
                found.append(f"{folder}/{name}")
    if not searched:
        raise MatchError(f"no test files under {', '.join(TEST_DIRS)} in {root}")
    return found


def checks_for(root, path):
    """(checks, note) for an edit to path: quick_checks, with unit-jmri narrowed when path is a script."""
    checks = quick_checks(root)
    if not path.endswith(".py"):
        return checks, ""
    # A module signal_coordinator.py loads is tested through the script: its tests name the script.
    tests = matching_tests(root, SIBLING.sub("signal_coordinator.py", path))
    name = os.path.basename(path)
    if not tests:
        return checks, f"no test file names {name}; ran the whole {UNIT_JMRI} job instead"
    # The edited script's own tests go first so the time budget never skips them.
    narrowed = []
    for test in tests:
        folder, file = os.path.split(test)
        narrowed.append((f"unit {test}", ["python3", "-m", "unittest", "discover", "-b", "-q", "-s", folder, "-p", file]))
    narrowed += [check for check in checks if check[0] != UNIT_JMRI]
    return narrowed, f"ran the {len(tests)} test file(s) that name {name}, not the whole {UNIT_JMRI} job: " + ", ".join(tests)


def ruff_problem(root, path):
    """pyflakes on the edited .py file: its findings as a failure text, or "" (clean, excluded by ruff.toml or ignored
    by git, as check.sh's whole-repo run leaves them, or a file outside root, which is not this checkout's). Paths are
    compared resolved, as git gives root: a file reached through a symlink (/tmp on macOS) is still the checkout's.
    When ruff cannot run, says why on stderr in one line and gives ""."""
    root, full = os.path.realpath(root), os.path.realpath(path)
    if os.path.commonpath([root, full]) != root:
        return ""
    script = os.path.join(root, RUFF_CHECK)
    if not os.path.isfile(script):
        print(f"check_after_edit: ruff not run on {os.path.basename(path)}: {root} has no {RUFF_CHECK}", file=sys.stderr)
        return ""
    try:
        spec = importlib.util.spec_from_file_location("hart_check_ruff", script)
        ruff = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ruff)
    except (Exception, SystemExit) as err:  # a broken check script is a failure to see, not a reason to pass
        return f"--- ruff FAILED\n{RUFF_CHECK} did not load: {err!r}"
    try:
        count, out = ruff.run(root, [full])
    except ruff.RuffSetupError as err:
        print(f"check_after_edit: ruff not run on {os.path.basename(path)}: {err}", file=sys.stderr)
        return ""
    except ruff.RuffError as err:
        return f"--- ruff FAILED\n{err}"
    return f"--- ruff FAILED ({count} pyflakes finding(s); ruff.toml says what is ignored)\n{out}" if count else ""


def toplevel(directory):
    try:
        done = subprocess.run(["git", "-C", directory, "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def main():
    data = json.load(sys.stdin)
    path = data.get("tool_input", {}).get("file_path", "")
    watched = WATCHED.search(path.replace(os.sep, "/"))
    if not (watched or path.endswith(".py")):
        return 0
    # Check the checkout that holds the edited file: agents often edit in a worktree,
    # and CLAUDE_PROJECT_DIR would test the main checkout instead.
    root = toplevel(os.path.dirname(os.path.abspath(path))) or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    failed = []
    if path.endswith(".py"):
        problem = ruff_problem(root, path)
        if problem:
            failed.append(problem)
    if not watched:
        if failed:
            print(f"Quick checks failed after editing {os.path.basename(path)}:\n" + "\n".join(failed), file=sys.stderr)
            return 2
        return 0
    env = dict(os.environ, JMRI_LAYOUT="hart")
    try:
        checks, note = checks_for(root, path)
    except (MatchError, ManifestLoadError) as err:
        print(f"Quick checks not run after editing {os.path.basename(path)}: {err}. Run ./tools/check.sh.",
              file=sys.stderr)
        if failed:
            print("\n".join(failed), file=sys.stderr)
        return 2
    if note:
        print(f"check_after_edit: {note}.", file=sys.stderr)
    started = time.monotonic()
    not_run = []    # over the budget: neither a pass nor a failure, and said so on a line of its own
    for name, argv in checks:
        left = BUDGET - (time.monotonic() - started)
        if left < MIN_LEFT:  # too little time to finish
            not_run.append(name)
            continue
        t0 = time.monotonic()
        try:
            done = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, timeout=left)
            ok, out = done.returncode == 0, done.stdout + done.stderr
        except subprocess.TimeoutExpired:   # a slow run under load, not a failing check
            not_run.append(name)
            continue
        except OSError as err:
            ok, out = False, str(err)
        if not ok:
            failed.append(f"--- {name} FAILED ({time.monotonic() - t0:.1f}s)\n{out.strip()[-2000:]}")
    over = [OVER_BUDGET.format(name=name, budget=BUDGET) for name in not_run]
    if failed:
        print(f"Quick checks failed after editing {os.path.basename(path)}:\n" + "\n".join(failed + over),
              file=sys.stderr)
        return 2
    if over:
        print("\n".join(over), file=sys.stderr)
        # exit 0 shows Claude no stderr: the lines go to its context as well, so the pass is never silent
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n".join(over)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
