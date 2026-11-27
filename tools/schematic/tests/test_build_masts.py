"""build_masts.py: masts.csv from the device master's mast and head rows, with staging's plan facts. main() on
temporary files, and, as data checks under a guard that fails any write into the repo (repo_read_only.py), the repo's
committed data. Staging's masts by the rule (part 1 of this script until naming-layers step 12) are tested in
test_device_map_masts.py, the wired heads in tools/audit/tests/test_staging_wired_heads.py, file_rows in
test_masts_file.py."""
from __future__ import annotations

import contextlib
import csv
import io
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_masts as bsm  # noqa: E402
import device_map_masts as dmm  # noqa: E402
from hartlib import level_masts  # noqa: E402
from hartlib import devices  # noqa: E402
from repo_read_only import RepoReadOnly, in_repo, repo_read_only  # noqa: E402

GEN = [dict(mast="Mast 2L", cp="Brick", switch="1", facing="Track Main West", protects="OS Switch 1",
            kind="two-searchlight", heads=2, dir="west"),
       dict(mast="Mast 67", cp="Princess", switch="", facing="Track K-2", protects="Track K-1", kind="one-searchlight",
            heads=1, dir="west")]


def rows_of(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


class CsvText(unittest.TestCase):
    def test_csv_text_has_lf_ends_and_quotes_only_what_needs_it(self):
        text = bsm.csv_text([dict(a="1", b="x,y"), dict(a="", b='say "hi"')], ("a", "b"))
        self.assertEqual(text, 'a,b\n1,"x,y"\n,"say ""hi"""\n')
        self.assertEqual(bsm.csv_text([], ("a", "b")), "a,b\n")

    def test_cp_cells_take_the_ids_of_the_lists_beside_the_file(self):
        """A masts.csv copy beside its own stations.csv is written by those lists, the ones level_masts.read
        names it by; the repo's file by the repo's."""
        from hartlib import places
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / places.SCHEMATIC.name
            folder.mkdir()
            (folder / places.INTERLOCKINGS.name).write_bytes(places.INTERLOCKINGS.read_bytes())
            (folder / places.STATIONS.name).write_text(
                places.STATIONS.read_text(encoding="utf-8").replace(",Engine House,", ",Roundhouse,"),
                encoding="utf-8")
            row = [dict(cp="Barn;Roundhouse")]
            self.assertEqual(bsm.csv_text(row, ("cp",), folder / "masts.csv"), "cp\nst:barn;st:engine-house\n")
            self.assertEqual(bsm.csv_text(row, ("cp",), level_masts.PATH), "cp\nst:barn;Roundhouse\n")  # the repo has no Roundhouse

    def test_the_rule_error_is_device_map_masts(self):
        self.assertIs(bsm.RuleError, dmm.RuleError)

class Cli(unittest.TestCase):
    """main() on temporary files (build() stubbed): --check and --show write nothing; a rule error is exit 2."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.current = self.dir / "current.csv"
        self.current.write_text("mast\nMast 2L\n", encoding="utf-8")
        self.stale = self.dir / "masts.csv"
        self.stale.write_text("mast\nold\n", encoding="utf-8")
        self.missing = self.dir / "missing.csv"
        want = {self.current: "mast\nMast 2L\n", self.stale: "mast\nnew\n", self.missing: "level\n1\n"}
        gen = [dict(GEN[0]), dict(GEN[1], milepost=6.714)]
        patch = unittest.mock.patch.object(bsm, "build", lambda check=False: (want, gen, []))
        patch.start()
        self.addCleanup(patch.stop)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        # main() looks for the plugin first, which prints where it was found; these tests are about what follows
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                unittest.mock.patch.object(bsm.sdm.lc, "plugin", lambda: None):
            code = bsm.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_check_names_each_stale_or_missing_file_and_writes_nothing(self):
        code, out, err = self.run_main("--check")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err.splitlines(),
                         ["masts.csv is stale: run python3 tools/schematic/build_masts.py",
                          "missing.csv is stale: run python3 tools/schematic/build_masts.py"])
        self.assertEqual(self.stale.read_text(encoding="utf-8"), "mast\nold\n")
        self.assertFalse(self.missing.exists())

    def test_a_run_writes_only_the_stale_files_and_then_check_passes(self):
        before = self.current.stat().st_mtime_ns
        code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), ["wrote masts.csv", "wrote missing.csv"])
        self.assertEqual(self.stale.read_text(encoding="utf-8"), "mast\nnew\n")
        self.assertEqual(self.missing.read_text(encoding="utf-8"), "level\n1\n")
        self.assertEqual(self.current.stat().st_mtime_ns, before)
        self.assertEqual(self.run_main("--check"), (0, "", ""))
        self.assertEqual(self.run_main(), (0, "", ""))

    def test_show_prints_the_masts_and_writes_nothing(self):
        code, out, _err = self.run_main("--show")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].split(), ["Mast", "2L", "two-searchlight", "2h", "Track", "Main", "West", "->", "OS",
                                            "Switch", "1", "switch", "1", "west"])
        self.assertTrue(lines[1].endswith("anchor     west  MP 6.714"), lines[1])
        self.assertEqual(self.stale.read_text(encoding="utf-8"), "mast\nold\n")
        self.assertFalse(self.missing.exists())

    def test_check_and_show_do_not_go_together(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            bsm.main(["--check", "--show"])

    def test_a_rule_error_is_exit_2(self):
        def stop(check=False):
            raise bsm.RuleError("the rule names a mast twice: ['Mast 2L']")
        with unittest.mock.patch.object(bsm, "build", stop):
            code, out, err = self.run_main("--check")
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err.strip(), "build_masts.py: the rule names a mast twice: ['Mast 2L']")


class WriteGuard(unittest.TestCase):
    """The guard the data checks run under: a write inside the repo fails, one outside it goes through."""

    def test_a_write_inside_the_repo_is_refused_before_it_happens(self):
        target = Path(__file__).with_name("never_written.tmp")
        self.assertTrue(in_repo(target))
        with repo_read_only():
            for write in (lambda: target.write_text("x", encoding="utf-8"), lambda: target.write_bytes(b"x"),
                          lambda: open(target, "w"), lambda: target.open("a"), target.touch, target.mkdir,
                          lambda: Path(__file__).rename(target)):
                with self.assertRaisesRegex(AssertionError, "data checks only read it"):
                    write()
            self.assertEqual(Path(__file__).read_text(encoding="utf-8")[:3], '"""')      # reading still works
        self.assertFalse(target.exists())

    def test_a_write_outside_the_repo_goes_through(self):
        with tempfile.TemporaryDirectory() as d, repo_read_only():
            self.assertFalse(in_repo(d))
            (Path(d) / "sub").mkdir()
            (Path(d) / "sub" / "a.txt").write_text("x", encoding="utf-8")
            self.assertEqual((Path(d) / "sub" / "a.txt").read_text(encoding="utf-8"), "x")

    def test_a_link_outside_the_repo_that_points_into_it_may_be_swapped_but_not_written_through(self):
        """layer_files.view replaces a cache link to the checkout's data: the link moves, the repo does not."""
        stray = Path(__file__).with_name("never_written.tmp")
        self.addCleanup(lambda: stray.unlink(missing_ok=True))      # only there if the guard let it through
        with tempfile.TemporaryDirectory() as d, repo_read_only():
            tmp, link = Path(d) / "tmp.link", Path(d) / "view"
            os.symlink(Path(__file__).parent, tmp)
            os.replace(tmp, link)
            self.assertEqual(Path(__file__).parent, Path(os.readlink(link)))
            with self.assertRaisesRegex(AssertionError, "data checks only read it"):
                open(link / "never_written.tmp", "w")
            link.unlink()
            with self.assertRaisesRegex(AssertionError, "data checks only read it"):
                os.symlink(d, stray)                # a link made inside the repo is a write

class CommittedData(RepoReadOnly, unittest.TestCase):
    """Data checks, not rule tests: the real build() over the repo's committed plan and data (built once), under
    RepoReadOnly, so a write into the repo fails the test instead of changing a file. A failure here can mean the data
    changed, not the code. These hold whatever masts the rule places; they name no mast."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.files = {p: p.read_bytes() for p in (bsm.MASTS, bsm.device_files().master, bsm.device_files().field)}
        cls.want, cls.gen, cls.virtual = bsm.build()

    def test_check_reports_the_committed_files_current_and_writes_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bsm.main(["--check"])
        self.assertEqual((code, err.getvalue()), (0, ""))
        for path, data in self.files.items():
            self.assertEqual(path.read_bytes(), data, path.name)

    def test_build_writes_masts_csv_alone(self):
        """The device master's mast and head rows are build_device_map.py's."""
        self.assertEqual(set(self.want), {bsm.MASTS})
        self.assertNotIn(bsm.WRITER, devices.WRITERS)

    def test_the_file_holds_every_level_in_level_number_and_name_order_the_placed_ones_with_plan_facts(self):
        rows = rows_of(self.want[bsm.MASTS])
        key = lambda r: (int(r["level"]), int("".join(c for c in r["mast"][5:] if c.isdigit())), r["mast"])  # noqa: E731
        self.assertEqual(rows, sorted(rows, key=key))
        self.assertEqual({r["level"] for r in rows}, {"1", "2", "3"})
        placed = {m["mast"] for m in self.gen + self.virtual}
        mine = [r for r in rows if r["level"] == str(dmm.LEVEL)]
        self.assertEqual({r["mast"] for r in mine}, placed)
        virtual = {m["mast"] for m in self.virtual}
        for r in rows:
            self.assertEqual(all(r[c] for c in ("toward", "run", "edge_cm")), r["mast"] in placed, r["mast"])
            if r["mast"] in placed:
                self.assertEqual(r["system_name"].startswith("IF$vsm:"), r["mast"] in virtual, r["mast"])
        kinds = {m["mast"]: m["signal_kind"] for m in self.gen + self.virtual}
        self.assertEqual({r["mast"]: level_masts.signal_kind(r) for r in mine}, kinds)

    def test_no_hand_kept_virtual_files_are_left(self):
        """The helix-foot masts were the last hand-kept ones (2026-11-20): the files that held them are gone."""
        self.assertFalse((bsm.DATA / "staging_masts_virtual.csv").exists())
        self.assertFalse((bsm.DATA / "staging_signals_virtual.csv").exists())

    def test_the_masters_staging_masts_are_the_rules(self):
        """build() stops when build_device_map.py's rows are not the rule's now (current)."""
        master = [r.cells() for r in devices.load(bsm.device_files())]
        some = [r for r in master if r["level"] == "1" and r["layer"] == "mast"][:1]
        with self.assertRaisesRegex(bsm.RuleError, "run tools/schematic/build_device_map.py first"):
            bsm.current(master, [r | {"user_name": "Mast 99L"} for r in some])

    def test_an_anchor_mast_on_any_level_protects_an_os_block(self):
        """One anchor rule on every level: a home mast at no switch is an anchor mast, on main and
        upper too, and it must protect an OS block of its level."""
        master = [r.cells() for r in devices.load(bsm.device_files())]
        home = next(r for r in master if r["level"] == "2" and r["layer"] == "mast" and r["role"] == "home")
        os_ = next(r for r in master if r["level"] == "2" and r["layer"] == "block" and r["role"] == "os")
        track = next(r for r in master if r["level"] == "2" and r["layer"] == "block" and r["role"] == "track")
        anchor = home | {"switch": "", "protects": os_["user_name"]}
        rows = bsm.file_rows([anchor if r is home else r for r in master], {})
        self.assertEqual(next(r for r in rows if r["mast"] == home["user_name"])["protects"], os_["user_name"])
        lost = home | {"switch": "", "protects": track["user_name"]}
        with self.assertRaisesRegex(bsm.RuleError, "a home signal lost its switch"):
            bsm.file_rows([lost if r is home else r for r in master], {})


if __name__ == "__main__":
    unittest.main()