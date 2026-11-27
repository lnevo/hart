"""Starts tools/audit/traced.py's hook in a Python process when HART_TRACE_LOG is set (the traced stamps of make panels
and tools/check.sh put this folder on PYTHONPATH for that), then runs the next sitecustomize on sys.path (Homebrew's,
a venv's, tools/audit/stamp_audit's), which this file would otherwise hide, through tools/audit/hook_chain.py."""
import importlib.util
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_chain_spec = importlib.util.spec_from_file_location("_hart_hook_chain",
                                                     os.path.join(os.path.dirname(_here), "hook_chain.py"))
if _chain_spec is None or _chain_spec.loader is None:
    raise ImportError("hook_chain.py has no loader")
_chain = importlib.util.module_from_spec(_chain_spec)
_chain_spec.loader.exec_module(_chain)
if os.environ.get("HART_TRACE_LOG"):
    try:
        _spec = importlib.util.spec_from_file_location("_hart_traced", os.path.join(os.path.dirname(_here), "traced.py"))
        if _spec is None or _spec.loader is None:
            raise ImportError("traced.py has no loader")
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        sys.modules["_hart_traced"] = _mod
        _mod.install()
    except Exception as _exc:  # noqa: BLE001 - no trace is recorded then (no process start in the log)
        sys.stderr.write(f"trace hook: {type(_exc).__name__}: {_exc}\n")


_chain.run_next(_here, "_sitecustomize_after_trace_hook")
