"""merge_ops writes the roster it was given, not always the main checkout's copy."""
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import car_ops_roster  # noqa: E402
import car_repo  # noqa: E402

HEADER = '<?xml version="1.0" encoding="utf-8"?>\n<?xml-stylesheet href="x"?>\n'


class WriteOps(unittest.TestCase):
    def test_writes_to_the_given_path_and_keeps_the_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "roster.xml"
            target.write_text(HEADER + "<operations-config><cars/></operations-config>\n", encoding="utf-8")
            real = car_repo.OPS_MERGED.read_bytes() if car_repo.OPS_MERGED.is_file() else None
            car_ops_roster.write_ops(ET.parse(target), target)
            self.assertTrue(target.read_text(encoding="utf-8").startswith(HEADER))
            after = car_repo.OPS_MERGED.read_bytes() if car_repo.OPS_MERGED.is_file() else None
            self.assertEqual(real, after)  # the main checkout's roster is untouched


if __name__ == "__main__":
    unittest.main()
