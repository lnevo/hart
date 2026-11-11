"""USS CTC head icons and the as-built remap must follow the heads in tables.xml."""
from __future__ import annotations

import ast
import csv
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[3]
TABLES = SCRIPTS.parent / "output" / "tables.xml"
GUI = SCRIPTS.parent / "ctc" / "GUIObjects.xml"
WIRING = ROOT / "docs/wiring/signals/signal_wiring.csv"
REFRESH = ROOT / "docs/wiring/scripts/refresh_wiring_docs.py"

sys.path.insert(0, str(SCRIPTS))
import gen_ctc_track_plan as gen  # noqa: E402


def mast_heads() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for el in ET.parse(TABLES).getroot().iter("signalmast"):
        sn = el.findtext("systemName") or ""
        if sn.startswith("IF$shsm:"):
            out[el.findtext("userName")] = re.findall(r"IH\d+", sn)
    return out


def head_icons(path: Path) -> set[tuple[str, str, str]]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r'<signalheadicon signalhead="(IH\d+)" x="(\d+)" y="(\d+)"', text))


def load_remap():
    """PANEL_TO_WIRING_IH and remap_panel_ih without importing openpyxl."""
    tree = ast.parse(REFRESH.read_text(encoding="utf-8"))
    keep = []
    for node in tree.body:
        targets = []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        names = {t.id for t in targets if isinstance(t, ast.Name)}
        if names & {"PANEL_TO_WIRING_IH", "_IH_TOKEN"}:
            keep.append(node)
        if isinstance(node, ast.FunctionDef) and node.name == "remap_panel_ih":
            keep.append(node)
    ns: dict = {"re": re}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(REFRESH), "exec"), ns)
    return ns["PANEL_TO_WIRING_IH"], ns["remap_panel_ih"]


class CtcSignalHeadsTest(unittest.TestCase):
    def test_track_plan_icons_show_the_mast_top_head(self) -> None:
        masts = mast_heads()
        for mast, _x, _y, _facing, kind, head in gen.SIGNALS:
            if head is None:
                continue
            with self.subTest(mast=mast):
                self.assertIn(mast, masts)
                self.assertEqual(head, masts[mast][0])

    def test_gui_objects_head_icons_match_tables(self) -> None:
        tables = head_icons(TABLES)
        gui = head_icons(GUI)
        self.assertEqual(gui, {i for i in tables if i[0] != "IH9990"})


class AsBuiltRemapTest(unittest.TestCase):
    def test_remap_is_one_pass_onto_wired_heads(self) -> None:
        mapping, remap = load_remap()
        self.assertEqual(len(mapping), 17)
        with WIRING.open(newline="") as f:
            wired = {r["system_name"] for r in csv.DictReader(f)}
        self.assertLessEqual(set(mapping.values()), wired)
        # IH1232 was 24RA (now IH232); IH1237 was 34L (now IH1232). No chaining.
        self.assertEqual(remap("IH1232=Red IH1237=Green"), "IH232=Red IH1232=Green")
        self.assertEqual(remap("IH137 IH132 IH13"), "IH132 IH1132 IH13")
        self.assertEqual(remap("IH1332"), "IH1332")
        self.assertEqual(remap(None), None)


if __name__ == "__main__":
    unittest.main()
