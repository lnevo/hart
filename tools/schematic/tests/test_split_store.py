"""split_store.py (R9d): the base a kept Store is split against (read_base), and that a failed apply, the
store_splits.csv row included, leaves every file as it was. Temporary folders only; the apply runs against stand-in
files and a stand-in build, so nothing in the repo is written."""
from __future__ import annotations

import contextlib
import hashlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hartlib/src"))
import split_store as S  # noqa: E402
from hartlib import devices  # noqa: E402


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReadBase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.store = self.dir / "pi-20261120-120000.xml"
        self.store.write_bytes(b"<layout-config><store/></layout-config>")
        self.head = subprocess.run(["git", "-C", str(S.ROOT), "rev-parse", "HEAD"], capture_output=True,
                                   text=True, check=True).stdout.strip()

    def note(self, text: str) -> None:
        Path(f"{self.store}.base").write_text(text + "\n", encoding="utf-8")

    def test_a_deploy_of_its_committed_file_is_the_base(self) -> None:
        committed = S.git("show", f"{self.head}:{S.TABLES_REL}").stdout
        self.note(f"deploy {sha(committed)} {self.head}")
        data, what = S.read_base(self.store, None, False)
        self.assertEqual(committed, data)
        self.assertEqual(f"deploy {self.head[:10]}", what)

    def test_a_deploy_of_another_file_finds_a_kept_copy_with_its_hash(self) -> None:
        shipped = b"<layout-config><shipped/></layout-config>"
        (self.dir / "pi-20261119-090000.xml").write_bytes(shipped)
        self.note(f"deploy {sha(shipped)} {self.head}")
        data, what = S.read_base(self.store, None, False)
        self.assertEqual(shipped, data)
        self.assertIn("store pi-20261119-090000.xml", what)
        self.assertIn("shipped another file", what)

    def test_a_deploy_of_another_file_with_no_kept_copy_has_no_base(self) -> None:
        self.note(f"deploy {sha(b'<gone/>')} {self.head}")
        data, what = S.read_base(self.store, None, False)
        self.assertIsNone(data)
        self.assertIn("shipped another file", what)
        self.assertIn("no kept file", what)

    def test_the_store_itself_is_never_its_own_base(self) -> None:
        self.note(f"store {sha(self.store.read_bytes())}")
        data, _ = S.read_base(self.store, None, False)
        self.assertIsNone(data)


class ApplyUndo(unittest.TestCase):
    def test_a_failed_store_splits_row_puts_every_file_back(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        files = {name: tmp / name for name in ("template.xml", devices.MASTER_FILE, "tables.xml", "store_splits.csv")}
        for f in files.values():
            f.write_text(f"before {f.name}\n", encoding="utf-8")
        build = tmp / "build.py"
        build.write_text(f"open({str(files['tables.xml'])!r}, 'w').write('rebuilt')\n", encoding="utf-8")
        new_doc = mock.Mock(tobytes=lambda: b"new template")
        plan = mock.Mock(by_content=frozenset(), fingerprint="abc")
        plan.of.return_value = []
        ctx = dict(template_doc=None, roots=dict(store=None, repo=None), rows=[], store_sha="x", base_what="none")
        with contextlib.ExitStack() as st:
            for attr, key in (("TEMPLATE", "template.xml"), ("DEVICES", devices.MASTER_FILE), ("TABLES", "tables.xml"),
                              ("SPLITS", "store_splits.csv")):
                st.enter_context(mock.patch.object(S, attr, files[key]))
            st.enter_context(mock.patch.object(S, "WRITES", tuple(files.values())))
            st.enter_context(mock.patch.object(S, "BUILD", build))
            st.enter_context(mock.patch.object(S.ss, "template_changes", return_value=[]))
            st.enter_context(mock.patch.object(S.ss, "new_template", return_value=new_doc))
            st.enter_context(mock.patch.object(S.ss, "device_edits", return_value=[]))
            st.enter_context(mock.patch.object(S.ss, "edited_rows", return_value=[]))
            st.enter_context(mock.patch.object(S.devices, "check_rows"))
            st.enter_context(mock.patch.object(S.tb, "read_template", return_value=new_doc))
            st.enter_context(mock.patch.object(S.ss, "normalised"))
            st.enter_context(mock.patch.object(S.ss, "verify", return_value=[]))
            st.enter_context(mock.patch.object(S, "record", side_effect=OSError("disk full")))
            err = io.StringIO()
            st.enter_context(contextlib.redirect_stderr(err))
            got = S.apply(tmp / "pi-1.xml", plan, ctx, S.ss.Choices())
        self.assertEqual(1, got)
        self.assertIn("could not be written", err.getvalue())
        for f in files.values():
            self.assertEqual(f"before {f.name}\n", f.read_text(encoding="utf-8"), f.name)


class ApplyWritesTheFieldFile(unittest.TestCase):
    def test_a_merged_device_lands_in_devices_field_csv_and_the_generated_file_is_untouched(self) -> None:
        """A DEVICE merge (here a Store's new device) is written to the field file, by key; the builders' file is
        never written by a split."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hartlib/tests"))
        from test_devices import unplaced
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        pair = devices.pair_copy(tmp / "data")
        before = devices.generated_rows(pair)
        others = {name: tmp / name for name in ("template.xml", "tables.xml", "store_splits.csv")}
        for f in others.values():
            f.write_text(f"before {f.name}\n", encoding="utf-8")
        build = tmp / "build.py"
        build.write_text("pass\n", encoding="utf-8")
        new_doc = mock.Mock(tobytes=lambda: b"new template")
        plan = mock.Mock(by_content=frozenset(), fingerprint="abc")
        plan.of.return_value = []
        ctx = dict(template_doc=None, roots=dict(store=None, repo=None), rows=[], store_sha="x", base_what="none")
        add = S.ss.RowAdd(tuple(unplaced().items()))
        with contextlib.ExitStack() as st:
            for attr, value in (("TEMPLATE", others["template.xml"]), ("DEVICES", pair.field),
                                ("DEVICE_FILES", pair), ("TABLES", others["tables.xml"]),
                                ("SPLITS", others["store_splits.csv"]), ("BUILD", build), ("ROOT", tmp),
                                ("WRITES", (others["template.xml"], pair.field, others["tables.xml"],
                                            others["store_splits.csv"]))):
                st.enter_context(mock.patch.object(S, attr, value))
            st.enter_context(mock.patch.object(S.ss, "template_changes", return_value=[]))
            st.enter_context(mock.patch.object(S.ss, "new_template", return_value=new_doc))
            st.enter_context(mock.patch.object(S.ss, "device_edits", return_value=[add]))
            st.enter_context(mock.patch.object(S.tb, "read_template", return_value=new_doc))
            st.enter_context(mock.patch.object(S.ss, "normalised"))
            st.enter_context(mock.patch.object(S.ss, "verify", return_value=[]))
            st.enter_context(mock.patch.object(S, "record"))
            st.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.assertEqual(0, S.apply(tmp / "pi-1.xml", plan, ctx, S.ss.Choices()))
        devices._read.cache_clear()             # read the generated file again: the split must not have written it
        self.assertEqual(before, devices.generated_rows(pair))
        field = devices.field_rows(pair)
        self.assertEqual([r["user_name"] for r in field if not r["level"]], ["Test 999"])
        self.assertTrue(devices.index(pair).is_unplaced("turnout", "Test 999"))


if __name__ == "__main__":
    unittest.main()
