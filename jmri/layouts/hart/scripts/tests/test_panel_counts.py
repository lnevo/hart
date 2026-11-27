"""panel_counts.json is the one source of the stored-table counts: audit_panel_graph.load_panel_counts reads it for
the audit, and the PanelPro smoke test (Jython) reads the same file from the path run_panelpro_smoke_test.sh passes.
Both take the same counts from it and both refuse a file they cannot trust, naming the file and the key."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # test_panelpro_smoke_steps, beside it
import audit_panel_contracts as apc  # noqa: E402
import audit_panel_graph as apg  # noqa: E402
from audit_panel_graph import (  # noqa: E402
    PANEL_COUNTS, PanelCounts, PanelCountsError, StoredCounts, load_panel_counts, panel_counts,
)
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
        counts = panel_counts()
        self.assertEqual(counts, load_panel_counts(PANEL_COUNTS))
        self.assertEqual({g: apc.expected_sml(g) for g in (False, True)},
                         {False: counts.hand_drawn.sml, True: counts.generated.sml})
        self.assertEqual({g: apc.expected_graph(g) for g in (False, True)},
                         {False: counts.hand_drawn[1:], True: counts.generated[1:]})
        self.assertEqual(apc.expected_traininfo(), counts.traininfo)

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


class FirstUse(Files):
    """The audit reads the counts file on first use, not on import: a broken file stops the audit with
    PanelCountsError naming the file, and the counts are read once."""

    def setUp(self) -> None:
        panel_counts.cache_clear()
        self.addCleanup(panel_counts.cache_clear)

    def broken(self) -> Path:
        path = self.write("{")
        patcher = mock.patch.object(apg, "PANEL_COUNTS", path)
        patcher.start()
        self.addCleanup(patcher.stop)
        return path

    def test_a_broken_file_is_the_audits_error_on_first_use(self) -> None:
        path = self.broken()
        with self.assertRaisesRegex(PanelCountsError, "cannot read the panel counts") as caught:
            apc.expected_sml(True)
        self.assertIn(path.name, str(caught.exception))

    def test_the_audit_stops_naming_the_file(self) -> None:
        path = self.broken()
        out = io.StringIO()
        with mock.patch.object(apc, "load_staging_masts", return_value=[]), redirect_stdout(out):
            code = apc.main([])
        self.assertEqual(code, 1)
        self.assertIn("ERROR: ", out.getvalue())
        self.assertIn(path.name, out.getvalue())
        self.assertIn("cannot read the panel counts", out.getvalue())

    def test_the_file_is_read_once(self) -> None:
        path = self.write(GOOD)
        with mock.patch.object(apg, "PANEL_COUNTS", path):
            self.assertEqual(apc.expected_traininfo(), 10)
            path.write_text("{", encoding="utf-8")
            self.assertEqual(apc.expected_sml(True), 7)


class SmokeReader(Files):
    def setUp(self) -> None:
        self.ns = steps()

    def test_takes_the_same_counts_as_the_audit(self) -> None:
        got = self.ns["expected_counts"](str(PANEL_COUNTS), set())
        counts = panel_counts()
        self.assertEqual(tuple(got), (counts.masts, counts.generated.sections, counts.generated.transits,
                                      counts.traininfo))

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
