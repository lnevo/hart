"""Shared by the guard tests (test_guards, test_guards_names, test_guards_after_edit): the repo root, a PATH
holding only git, the operating-flag stand-in, and the helpers that load a hook or start one as Claude Code does.
Each test file names the hooks it tests itself, so the after-edit hook finds it by their names. Not a test
file: it holds no tests."""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

_BIN = tempfile.TemporaryDirectory()
os.symlink(shutil.which("git"), os.path.join(_BIN.name, "git"))
GIT_ONLY_PATH = _BIN.name


# The guard reads the Mac's operating flag (tools/hosts/operating.sh); these tests never see the real one.
os.environ["HART_OPERATING_FLAG"] = "/nonexistent/hart-test-operating-flag"
os.environ.pop("HART_GUARD_OPERATING", None)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(hook: Path, command: str, cwd: str):
    """Start a hook as Claude Code does, with no MQTT client reachable on PATH."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=cwd, PATH=GIT_ONLY_PATH)
    payload = json.dumps({"tool_input": {"command": command}, "cwd": cwd})
    return subprocess.run([sys.executable, str(hook)], input=payload, capture_output=True, text=True, env=env)



@contextlib.contextmanager
def mock_env(**values):
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
