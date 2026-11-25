"""tools/ops/check_locos.py: each gap it finds, the repo passing, and the loco master's two existing rows
still building the import list that is committed (lane L4d of ADR-039)."""
from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("check_locos", ROOT / "tools/ops/check_locos.py")
L = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(L)
locos = L.locos


def row(road: str, number: str, rid: str | None = None) -> dict:
    return {"roster_id": rid if rid is not None else f"{road} {number}", "road_name": road, "road_number": number}


class GapTests(unittest.TestCase):
    def test_a_complete_master_has_no_gaps(self) -> None:
        rows = [row("BO", "572"), row("NWR", "06")]
        self.assertEqual(L.gaps(rows, {"r.xml": ["BO572", "NWR06"]}, {"t.csv": ["572", "06"]}), [])

    def test_a_roster_engine_the_master_lacks(self) -> None:
        found = L.gaps([row("POHC", "2091")], {"r.xml": ["CWRY2091"]}, {})
        self.assertEqual([(f, v) for f, v, _ in found], [("r.xml", "CWRY2091")])

    def test_a_train_engine_with_no_row_or_two_rows(self) -> None:
        found = L.gaps([row("BO", "2091"), row("POHC", "2091")], {}, {"t.csv": ["2091", "4501", "4501"]})
        self.assertEqual([(v, p.split(" ")[0]) for _, v, p in found], [("2091", "road"), ("4501", "no")])

    def test_a_roster_id_that_is_not_road_space_number(self) -> None:
        found = L.gaps([row("CSX", "2121", rid="CSX2121")], {}, {})
        self.assertEqual(found[0][1:], ("CSX2121", "roster_id should be 'CSX 2121'"))


class RepoTests(unittest.TestCase):
    def test_the_repo_passes(self) -> None:
        run = subprocess.run([sys.executable, str(ROOT / "tools/ops/check_locos.py")], capture_output=True,
                             text=True, cwd=ROOT)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_the_two_published_locos_still_build_the_committed_import_list(self) -> None:
        rows = {r["roster_id"]: r for r in L.read_master()}
        committed = json.loads((ROOT / "jmri/layouts/hart/data/new_locos.json").read_text(encoding="utf-8"))
        self.assertEqual([locos.roster_entry(rows[e["id"]]) for e in committed], committed)

    def test_publish_takes_only_queued_locos(self) -> None:
        """A row added to the master without a loco_queue.csv entry is not published or carded."""
        with (ROOT / "ops/hart-ops/data/loco_queue.csv").open(newline="", encoding="utf-8") as fh:
            queue = list(csv.DictReader(fh))
        self.assertEqual([q["roster_id"] for q in queue if not q["published"]], [])
        self.assertEqual([q["roster_id"] for q in queue if not q["card_printed"]], [])


if __name__ == "__main__":
    unittest.main()
