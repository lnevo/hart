"""check_layout_facts.py's parts name what is missing (LayoutFactsError), and main turns that into exit 1."""
from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
import sys  # noqa: E402

sys.path.insert(0, str(ROOT / "tools/audit"))
import check_layout_facts as check  # noqa: E402
import layout_facts_desks as desks  # noqa: E402
import layout_facts_tables as tables_part  # noqa: E402
from hartlib import devices  # noqa: E402
from layout_facts_xml import LayoutFactsError  # noqa: E402


class LayoutFactsErrors(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def main(self, *argv: str) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = check.main(list(argv))
        return code, err.getvalue()

    def test_a_missing_input_is_named_and_exits_1(self) -> None:
        code, err = self.main("--tables", str(self.tmp / "none.xml"))
        self.assertEqual(code, 1)
        self.assertIn(f"--tables {self.tmp / 'none.xml'}: no such file", err)
        code, err = self.main("--data", str(self.tmp / "nodata"))
        self.assertEqual((code, "--data" in err and "no such folder" in err), (1, True))
        code, err = self.main("--desk", str(self.tmp / "desk.xml"))
        self.assertIn("--desk", err)
        self.assertEqual(code, 1)

    def test_a_master_with_no_main_or_upper_block_rows_is_named(self) -> None:
        rows = [r.cells() for r in devices.load(check.DEVICE_MAP)
                if not (r.level_cell in ("2", "3") and r.layer == "block")]
        master = self.tmp / devices.ONE_FILE
        master.write_text(devices.master_text(rows), encoding="utf-8")
        desks.block_rows.cache_clear()
        self.addCleanup(desks.block_rows.cache_clear)
        with mock.patch.object(desks, "DEVICE_MAP", master):
            with self.assertRaisesRegex(LayoutFactsError, "has no block rows"):
                desks.block_rows()

    def test_a_leg_walk_past_the_limit_is_named(self) -> None:
        """A chain of track longer than TRACK_WALK_LIMIT segments, all inside the turnout's own block."""
        t = check.Tables(check.TABLES)
        n = tables_part.TRACK_WALK_LIMIT + 1
        t.layout_turnouts = {"T": ET.Element("layoutturnout", ident="T", blockname="Own")}
        t.segments, t.points = {}, {}
        for i in range(n):
            first = ("T", "TURNOUT_B") if i == 0 else (f"P{i - 1}", "POS_POINT")
            t.segments[f"S{i}"] = ET.Element("tracksegment", ident=f"S{i}", blockname="Own",
                                             connect1name=first[0], type1=first[1],
                                             connect2name=f"P{i}", type2="POS_POINT")
            t.points[f"P{i}"] = ET.Element("positionablepoint", ident=f"P{i}", connect1name=f"S{i}",
                                           connect2name=f"S{i + 1}")
        with self.assertRaisesRegex(LayoutFactsError, "runs past .* segments inside Own"):
            t.leg_block("T", "B", "Own")
        for i in (n - 1, n - 2):            # the chain now ends inside the limit: no block reached
            t.segments.pop(f"S{i}")
        self.assertIsNone(t.leg_block("T", "B", "Own"))

    def test_a_desk_route_with_no_routeid_is_named(self) -> None:
        tree = ET.parse(check.DESKS[0])
        for ri in tree.getroot().iter("ROUTEINFO"):
            ri.attrib.pop("ROUTEID", None)
        desk = self.tmp / check.DESKS[0].name
        tree.write(desk, encoding="utf-8")
        with self.assertRaisesRegex(LayoutFactsError, "ROUTEINFO.*has no ROUTEID"):
            check.run(desks=(desk,))


if __name__ == "__main__":
    unittest.main()
