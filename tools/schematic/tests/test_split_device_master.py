"""split_device_master.py: the one-time split of devices.csv into devices_generated.csv and devices_field.csv
(ADR-029 amendment, 2026-11-21). Its rule holds the committed pair (split(load()) gives both files byte for byte),
and the commit that made the split merged back to the last devices.csv byte for byte."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import split_device_master as sdm  # noqa: E402
from hartlib import devices  # noqa: E402

ROOT = HERE.parents[2]
DATA = "jmri/layouts/hart/data"


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


class TheCommittedPair(unittest.TestCase):
    def test_the_rule_splits_the_merged_view_back_into_the_two_files(self):
        files = devices.Files.here()
        for path, text in sdm.texts(devices.load(files), files).items():
            self.assertEqual(path.read_text(encoding="utf-8"), text, path.name)

    def test_every_staging_device_has_a_field_row_and_only_owner_cells(self):
        field = devices.field_index()
        staging = [r for r in devices.load() if r["level"] == "1" and r["role"] not in ("part", "spare")
                   and r["layer"] in ("turnout", "fb", "occupancy", "block")]
        self.assertEqual(len(staging), 168)
        self.assertFalse([k for k in field if k[2].startswith("unused ")])     # a spare is wiring.csv's alone
        self.assertTrue(all(devices.key_of(r) in field for r in staging))
        for f in field.values():
            self.assertEqual({c for c in devices.COLUMNS if f[c]} - set(devices.KEY), {c for c in devices.FIELD_COLUMNS
                                                                                    if f[c]})

    def test_the_owner_cells_are_not_in_the_generated_file_too(self):
        field = devices.field_index()
        for g in devices.generated_rows():
            f = field.get(devices.key_of(g))
            if f is None:
                continue
            for c in devices.FIELD_COLUMNS:
                if f[c] and devices.OCCUPANCY_MARK not in f[c]:
                    self.assertEqual(g[c], "", f"{devices.key_text(devices.key_of(g))}: {c}")
        self.assertEqual(devices.redundant(devices.generated_rows(), devices.field_rows()), [])

    def test_a_wired_block_keeps_the_owners_words_and_marks_its_detector(self):
        f = devices.field_index()["1", "block", "OS Switch 1"]
        self.assertEqual(f["jmri_comment"], "Brick CP, Switch 1; {occupancy}")
        self.assertEqual(f["node"], "")                  # wiring.csv's pin gives it


class TheSplitCommit(unittest.TestCase):
    def test_the_split_merged_back_to_the_last_one_file_master(self):
        found = git("log", "--diff-filter=A", "--format=%H", "--", f"{DATA}/{devices.FIELD_FILE}")
        commits = found.stdout.decode().split()
        if found.returncode or not commits:
            raise unittest.SkipTest("the split commit is not in this clone's history")
        c = commits[-1]
        old = git("show", f"{c}^:{DATA}/{devices.ONE_FILE}")
        if old.returncode:
            raise unittest.SkipTest("the commit before the split is not in this clone")
        with tempfile.TemporaryDirectory() as d:
            files = devices.Files.under(Path(d))
            for path, name in ((files.master, devices.GENERATED_FILE), (files.field, devices.FIELD_FILE)):
                path.write_bytes(git("show", f"{c}:{DATA}/{name}").stdout)
            self.assertEqual(devices.master_text(devices.load(files)).encode("utf-8"), old.stdout)


if __name__ == "__main__":
    unittest.main()
