"""tools/ctc_history/films.py sends each film name to its builder's main() and nothing else; no film is built here."""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
HISTORY = ROOT / "tools/ctc_history"
sys.path.insert(0, str(HISTORY))
import films  # noqa: E402


class Dispatch(unittest.TestCase):
    def test_each_film_runs_its_own_builder(self) -> None:
        for name, module in films.FILMS.items():
            calls: list[str] = []
            fake = types.SimpleNamespace(main=lambda m=module: calls.append(m))
            with mock.patch.object(films.importlib, "import_module", return_value=fake) as imp:
                self.assertEqual(films.main([name]), 0)
            imp.assert_called_once_with(module)
            self.assertEqual(calls, [module])

    def test_every_builder_is_a_module_with_main(self) -> None:
        self.assertEqual(sorted(films.FILMS), ["cats", "ctc", "le"])
        for module in films.FILMS.values():
            src = (HISTORY / f"{module}.py").read_text(encoding="utf-8")
            self.assertIn("\ndef main() -> None:", src)
            self.assertNotIn("__main__", src, f"{module}.py is run through films.py, not on its own")

    def test_an_unknown_or_missing_film_is_refused(self) -> None:
        for argv in ([], ["schematic"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
                films.main(argv)
            self.assertEqual(e.exception.code, 2)

    def test_help_needs_no_pillow(self) -> None:
        done = subprocess.run([sys.executable, "-S", str(HISTORY / "films.py"), "--help"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("{cats,ctc,le}", done.stdout)


if __name__ == "__main__":
    unittest.main()
