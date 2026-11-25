#!/usr/bin/env python3
"""After an edit to the tables or the signal files, run the quick checks from tools/check.sh.

PostToolUse hook for Edit, Write and MultiEdit. A failing check exits 2 with its output on
stderr, which Claude sees. The table checks take about a second together. The unit-jmri job
(about 14 s) runs after an edit to a data file (tables.xml, the signal CSVs). After an edit
to a script it is replaced by the test files that name that script (matching_tests), each
well under a second; a script no test file names gets the whole unit-jmri job, and the hook
says so. The slow parts of check.sh (portal build, the other unit suites) stay in
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
CHECKS = [  # (name, argv) as in tools/check.sh; test_guards checks each one is still there
    ("phase02", ["python3", "jmri/scripts/check_hart_phase02.py"]),
    ("tables-browser", ["python3", "www/scripts/build_tables_browser.py", "--check"]),
    ("track-lengths", ["python3", "jmri/layouts/hart/scripts/export_track_lengths.py", "--check"]),
    ("panel-contracts", ["python3", "jmri/layouts/hart/scripts/audit_panel_contracts.py", "--strict"]),
    ("sml-invariants", ["python3", "tools/audit/check_sml_invariants.py"]),
    ("mqtt-static", ["python3", "tools/audit/check_mqtt_no_static_lists.py"]),
    ("wiring-crosswalk", ["python3", "tools/audit/check_wiring_crosswalk.py"]),
    ("unit-jmri", ["python3", "-m", "unittest", "discover", "-b", "-q", "-s", "jmri/layouts/hart/scripts/tests"]),
]
UNIT_JMRI = "unit-jmri"
SIBLING = re.compile(r"(?<=jmri/scripts/)sml_[a-z_]+\.py$")
# Folders whose test files are searched for the edited script's name; each is a unit job in tools/check.sh.
TEST_DIRS = ["jmri/layouts/hart/scripts/tests", "jmri/scripts/tests", "cats/scripts/tests"]
RUFF_CHECK = "tools/audit/check_ruff.py"
BUDGET = 20.0
MIN_LEFT = 5.0


class MatchError(Exception):
    """The test files could not be searched, so the hook cannot tell which ones match."""


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
    """(checks, note) for an edit to path: CHECKS, with unit-jmri narrowed when path is a script."""
    if not path.endswith(".py"):
        return CHECKS, ""
    # A module signal_coordinator.py loads is tested through the script: its tests name the script.
    tests = matching_tests(root, SIBLING.sub("signal_coordinator.py", path))
    name = os.path.basename(path)
    if not tests:
        return CHECKS, f"no test file names {name}; ran the whole {UNIT_JMRI} job instead"
    # The edited script's own tests go first so the time budget never skips them.
    narrowed = []
    for test in tests:
        folder, file = os.path.split(test)
        narrowed.append((f"unit {test}", ["python3", "-m", "unittest", "discover", "-b", "-q", "-s", folder, "-p", file]))
    narrowed += [check for check in CHECKS if check[0] != UNIT_JMRI]
    return narrowed, f"ran the {len(tests)} test file(s) that name {name}, not the whole {UNIT_JMRI} job: " + ", ".join(tests)


def ruff_problem(root, path):
    """pyflakes on the edited .py file: its findings as a failure text, or "" (clean, excluded by ruff.toml, or a file
    outside root, which is not this checkout's). When ruff cannot run, says why on stderr in one line and gives ""."""
    root, full = os.path.abspath(root), os.path.abspath(path)
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
    except MatchError as err:
        print(f"Quick checks not run after editing {os.path.basename(path)}: {err}. Run ./tools/check.sh.",
              file=sys.stderr)
        if failed:
            print("\n".join(failed), file=sys.stderr)
        return 2
    if note:
        print(f"check_after_edit: {note}.", file=sys.stderr)
    started = time.monotonic()
    for name, argv in checks:
        left = BUDGET - (time.monotonic() - started)
        if left < MIN_LEFT:  # too little time to finish; a timeout here would look like a failure
            print(f"check budget of {BUDGET:.0f}s used; skipped {name} and later. Run ./tools/check.sh.", file=sys.stderr)
            break
        t0 = time.monotonic()
        try:
            done = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, timeout=left)
            ok, out = done.returncode == 0, done.stdout + done.stderr
        except subprocess.TimeoutExpired:
            ok, out = False, "timed out"
        except OSError as err:
            ok, out = False, str(err)
        if not ok:
            failed.append(f"--- {name} FAILED ({time.monotonic() - t0:.1f}s)\n{out.strip()[-2000:]}")
    if failed:
        print(f"Quick checks failed after editing {os.path.basename(path)}:\n" + "\n".join(failed), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
