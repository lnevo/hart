"""The unit jobs' stamp declarations (tools/audit/check_stamps.py BY_KIND and EXTRA) name the files each suite reads,
not whole folders, so a data edit no suite reads is light (tools/ci/changed_kind.py). For each narrowed declaration:
a file the suite reads is still covered and makes the change full, and a file beside it that the suite does not read
is not covered. With that job's declaration the only one loaded, an edit to the file beside it is not full because of
that job. With the real declarations, the data files in LIGHT are light and the files in FULL are full for the reason
given, and the master lists the data checks' tests declare are the ones their sources name."""
from __future__ import annotations

import dataclasses
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "ci"))
sys.path.insert(0, str(ROOT / "tools" / "audit"))
sys.path.insert(0, str(ROOT / "tools" / "hartlib" / "src"))
import changed_kind  # noqa: E402
import check_stamps  # noqa: E402
from hartlib import hand_tables  # noqa: E402

ENTITIES = hand_tables.ENTITIES.relative_to(ROOT).as_posix()
PROFILE_08 = "docs/jmri/speedmatching/profile-2026-11-08"       # the speed matching runs the jmri tests replay
PROFILE_13 = "docs/jmri/speedmatching/profile-2026-11-13"       # a later profile no test reads
LCOS_LOGIC = "docs/wiring/lcos/lcos_signal_logic.csv"           # an LCOS master with a sidecar
TRAINS = "ops/hart-ops/data/trains.csv"
LOCOS = "ops/hart-ops/data/locos.csv"
CAR_QUEUE = "ops/hart-ops/data/car_queue.csv"                   # the car intake queue: no unit job reads it
CREW = "ops/hart-ops/data/crew.json"                            # the crew master

# job -> (files it reads, files beside them it does not read): each a tracked file, from a traced run of the job
CASES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "unit-portal": (("ops/hart-ops/data/industries.csv", "docs/ops/schematic-system-draft.svg", "docs/INDEX.md"),
                    (TRAINS, LCOS_LOGIC, ENTITIES)),
    "unit-hart-ops": (("ops/hart-ops/data/image_metadata.csv", "ops/hart-ops/data/OperationsCarRoster.xml",
                       "ops/hart-ops/operator_logos/party_logo_map.json", "ops/hart-ops/requirements-test.txt",
                       "docs/ops/HART Railroad Scale Operating Instructions.docx", "www/data/crew.json"),
                      (ENTITIES, LCOS_LOGIC, TRAINS, LOCOS, CAR_QUEUE, "ops/packages/README.md",
                       "www/data/site.json")),
    "unit-schematic": ((CREW, "ops/hart-ops/data/industries.csv", "ops/hart-ops/publications/crew_master.py",
                        "docs/ops/stations/barn.svg", "www/data/publications.json",
                        "www/crew/maps/barn/index.html"),
                       (TRAINS, CAR_QUEUE, "ops/hart-ops/data/image_metadata.csv", "www/data/site.json")),
    "unit-anyrail": (("www/build/track-plan.html",), (ENTITIES,)),
    "unit-guards test_check_sh_tables": (("www/assets/layout/HART_le_schematic.png",
                                          "docs/pipeline-map/pipeline_map.json"), ("www/data/site.json",)),
    "unit-guards test_hart_tables_writers": (("www/scripts/build_tables_browser.py",),
                                             ("www/scripts/share-cards.json",)),
    "unit-guards test_helix_stl_index": (("www/scripts/build_helix_page.py",), ("www/scripts/provenance.json",)),
    "unit-guards test_jmri_process_patterns": (("ops/hart-ops/bin/apply_hart_seed.sh",), (TRAINS, ENTITIES)),
    "unit-guards test_manifest_scans": ((ENTITIES,), (LCOS_LOGIC,)),
    "unit-guards test_publish_draft": (("docs/ops/stations/barn.svg", "ops/hart-ops/data/crew.json"), (TRAINS,)),
    "unit-guards test_write_inventory": (("docs/wiring/LCOS_Layout_Inventory_v86.xlsx",), (LCOS_LOGIC,)),
    "unit-guards test_docs_index": ((), (ENTITIES,)),
    "unit-guards test_name_copies": ((), (ENTITIES, LCOS_LOGIC, TRAINS, f"{PROFILE_13}/profile.csv")),
    "unit-guards test_check_data": ((LCOS_LOGIC, "docs/wiring/lcos/lcos_signal_logic.columns.csv", TRAINS),
                                    (ENTITIES, "ops/hart-ops/data/image_metadata.csv")),
    "unit-guards test_check_hand_tables": ((ENTITIES, LCOS_LOGIC, "ops/hart-ops/data/image_metadata.csv"),
                                           ("docs/wiring/lcos/lcos_signal_logic.columns.csv",
                                            "ops/hart-ops/data/car_queue.csv")),
    "unit-guards test_check_fleet_gallery": ((LOCOS, "ops/hart-ops/data/image_metadata.csv"), (TRAINS,)),
    "unit-guards test_check_locos": ((LOCOS, "ops/hart-ops/data/loco_queue.csv"), (TRAINS,)),
    "unit-guards test_check_roster": ((LOCOS,), ("ops/hart-ops/data/loco_queue.csv",)),
    "unit-guards test_check_json": (("www/scripts/published-files.json",), ("www/scripts/share-cards.json",)),
    "unit-hosts test_live_paths": ((), (ENTITIES,)),
    "unit-hosts test_host_copies": (("ops/packages/README.md",), (TRAINS,)),
    "unit-hosts test_pull_tables": ((), (TRAINS,)),
    "unit-hosts test_roster_master": ((LOCOS,), (TRAINS,)),
    "unit-jmri test_speedmatch": ((f"{PROFILE_08}/block_events.csv",), (f"{PROFILE_13}/profile.csv",)),
    "unit-jmri test_infer_block_lengths": ((f"{PROFILE_08}/block_events.csv",), (f"{PROFILE_13}/profile.csv",)),
    "unit-jmri test_speedmatch_distance": (("docs/jmri/speedmatching/RUNBOOK.md",), (f"{PROFILE_13}/profile.csv",)),
    "unit-jmri test_speedmatch_dashboard": ((), (f"{PROFILE_13}/profile.csv",)),
    "unit-jmri test_speedmatch_publish_live": ((), (f"{PROFILE_13}/profile.csv",)),
    "unit-jmri test_speedmatch_site_export": (("www/ai/speed-runs.html",), (f"{PROFILE_13}/profile.csv",)),
    "unit-jmri test_speedmatch_speed_table": ((f"{PROFILE_08}/manual_laps.csv", f"{PROFILE_08}/results.csv"),
                                              (f"{PROFILE_08}/block_summary.csv",)),
}

# Data files that the real declarations call light: no unit job reads them, and only make static's checks do.
LIGHT = (f"{PROFILE_13}/profile.csv", f"{PROFILE_13}/site_labels.json", f"{PROFILE_08}/block_summary.csv", CAR_QUEUE)
# Files the real declarations call full, with the reason's words: code, a master a unit job reads (trains.csv by the
# data check's test, no longer by the ops suites), and www/, which the portal job reads whole.
FULL = {
    "tools/ci/changed_kind.py": "is code or configuration",
    LCOS_LOGIC: "may be read by unit-guards test_check_data",
    f"{PROFILE_08}/results.csv": "may be read by unit-jmri test_speedmatch_speed_table",
    TRAINS: "may be read by unit-guards test_check_data and 1 more",
    CREW: "may be read by unit-portal",
    "www/data/site.json": "is read by check.sh job portal",
}


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec is not None and spec.loader is not None, rel
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NarrowedDeclarations(unittest.TestCase):
    d: changed_kind.Declarations

    @classmethod
    def setUpClass(cls) -> None:
        cls.d = changed_kind.load_declarations()

    def declared(self, job: str) -> tuple[str, ...]:
        pats = check_stamps.declared(job)
        assert pats is not None, job
        return pats

    def covered(self, job: str, path: str) -> bool:
        return any(self.d.covers(pat, path) for pat in self.declared(job))

    def only(self, job: str) -> changed_kind.Declarations:
        """The real declarations with this one unit job's as the only unit declaration."""
        return dataclasses.replace(self.d, units={job: self.declared(job)})

    def verdict(self, path: str, d: changed_kind.Declarations | None = None) -> changed_kind.Verdict:
        decl = d or self.d
        return changed_kind.verdict([path], load=lambda _root: decl)

    def test_the_examples_are_tracked_files(self) -> None:
        examples = (*(p for reads, unread in CASES.values() for p in (*reads, *unread)), *LIGHT, *FULL)
        for path in examples:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)

    def test_each_job_covers_what_it_reads_and_not_the_files_beside_them(self) -> None:
        for job, (reads, unread) in CASES.items():
            with self.subTest(job=job):
                self.assertEqual([], [p for p in reads if not self.covered(job, p)], "read but not declared")
                self.assertEqual([], [p for p in unread if self.covered(job, p)], "declared but not read")

    def test_its_reads_are_full_and_the_files_beside_them_are_not_its_doing(self) -> None:
        """With only that job declared, a data file it reads is full and names it, and a data file beside it is
        light: the narrowed declaration alone no longer makes that edit full."""
        for job, (reads, unread) in CASES.items():
            d = self.only(job)
            no_units = dataclasses.replace(self.d, units={})
            # data files only: code is full by its suffix, Markdown takes the docs path
            data = [p for p in reads if not p.endswith(changed_kind.CODE_SUFFIXES) and not changed_kind.is_docs(p)]
            for path in data:
                with self.subTest(job=job, path=path):
                    v = self.verdict(path, d)
                    self.assertEqual("full", v.kind, v.why)
                    # a file full before any unit declaration is read (its suffix, the map, a built file) is full
                    # for that reason; any other is full because this job reads it
                    if self.verdict(path, no_units).kind == "light":
                        self.assertIn(f"may be read by {job}", v.why)
            for path in unread:
                with self.subTest(job=job, path=path):
                    self.assertNotIn("may be read by", self.verdict(path, d).why)

    def test_with_the_real_declarations_the_light_examples_are_light(self) -> None:
        for path in LIGHT:
            with self.subTest(path):
                v = self.verdict(path)
                self.assertEqual("light", v.kind, v.why)
        for path, why in FULL.items():
            with self.subTest(path):
                v = self.verdict(path)
                self.assertEqual("full", v.kind, v.why)
                self.assertIn(why, v.why)


class MasterLists(unittest.TestCase):
    """check_stamps.SIDECAR_MASTERS and ENTITY_MASTERS are the masters outside the unit jobs' code that the data
    checks' sources name: a new master there must join the declaration, or an edit to it would be called light."""

    @staticmethod
    def outside_code(paths: list[str]) -> list[str]:
        cover = check_stamps.pm.covers
        return sorted(p for p in set(paths) if not any(cover(pat, p) for pat in check_stamps.CODE))

    def test_the_sidecar_masters_are_check_data_s(self) -> None:
        check_data = load("check_data_for_declarations", "tools/ops/check_data.py")
        masters = [m.relative_to(ROOT).as_posix() for s in check_data.find_sidecars() for m in check_data.master_files(s)]
        self.assertEqual(self.outside_code(masters), sorted(check_stamps.SIDECAR_MASTERS))

    def test_the_entity_masters_are_entities_csv_s(self) -> None:
        self.assertEqual(self.outside_code([ENTITIES, *hand_tables.master_files()]),
                         sorted(check_stamps.ENTITY_MASTERS))


if __name__ == "__main__":
    unittest.main()
