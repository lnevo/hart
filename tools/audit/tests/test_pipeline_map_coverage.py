"""tools/ops/pipeline_map_coverage.py: what the scan finds in entry files, and what counts as known to the map."""
from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("pipeline_map_coverage", ROOT / "tools/ops/pipeline_map_coverage.py")
COV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COV)

FILES = frozenset({
    "tools/check.sh", "Makefile", "tools/a.py", "tools/b.sh", "www/scripts/deploy.sh", "www/scripts/build.py",
    "deploy/one.sh", "deploy/two.sh", "deploy/sub/three.sh", "lib/src/pkg/__init__.py", "lib/src/pkg/mod.py",
    "out/x.xml", "out/y.csv", "site/page.html",
})
WWW_ROOT = 'ROOT="$(cd "$(dirname "$0")/.." && pwd)"\n'


def scan(texts: dict[str, str], entries=("tools/check.sh",), roots=(), files=FILES, submodules=()):
    return COV.scan(files, submodules, texts.__getitem__, entries, roots)


class ScanTest(unittest.TestCase):
    def test_repo_paths_and_dot_slash(self) -> None:
        scripts, _ = scan({"tools/check.sh": "run a python3 tools/a.py --check\n./tools/b.sh x\n"})
        self.assertEqual(set(scripts), {"tools/a.py", "tools/b.sh"})

    def test_root_variable_reads_from_the_entry_files_own_root(self) -> None:
        text = WWW_ROOT + 'python3 "$ROOT/scripts/build.py"\n'
        scripts, _ = scan({"www/scripts/deploy.sh": text}, ("www/scripts/deploy.sh",))
        self.assertEqual(set(scripts), {"www/scripts/build.py"})
        # without its own ROOT line (a deploy step gets ROOT from common.sh) $ROOT is the repo root
        scripts, _ = scan({"deploy/one.sh": 'python3 "$ROOT/tools/a.py"\n'}, ("deploy/one.sh",))
        self.assertEqual(set(scripts), {"tools/a.py"})

    def test_a_repo_root_file_of_the_same_name_does_not_stand_in(self) -> None:
        """Review finding: $ROOT/scripts/build.py in www/scripts/deploy.sh is www/scripts/build.py, never scripts/build.py."""
        text = WWW_ROOT + 'python3 "$ROOT/scripts/build.py"\n'
        scripts, _ = scan({"www/scripts/deploy.sh": text}, ("www/scripts/deploy.sh",), files=FILES | {"scripts/build.py"})
        self.assertEqual(set(scripts), {"www/scripts/build.py"})

    def test_variables_set_from_root_or_repo_are_followed(self) -> None:
        """Review finding: `local sm="$ROOT/..."` then `$sm/x.py` is a call (stage.sh's speed-match publisher)."""
        text = ('  local sm="$ROOT/tools"\npython3 "$sm/a.py" x\ncp "$sm/b.sh" "$dest/"\n'
                'REPO="$(git -C "$ROOT" rev-parse --show-toplevel)"\npython3 "$REPO/lib/src/pkg/mod.py"\n')
        scripts, _ = scan({"tools/check.sh": text})
        self.assertEqual(set(scripts), {"tools/a.py", "tools/b.sh", "lib/src/pkg/mod.py"})
        with self.assertRaisesRegex(COV.CoverageError, r"\$sm/gone.py names no file in the checkout \(tried tools/gone.py\)"):
            scan({"tools/check.sh": 'sm="$ROOT/tools"\npython3 "$sm/gone.py"\n'})

    def test_other_variables_prefixes_and_comments_are_not_calls(self) -> None:
        text = ('cp x "$dest/gone/a.py"\ncp x ${DROP}/gone/b.py\n--script preference:jython/gone.py\n'
                "# python3 gone/in_comment.py\n")
        self.assertEqual(scan({"tools/check.sh": text}), ({}, {}))

    def test_trailing_comments_are_not_read_but_quoted_hashes_are_kept(self) -> None:
        """Review finding: a path in a trailing comment is not a call."""
        text = 'python3 tools/a.py   # replaces tools/old.py\necho "# not a comment" tools/b.sh\n'
        scripts, _ = scan({"tools/check.sh": text})
        self.assertEqual(set(scripts), {"tools/a.py", "tools/b.sh"})

    def test_makefile_help_text_is_not_read_but_recipes_with_hashes_are(self) -> None:
        text = "x:  ## see gone/help.py\n\tpython3 tools/a.py\n\tgrep -h '##' tools/b.sh\n"
        scripts, _ = scan({"Makefile": text}, ("Makefile",))
        self.assertEqual(set(scripts), {"tools/a.py", "tools/b.sh"})

    def test_a_gone_path_fails_naming_the_entry_file(self) -> None:
        with self.assertRaisesRegex(COV.CoverageError, r"tools/check.sh: tools/gone.py names no file in the checkout.*"
                                                       r"fix the path in tools/check.sh"):
            scan({"tools/check.sh": "python3 tools/gone.py\n"})

    def test_unreadable_entry_file_is_a_clear_error(self) -> None:
        """Review finding: a tracked entry file deleted from the working tree is named, not a traceback."""
        def read(_name: str) -> str:
            raise FileNotFoundError(2, "No such file or directory")
        with self.assertRaisesRegex(COV.CoverageError, "tools/check.sh is in git but cannot be read"):
            COV.scan(FILES, (), read, ("tools/check.sh",), ())

    def test_a_submodule_path_is_not_ours(self) -> None:
        self.assertEqual(scan({"tools/check.sh": "python3 ext/sub/x.py\n"}, submodules=("ext/sub",)), ({}, {}))

    def test_modules_from_pythonpath(self) -> None:
        scripts, _ = scan({"tools/check.sh": "env PYTHONPATH=lib/src python3 -m pkg.mod check\n"
                                             "env PYTHONPATH=lib/src python3 -m unittest discover\n"})
        self.assertEqual(set(scripts), {"lib/src/pkg/mod.py"})
        with self.assertRaisesRegex(COV.CoverageError, "python3 -m pkg.gone with PYTHONPATH=lib/src finds no "
                                                       "lib/src/pkg/gone.py"):
            scan({"tools/check.sh": "PYTHONPATH=lib/src python3 -m pkg.gone\n"})

    def test_quoted_joined_and_continued_pythonpath(self) -> None:
        """Review finding: quoted, joined (dir:$PYTHONPATH) and continued forms are checked too."""
        scripts, _ = scan({"tools/check.sh": 'X="$(PYTHONPATH="$ROOT/lib/src" python3 -m pkg.mod dirs)"\n'})
        self.assertEqual(set(scripts), {"lib/src/pkg/mod.py"})
        with self.assertRaisesRegex(COV.CoverageError, "pkg.gone with PYTHONPATH=lib/src"):
            scan({"tools/check.sh": "env PYTHONPATH=lib/src:$PYTHONPATH \\\n  python3 -m pkg.gone\n"})

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

    def test_a_root_level_file_node_counts(self) -> None:
        """Review finding: the top-level rule is for folders only."""
        self.assertEqual(self.gaps({"setup.sh": "m"}, {"setup.sh": "setup"}), [])

    def test_listing_marks_what_is_missing(self) -> None:
        """Review finding: --list said 'allowed: None' for a gap."""
        listing: list[str] = []
        COV.gaps({"tools/a.py": "m", "tools/b.sh": "m"}, {}, {}, {"tools/b.sh": "why"}, "g.json", listing)
        self.assertTrue(listing[0].endswith("MISSING") and listing[1].endswith("allowed: tools/b.sh"), listing)

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
    def test_new_files_not_yet_added_count_as_in_the_checkout(self) -> None:
        """Review finding: check.sh runs before the commit, so an unstaged new script is not 'gone'."""
        real = COV._git_files
        with mock.patch.object(COV, "_git_files", side_effect=real) as files:
            COV.check(COV.BUILD.GRAPH)
        self.assertIn(mock.call("--others", "--exclude-standard"), files.call_args_list)

    def test_the_scripts_check_sh_runs_from_the_manifest_count(self) -> None:
        listing: list[str] = []
        COV.check(COV.BUILD.GRAPH, listing)
        frozen = [line for line in listing if " tools/wiring/check_wiring_frozen.py " in line]
        self.assertEqual(len(frozen), 1, "check_wiring_frozen.py runs only from tools/pipeline/checks.toml")
        self.assertIn("allowed: tools/wiring/check_wiring_frozen.py", frozen[0])
        with mock.patch.object(COV.MANIFEST, "load", side_effect=COV.MANIFEST.ManifestError("t.toml: broken")):
            with self.assertRaisesRegex(COV.CoverageError, "cannot be read:\nt.toml: broken"):
                COV.check(COV.BUILD.GRAPH)

    def test_the_repo_map_knows_every_pipeline_file(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            code = COV.main([])
        self.assertEqual(code, 0, err.getvalue())


if __name__ == "__main__":
    unittest.main()
