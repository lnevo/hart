"""The last hand-wired desks (git, before the CATS cut-over) are what wire_digicon.py builds from the Designer panel.

wire_digicon.py is retired: the live desks are generated (tools/schematic/build_cats_panel.py), and it refuses to
write them. This keeps the record honest: a rebuild into a temporary folder still gives the hand-wired desks.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
# The header carries the build date, which is not a change to the desk.
EFFECTIVE = re.compile(r"Eff \d{4}-\d{2}-\d{2}")


def load_wire_digicon():
    spec = importlib.util.spec_from_file_location("wire_digicon", SCRIPTS / "wire_digicon.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def comparable(path: Path) -> str:
    return EFFECTIVE.sub("Eff DATE", path.read_text(encoding="utf-8"))


class DesksMatchSource(unittest.TestCase):
    def test_rebuild_matches_committed_desks(self) -> None:
        wire = load_wire_digicon()
        # The header step only accepts paths inside the repo.
        with tempfile.TemporaryDirectory(dir=SCRIPTS.parent / "panels") as tmp:
            ctc, abs_desk = Path(tmp) / "HART_CTC.xml", Path(tmp) / "HART_ABS.xml"
            with mock.patch.object(wire, "CTC", ctc), mock.patch.object(wire, "ABS", abs_desk), \
                    mock.patch.object(sys, "argv", ["wire_digicon.py"]), \
                    contextlib.redirect_stdout(io.StringIO()):
                wire.main()
            sys.path.insert(0, str(SCRIPTS.parents[1] / "tools/hartlib/src"))
            from hartlib import hand_drawn
            for built in (ctc, abs_desk):
                committed = hand_drawn.skip_unless_available(built.name)
                self.assertEqual(comparable(built), comparable(committed),
                                 f"{committed.name} differs from a rebuild")


    def test_the_retired_builder_refuses_the_live_desks(self) -> None:
        wire = load_wire_digicon()
        before = [p.read_bytes() for p in wire.LIVE_DESKS]
        with mock.patch.object(sys, "argv", ["wire_digicon.py"]), \
                self.assertRaisesRegex(SystemExit, "generated since the CATS cut-over"):
            wire.main()
        self.assertEqual([p.read_bytes() for p in wire.LIVE_DESKS], before)


if __name__ == "__main__":
    unittest.main()
