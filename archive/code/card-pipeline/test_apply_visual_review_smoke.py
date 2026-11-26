"""Smoke test of the archived apply_visual_review.py, kept beside it. It imports modules from ops/hart-ops/card_pipeline."""
import contextlib
import csv
import io
import sys
import tempfile
import unittest
import unittest.mock as mock
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "ops/hart-ops/card_pipeline"))
sys.path.insert(0, str(HERE))

import apply_visual_review  # noqa: E402


class VisualReviewSmoke(unittest.TestCase):
    def test_apply_review_rewrites_the_metadata_csv(self):
        source = next(iter(apply_visual_review.VISUAL))
        review = apply_visual_review.VISUAL[source]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            roster = tmp / "roster.xml"
            root = ET.Element("operations-config")
            cars = ET.SubElement(root, "cars")
            ET.SubElement(cars, "car", id=review["roster_id"], roadName="NW",
                          roadNumber="1", type="Flatcar", length="40", weight="1",
                          weightTons="2")
            ET.ElementTree(root).write(roster)
            meta = tmp / "image_metadata.csv"
            with meta.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=apply_visual_review.CSV_COLUMNS)
                w.writeheader()
                w.writerow({"source_image": source})
                w.writerow({"source_image": "unreviewed.png", "car_type": "Locomotive"})
            with mock.patch.object(apply_visual_review, "ROSTER_XML", roster), \
                    mock.patch.object(apply_visual_review, "METADATA_CSV", meta):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = apply_visual_review.main()
            self.assertEqual(code, 0)
            with meta.open(newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["match_confidence"], "visual_review")
            self.assertEqual(rows[0]["roster_id"], review["roster_id"])
            self.assertEqual(rows[0]["roster_road"], "NW")
            self.assertEqual(rows[1]["source_image"], "unreviewed.png")


if __name__ == "__main__":
    unittest.main()
