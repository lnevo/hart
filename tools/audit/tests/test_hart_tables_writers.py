"""While HART_TABLES is set nothing is written: every table writer, profile copier and generator of a committed
output that reads the tables stops before writing (hartlib.paths.exit_if_overridden, or hartlib Tables.save).

Each runs in its writing mode with HART_TABLES on a temp copy and HOME on a temp folder (so no JMRI profile is
near), and must exit non-zero with the check-only message, leaving the copy, the repo and HOME untouched.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
S = "jmri/layouts/hart/scripts/"
WRITERS = (
    (S + "polish_hart_layout_editor.py", []), (S + "polish_hart_layout_editor.py", ["--block-labels-only"]),
    (S + "reconcile_dispatcher_stations.py", ["--no-sync"]),
    (S + "restore_manual_sml_pairs.py", ["--reference", "jmri/layouts/hart/output/tables.xml"]),
    (S + "disable_digicon_sml_in_tables.py", []), (S + "refresh_bean_comments.py", []),
    (S + "apply_nx_layer.py", []), (S + "apply_le_sml_facing.py", []), (S + "apply_le_cleanup.py", []),
    (S + "apply_yard_throat_blocks.py", []), (S + "add_yard_ladder_le_icons.py", []),
    (S + "add_digicon_le_signal_icons.py", []), (S + "apply_public_names.py", ["--apply"]),
    (S + "sync_public_name_map.py", ["--apply-comments"]), (S + "cleanup_uss_ctc_leftovers.py", ["--apply"]),
    (S + "uss_switch_only_columns.py", ["--apply"]), (S + "retarget_dispatcher_traininfo_transits.py", []),
    (S + "build_hart_signal_heads.py", []), (S + "export_track_lengths.py", []),
    (S + "capture_public_name_baseline.py", []), (S + "speedmatch/build_routes.py", []),
    ("www/scripts/build_layout_index.py", []), ("www/scripts/build_tables_browser.py", []),
    ("tools/ops/status_counts.py", []), ("tools/schematic/build_cats_panel.py", []),
    ("tools/schematic/build_signals.py", []), ("tools/schematic/build_layout_le.py", ["--levels", "staging"]),
)


def git_status() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                          capture_output=True, text=True, check=True).stdout


class NothingWrittenUnderHartTables(unittest.TestCase):
    def test_every_writer_stops(self) -> None:
        before_repo = git_status()
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "home"
            home.mkdir()
            copy = Path(d) / "tables.xml"
            copy.write_bytes((ROOT / "jmri/layouts/hart/output/tables.xml").read_bytes())
            before = copy.read_bytes()
            env = {**os.environ, "HART_TABLES": str(copy), "HOME": str(home), "HART_GUARD_JMRI_RUNNING": "0"}
            for script, args in WRITERS:
                with self.subTest(script=script, args=args):
                    done = subprocess.run([sys.executable, str(ROOT / script), *args], cwd=ROOT, env=env,
                                          capture_output=True, text=True, timeout=300)
                    self.assertNotEqual(0, done.returncode, done.stdout[-500:])
                    self.assertIn("HART_TABLES is set", done.stdout + done.stderr)
                    self.assertEqual(before, copy.read_bytes())
            self.assertEqual([], list(home.rglob("*")))
        self.assertEqual(before_repo, git_status())


if __name__ == "__main__":
    unittest.main()
