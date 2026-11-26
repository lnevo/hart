from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path
from types import ModuleType
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "diagnose_turnout_states.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("diagnose_turnout_states", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _turnout(name: str, user: str, state: int, fb: str | None) -> dict[str, object]:
    sensors = [{"data": {"userName": f"{user} FB {fb}", "state": 4}}] if fb else []
    return {"name": name, "userName": user, "state": state, "feedbackMode": 8, "sensor": sensors}


class DiagnoseTurnoutStatesReadOnlyTest(unittest.TestCase):
    def test_write_mode_is_gone(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--write"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2)

    def test_never_publishes_mqtt(self) -> None:
        self.assertNotIn("mosquitto_pub", SCRIPT.read_text(encoding="utf-8"))


class Unreachable(unittest.TestCase):
    def test_exits_1_with_a_message_when_jmri_does_not_answer(self) -> None:
        mod = _load()
        err = io.StringIO()
        with mock.patch.object(mod.tf, "get_json", side_effect=urllib.error.URLError("refused")), \
                mock.patch.object(sys, "argv", ["diagnose_turnout_states.py"]), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()) as out:
            code = mod.main()
        self.assertEqual(code, 1)
        self.assertIn("JMRI unreachable", err.getvalue())
        self.assertEqual(out.getvalue(), "")


class Table(unittest.TestCase):
    def test_rows_skip_yard_switches_and_flag_mismatches(self) -> None:
        mod = _load()
        by_name = {
            "M2T5": _turnout("M2T5", "Switch 5", 2, "R"),
            "M2T116": _turnout("M2T116", "Switch 13", 2, "N"),
            "M2T1": _turnout("M2T1", "Switch 1", 2, "N"),
            "IT9": _turnout("IT9", "Switch 9", 2, None),
        }
        retained = {5: "CLOSED", 1: "CLOSED"}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(mod.diagnose(by_name, retained.get), 0)
        lines = out.getvalue().splitlines()
        rows = [ln for ln in lines if ln.strip().startswith(("1 ", "5 "))]
        self.assertEqual(len(rows), 2, lines)
        self.assertIn("not-thrown(starts-thrown)", rows[0])
        self.assertIn("mqtt≠fb", rows[1])
        self.assertNotIn("M2T116", out.getvalue())


if __name__ == "__main__":
    unittest.main()
