"""Search result ranking: runs search_rank_test.js with node; skipped when node is missing."""
import shutil
import subprocess
import unittest
from pathlib import Path

JS = Path(__file__).with_name("search_rank_test.js")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SearchRank(unittest.TestCase):
    def test_ranking(self):
        r = subprocess.run(["node", str(JS)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
