"""tools/audit/stamp_audit/sitecustomize.py, the CHECK_AUDIT hook: it logs the repo files a Python process reads, then
runs the next sitecustomize on sys.path through tools/audit/trace_hook/hook_chain.py, as tools/audit/trace_hook's
does: Homebrew's Python adds its site-packages from its own sitecustomize, so a hook that stops the chain hides
the installed packages from every audited job."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1]
STAMP_AUDIT = AUDIT / "stamp_audit"
TRACE_HOOK = AUDIT / "trace_hook"
# The next sitecustomize: it records that it ran by appending a line to the file NEXT_RAN names.
NEXT = 'import os\nwith open(os.environ["NEXT_RAN"], "a") as f:\n    f.write("ran\\n")\n'


class ChainTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "repo"
        self.root.mkdir()
        (self.root / "data.txt").write_text("x\n")
        self.log = self.tmp / "audit.log"
        self.ran = self.tmp / "next-ran"

    def run_python(self, *folders: Path, code: str = "import sys; open(sys.argv[1]).read()",
                   audit: bool = True) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("HART_TRACE", "CHECK_AUDIT")) and k != "PYTHONPATH"}
        env.update(PYTHONPATH=os.pathsep.join(str(f) for f in folders), NEXT_RAN=str(self.ran))
        if audit:
            env.update(CHECK_AUDIT_LOG=str(self.log), CHECK_AUDIT_ROOT=str(self.root))
        return subprocess.run([sys.executable, "-c", code, str(self.root / "data.txt")], env=env, cwd=self.tmp,
                              capture_output=True, text=True, timeout=60)

    def next_folder(self, name: str) -> Path:
        folder = self.tmp / name
        folder.mkdir()
        (folder / "sitecustomize.py").write_text(NEXT)
        return folder

    def test_the_next_sitecustomize_runs_and_reads_are_still_logged(self) -> None:
        done = self.run_python(STAMP_AUDIT, self.next_folder("next"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.ran.read_text(), "ran\n")
        self.assertIn("r\tdata.txt", self.log.read_text().splitlines())

    def test_only_the_first_sitecustomize_after_the_hook_runs(self) -> None:
        """The one it runs chains on by itself, as Python would run only the first."""
        done = self.run_python(STAMP_AUDIT, self.next_folder("first"), self.next_folder("second"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.ran.read_text(), "ran\n")

    def test_a_sitecustomize_before_the_hook_is_not_run_again(self) -> None:
        """A folder ahead of the hook's is Python's own pick, not the hook's to chain to."""
        done = self.run_python(self.next_folder("ahead"), STAMP_AUDIT)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.ran.read_text(), "ran\n")
        self.assertFalse(self.log.exists(), "Python ran the folder ahead's sitecustomize, not the hook")

    def test_behind_the_trace_hook_the_chain_reaches_the_next_one(self) -> None:
        """check.sh's audited and traced job: trace_hook, then stamp_audit, then the interpreter's own."""
        done = self.run_python(TRACE_HOOK, STAMP_AUDIT, self.next_folder("next"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.ran.read_text(), "ran\n")
        self.assertIn("r\tdata.txt", self.log.read_text().splitlines())

    def test_each_hook_hands_on_through_hook_chain(self) -> None:
        """trace_hook runs stamp_audit's file, and stamp_audit the next one, each as the module its run_next call
        names; the audit never logs hook_chain.py itself (stamp_audit loads it before its hook)."""
        code = ("import json, sys; print(json.dumps({n: sys.modules[n].__file__ for n in sys.modules"
                " if n.startswith('_sitecustomize_after_')}))")
        done = self.run_python(TRACE_HOOK, STAMP_AUDIT, self.next_folder("next"), code=code)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout),
                         {"_sitecustomize_after_trace_hook": str(STAMP_AUDIT / "sitecustomize.py"),
                          "_sitecustomize_after_stamp_audit": str(self.tmp / "next" / "sitecustomize.py")})
        self.assertEqual(self.ran.read_text(), "ran\n")
        self.assertNotIn("hook_chain.py", self.log.read_text() if self.log.exists() else "")

    def test_the_trace_hook_alone_runs_the_next_one(self) -> None:
        done = self.run_python(TRACE_HOOK, self.next_folder("next"), audit=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.ran.read_text(), "ran\n")

    def test_a_package_from_the_interpreters_own_site_setup_still_imports(self) -> None:
        """Whatever site-packages the interpreter adds (Homebrew's sitecustomize, a venv's site.py) is still on
        sys.path under the hook."""
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("HART_TRACE", "CHECK_AUDIT")) and k != "PYTHONPATH"}
        plain = subprocess.run([sys.executable, "-c", "import json, sys; print(json.dumps(sys.path))"], env=env,
                               capture_output=True, text=True, timeout=60, cwd=self.tmp)
        self.assertEqual(plain.returncode, 0, plain.stderr)
        env.update(PYTHONPATH=str(STAMP_AUDIT), CHECK_AUDIT_LOG=str(self.log), CHECK_AUDIT_ROOT=str(self.root))
        hooked = subprocess.run([sys.executable, "-c", "import json, sys; print(json.dumps(sys.path))"], env=env,
                                capture_output=True, text=True, timeout=60, cwd=self.tmp)
        self.assertEqual(hooked.returncode, 0, hooked.stderr)
        missing = set(json.loads(plain.stdout)) - set(json.loads(hooked.stdout))
        self.assertEqual(missing, set())


class RunNextTest(unittest.TestCase):
    """hook_chain.run_next in this process, loaded by path as the hooks load it."""

    def setUp(self) -> None:
        spec = importlib.util.spec_from_file_location("_hart_hook_chain_test", TRACE_HOOK / "hook_chain.py")
        assert spec is not None and spec.loader is not None
        self.chain = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.chain)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        path_before, modules_before = list(sys.path), set(sys.modules)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), path_before))
        self.addCleanup(lambda: [sys.modules.pop(n) for n in set(sys.modules) - modules_before])

    def folder(self, name: str) -> Path:
        folder = self.tmp / name
        folder.mkdir()
        (folder / "sitecustomize.py").write_text(f"RAN = {name!r}\n")
        return folder

    def test_runs_only_the_first_after_the_hook_under_the_given_name(self) -> None:
        hook = self.tmp / "hook"
        hook.mkdir()
        sys.path[:] = [str(self.folder("ahead")), str(hook), str(self.tmp / "empty"), str(self.folder("first")),
                       str(self.folder("second"))]
        self.chain.run_next(str(hook), "_chain_test_next")
        self.assertEqual(sys.modules["_chain_test_next"].RAN, "first")

    def test_nothing_runs_when_the_hook_folder_is_not_on_sys_path(self) -> None:
        sys.path[:] = [str(self.folder("other"))]
        self.chain.run_next(str(self.tmp / "hook"), "_chain_test_none")
        self.assertNotIn("_chain_test_none", sys.modules)


if __name__ == "__main__":
    unittest.main()
