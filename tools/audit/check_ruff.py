#!/usr/bin/env python3
"""Pyflakes over the repo's Python: ruff's F rules (undefined and unused names, unused imports), as ruff.toml sets.

    python3 tools/audit/check_ruff.py            every .py file ruff.toml does not exclude
    python3 tools/audit/check_ruff.py FILE...    those files (.claude/hooks/check_after_edit.py names the edited one)

ruff.toml holds the rules, the excluded folders and the per-file ignores (the Jython scripts, files other branches
are changing). Ruff is pinned in requirements.txt. The check runs the pinned version from the main checkout's .venv
(where `pip install -r requirements.txt` puts it), else from PATH (CI installs the pin there), and fails when neither
holds that version: another version may report other findings.

Exit 0 when clean, 1 with findings, 2 when ruff cannot run (missing, another version, no pin, a ruff error).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

ROOT = paths.REPO_ROOT
CONFIG = "ruff.toml"
REQUIREMENTS = "requirements.txt"
PIN = re.compile(r"ruff==(\S+)")
VERSION = re.compile(r"ruff (\S+)")
TIMEOUT = 120       # a whole-repo run takes about a second


class RuffSetupError(Exception):
    """Ruff cannot run as pinned: no pin, not installed, another version, or it could not be started."""


class RuffError(Exception):
    """Ruff ran and stopped with an error of its own (exit 2: a bad config, an unreadable file)."""


def pinned_version(root: Path) -> str:
    """The ruff version root's requirements.txt pins (its one `ruff==X` line)."""
    req = root / REQUIREMENTS
    try:
        lines = req.read_text(encoding="utf-8").splitlines()
    except OSError as err:
        raise RuffSetupError(f"cannot read {req}: {err}") from err
    pins = [m.group(1) for line in lines if (m := PIN.fullmatch(line.split("#", 1)[0].strip()))]
    if len(pins) != 1:
        raise RuffSetupError(f"{req} pins ruff {len(pins)} times (ruff==X), not once")
    return pins[0]


def candidates(root: Path) -> list[Path]:
    """Where ruff is looked for, in order: the main checkout's .venv (a worktree has none of its own), then PATH."""
    found = [paths.main_checkout(root) / ".venv" / "bin" / "ruff"]
    on_path = shutil.which("ruff")
    if on_path:
        found.append(Path(on_path))
    return found


def version_of(binary: Path) -> str:
    """`ruff --version`'s version of binary."""
    try:
        done = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as err:
        raise RuffSetupError(f"{binary} --version could not run: {err}") from err
    m = VERSION.match(done.stdout.strip())
    if done.returncode != 0 or not m:
        raise RuffSetupError(f"{binary} --version answered {done.returncode}: {(done.stdout + done.stderr).strip()!r}")
    return m.group(1)


def find_ruff(pin: str, places: list[Path]) -> Path:
    """The first of places that exists and is ruff `pin`; RuffSetupError naming what was found otherwise."""
    seen = []
    for binary in places:
        if not binary.is_file():
            continue
        got = version_of(binary)
        if got == pin:
            return binary
        seen.append(f"{binary} is {got}")
    where = "; ".join(seen) if seen else "not installed at " + " or ".join(str(p) for p in places) + " or on PATH"
    raise RuffSetupError(f"ruff {pin} (requirements.txt) not found: {where}. "
                         f"Install it with: {places[0].parent / 'pip'} install ruff=={pin}")


def run(root: Path, files: list[str] | None = None) -> tuple[int, str]:
    """(finding count, ruff's output) for files, or the whole of root when files is None. Each file must exist."""
    root = Path(os.path.abspath(root))
    config = root / CONFIG
    if not config.is_file():
        raise RuffSetupError(f"no {CONFIG} in {root}")
    targets = [str(root)] if files is None else [os.path.abspath(f) for f in files]
    if not targets:
        raise ValueError("run() was given an empty file list: pass None for the whole repo")
    missing = [t for t in targets if not os.path.isfile(t) and not os.path.isdir(t)]
    if missing:
        raise RuffSetupError("no such file: " + ", ".join(missing))
    ruff = find_ruff(pinned_version(root), candidates(root))
    argv = [str(ruff), "check", "--config", str(config), "--no-cache", "--output-format", "concise", *targets]
    try:
        done = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as err:
        raise RuffSetupError(f"{ruff} could not run: {err}") from err
    out = (done.stdout + done.stderr).strip()
    if done.returncode == 0:
        return 0, out
    if done.returncode != 1:
        raise RuffError(f"ruff stopped with exit {done.returncode}:\n{out}")
    count = sum(1 for line in done.stdout.splitlines() if re.match(r".+:\d+:\d+: ", line))
    if count == 0:      # exit 1 says it found something: output we cannot read is not a pass
        raise RuffError(f"ruff exited 1 but printed no finding this check can read:\n{out}")
    return count, out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", help="files to check (default: the whole repo)")
    args = ap.parse_args(argv)
    try:
        count, out = run(ROOT, args.files or None)
    except (RuffSetupError, RuffError) as err:
        print(f"check_ruff: {err}", file=sys.stderr)
        return 2
    if count:
        print(out)
        print(f"check_ruff: {count} pyflakes finding(s). Fix them; ruff.toml says what is ignored and why.")
        return 1
    print("check_ruff: no pyflakes findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
