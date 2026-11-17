"""wire_digicon.py, which built the hand-wired desks from HART_Digicon.xml, is retired by the CATS cut-over: it
refuses to write the live desks, which tools/schematic/build_cats_panel.py generates (and its --check holds)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]


def load_wire_digicon():
    spec = importlib.util.spec_from_file_location("wire_digicon", SCRIPTS / "wire_digicon.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class Retired(unittest.TestCase):
    def test_the_retired_builder_refuses_the_live_desks(self) -> None:
        wire = load_wire_digicon()
        before = [p.read_bytes() for p in wire.LIVE_DESKS]
        with mock.patch.object(sys, "argv", ["wire_digicon.py"]), \
                self.assertRaisesRegex(SystemExit, "generated since the CATS cut-over"):
            wire.main()
        self.assertEqual([p.read_bytes() for p in wire.LIVE_DESKS], before)


if __name__ == "__main__":
    unittest.main()
