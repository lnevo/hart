#!/usr/bin/env python3
"""After an edit to the tables or the signal files, run the quick checks from tools/check.sh.

PostToolUse hook for Edit, Write and MultiEdit. A failing check exits 2 with its output on
stderr, which Claude sees. The slow parts of check.sh (portal build, the other unit suites)
stay in ./tools/check.sh; these eight take about a second together. Edits made by Bash
scripts (sed, a table generator) do not pass through this hook and are not caught.
"""
import json
import os
import re
import subprocess
import sys
import time

WATCHED = re.compile(
    r"(^|/)(jmri/layouts/hart/output/tables\.xml"
    r"|jmri/layouts/hart/data/le_signal_boundaries\.csv"
    r"|docs/wiring/signals/signal_[a-z_]+\.csv"
    r"|jmri/scripts/signal_coordinator\.py)$"
)
CHECKS = [  # (name, argv) as in tools/check.sh; test_guards checks each one is still there
    ("phase02", ["python3", "jmri/scripts/check_hart_phase02.py"]),
    ("tables-browser", ["python3", "www/scripts/build_tables_browser.py", "--check"]),
    ("track-lengths", ["python3", "jmri/layouts/hart/scripts/export_track_lengths.py", "--check"]),
    ("panel-contracts", ["python3", "jmri/layouts/hart/scripts/audit_panel_contracts.py", "--strict"]),
    ("sml-invariants", ["python3", "tools/audit/check_sml_invariants.py"]),
    ("mqtt-static", ["python3", "tools/audit/check_mqtt_no_static_lists.py"]),
    ("wiring-crosswalk", ["python3", "tools/audit/check_wiring_crosswalk.py"]),
    ("unit-jmri", ["python3", "-m", "unittest", "discover", "-q", "-s", "jmri/layouts/hart/scripts/tests"]),
]
BUDGET = 20.0
MIN_LEFT = 5.0


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
    if not WATCHED.search(path.replace(os.sep, "/")):
        return 0
    # Check the checkout that holds the edited file: agents often edit in a worktree,
    # and CLAUDE_PROJECT_DIR would test the main checkout instead.
    root = toplevel(os.path.dirname(os.path.abspath(path))) or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    env = dict(os.environ, JMRI_LAYOUT="hart")
    started, failed = time.monotonic(), []
    for name, argv in CHECKS:
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
