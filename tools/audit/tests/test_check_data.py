"""tools/ops/check_data.py: each sidecar rule passes and fails, the glob, the pair master and the repo's readers."""
from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("check_data", ROOT / "tools/ops/check_data.py")
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)

HEAD = "column,description,type,required,key,refs,values\n"


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, name: str, text: str) -> Path:
        p = self.tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def problems(self, sidecar_rows: str, master: str, name: str = "t") -> list[str]:
        side = self.write(f"{name}.columns.csv", HEAD + sidecar_rows)
        self.write(f"{name}.csv", master)
        return C.Checker().check(side)

    def passes(self, sidecar_rows: str, master: str) -> None:
        self.assertEqual(self.problems(sidecar_rows, master), [])

    def fails(self, sidecar_rows: str, master: str, pattern: str) -> None:
        found = self.problems(sidecar_rows, master)
        self.assertTrue(found, "expected a problem")
        self.assertRegex(" | ".join(found), pattern)


class Types(Base):
    def test_int(self) -> None:
        self.passes("n,x,int,,,,\n", "n\n1\n-4\n\"\"\n")
        self.fails("n,x,int,,,,\n", "n\n1\n2.5\n", r"'2.5' is not an integer")

    def test_float(self) -> None:
        self.passes("n,x,float,,,,\n", "n\n1\n2.5\n.5\n1e3\n")
        self.fails("n,x,float,,,,\n", "n\nabc\n", r"'abc' is not a number")

    def test_bool(self) -> None:
        self.passes("b,x,bool,,,,\n", "b\nyes\nno\n\"\"\n")
        self.fails("b,x,bool,,,,\n", "b\ntrue\n", r"'true' is not yes or no")

    def test_enum(self) -> None:
        self.passes("e,x,enum,,,,L;R\n", "e\nL\nR\n")
        self.fails("e,x,enum,,,,L;R\n", "e\nX\n", r"'X' is not one of L;R")

    def test_id_list(self) -> None:
        self.passes("l,x,id-list,,,,\n", "l\na;b\nc\n")
        self.fails("l,x,id-list,,,,\n", "l\na;;b\n", r"empty or padded item")
        self.fails("l,x,id-list,,,,\n", "l\na; b\n", r"empty or padded item")
        self.fails("l,x,id-list,,,,\n", "l\na;a\n", r"names an item twice")

    def test_str_and_empty_rules_take_anything(self) -> None:
        self.passes("s,x,str,,,,\nt,x,,,,,\n", "s,t\n,\nanything,at all\n")


class Required(Base):
    def test_yes(self) -> None:
        self.passes("a,x,,yes,,,\n", "a\n1\n")
        self.fails("a,x,,yes,,,\n", "a\n1\n\"\"\n", r"a is required: row 3")

    def test_condition(self) -> None:
        rows = "lv,x,,,,,\nh,x,,lv=2;3,,,\n"
        self.passes(rows, "lv,h\n1,\n2,x\n3,y\n")
        self.fails(rows, "lv,h\n1,\n3,\n", r"h is required where lv is 2\|3: row 3")

    def test_condition_on_an_empty_value(self) -> None:
        self.fails("lv,x,,,,,\nh,x,,lv=,,,\n", "lv,h\n,\n1,\n", r"where lv is : row 2")


class Keys(Base):
    def test_one_column(self) -> None:
        self.passes("id,x,,,yes,,\n", "id\na\nb\n")
        self.fails("id,x,,,yes,,\n", "id\na\na\n", r"key id is not unique: a")
        self.fails("id,x,,,yes,,\n", "id\na\n\"\"\n", r"key id is empty: row 3")

    def test_composite_key_with_a_condition(self) -> None:
        rows = "lv,x,,,lv=1;2,,\nid,x,,,lv=1;2,,\n"
        self.passes(rows, "lv,id\n1,a\n2,a\n,\n,\n")               # (1,a) and (2,a) differ; level-less rows are out
        self.fails(rows, "lv,id\n1,a\n1,a\n", r"key lv,id is not unique: 1/a")

    def test_two_keys(self) -> None:
        rows = "lv,x,,,,,\nh,x,,,lv=2,,\nos,x,,,lv=1,,\n"
        self.passes(rows, "lv,h,os\n2,a,\n2,b,\n1,,a\n1,,b\n")
        self.fails(rows, "lv,h,os\n1,,a\n1,,a\n", r"key os is not unique")


class Refs(Base):
    def test_values_and_list_items_must_exist(self) -> None:
        self.write("places.csv", "name\nBrick\nBarn\n")
        rows = "p,x,,,,places.csv:name,\nps,x,id-list,,,places.csv:name,\n"
        old, C.ROOT = C.ROOT, self.tmp
        try:
            self.passes(rows, "p,ps\nBrick,Brick;Barn\n,\n")
            self.fails(rows, "p,ps\nPlane,Brick\n", r"p names what is not in .*'Plane'")
            self.fails(rows, "p,ps\nBrick,Brick;Mill\n", r"ps names what is not in .*'Mill'")
        finally:
            C.ROOT = old

    def test_several_targets(self) -> None:
        self.write("a.csv", "n\nx\n")
        self.write("b.csv", "m\ny\n")
        old, C.ROOT = C.ROOT, self.tmp
        try:
            self.passes("p,x,id-list,,,a.csv:n;b.csv:m,\n", "p\nx;y\n")
            self.fails("p,x,,,,a.csv:n;b.csv:m,\n", "p\nz\n", r"'z'")
            self.assertRaisesRegex(C.DataError, "no column q", self.problems, "p,x,,,,a.csv:q,\n", "p\nx\n")
        finally:
            C.ROOT = old


class Sidecars(Base):
    def test_a_bad_sidecar_is_an_error(self) -> None:
        cases = [("t.columns.csv", "column,colour\n", "header"),
                 ("t.columns.csv", HEAD + "a,x,date,,,,\n", "type 'date'"),
                 ("t.columns.csv", HEAD + "a,x,enum,,,,\n", "enum column has values"),
                 ("t.columns.csv", HEAD + "a,x,,maybe,,,\n", "not yes or a condition"),
                 ("t.columns.csv", HEAD + "a,x,,,,nofile,\n", "is not path/file.csv:column"),
                 ("t.columns.csv", HEAD + "a,x\n", "2 fields, expected 7"),
                 ("t.columns.csv", HEAD + "a,x,,,,,\na,y,,,,,\n", "described twice")]
        for name, text, pattern in cases:
            with self.subTest(pattern):
                self.assertRaisesRegex(C.DataError, pattern, C.read_sidecar, self.write(name, text))

    def test_the_master_header_is_the_sidecar_columns(self) -> None:
        self.assertRaisesRegex(C.DataError, "header is not the sidecar", self.problems, "a,x,,,,,\nb,x,,,,,\n",
                               "b,a\n1,2\n")

    def test_no_master(self) -> None:
        side = self.write("lone.columns.csv", HEAD + "a,x,,,,,\n")
        self.assertRaisesRegex(C.DataError, "no master", C.Checker().check, side)

    def test_the_old_formats_still_read(self) -> None:
        side = self.write("old.columns.csv", "column,file,description\na,field,text\n")
        self.write("old.csv", "a\n1\n")
        self.assertEqual(C.Checker().check(side), [])


class Pair(Base):
    RULES = "column,file,description,type,required,key,refs,values\n" \
            "level,field,x,enum,,level=1;2,,1;2\nid,field,x,,level=1;2,level=1;2,,\n" \
            "role,field,x,enum,level=1;2,,,a;b\nname,field,x,,yes,level=,,\n"

    def test_field_cells_win_and_unmatched_field_rows_are_added(self) -> None:
        side = self.write("dev.columns.csv", self.RULES)
        self.write("dev_generated.csv", "level,id,role,name\n1,x,,X\n2,x,b,X2\n")
        self.write("dev_field.csv", "level,id,role,name\n1,x,a,\n,,,Loose\n")
        checker = C.Checker()
        self.assertEqual(checker.check(side), [])
        _, rows = checker.master(side)
        self.assertEqual([(r["level"], r["role"], r["name"]) for r in rows], [("1", "a", "X"), ("2", "b", "X2"),
                                                                              ("", "", "Loose")])

    def test_a_rule_the_merge_breaks_fails(self) -> None:
        side = self.write("dev.columns.csv", self.RULES)
        self.write("dev_generated.csv", "level,id,role,name\n1,x,,X\n")
        self.write("dev_field.csv", "level,id,role,name\n1,x,c,\n")
        self.assertRegex(" | ".join(C.Checker().check(side)), r"role \(enum\): 1/x/X 'c'")

    def test_refs_to_the_pair_read_the_merged_view(self) -> None:
        self.write("dev.columns.csv", self.RULES)
        self.write("dev_generated.csv", "level,id,role,name\n1,x,a,Old\n")
        self.write("dev_field.csv", "level,id,role,name\n1,x,,New\n")
        old, C.ROOT = C.ROOT, self.tmp
        try:
            self.passes("p,x,,,,dev.csv:name,\n", "p\nNew\n")
            self.fails("p,x,,,,dev.csv:name,\n", "p\nOld\n", r"'Old'")
        finally:
            C.ROOT = old


class Glob(Base):
    def test_finds_sidecars_and_skips_the_left_out_folders(self) -> None:
        for p in ("a/x.columns.csv", "a/b/y.columns.csv", "archive/z.columns.csv", "external/q.columns.csv",
                  "reference/r.columns.csv", ".claude/w/s.columns.csv", "tools/cats/src-repo/u.columns.csv",
                  "tools/v.columns.csv", "a/not_a_sidecar.csv"):
            self.write(p, "column,description\n")
        found = [p.relative_to(self.tmp).as_posix() for p in C.find_sidecars(self.tmp)]
        self.assertEqual(found, ["a/b/y.columns.csv", "a/x.columns.csv", "tools/v.columns.csv"])

    def test_main_reports_and_exits_1(self) -> None:
        side = self.write("t.columns.csv", HEAD + "a,x,int,,,,\n")
        self.write("t.csv", "a\nz\n")
        import io
        from contextlib import redirect_stderr, redirect_stdout
        err, out = io.StringIO(), io.StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            self.assertEqual(C.main([str(side)]), 1)
        self.assertIn("is not an integer", err.getvalue())
        self.assertIn("0 of 1 sidecars pass", out.getvalue())


class TheRepo(unittest.TestCase):
    """The repo's sidecars pass, and the readers of the extended format still read them."""

    def test_every_sidecar_passes(self) -> None:
        sidecars = C.find_sidecars()
        self.assertIn(ROOT / "jmri/layouts/hart/data/devices.columns.csv", sidecars)
        self.assertIn(ROOT / "jmri/layouts/hart/data/switches.columns.csv", sidecars)
        checker = C.Checker()
        self.assertEqual([p for s in sidecars for p in checker.check(s)], [])

    def test_hartlib_reads_the_device_dictionary(self) -> None:
        sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
        try:
            from hartlib import devices as D
        finally:
            sys.path.remove(str(ROOT / "tools/hartlib/src"))
        self.assertEqual(set(D.read_dictionary(D.Files.here().dictionary)), set(D.COLUMNS))

    def test_the_switch_dictionary_names_the_columns_in_order(self) -> None:
        with (ROOT / "jmri/layouts/hart/data/switches.columns.csv").open(newline="", encoding="utf-8") as fh:
            names = [r["column"] for r in csv.DictReader(fh)]
        with (ROOT / "jmri/layouts/hart/data/switches.csv").open(newline="", encoding="utf-8") as fh:
            self.assertEqual(names, next(csv.reader(fh)))


if __name__ == "__main__":
    unittest.main()
