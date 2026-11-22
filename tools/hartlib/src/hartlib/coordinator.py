"""The files that make up signal_coordinator.py: the script and the sibling modules it loads.

The script names its siblings in its SIBLING_MODULES tuple and loads them in that order from
the jython folder it is installed in. That tuple is the one list: the checks that read the
script's source (tools/audit/check_mqtt_no_static_lists.py, cats/scripts/tests) and the test
that every deploy list ships each module (tools/hosts/tests/test_coordinator_shipping.py) read it
here. The script is Jython and imports jmri, so the tuple is read from its source text.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from . import paths

SCRIPT = paths.REPO_ROOT / "jmri/scripts/signal_coordinator.py"
_TUPLE = re.compile(r"^SIBLING_MODULES = (\(.*?^\))$", re.M | re.S)
_MODULE = re.compile(r"[a-z_][a-z0-9_]*")


class CoordinatorError(ValueError):
    """The script's SIBLING_MODULES is missing or malformed, or names a module that is not beside it."""


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(paths.REPO_ROOT))
    except ValueError:
        return str(path)


def sibling_modules(script: Path = SCRIPT) -> tuple[str, ...]:
    """The script's SIBLING_MODULES, in load order. Each must be a module name with a .py beside the script."""
    try:
        text = script.read_text(encoding="utf-8")
    except OSError as exc:
        raise CoordinatorError(f"cannot read {_rel(script)}: {exc.strerror or exc}") from None
    found = _TUPLE.findall(text)
    if len(found) != 1:
        raise CoordinatorError(f"{_rel(script)}: expected one SIBLING_MODULES = ( ... ) tuple, found {len(found)}")
    try:
        names = ast.literal_eval(found[0])
    except (ValueError, SyntaxError) as exc:
        raise CoordinatorError(f"{_rel(script)}: SIBLING_MODULES is not a literal tuple ({exc})") from None
    if not isinstance(names, tuple) or not names:
        raise CoordinatorError(f"{_rel(script)}: SIBLING_MODULES must be a non-empty tuple of module names")
    bad = [n for n in names if not isinstance(n, str) or not _MODULE.fullmatch(n)]
    if bad:
        raise CoordinatorError(f"{_rel(script)}: SIBLING_MODULES has entries that are not module names: {bad}")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise CoordinatorError(f"{_rel(script)}: SIBLING_MODULES lists {dupes} more than once")
    missing = [n for n in names if not (script.parent / f"{n}.py").is_file()]
    if missing:
        raise CoordinatorError(f"{_rel(script)}: SIBLING_MODULES names modules with no .py beside it: {missing}")
    return names


def files(script: Path = SCRIPT) -> list[Path]:
    """The script, then each sibling module's file in load order."""
    return [script] + [script.parent / f"{n}.py" for n in sibling_modules(script)]


def source(script: Path = SCRIPT) -> str:
    """The text of every file in `files`, joined in that order (for checks that read the code as text)."""
    return "\n".join(p.read_text(encoding="utf-8") for p in files(script))
