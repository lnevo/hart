# JMRI jython -- the loader signal_coordinator.py and panel_status.py import their sibling modules with,
# and the one helper those modules share (once_printer).
#
# JMRI runs a Start Up script from preference:jython with no __file__ and without that folder on sys.path, and
# keeps every imported module across runs of the script. Each script puts the folder on sys.path, imports this
# module from it (reloading it on a re-run) and calls load() with its own name and its tuple of siblings. The
# deploy ships this file beside both scripts (tools/hosts/deploy/common.sh, JYTHON_SIBLING_MODULES).
#
# Jython 2.7: no f-strings or annotations.

import os
import sys

try:
    _reload = reload  # noqa: F821 (Jython 2.7: a builtin)
except NameError:  # CPython 3, where the tests run the scripts
    from importlib import reload as _reload


class SiblingModuleError(ImportError):
    """A sibling module is missing from the jython folder, does not compile, fails to import, or was loaded from
    another folder."""


def once_printer():
    """A new print function that prints each message the first time only, with its own record of what it printed.

    A module calls this at its top level (`_log_once = once_printer()`), so each module keeps its own record and
    a reload of that module starts a new one: a failure line that repeats on every bean or turnout event is
    printed once per run of the script.
    """
    printed = set()

    def log_once(msg):
        """Print msg the first time only."""
        if msg not in printed:
            printed.add(msg)
            print(msg)

    return log_once


def reload_module(module):
    """`module` executed afresh from its file (the builtin reload, or importlib's under CPython)."""
    return _reload(module)


def check_folder(script, folder):
    """Raise SiblingModuleError unless `folder` (preference:jython) is an existing folder."""
    if not folder or not os.path.isdir(folder):
        raise SiblingModuleError("%s: no jython folder (preference:jython is %r)" % (script, folder))


def load(script, folder, names):
    """Import each of `names` from `folder`, or reload it if an earlier run imported it; returns the modules in order.

    `names` is in load order: each comes after every sibling it imports, so a reload sees the reloaded ones. Every
    file is found and compiled before any is loaded, so a missing or broken one stops a re-run before it reloads
    the earlier run's modules under a live script. Each file is compiled from its bytes, as an import reads it
    (a non-ASCII file needs its coding line). A module that comes from another folder on sys.path stops the run.
    """
    check_folder(script, folder)
    if folder not in sys.path:
        sys.path.insert(0, folder)
    want = os.path.normcase(os.path.realpath(folder))
    for name in names:
        path = os.path.join(folder, name + ".py")
        if not os.path.isfile(path):
            raise SiblingModuleError(
                "%s: %s.py is missing from %s; the deploy ships it beside this script" % (script, name, folder)
            )
        try:
            with open(path, "rb") as f:
                compile(f.read(), path, "exec")
        except Exception as exc:
            raise SiblingModuleError("%s: %s.py in %s does not compile: %s" % (script, name, folder, exc))
    modules = []
    for name in names:
        try:
            module = sys.modules.get(name)
            if module is None:
                module = __import__(name)
            else:
                module = _reload(module)
        except Exception as exc:
            raise SiblingModuleError("%s: cannot import %s from %s: %s" % (script, name, folder, exc))
        got = os.path.dirname(getattr(module, "__file__", None) or "")
        if os.path.normcase(os.path.realpath(got)) != want:
            raise SiblingModuleError("%s: %s was loaded from %r, not from %s" % (script, name, got, folder))
        modules.append(module)
    return modules
