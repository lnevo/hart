"""The files that make up signal_coordinator.py and panel_status.py: each script and the parts it loads.

signal_coordinator.py names its sibling modules in its SIBLING_MODULES tuple and panel_status.py names its
parts in its PARTS tuple; each imports them, in that order, as modules from the jython folder it is installed in,
through the shared loader jmri/scripts/jython_siblings.py. Each tuple is the one list for its script: the checks
that read the scripts' source (tools/audit/check_mqtt_no_static_lists.py, cats/scripts/tests) and the test that
every deploy list ships each part (tools/hosts/tests/test_coordinator_shipping.py) read it here. The scripts are
Jython and import jmri, so each tuple is read from the script's source text.

One sibling module, sml_lcos.py (LCOS_RULE), imports nothing but re: lcos_rule loads it in CPython, so the Layout
Editor build tests names with the same code signal_coordinator.py enrols LCOS heads by.
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from . import paths
from .errors import HartlibError

SCRIPT = paths.REPO_ROOT / "jmri/scripts/signal_coordinator.py"
PANEL_STATUS = paths.REPO_ROOT / "jmri/layouts/hart/scripts/panel_status.py"
# The tuple each script lists its parts in, by the script's file name.
TUPLE_NAMES = {SCRIPT.name: "SIBLING_MODULES", PANEL_STATUS.name: "PARTS"}
_MODULE = re.compile(r"[a-z_][a-z0-9_]*")
# signal_coordinator.py's LCOS head rule, the one sibling module CPython can import, and the name lcos_rule
# registers it under in sys.modules (not its own: the script tests import the staged copy as sml_lcos).
LCOS_RULE = SCRIPT.parent / "sml_lcos.py"
_LCOS_MODULE = "hartlib_coordinator_sml_lcos"


class CoordinatorError(HartlibError, ValueError):
    """A script's parts tuple is missing or malformed or names a part with no .py beside it, or the script is not
    one of TUPLE_NAMES."""


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(paths.REPO_ROOT))
    except ValueError:
        return str(path)


def tuple_name(script: Path) -> str:
    """The name of the tuple `script` lists its parts in: SIBLING_MODULES or PARTS."""
    try:
        return TUPLE_NAMES[script.name]
    except KeyError as exc:
        raise CoordinatorError(f"{_rel(script)}: not a script with parts (known: {sorted(TUPLE_NAMES)})") from exc


def sibling_modules(script: Path = SCRIPT) -> tuple[str, ...]:
    """The script's parts (its SIBLING_MODULES or PARTS), in load order. Each must be a module name with a .py
    beside the script."""
    name = tuple_name(script)
    try:
        text = script.read_text(encoding="utf-8")
    except OSError as exc:
        raise CoordinatorError(f"cannot read {_rel(script)}: {exc.strerror or exc}") from exc
    found = re.findall(r"^" + name + r" = (\(.*?^\))$", text, re.M | re.S)
    if len(found) != 1:
        raise CoordinatorError(f"{_rel(script)}: expected one {name} = ( ... ) tuple, found {len(found)}")
    try:
        names = ast.literal_eval(found[0])
    except (ValueError, SyntaxError) as exc:
        raise CoordinatorError(f"{_rel(script)}: {name} is not a literal tuple ({exc})") from exc
    if not isinstance(names, tuple) or not names:
        raise CoordinatorError(f"{_rel(script)}: {name} must be a non-empty tuple of module names")
    bad = [n for n in names if not isinstance(n, str) or not _MODULE.fullmatch(n)]
    if bad:
        raise CoordinatorError(f"{_rel(script)}: {name} has entries that are not module names: {bad}")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise CoordinatorError(f"{_rel(script)}: {name} lists {dupes} more than once")
    missing = [n for n in names if not (script.parent / f"{n}.py").is_file()]
    if missing:
        raise CoordinatorError(f"{_rel(script)}: {name} names modules with no .py beside it: {missing}")
    return names


def panel_status_parts() -> tuple[str, ...]:
    """panel_status.py's PARTS, in the order they run."""
    return sibling_modules(PANEL_STATUS)


def files(script: Path = SCRIPT) -> list[Path]:
    """The script, then each part's file in load order."""
    return [script] + [script.parent / f"{n}.py" for n in sibling_modules(script)]


def source(script: Path = SCRIPT) -> str:
    """The text of every file in `files`, joined in that order (for checks that read the code as text)."""
    return "\n".join(p.read_text(encoding="utf-8") for p in files(script))


class LcosRule(NamedTuple):
    """signal_coordinator.py's LCOS head rule: is_head(system name) is its _is_lcos_ih_sys, the test a head name
    passes to be enrolled; in_mast is its _HEAD_IN_MAST, the pattern that finds "(IH<digits>)" heads in a mast's
    system name."""
    is_head: Callable[[str | None], bool]   # None is no head
    in_mast: re.Pattern[str]


def lcos_rule(path: Path = LCOS_RULE) -> LcosRule:
    """sml_lcos.py at `path`, imported in CPython and kept in sys.modules: its _is_lcos_ih_sys and _HEAD_IN_MAST.
    CoordinatorError when the file is missing, does not import, or no longer defines them as a function and a
    compiled pattern."""
    if not path.is_file():
        raise CoordinatorError(f"{_rel(path)}: missing; signal_coordinator.py's LCOS head rule lives there")
    spec = importlib.util.spec_from_file_location(_LCOS_MODULE, path)
    if spec is None or spec.loader is None:
        raise CoordinatorError(f"{_rel(path)}: cannot be imported as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_LCOS_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:    # running a module's top level can raise any error; each becomes this one
        del sys.modules[_LCOS_MODULE]
        raise CoordinatorError(f"{_rel(path)}: does not import: {exc}") from exc
    is_head = getattr(module, "_is_lcos_ih_sys", None)
    in_mast = getattr(module, "_HEAD_IN_MAST", None)
    if not callable(is_head) or not isinstance(in_mast, re.Pattern):
        del sys.modules[_LCOS_MODULE]
        raise CoordinatorError(f"{_rel(path)}: no longer defines _is_lcos_ih_sys (a function) and _HEAD_IN_MAST "
                               "(a compiled pattern)")
    return LcosRule(is_head, in_mast)
