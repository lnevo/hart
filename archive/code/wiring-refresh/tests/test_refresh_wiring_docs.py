"""refresh_wiring_docs: golden outputs and unit tests on its parsing and error paths.

The script writes into docs/wiring/ through its module-level WIRING; the tests point WIRING at a temp dir, so the
committed workbooks are never touched. Everything the script reads that changes with the railroad is pinned to the
frozen copies under golden/inputs/ (the name map, the occupancy bindings, three signal CSVs from before the
2026-11-19 wiring cut, and a heads-only tables stand-in), so data PRs and tables pulls cannot fail these tests. The
only live inputs left are docs/wiring/imported/*.xlsx, the frozen import snapshots. Two golden checks:

- signals_split_v8.xlsx is compared cell by cell with the committed file (it depends on the imported workbook only).
- LCOS_Layout_Inventory_v85.xlsx and signals_asbuilt_abs_v2.xlsx are compared with golden/refresh_wiring_docs.json,
  a row-hash snapshot of what the script writes from the pinned inputs. It changes only when the script, the
  pinned inputs or docs/wiring/imported change; refresh it after an intended change with the command in REFRESH.
"""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import Workbook, load_workbook

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "tools/hartlib/src").is_dir())
sys.path[:0] = [str(ROOT / "tools/wiring"), str(ROOT / "tools/hartlib/src")]
from hartlib import paths  # noqa: E402
from hartlib.railroad import FactsError  # noqa: E402

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
GOLDEN = GOLDEN_DIR / "refresh_wiring_docs.json"
PINNED = GOLDEN_DIR / "inputs"
import refresh_wiring_docs as rw  # noqa: E402
REFRESH = ("UPDATE_GOLDEN=1 python3 -m unittest discover -s tools/audit/tests -p test_refresh_wiring_docs.py "
           "(the snapshot depends on the script, golden/inputs/*, and docs/wiring/imported/*.xlsx)")
SNAPSHOT_BOOKS = ("LCOS_Layout_Inventory_v85.xlsx", "signals_asbuilt_abs_v2.xlsx")


def row_hash(values) -> str:
    return hashlib.sha1(repr(tuple(values)).encode()).hexdigest()[:10]


def digest(path: Path) -> dict:
    wb = load_workbook(path)
    return {ws.title: {"dimensions": ws.dimensions, "rows": [row_hash(r) for r in ws.iter_rows(values_only=True)]}
            for ws in wb.worksheets}


def tree_hashes(*dirs: Path) -> dict[str, str]:
    """{path: sha256} for every file under dirs, to prove a run leaves its inputs alone."""
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for d in dirs for p in sorted(d.rglob("*")) if p.is_file()}


@contextlib.contextmanager
def pinned(dest: Path, **extra):
    """The script writing into dest and reading only the pinned inputs (plus docs/wiring/imported)."""
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(rw, "WIRING", dest))
        stack.enter_context(mock.patch.object(rw, "CATS", PINNED))
        stack.enter_context(mock.patch.object(rw, "SIGNALS", PINNED / "signals"))
        # live_heads() and occupancy_by_hw() bind their path defaults when defined, so patching CATS or TABLES_XML is not enough.
        stack.enter_context(mock.patch.object(rw.live_heads, "__defaults__", (PINNED / "tables_heads.xml",)))
        stack.enter_context(mock.patch.object(rw.occupancy_by_hw, "__defaults__", (PINNED / "occupancy_bindings.csv",)))
        for name, value in extra.items():
            stack.enter_context(mock.patch.object(rw, name, value))
        yield


def run_script(dest: Path) -> str:
    """main() with the inputs pinned and WIRING at dest; returns what it printed."""
    out = io.StringIO()
    with pinned(dest), contextlib.redirect_stdout(out):
        rw.main()
    return out.getvalue()


class Golden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dest = Path(cls.tmp.name)
        cls.inputs_before = tree_hashes(rw.IMPORTED, PINNED)
        cls.stdout = run_script(cls.dest)
        cls.inputs_after = tree_hashes(rw.IMPORTED, PINNED)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_writes_the_three_workbooks_and_only_them(self):
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()),
                         sorted(SNAPSHOT_BOOKS + ("signals_split_v8.xlsx",)))
        for name in (*SNAPSHOT_BOOKS, "signals_split_v8.xlsx"):
            self.assertIn(f"wrote {self.dest / name}", self.stdout)

    def test_split_v8_matches_committed_file(self):
        new = load_workbook(self.dest / "signals_split_v8.xlsx")
        old = load_workbook(ROOT / "docs/wiring/signals_split_v8.xlsx")
        self.assertEqual(new.sheetnames, old.sheetnames)
        for ws in old.worksheets:
            got = new[ws.title]
            self.assertEqual(got.dimensions, ws.dimensions, f"signals_split_v8 sheet {ws.title}: size")
            for r in ws.iter_rows():
                for c in r:
                    self.assertEqual(got[c.coordinate].value, c.value,
                                     f"signals_split_v8 {ws.title}!{c.coordinate} differs from the committed file")

    def test_snapshot_workbooks_match_golden(self):
        got = {name: digest(self.dest / name) for name in SNAPSHOT_BOOKS}
        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN.parent.mkdir(exist_ok=True)
            GOLDEN.write_text(json.dumps(got, indent=0, sort_keys=True) + "\n", encoding="utf-8")
            self.skipTest(f"UPDATE_GOLDEN set: wrote {GOLDEN}; rerun without it to check")
        want = json.loads(GOLDEN.read_text(encoding="utf-8"))
        for name in SNAPSHOT_BOOKS:
            self.assertEqual(sorted(got[name]), sorted(want[name]), f"{name}: sheet names")
            for sheet, g in got[name].items():
                w = want[name][sheet]
                self.assertEqual(g["dimensions"], w["dimensions"], f"{name} sheet {sheet}: size")
                self.assertEqual(len(g["rows"]), len(w["rows"]), f"{name} sheet {sheet}: row count")
                bad = [i + 1 for i, (a, b) in enumerate(zip(g["rows"], w["rows"])) if a != b]
                self.assertFalse(bad, f"{name} sheet {sheet}: rows differ from the golden snapshot: {bad[:20]} "
                                      f"; after an intended change run {REFRESH}")

    def test_committed_workbooks_have_the_same_sheets(self):
        for name in (*SNAPSHOT_BOOKS, "signals_split_v8.xlsx"):
            self.assertEqual(load_workbook(self.dest / name).sheetnames,
                             load_workbook(ROOT / "docs/wiring" / name).sheetnames, name)

    def test_inputs_are_not_modified(self):
        self.assertTrue(self.inputs_before, "no input files found to compare")
        self.assertEqual(self.inputs_after, self.inputs_before,
                         "a run changed, added or removed a file under docs/wiring/imported or golden/inputs")

    def test_summary_lines(self):
        for needle in ("Mangled SW1xx restorations", "Legacy SW/SCX tokens", "BlockSensors renames",
                       "v8 Mast cells:", "Princess dwarf rows"):
            self.assertIn(needle, self.stdout)


class Parsing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_load_csv_keeps_every_column(self):
        p = self.write("a.csv", "x,y,extra\n1,2,3\n")
        self.assertEqual(rw.load_csv(p), [{"x": "1", "y": "2", "extra": "3"}])

    def test_occupancy_by_hw_prefers_os_then_other_and_joins(self):
        p = self.write("occ.csv", "block_user_name,occupancy_sensor_user_name,cats_discipline\n"
                                  "OS 1,Block 1-1,\nMain 1,Block 1-1,\nOS 1,Block 1-1,\nOnly,Block 2-2,\n"
                                  "OS Solo,Block 3-3,\n,Block 4-4,\nNoSensor,,\n")
        got = rw.occupancy_by_hw(p)
        self.assertEqual(got, {"Block 1-1": "OS 1 / Main 1", "Block 2-2": "Only", "Block 3-3": "OS Solo"})

    def test_occupancy_by_hw_missing_column_is_a_facts_error(self):
        p = self.write("occ.csv", "block_user_name\nX\n")
        with self.assertRaises(FactsError):
            rw.occupancy_by_hw(p)

    def test_replace_in_cell(self):
        self.assertEqual(rw.replace_in_cell("a-b-a", [("a", "x"), ("b", "y")]), "x-y-x")
        self.assertEqual(rw.replace_in_cell(7, [("7", "8")]), 7)
        self.assertEqual(rw.replace_in_cell("", [("", "z")]), "")
        self.assertIsNone(rw.replace_in_cell(None, [("a", "b")]))

    def test_walk_replace_counts_changed_cells(self):
        ws = Workbook().active
        ws.append(["aa", 1, "b"])
        ws.append(["c", "a", None])
        self.assertEqual(rw.walk_replace(ws, [("a", "z")]), 2)
        self.assertEqual([c.value for r in ws.iter_rows() for c in r], ["zz", 1, "b", "c", "z", None])

    def test_remap_panel_ih_is_one_pass_and_whole_token(self):
        # IH1232 -> IH232 and IH132 -> IH1132 overlap: a second pass would chain them.
        self.assertEqual(rw.remap_panel_ih("IH1232=Green IH132=Red"), "IH232=Green IH1132=Red")
        self.assertEqual(rw.remap_panel_ih("IH12320"), "IH12320")
        self.assertEqual(rw.remap_panel_ih(5), 5)

    def test_walk_remap_panel_ih(self):
        ws = Workbook().active
        ws.append(["IH137", "x", 3])
        self.assertEqual(rw.walk_remap_panel_ih(ws), 1)
        self.assertEqual(ws["A1"].value, "IH132")

    def test_rewrite_legacy_node_ids_whole_tokens(self):
        legacy = next((k for k, v in rw.LEGACY_NODE_IDS.items() if v != k), None)
        self.assertIsNotNone(legacy, "LEGACY_NODE_IDS maps no id to a different one; the test needs one that does")
        self.assertEqual(rw.rewrite_legacy_node_ids(f"node {legacy}, x"), f"node {rw.LEGACY_NODE_IDS[legacy]}, x")
        self.assertEqual(rw.rewrite_legacy_node_ids(f"A{legacy}"), f"A{legacy}")
        self.assertIsNone(rw.rewrite_legacy_node_ids(None))

    def test_unique_keep_order(self):
        self.assertEqual(rw._unique_keep_order(["b", "a", "b", "", "c", "a"]), ["b", "a", "c"])

    def test_header_index_is_one_based_and_skips_blanks(self):
        ws = Workbook().active
        ws.append(["A", None, "C"])
        self.assertEqual(rw.header_index(ws), {"A": 1, "C": 3})

    def test_live_heads_reads_system_names(self):
        p = self.write("t.xml", "<x><systemName>IH1</systemName><systemName>IT5</systemName>"
                                "<systemName>IH22</systemName></x>")
        self.assertEqual(rw.live_heads(p), {"IH1", "IH22"})

    def test_strip_dead_head_tokens(self):
        live = {"IH1"}
        self.assertEqual(rw.strip_dead_head_tokens("IH1=Green IH2=Red", live), "IH1=Green")
        self.assertEqual(rw.strip_dead_head_tokens("IH2=Red, IH1=Green", live), "IH1=Green")
        self.assertEqual(rw.strip_dead_head_tokens("IH1=Green", live), "IH1=Green")
        self.assertEqual(rw.strip_dead_head_tokens(4, live), 4)

    def test_drop_dead_heads_deletes_mqtt_row_and_untags_survivor(self):
        ws = Workbook().active
        ws.title = "mqtt_topics"
        ws.append(["JMRI", "Name", "Digicon_Block_or_Role"])
        ws.append(["IH1", "Mast 6 Top", "Mast 6"])
        ws.append(["IH2", "Mast 6 Bottom", "Mast 6"])
        ws.append(["IH3", "Mast 7 Top", "Mast 7"])
        ws.append(["IH4", "Mast 7 Bottom", "Mast 7"])
        self.assertEqual(rw.drop_dead_heads(ws, {"IH1", "IH3", "IH4"}), 2)
        self.assertEqual([list(r) for r in ws.iter_rows(min_row=2, values_only=True)],
                         [["IH1", "Mast 6", "Mast 6"], ["IH3", "Mast 7 Top", "Mast 7"],
                          ["IH4", "Mast 7 Bottom", "Mast 7"]])

    def test_drop_dead_heads_other_sheet_only_strips_tokens(self):
        ws = Workbook().active
        ws.title = "Brick"
        ws.append(["IH1=Green IH2=Red"])
        self.assertEqual(rw.drop_dead_heads(ws, {"IH1"}), 1)
        self.assertEqual(ws["A1"].value, "IH1=Green")


class ErrorPaths(unittest.TestCase):
    def run_main(self, **patches):
        with tempfile.TemporaryDirectory() as tmp, pinned(Path(tmp), **patches), contextlib.redirect_stdout(io.StringIO()):
            rw.main()

    def test_facts_error_exits_with_script_name_and_message(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main(refresh_inventory=mock.Mock(side_effect=FactsError("bad.csv: no column x")))
        self.assertEqual(str(cm.exception.code), "refresh_wiring_docs.py: bad.csv: no column x")

    def test_missing_imported_workbook_stops(self):
        with tempfile.TemporaryDirectory() as t, self.assertRaises(FileNotFoundError):
            self.run_main(IMPORTED=Path(t))

    def test_calibration_pin_clash_stops_naming_the_port(self):
        used = rw.load_csv(PINNED / "signals/signal_wiring.csv")[0]["port_id"]
        with self.assertRaises(SystemExit) as cm:
            self.run_main(first_5v_cal_ports=mock.Mock(return_value={"Block 1-1": used}))
        self.assertIn("Digicon heads on block-sensor calibration pins", str(cm.exception.code))
        self.assertIn(used, str(cm.exception.code))

    def test_node_id_address_mismatch_stops(self):
        def break_node(wb, wiring, heads):
            nodes = wb["Nodes"]
            idx = rw.header_index(nodes)
            for row in range(2, nodes.max_row + 1):
                if str(nodes.cell(row, idx["Node ID"]).value or "")[:1] in ("C", "D"):
                    nodes.cell(row, idx["Address"]).value = 9999
                    return

        with self.assertRaises(SystemExit) as cm:
            self.run_main(add_digicon_sheet=break_node)
        self.assertIn("Node ID != C/D{Address}", str(cm.exception.code))
        self.assertIn("9999", str(cm.exception.code))


if __name__ == "__main__":
    unittest.main()
