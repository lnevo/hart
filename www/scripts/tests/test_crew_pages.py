"""The session paperwork pages (js/crew.js) drawn from data/crew.json: runs crew_pages_test.js with node; skipped when
node is missing."""
import shutil
import subprocess
import unittest
from pathlib import Path

JS = Path(__file__).with_name("crew_pages_test.js")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class CrewPages(unittest.TestCase):
    def test_every_crew_page_renders(self) -> None:
        r = subprocess.run(["node", str(JS)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
