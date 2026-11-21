"""tools/ops/pipeline_map_coverage.py: what the scan finds in entry files, and what counts as known to the map."""
from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("pipeline_map_coverage", ROOT / "tools/ops/pipeline_map_coverage.py")
COV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COV)

FILES = frozenset({
    "tools/check.sh", "Makefile", "tools/a.py", "tools/b.sh", "www/scripts/deploy.sh", "www/scripts/build.py",
    "deploy/one.sh", "deploy/two.sh", "deploy/sub/three.sh", "lib/src/pkg/__init__.py", "lib/src/pkg/mod.py",
    "out/x.xml", "out/y.csv", "site/page.html",
})


def scan(texts: dict[str, str], entries=("tools/check.sh",), roots=(), files=FILES, submodules=()):
    return COV.scan(files, submodules, texts.__getitem__, entries, roots)


class ScanTest(unittest.TestCase):
    def test_repo_paths_and_dot_slash(self) -> None:
        scripts, _ = scan({"tools/check.sh": "run a python3 tools/a.py --check\n./tools/b.sh x\n"})
        self.assertEqual(set(scripts), {"tools/a.py", "tools/b.sh"})

    def test_root_variable_reads_from_the_entry_folder_and_the_one_above(self) -> None:
        scripts, _ = scan({"www/scripts/deploy.sh": 'python3 "$ROOT/scripts/build.py"\n'}, ("www/scripts/deploy.sh",))
        self.assertEqual(set(scripts), {"www/scripts/build.py"})

    def test_other_variables_prefixes_and_comments_are_not_calls(self) -> None:
        text = ('cp x "$dest/gone/a.py"\ncp x ${DROP}/gone/b.py\n--script preference:jython/gone.py\n'
                "# python3 gone/in_comment.py\n")
        self.assertEqual(scan({"tools/check.sh": text}), ({}, {}))

    def test_makefile_help_text_is_not_read(self) -> None:
        text = "x:  ## see gone/help.py\n\tpython3 tools/a.py\n"
        scripts, _ = scan({"Makefile": text}, ("Makefile",))
        self.assertEqual(set(scripts), {"tools/a.py"})

    def test_a_gone_path_fails_naming_the_entry_file(self) -> None:
        with self.assertRaisesRegex(COV.CoverageError, r"tools/check.sh: tools/gone.py names no tracked file.*fix the "
                                                       r"path in tools/check.sh"):
            scan({"tools/check.sh": "python3 tools/gone.py\n"})

    def test_a_submodule_path_is_not_ours(self) -> None:
        self.assertEqual(scan({"tools/check.sh": "python3 ext/sub/x.py\n"}, submodules=("ext/sub",)), ({}, {}))

    def test_modules_from_pythonpath(self) -> None:
        scripts, _ = scan({"tools/check.sh": "env PYTHONPATH=lib/src python3 -m pkg.mod check\n"
                                             "env PYTHONPATH=lib/src python3 -m unittest discover\n"})
        self.assertEqual(set(scripts), {"lib/src/pkg/mod.py"})
        with self.assertRaisesRegex(COV.CoverageError, "python3 -m pkg.gone with PYTHONPATH=lib/src finds no tracked "
                                                       "lib/src/pkg/gone.py"):
            scan({"tools/check.sh": "PYTHONPATH=lib/src python3 -m pkg.gone\n"})

    def test_outputs_from_out_and_output_roots(self) -> None:
        _, outputs = scan({"tools/check.sh": "python3 tools/a.py --out site/page.html --out /tmp/x\n"}, roots=("out",))
        self.assertEqual(outputs, {"site/page.html": "tools/check.sh --out", "out/x.xml": "under out",
                                   "out/y.csv": "under out"})

    def test_entry_folder_is_its_own_sh_files(self) -> None:
        texts = {"deploy/one.sh": "python3 tools/a.py\n", "deploy/two.sh": "bash tools/b.sh\n"}
        scripts, _ = scan(texts, ("deploy",))
        self.assertEqual(scripts, {"tools/a.py": "deploy/one.sh", "tools/b.sh": "deploy/two.sh"})

    def test_bad_entry_or_output_root_names_the_setting(self) -> None:
        with self.assertRaisesRegex(COV.CoverageError, "ENTRY_FILES .* names nowhere"):
            scan({}, ("nowhere",))
        with self.assertRaisesRegex(COV.CoverageError, "OUTPUT_ROOTS .* names empty"):
            scan({"tools/check.sh": ""}, roots=("empty",))


class GapsTest(unittest.TestCase):
    def gaps(self, scripts, node_paths, allowed=None, outputs=None):
        return COV.gaps(scripts, outputs or {}, node_paths, allowed or {}, "g.json")

    def test_missing_script_names_both_fixes(self) -> None:
        [p] = self.gaps({"tools/a.py": "tools/check.sh"}, {})
        self.assertIn("script tools/a.py (tools/check.sh) is not in the map: add a node for it", p)
        self.assertIn("or add it to ALLOWED", p)

    def test_a_folder_node_covers_but_not_a_top_level_one(self) -> None:
        self.assertEqual(self.gaps({"tools/hosts/x.sh": "m"}, {"tools/hosts": "hosts"}), [])
        self.assertEqual(len(self.gaps({"www/scripts/x.py": "m"}, {"www": "site"})), 1)

    def test_allowed_entries_are_used_folder_wide_and_never_stale(self) -> None:
        self.assertEqual(self.gaps({"deploy/one.sh": "m"}, {}, {"deploy": "steps"}), [])
        [p] = self.gaps({}, {}, {"tools/old.py": "gone"})
        self.assertIn("ALLOWED entry tools/old.py matches nothing", p)

    def test_allowed_and_a_node_at_once_or_no_reason(self) -> None:
        [p] = self.gaps({"tools/a.py": "m"}, {"tools/a.py": "a"}, {"tools/a.py": "why"})
        self.assertIn("is node 'a' and also in ALLOWED", p)
        [p] = self.gaps({"tools/a.py": "m"}, {}, {"tools/a.py": " "})
        self.assertIn("has no reason", p)


class RepoTest(unittest.TestCase):
    def test_the_repo_map_knows_every_pipeline_file(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            code = COV.main([])
        self.assertEqual(code, 0, err.getvalue())


if __name__ == "__main__":
    unittest.main()
