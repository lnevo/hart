"""panel_counts.json is the one source of the stored-table counts: audit_panel_graph.load_panel_counts reads it for
the audit, and the PanelPro smoke test (Jython) reads the same file from the path run_panelpro_smoke_test.sh passes.
Both take the same counts from it and both refuse a file they cannot trust, naming the file and the key."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_panel_contracts as apc  # noqa: E402
from audit_panel_graph import COUNTS, PANEL_COUNTS, PanelCounts, StoredCounts, load_panel_counts  # noqa: E402
from hartlib.errors import FactsError  # noqa: E402
from test_panelpro_smoke_steps import steps  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
WRAPPER = ROOT / "jmri/layouts/hart/scripts/run_panelpro_smoke_test.sh"
GOOD = {"masts": 3, "hand_drawn": {"sml": 4, "sections": 5, "transits": 6},
        "generated": {"sml": 7, "sections": 8, "transits": 9}, "traininfo": 10}


class Files(unittest.TestCase):
    def write(self, data: object) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "panel_counts.json"
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    def bad_files(self) -> list[tuple[str, object, str]]:
        """(case, file contents, what both readers' message holds)."""
        return [
            ("not JSON", "{", "cannot read the panel counts"),
            ("a key less", {k: v for k, v in GOOD.items() if k != "traininfo"}, "expected the keys"),
            ("a key more", {**GOOD, "extra": 1}, "expected the keys"),
            ("a list", [1, 2], "expected the keys"),
            ("a panel key less", {**GOOD, "generated": {"sml": 1, "sections": 2}}, "generated: expected the keys"),
            ("a bool", {**GOOD, "masts": True}, "masts: expected a whole number"),
            ("a negative", {**GOOD, "traininfo": -1}, "traininfo: expected a whole number"),
            ("a float", {**GOOD, "hand_drawn": {"sml": 1.5, "sections": 2, "transits": 3}},
             "hand_drawn.sml: expected a whole number"),
            ("a string", {**GOOD, "generated": {"sml": 1, "sections": "2", "transits": 3}},
             "generated.sections: expected a whole number"),
        ]


class AuditReader(Files):
    def test_reads_each_count(self) -> None:
        self.assertEqual(load_panel_counts(self.write(GOOD)),
                         PanelCounts(3, StoredCounts(4, 5, 6), StoredCounts(7, 8, 9), 10))

    def test_the_audit_holds_the_tables_to_the_files_counts(self) -> None:
        self.assertEqual(COUNTS, load_panel_counts(PANEL_COUNTS))
        self.assertEqual(apc.EXPECTED_SML, {False: COUNTS.hand_drawn.sml, True: COUNTS.generated.sml})
        self.assertEqual(apc.EXPECTED_GRAPH, {False: COUNTS.hand_drawn[1:], True: COUNTS.generated[1:]})
        self.assertEqual(apc.EXPECTED_TRAININFO, COUNTS.traininfo)

    def test_refuses_a_file_it_cannot_trust(self) -> None:
        for case, data, message in self.bad_files():
            with self.subTest(case=case):
                path = self.write(data)
                with self.assertRaisesRegex(FactsError, message) as caught:
                    load_panel_counts(path)
                self.assertIn(path.name, str(caught.exception))

    def test_refuses_a_missing_file(self) -> None:
        with self.assertRaisesRegex(FactsError, "cannot read the panel counts"):
            load_panel_counts(ROOT / "no/such/panel_counts.json")


class SmokeReader(Files):
    def setUp(self) -> None:
        self.ns = steps()

    def test_takes_the_same_counts_as_the_audit(self) -> None:
        got = self.ns["expected_counts"](str(PANEL_COUNTS), set())
        self.assertEqual(tuple(got), (COUNTS.masts, COUNTS.generated.sections, COUNTS.generated.transits,
                                      COUNTS.traininfo))

    def test_expects_no_section_or_transit_while_the_dispatcher_is_parked(self) -> None:
        got = steps("dispatcher")["expected_counts"](str(self.write(GOOD)), {"dispatcher"})
        self.assertEqual(tuple(got), (3, 0, 0, 10))

    def test_refuses_a_file_it_cannot_trust(self) -> None:
        error = self.ns["CountsError"]
        for case, data, message in self.bad_files():
            with self.subTest(case=case):
                path = str(self.write(data))
                with self.assertRaisesRegex(error, message) as caught:
                    self.ns["expected_counts"](path, set())
                self.assertIn(path, str(caught.exception))

    def test_refuses_no_path_or_a_missing_file(self) -> None:
        error = self.ns["CountsError"]
        with self.assertRaisesRegex(error, "HART_PANEL_COUNTS names no panel counts file"):
            self.ns["expected_counts"]("", set())
        with self.assertRaisesRegex(error, "cannot read the panel counts"):
            self.ns["expected_counts"](str(ROOT / "no/such/panel_counts.json"), set())


class Wrapper(unittest.TestCase):
    def test_the_wrapper_passes_the_audits_file(self) -> None:
        """run_panelpro_smoke_test.sh's HART_PANEL_COUNTS line, run in bash with ROOT set: the audit's file."""
        line = next(ln for ln in WRAPPER.read_text(encoding="utf-8").splitlines()
                    if ln.startswith("export HART_PANEL_COUNTS="))
        done = subprocess.run(["bash", "-c", f'{line}; printf "%s" "$HART_PANEL_COUNTS"'],
                              env={**os.environ, "ROOT": str(ROOT)}, capture_output=True, text=True, check=True)
        self.assertEqual(Path(done.stdout), PANEL_COUNTS)


if __name__ == "__main__":
    unittest.main()
