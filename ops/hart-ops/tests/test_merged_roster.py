"""The merged car roster with the ROSTER_TYPO_IDS map gone (ADR-039 lane L7).

The map listed ten misread or wrong-road ids and dropped them from the merged roster. The car
master and the legacy roster carry only the right ids, so the build makes the same roster
without it: these tests hold that.
"""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import build_merged_car_roster as b  # noqa: E402

# The ten renames, applied once in the master (old id -> right id).
RENAMED = {
    "BO446063": "BO466063",
    "UTLX32638": "UTLX32642",
    "UTLX39084": "UTLX39042",
    "CO37700": "CO377700",
    "CO306585": "CO306607",
    "PRR474261": "PRR474563",
    "SHPX22425": "SHPX22329",
    "GATX31028": "GATX31090",
    "MSTL52763": "MSTL52673",
    "BO371604": "PRR371604",
}


def car_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.lstrip().startswith("<car ")]


class MergedRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cars, _ = b.merge_roster()

    def test_old_ids_are_gone_from_the_inputs(self):
        legacy = {c.get("id") for c in ET.parse(b.SOURCE_ROSTER).getroot().findall("./cars/car")}
        master = {b.manifest_car_id(r) for r in b.load_manifest_freight()}
        for old in RENAMED:
            self.assertNotIn(old, legacy, f"{old} is back in {b.SOURCE_ROSTER.name}")
            self.assertNotIn(old, master, f"{old} is back in {b.MANIFEST_CSV.name}")

    def test_right_ids_are_built(self):
        for old, new in RENAMED.items():
            self.assertIn(new, self.cars)
            self.assertNotIn(old, self.cars)

    def test_build_matches_the_committed_roster(self):
        cars = self.cars
        built = [b.format_car_line(cars[cid]) for cid in sorted(cars, key=lambda i: b.car_sort_key(cars[i]))]
        self.assertEqual(
            built, car_lines(b.OUTPUT_ROSTER),
            f"{b.OUTPUT_ROSTER.name} differs from a fresh build; run build_merged_car_roster.py",
        )


if __name__ == "__main__":
    unittest.main()
