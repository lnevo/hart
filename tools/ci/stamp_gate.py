#!/usr/bin/env python3
"""Decide whether a pull request's CI run may skip the check.sh jobs main's last full pass already covered.

    stamp_gate.py manifest DIR --sha SHA      main's push run, after check.sh passed with CHECK_RECORD_TO=DIR: write
                                              DIR/manifest.json (the commit and the runner the stamps were made on)
    stamp_gate.py decide DIR --base SHA [--pin-changed true|false] [--labels L1,L2] [--message-file F] < changed paths
                                              a pull request run: print "skip" or "full: <reason>"; exit 0 for skip
                                              (run check.sh with CHECK_SKIP_FROM=DIR), 3 for full

.github/workflows/check.yml restores main's stamps by the pull request's merge base (the merge commit's first parent)
from actions/cache, then asks `decide`. A skip means: a job whose stamp matches has inputs byte-identical to the ones
it passed with on that main commit (tools/audit/check_stamps.py: its traced read set, check.sh and the hook, the
interpreter, the plugin and the environment). Any doubt is a full run, with the reason in the log:

- the full-ci label on the pull request, or [full-ci] in one of its commit messages;
- the plugin pin differs from the base's;
- the change touches the machinery that makes or reads the stamps, or the workflow itself (MACHINERY);
- no manifest, an unreadable one, or one for another commit than the merge base, another runner image, OS,
  architecture, Python, git or bash (runner());
- no stamp files next to the manifest.

Stamps are only ever compared on the GitHub runner they were made on: check.sh refuses CHECK_SKIP_FROM off CI.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

MANIFEST = "manifest.json"
VERSION = 1
LABEL = "full-ci"
TOKEN = "[full-ci]"
# Changed paths that force a full run: the workflow, check.sh, this gate and the stamp code (a change to how stamps
# are made or compared must be proven by a full run, not judged by the stamps it changes).
MACHINERY = (
    ".github/workflows/check.yml",
    "tools/check.sh",
    "tools/ci/",
    "tools/audit/check_stamps.py",
    "tools/audit/traced.py",
    "tools/audit/trace_hook/",
    "tools/schematic/panel_stamps.py",
    "tools/hosts/profile_tables_guard.sh",
    "tools/hartlib/src/hartlib/paths.py",     # check_stamps: the stamp folder and main_checkout (what counts as traced)
    "tools/audit/stamp_audit/",
)
SHA = re.compile(r"[0-9a-f]{40}")


def _version(*cmd: str) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return f"unavailable: {e}"
    return (done.stdout.splitlines() or [f"failed:{done.returncode}"])[0]


def runner() -> dict[str, str]:
    """The runner the stamps are tied to: GitHub's image (not its build number: runners of one image differ in it
    from hour to hour), the OS, the architecture, the Python, and the git and bash the untraced jobs run."""
    return {
        "image_os": os.environ.get("ImageOS", ""),
        "runner_os": os.environ.get("RUNNER_OS", ""),
        "arch": platform.machine(),
        "python": sys.version,
        "executable": os.path.realpath(sys.executable),
        "git": _version("git", "--version"),
        "bash": _version("bash", "--version"),
    }


def write_manifest(folder: Path, sha: str) -> Path:
    if not SHA.fullmatch(sha):
        raise SystemExit(f"not a commit sha: {sha!r}")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "filehash.json").unlink(missing_ok=True)      # mtimes of this checkout: never trusted by another
    stamps = sorted(p.name for p in folder.glob("*.json") if p.name != MANIFEST)
    path = folder / MANIFEST
    path.write_text(json.dumps({"version": VERSION, "sha": sha, "runner": runner(), "stamps": len(stamps)},
                               indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def machinery(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        p = p.strip().removeprefix("./")
        if p and any(p == m or (m.endswith("/") and p.startswith(m)) for m in MACHINERY):
            out.append(p)
    return out


def decide(folder: Path, base: str, changed: list[str], pin_changed: bool = False, labels: list[str] | None = None,
           message: str = "", now: dict[str, str] | None = None) -> str | None:
    """None when the run may skip with `folder`'s stamps, else why it must run everything."""
    labels = [label.strip() for label in (labels or []) if label.strip()]
    changed = [p for p in changed if p.strip()]
    if LABEL in labels:
        return f"the pull request has the {LABEL} label"
    if TOKEN in message:
        return f"a commit message of the pull request has {TOKEN}"
    if pin_changed:
        return "the plugin pin differs from the base's"
    touched = machinery(changed)
    if touched:
        return f"the change touches the CI or stamp machinery ({', '.join(touched[:3])})"
    if not changed:
        return "no changed paths were given"
    if not SHA.fullmatch(base or ""):
        return f"no merge base commit ({base!r})"
    path = folder / MANIFEST
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"no stamps from main {base[:12]} (its push run is not done, failed, or the cache expired)"
    except (OSError, ValueError) as e:
        return f"the stamps' manifest cannot be read: {e}"
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return "the stamps' manifest is of another version"
    if data.get("sha") != base:
        return f"the stamps were made on main {str(data.get('sha'))[:12]}, not on the merge base {base[:12]}"
    now = runner() if now is None else now
    made = data.get("runner")
    if not isinstance(made, dict):
        return "the stamps' manifest names no runner"
    for k in sorted(set(now) | set(made)):
        if made.get(k) != now.get(k):
            return f"the stamps were made on another runner ({k}: {made.get(k)!r}, now {now.get(k)!r})"
    if not any(p.name != MANIFEST and p.name != "filehash.json" for p in folder.glob("*.json")):
        return "the stamps folder holds no stamps"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("dir", type=Path)
    m.add_argument("--sha", required=True)
    d = sub.add_parser("decide")
    d.add_argument("dir", type=Path)
    d.add_argument("--base", required=True)
    d.add_argument("--pin-changed", default="false", choices=("true", "false"))
    d.add_argument("--labels", default="")
    d.add_argument("--message-file", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "manifest":
        path = write_manifest(a.dir, a.sha)
        print(f"wrote {path}: {json.loads(path.read_text())['stamps']} stamps for {a.sha[:12]}")
        return 0
    try:
        message = a.message_file.read_text(encoding="utf-8", errors="replace") if a.message_file else ""
    except OSError as e:
        print(f"full: the commit messages cannot be read: {e}")
        return 3
    reason = decide(a.dir, a.base, sys.stdin.read().splitlines(), a.pin_changed == "true", a.labels.split(","), message)
    print("skip" if reason is None else f"full: {reason}")
    return 0 if reason is None else 3


if __name__ == "__main__":
    sys.exit(main())
