"""Runs the next sitecustomize on sys.path after a repo hook (tools/audit/trace_hook, tools/audit/stamp_audit).

Python imports only the first sitecustomize it finds, so a hook folder put on PYTHONPATH hides the interpreter's own
(Homebrew's adds its site-packages there; a venv may have one). Each hook loads this file by path (stamp_audit's from
../trace_hook, so tools/ci/stamp_gate.MACHINERY's trace_hook/ entry covers it), with nothing of the repo on sys.path,
and calls run_next with its own folder.
"""
import importlib.util
import os
import sys


def run_next(hook_dir: str, name: str) -> None:
    """Run the first sitecustomize.py in a sys.path folder after `hook_dir`, as the module `name`; it chains on by
    itself. A folder ahead of `hook_dir` is Python's own pick and is not run again."""
    seen = False
    for entry in list(sys.path):
        folder = os.path.abspath(entry or os.getcwd())
        if folder == hook_dir:
            seen = True
            continue
        candidate = os.path.join(folder, "sitecustomize.py")
        if seen and os.path.isfile(candidate):
            spec = importlib.util.spec_from_file_location(name, candidate)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {candidate}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return
