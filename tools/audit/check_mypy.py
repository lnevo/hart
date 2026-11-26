#!/usr/bin/env python3
"""mypy over the repo's CPython code: hartlib with no errors, every other file held to a per-file baseline.

    python3 tools/audit/check_mypy.py            check; exit 1 when hartlib has errors or a file's count moved
    python3 tools/audit/check_mypy.py --update   rewrite the baseline with the current counts (refused on a rise)
    python3 tools/audit/check_mypy.py --list     print the files the check runs mypy on

mypy.ini holds the settings: strict options for hartlib, basic mode for the rest. The files checked are every
tracked .py file except those ruff.toml's extend-exclude lists, the Jython scripts ruff.toml gives an F821 ignore,
any file that imports jmri, java or javax, and the paths mypy.ini's `exclude` matches. ruff.toml stays the one list
of code no linter checks; mypy.ini's `exclude` adds the Jython that ruff can still lint but mypy cannot type.

mypy is pinned in requirements.txt and runs from the main checkout's .venv (`python -m mypy`), else from the
python3 running this script. Files are checked in batches with no two files of one name in a batch: scripts are not
packages, so mypy would call two `main_guard.py` files the same module.

Exit 0 when clean, 1 with findings, 2 when mypy cannot run (missing, another version, no pin, a mypy crash).
"""
from __future__ import annotations

import argparse
import configparser
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import files, paths  # noqa: E402

ROOT = paths.REPO_ROOT
CONFIG = "mypy.ini"
RUFF_CONFIG = "ruff.toml"
REQUIREMENTS = "requirements.txt"
BASELINE = "tools/audit/mypy_baseline.json"
STRICT_PREFIX = "tools/hartlib/src/"
PIN = re.compile(r"mypy==(\S+)")
VERSION = re.compile(r"mypy (\S+)")
ERROR = re.compile(r"(?P<path>[^:\n]+\.py):\d+(?::\d+)?: error: ")
JYTHON_IMPORT = re.compile(r"^\s*(?:import|from)\s+(?:jmri|java|javax)\b", re.M)
TIMEOUT = 600


class MypySetupError(Exception):
    """mypy cannot run as pinned or configured: no pin, not installed, another version, a bad config file."""


class MypyError(Exception):
    """mypy ran and stopped with an error of its own (exit 2, or output this check cannot read)."""


class BaselineError(Exception):
    """The baseline file cannot be read, or holds something other than {path: positive count}."""


@dataclass(frozen=True)
class Verdict:
    """The comparison of one run with the baseline."""
    strict: dict[str, int]       # hartlib files with errors (must be empty)
    rose: dict[str, tuple[int, int]]   # path -> (baseline, now), now above baseline; a new file has baseline 0
    fell: dict[str, tuple[int, int]]   # path -> (baseline, now), now below baseline (0 when the file is clean or gone)

    @property
    def ok(self) -> bool:
        return not self.strict and not self.rose


def pinned_version(root: Path) -> str:
    """The mypy version root's requirements.txt pins (its one `mypy==X` line)."""
    req = root / REQUIREMENTS
    try:
        lines = req.read_text(encoding="utf-8").splitlines()
    except OSError as err:
        raise MypySetupError(f"cannot read {req}: {err}") from err
    pins = [m.group(1) for line in lines if (m := PIN.fullmatch(line.split("#", 1)[0].strip()))]
    if len(pins) != 1:
        raise MypySetupError(f"{req} pins mypy {len(pins)} times (mypy==X), not once")
    return pins[0]


def interpreters(root: Path) -> list[Path]:
    """Where mypy is looked for, in order: the main checkout's .venv python, then the python running this check."""
    return [paths.main_checkout(root) / ".venv" / "bin" / "python", Path(sys.executable)]


def find_mypy(pin: str, places: Sequence[Path]) -> Path:
    """The first python of places whose `-m mypy` is version pin; MypySetupError naming what was found otherwise."""
    seen = []
    for python in places:
        if not python.is_file():
            continue
        try:
            done = subprocess.run([str(python), "-m", "mypy", "--version"], capture_output=True, text=True,
                                  timeout=60)
        except (OSError, subprocess.SubprocessError) as err:
            seen.append(f"{python} -m mypy could not run: {err}")
            continue
        m = VERSION.match(done.stdout.strip())
        if done.returncode != 0 or not m:
            seen.append(f"{python} has no mypy ({(done.stdout + done.stderr).strip()[:120]!r})")
        elif m.group(1) == pin:
            return python
        else:
            seen.append(f"{python} has mypy {m.group(1)}")
    where = "; ".join(seen) or "no python at " + " or ".join(str(p) for p in places)
    raise MypySetupError(f"mypy {pin} (requirements.txt) not found: {where}. "
                         f"Install it with: {places[0]} -m pip install mypy=={pin}")


def ruff_skips(root: Path) -> tuple[list[str], list[str]]:
    """ruff.toml's extend-exclude entries and the files its per-file-ignores give F821 (the Jython scripts)."""
    try:
        data = tomllib.loads((root / RUFF_CONFIG).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise MypySetupError(f"cannot read {root / RUFF_CONFIG}: {err}") from err
    excludes = data.get("extend-exclude", [])
    ignores = data.get("lint", {}).get("per-file-ignores", {})
    if not isinstance(excludes, list) or not isinstance(ignores, dict):
        raise MypySetupError(f"{root / RUFF_CONFIG}: extend-exclude must be a list, per-file-ignores a table")
    return [str(e).rstrip("/") for e in excludes], [str(k) for k, v in ignores.items() if "F821" in v]


def mypy_exclude(root: Path) -> re.Pattern[str] | None:
    """mypy.ini's [mypy] exclude pattern, compiled; None when it sets none."""
    cfg = configparser.ConfigParser()
    try:
        with open(root / CONFIG, encoding="utf-8") as fh:
            cfg.read_file(fh)
    except (OSError, configparser.Error) as err:
        raise MypySetupError(f"cannot read {root / CONFIG}: {err}") from err
    if not cfg.has_section("mypy"):
        raise MypySetupError(f"{root / CONFIG} has no [mypy] section")
    text = cfg.get("mypy", "exclude", fallback="").strip()
    try:
        return re.compile(text) if text else None
    except re.error as err:
        raise MypySetupError(f"{root / CONFIG}: exclude is not a regular expression: {err}") from err


def under(path: str, prefixes: Iterable[str]) -> bool:
    """True when path is one of prefixes or inside one of them."""
    parts = PurePosixPath(path).parts
    return any(parts[:len(PurePosixPath(p).parts)] == PurePosixPath(p).parts for p in prefixes)


def is_jython(text: str) -> bool:
    """True for source that imports jmri, java or javax: it runs inside JMRI."""
    return bool(JYTHON_IMPORT.search(text))


def checked_files(root: Path) -> list[str]:
    """The tracked .py files mypy checks, relative to root, in git's order."""
    excludes, jython = ruff_skips(root)
    pattern = mypy_exclude(root)
    out = []
    for rel in files.tracked_files(root, "*.py", submodules=False):
        if under(rel, excludes) or rel in jython or (pattern and pattern.search(rel)):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError as err:
            raise MypySetupError(f"cannot read {root / rel}: {err}") from err
        if not is_jython(text):
            out.append(rel)
    return out


def batches(names: Sequence[str]) -> list[list[str]]:
    """names split so no batch holds two files of one name; each file goes in the first batch without its name."""
    out: list[list[str]] = []
    seen: list[set[str]] = []
    for name in names:
        base = PurePosixPath(name).name
        for batch, bases in zip(out, seen):
            if base not in bases:
                batch.append(name)
                bases.add(base)
                break
        else:
            out.append([name])
            seen.append({base})
    return out


def count_errors(output: str) -> dict[str, int]:
    """Error lines per file in mypy's output (notes are not errors)."""
    counts: dict[str, int] = {}
    for line in output.splitlines():
        m = ERROR.match(line)
        if m:
            counts[m["path"]] = counts.get(m["path"], 0) + 1
    return counts


def run_batch(python: Path, root: Path, batch: Sequence[str]) -> dict[str, int]:
    """Error counts for one batch; MypyError when mypy stops on its own error or reports what it cannot parse."""
    argv = [str(python), "-m", "mypy", "--config-file", str(root / CONFIG), "--no-error-summary",
            "--cache-dir", str(paths.cache_dir("mypy", root)), *batch]
    try:
        done = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as err:
        raise MypyError(f"mypy could not run: {err}") from err
    out = (done.stdout + done.stderr).strip()
    if done.returncode not in (0, 1):
        raise MypyError(f"mypy stopped with exit {done.returncode}:\n{out[-4000:]}")
    counts = count_errors(done.stdout)
    if done.returncode == 1 and not counts:
        raise MypyError(f"mypy exited 1 but printed no error this check can read:\n{out[-4000:]}")
    return counts


def run(root: Path) -> dict[str, int]:
    """Error counts per file over every checked file."""
    python = find_mypy(pinned_version(root), interpreters(root))
    counts: dict[str, int] = {}
    for batch in batches(checked_files(root)):
        counts.update(run_batch(python, root, batch))
    return counts


def read_baseline(path: Path) -> dict[str, int]:
    """The committed {path: error count}; an absent file is an empty baseline."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise BaselineError(f"cannot read {path}: {err}") from err
    if not isinstance(data, dict) or not all(
            isinstance(k, str) and type(v) is int and v > 0 for k, v in data.items()):
        raise BaselineError(f"{path} must map each path to a positive error count")
    return data


def compare(now: Mapping[str, int], base: Mapping[str, int]) -> Verdict:
    """now against base: hartlib errors, counts that rose (new files included) and counts that fell."""
    strict = {p: n for p, n in now.items() if p.startswith(STRICT_PREFIX)}
    rest = {p: n for p, n in now.items() if p not in strict}
    rose = {p: (base.get(p, 0), n) for p, n in rest.items() if n > base.get(p, 0)}
    fell = {p: (b, rest.get(p, 0)) for p, b in base.items() if rest.get(p, 0) < b}
    return Verdict(strict, rose, fell)


def write_baseline(path: Path, now: Mapping[str, int]) -> None:
    """Write the non-hartlib counts, sorted, one file per line."""
    keep = {p: now[p] for p in sorted(now) if not p.startswith(STRICT_PREFIX)}
    files.write_atomic(path, json.dumps(keep, indent=1) + "\n")


def report(verdict: Verdict) -> list[str]:
    """The lines that explain a verdict."""
    lines = [f"  hartlib: {p}: {n} error(s); hartlib must have none" for p, n in sorted(verdict.strict.items())]
    lines += [f"  rose: {p}: {b} -> {n}" for p, (b, n) in sorted(verdict.rose.items())]
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true", help="rewrite the baseline; refused when a count rose")
    mode.add_argument("--list", action="store_true", help="print the files checked and stop")
    args = ap.parse_args(argv)
    baseline = ROOT / BASELINE
    try:
        if args.list:
            print("\n".join(checked_files(ROOT)))
            return 0
        base = read_baseline(baseline)
        now = run(ROOT)
    except (MypySetupError, MypyError, BaselineError, files.GitError) as err:
        print(f"check_mypy: {err}", file=sys.stderr)
        return 2
    verdict = compare(now, base)
    if not verdict.ok:
        print("\n".join(report(verdict)))
        what = "--update refused" if args.update else "fix them (mypy.ini has the settings)"
        print(f"check_mypy: {len(verdict.strict)} hartlib file(s) with errors, {len(verdict.rose)} file(s) above "
              f"{BASELINE}; {what}")
        return 1
    if args.update:
        write_baseline(baseline, now)
        print(f"check_mypy: wrote {BASELINE} ({sum(1 for p in now if not p.startswith(STRICT_PREFIX))} files)")
        return 0
    if verdict.fell:
        # a lower count is locked in by --update, so the file cannot climb back up to its old count unseen
        print("\n".join(f"  fell: {p}: {b} -> {n}" for p, (b, n) in sorted(verdict.fell.items())))
        print(f"check_mypy: {len(verdict.fell)} file(s) below {BASELINE}: run --update to lock the lower counts in")
        return 1
    print("check_mypy: hartlib clean, every file at its baseline count")
    return 0


if __name__ == "__main__":
    sys.exit(main())
