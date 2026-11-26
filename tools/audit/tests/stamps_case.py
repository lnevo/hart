"""RepoCase: a fake repo with a stamp store of its own, whose job is a script run under the real trace hook,
for the check_stamps tests (test_stamps_record, test_stamps_batch, test_stamps_keys, test_stamps_audit,
test_audit_fails, test_panels_jobs). Not a test file: it holds no tests."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_stamps as cs  # noqa: E402

# A step manifest for the fake repos: the jobs check.sh runs from it, one per step (a and b in the static group, a
# keyed on HEAD and the merge base, b on no ref, and three in no group). Only manifest.job_keys reads it here, which
# does not check paths against git or the map.
MANIFEST = "".join(f'[[step]]\nname = "{name}"\nrunner = "check"\n{group}cmd = ["python3", "tools/{name}.py"]\n'
                   f'git = {refs}\n'
                   for name, group, refs in (("a", 'group = "static"\n', '["head", "base"]'),
                                             ("b", 'group = "static"\n', "[]"), ("public-text", "", "[]"),
                                             ("ruff", "", "[]"), ("portal", "", '["head", "base"]')))


class RepoCase(unittest.TestCase):
    """A fake repo with a store of its own; the job is a script run under the real trace hook."""

    JOB = "open('tools/x/tests/test_a.py').read()\n"

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root, self.store = self.tmp / "repo", self.tmp / "store"
        for rel in ("tools/check.sh", "tools/x/tests/test_a.py", "jmri/layouts/hart/data/switches.csv",
                    "www/index.html", "docs/a.md", ".claude/worktrees/other/tools/y.py"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("v1\n")
        (self.root / cs.MANIFEST).parent.mkdir(parents=True, exist_ok=True)
        (self.root / cs.MANIFEST).write_text(MANIFEST)
        for target, value in (("plugin_state", "plugin"),):
            patch = unittest.mock.patch.object(cs.ps, target, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = unittest.mock.patch.object(cs, "main_checkout", return_value=None)
        patch.start()
        self.addCleanup(patch.stop)

    def run_job(self, code: str | None = None, script: str = "job.py") -> Path:
        log = self.tmp / "trace.log"
        log.write_text("0\tb\n")
        (self.root / script).write_text(code or self.JOB)
        env = {k: v for k, v in os.environ.items() if not k.startswith("HART_TRACE")}
        env.update(HART_TRACE_LOG=str(log), HART_TRACE_ROOT=str(self.root), PYTHONPATH=cs.traced.HOOK_DIR)
        subprocess.run([sys.executable, script], cwd=self.root, env=env, check=True, capture_output=True)
        return log

    def record(self, name: str = "unit-hartlib", code: str | None = None, script: str = "job.py") -> str | None:
        return cs.record(name, self.run_job(code, script), self.root, self.store)

    def current(self, name: str = "unit-hartlib") -> bool:
        return cs.is_current(name, self.root, self.store)
