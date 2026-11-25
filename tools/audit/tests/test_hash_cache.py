"""check_stamps.HashCache: the shared file-hash cache keeps its entries while their folder is there and drops those of
a removed worktree on save (make remote makes a worktree per run, so the box's cache had grown to 747k entries, 5.6k
of them live, 2026-11-25)."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_stamps as cs  # noqa: E402


class HashCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_entries_of_a_removed_worktree_are_dropped_on_save(self) -> None:
        live, gone = self.tmp / "wt/live", self.tmp / "wt/gone"
        for root in (live, gone):
            (root / "data").mkdir(parents=True)
            (root / "data/a.csv").write_text("v1\n")
        store = self.tmp / "stamps/filehash.json"
        cache = cs.HashCache(store)
        sha = cache(live / "data/a.csv")
        cache(gone / "data/a.csv")
        (live / "data/b.csv").write_text("v2\n")
        cache(live / "data/b.csv")
        (live / "data/b.csv").unlink()            # a file gone from a live folder: kept, it costs one entry
        shutil.rmtree(gone)
        cache.save()
        kept = json.loads(store.read_text())
        self.assertEqual(set(kept), {str(live / "data/a.csv"), str(live / "data/b.csv")})
        self.assertEqual(kept[str(live / "data/a.csv")][2], sha)
        self.assertEqual(cs.HashCache(store)(live / "data/a.csv"), sha)

    def test_a_key_with_no_folder_part_is_kept(self) -> None:
        store = self.tmp / "filehash.json"
        store.write_text(json.dumps({"loose.txt": [1, 2, "x"]}))
        cache = cs.HashCache(store)
        (self.tmp / "a.csv").write_text("v1\n")
        cache(self.tmp / "a.csv")
        cache.save()
        self.assertIn("loose.txt", json.loads(store.read_text()))

    def test_a_clean_cache_is_not_rewritten(self) -> None:
        store = self.tmp / "filehash.json"
        cs.HashCache(store).save()
        self.assertFalse(store.exists())


if __name__ == "__main__":
    unittest.main()
