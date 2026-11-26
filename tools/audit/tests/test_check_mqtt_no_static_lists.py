"""tools/audit/check_mqtt_no_static_lists.py: a missing HART file fails, a missing bridge file fails when the
bridge is checked out, and no bridge checkout is said and not failed."""
from __future__ import annotations

import contextlib
import importlib.util
import sys
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path) -> ModuleType:
    """The module at `path`, loaded by path under `name`."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CHECK = _load("check_mqtt_no_static_lists", ROOT / "tools/audit/check_mqtt_no_static_lists.py")


class StaticLists(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.clean = self.tmp / "clean.py"
        self.clean.write_text("heads = read_heads()\n", encoding="utf-8")
        self.lcos = self.tmp / "lcos"
        self.lcos.mkdir()

    def run_check(self, strict: list[Path], guard_ok: list[Path]) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CHECK.run(strict, guard_ok, self.lcos)
        return rc, out.getvalue()

    def bridge(self) -> None:
        for name in CHECK.LCOS_FILES:
            (self.lcos / name).write_text("// no lists\n", encoding="utf-8")

    def test_clean_files_and_bridge_pass(self) -> None:
        self.bridge()
        rc, out = self.run_check([self.clean], [self.clean])
        self.assertEqual(0, rc, out)
        self.assertNotIn("NOT CHECKED", out)

    def test_a_missing_hart_file_fails(self) -> None:
        self.bridge()
        rc, out = self.run_check([self.clean, self.tmp / "gone.py"], [])
        self.assertEqual(1, rc)
        self.assertIn("gone.py: missing, so it cannot be checked", out)

    def test_a_missing_bridge_file_in_a_checkout_fails(self) -> None:
        (self.lcos / "README.md").write_text("bridge\n", encoding="utf-8")
        rc, out = self.run_check([self.clean], [])
        self.assertEqual(1, rc)
        self.assertIn("serial_to_mqtt.py: missing", out)

    def test_no_bridge_checkout_is_said_and_the_rest_is_read(self) -> None:
        bad = self.tmp / "bad.py"
        bad.write_text("x = 1\nHEAD_NAMES = ['a']\n", encoding="utf-8")
        rc, out = self.run_check([self.clean], [])
        self.assertEqual(0, rc, out)
        self.assertIn("NOT CHECKED: no LCOS bridge checkout", out)
        rc, out = self.run_check([bad], [])
        self.assertEqual(1, rc)
        self.assertIn("contains 'HEAD_NAMES = ['", out)
        self.assertIn("HEAD_NAMES assignment", out)

    def test_guard_ok_files_may_assign_head_names(self) -> None:
        self.bridge()
        build = self.tmp / "build.py"
        build.write_text("x = 1\nHEAD_NAMES = read()\n", encoding="utf-8")
        rc, out = self.run_check([], [build])
        self.assertEqual(0, rc, out)


if __name__ == "__main__":
    unittest.main()
