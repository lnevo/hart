"""tools/hosts/run_panelpro_roundtrip.sh against a fake StartJMRI (the Sandbox of test_panelpro_wrappers.py): it
refuses while JMRI or CATS runs, hands the Jython script a Store path in the gitignored pulled/ folder (never the
repo's tables.xml), and fails clearly when PanelPro leaves no Store. The comparison itself is hartlib's
(tools/hartlib/tests/test_tables_build.py, RoundTrip)."""
from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_panelpro_wrappers import ROOT, WrapperCase, _default_signals  # noqa: E402

WRAPPER = "tools/hosts/run_panelpro_roundtrip.sh"
SCRIPT = "jmri/layouts/hart/scripts/panelpro_roundtrip.py"


class RoundTripWrapper(WrapperCase):
    def setUp(self) -> None:
        super().setUp()
        for rel in (WRAPPER, SCRIPT):
            (self.box.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, self.box.root / rel)

    def run_wrapper(self, **extra: str) -> subprocess.CompletedProcess[str]:
        env = self.box.env(HART_ROUNDTRIP_LOG=str(self.box.state / "rt.log"), **extra)
        return subprocess.run(["/bin/bash", str(self.box.root / WRAPPER)], env=env, capture_output=True, text=True,
                              timeout=90, cwd=self.box.tmp, preexec_fn=_default_signals)

    def test_running_jmri_or_cats_is_refused_before_anything_changes(self) -> None:
        done = self.run_wrapper(HART_GUARD_JMRI_RUNNING="1")
        self.assertEqual(1, done.returncode)
        self.assertIn("Quit PanelPro, DecoderPro and CATS first", done.stderr)
        self.assertFalse((self.box.state / "launch_arg").exists())
        self.assert_restored()

    def test_the_store_goes_to_the_pulled_folder_and_a_missing_one_fails(self) -> None:
        done = self.run_wrapper(FAKE_MODE="marker", FAKE_MARKER_FROM="HART_ROUNDTRIP_MARKER")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("left no Store or block path counts", done.stderr)
        env = dict(line.split("=", 1) for line in (self.box.state / "env").read_text().splitlines() if "=" in line)
        store = Path(env["HART_ROUNDTRIP_STORE"])
        self.assertEqual(self.box.root / "jmri/layouts/hart/output/pulled", store.parent)
        self.assertTrue(store.name.startswith("roundtrip-"), store)
        self.assertEqual(f"{store}.paths.tsv", env["HART_ROUNDTRIP_PATHS"])
        self.assert_restored()


if __name__ == "__main__":
    unittest.main()
