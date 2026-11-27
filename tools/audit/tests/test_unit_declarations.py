"""The unit jobs' stamp declarations (tools/audit/check_stamps.py BY_KIND and EXTRA) name the files each suite reads,
not whole folders, so a data edit no suite reads is light (tools/ci/changed_kind.py). For each narrowed declaration:
a file the suite reads is still covered and makes the change full, and a file beside it that the suite does not read
is not covered,
and with that job's declaration the only one, the file beside them is not full on its account.

unit-guards test_name_copies still reads every tracked text file (its rename test scans the real checkout), and other
unit-guards tests read data masters their declarations do not name yet, so with the real declarations every data
file is still full."""
from __future__ import annotations

import dataclasses
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "ci"))
sys.path.insert(0, str(ROOT / "tools" / "audit"))
import changed_kind  # noqa: E402
import check_stamps  # noqa: E402

NAME_COPIES = "unit-guards test_name_copies"

# job -> (files it reads, files beside them it does not read): each a tracked file, from a traced run of the job
CASES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "unit-portal": (("ops/hart-ops/data/industries.csv", "docs/ops/schematic-system-draft.svg", "docs/INDEX.md"),
                    ("ops/hart-ops/data/trains.csv", "docs/wiring/lcos/lcos_signal_logic.csv",
                     "docs/data/entities.csv")),
    "unit-hart-ops": (("ops/hart-ops/data/image_metadata.csv",
                       "docs/ops/HART Railroad Scale Operating Instructions.docx"),
                      ("docs/data/entities.csv", "docs/wiring/lcos/lcos_signal_logic.csv")),
    "unit-anyrail": (("www/build/track-plan.html",), ("docs/data/entities.csv",)),
    "unit-guards test_check_sh_tables": (("www/assets/layout/HART_le_schematic.png",
                                          "docs/pipeline-map/pipeline_map.json"), ("www/data/site.json",)),
    "unit-guards test_hart_tables_writers": (("www/scripts/build_tables_browser.py",),
                                             ("www/scripts/share-cards.json",)),
    "unit-guards test_helix_stl_index": (("www/scripts/build_helix_page.py",), ("www/scripts/provenance.json",)),
    "unit-guards test_jmri_process_patterns": (("ops/hart-ops/bin/apply_hart_seed.sh",),
                                               ("ops/hart-ops/data/trains.csv", "docs/data/entities.csv")),
    "unit-guards test_manifest_scans": (("docs/data/entities.csv",), ("docs/wiring/lcos/lcos_signal_logic.csv",)),
    "unit-guards test_publish_draft": (("docs/ops/stations/barn.svg", "ops/hart-ops/data/crew.json"),
                                       ("ops/hart-ops/data/trains.csv",)),
    "unit-guards test_write_inventory": (("docs/wiring/LCOS_Layout_Inventory_v86.xlsx",),
                                         ("docs/wiring/lcos/lcos_signal_logic.csv",)),
    "unit-guards test_docs_index": ((), ("docs/data/entities.csv",)),
    "unit-hosts test_live_paths": ((), ("docs/data/entities.csv",)),
    "unit-hosts test_host_copies": (("ops/packages/README.md",), ("ops/hart-ops/data/trains.csv",)),
    "unit-hosts test_pull_tables": ((), ("ops/hart-ops/data/trains.csv",)),
    "unit-jmri test_speedmatch": (("docs/jmri/speedmatching/profile-2026-11-08/block_events.csv",),
                                  ("docs/jmri/speedmatching/profile-2026-11-13/profile.csv",)),
    "unit-jmri test_infer_block_lengths": (("docs/jmri/speedmatching/profile-2026-11-08/block_events.csv",),
                                           ("docs/jmri/speedmatching/profile-2026-11-13/profile.csv",)),
    "unit-jmri test_speedmatch_distance": (("docs/jmri/speedmatching/RUNBOOK.md",),
                                           ("docs/jmri/speedmatching/profile-2026-11-13/profile.csv",)),
    "unit-jmri test_speedmatch_dashboard": ((), ("docs/jmri/speedmatching/profile-2026-11-13/profile.csv",)),
    "unit-jmri test_speedmatch_publish_live": ((), ("docs/jmri/speedmatching/profile-2026-11-13/profile.csv",)),
    "unit-jmri test_speedmatch_site_export": (("www/ai/speed-runs.html",),
                                              ("docs/jmri/speedmatching/profile-2026-11-13/profile.csv",)),
}

def covered(job: str, path: str) -> bool:
    pats = check_stamps.declared(job)
    assert pats is not None, job
    return any(check_stamps.ps._glob_match(path, pat) for pat in pats)


class NarrowedDeclarations(unittest.TestCase):
    d: changed_kind.Declarations

    @classmethod
    def setUpClass(cls) -> None:
        cls.d = changed_kind.load_declarations()

    def only(self, job: str) -> changed_kind.Declarations:
        """The real declarations with this one unit job's as the only unit declaration."""
        pats = check_stamps.declared(job)
        assert pats is not None, job
        return dataclasses.replace(self.d, units={job: pats})

    def test_the_examples_are_tracked_files(self) -> None:
        for job, (reads, unread) in CASES.items():
            for path in (*reads, *unread):
                with self.subTest(job=job, path=path):
                    self.assertTrue((ROOT / path).is_file(), path)

    def test_each_job_covers_what_it_reads_and_not_the_files_beside_them(self) -> None:
        for job, (reads, unread) in CASES.items():
            with self.subTest(job=job):
                self.assertEqual([], [p for p in reads if not covered(job, p)], "read but not declared")
                self.assertEqual([], [p for p in unread if covered(job, p)], "declared but not read")

    def test_its_reads_are_full_and_the_files_beside_them_are_not_its_doing(self) -> None:
        """With only that job declared, a data file it reads is full and names it, and a data file beside it is
        light: the narrowed declaration alone no longer makes that edit full."""
        for job, (reads, unread) in CASES.items():
            d = self.only(job)
            # data files only: code is full by its suffix, Markdown takes the docs path
            data = [p for p in reads if not p.endswith(changed_kind.CODE_SUFFIXES) and not changed_kind.is_docs(p)]
            for path in data:
                with self.subTest(job=job, path=path):
                    v = changed_kind.verdict([path], load=lambda _root: d)
                    if "may be read by" in v.why:
                        self.assertIn(f"may be read by {job}", v.why)
                    self.assertEqual("full", v.kind, v.why)
            for path in unread:
                with self.subTest(job=job, path=path):
                    v = changed_kind.verdict([path], load=lambda _root: d)
                    self.assertNotIn("may be read by", v.why)

    def test_with_the_real_declarations_test_name_copies_still_reads_every_data_file(self) -> None:
        for path in ("docs/wiring/lcos/lcos_signal_logic.csv",
                     "docs/jmri/speedmatching/profile-2026-11-13/profile.csv"):
            with self.subTest(path):
                v = changed_kind.verdict([path], load=lambda _root: self.d)
                self.assertEqual("full", v.kind)
                self.assertIn("may be read by", v.why)
                self.assertTrue(covered(NAME_COPIES, path))


if __name__ == "__main__":
    unittest.main()
