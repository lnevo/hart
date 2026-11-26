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

    def test_a_comment_ending_in_a_backslash_ends_at_its_line(self) -> None:
        """Review finding (#1168): the shell ends a comment at its line, so the call after `# ... \\` is read."""
        scripts, _ = scan({"tools/check.sh": "# see tools/gone.py \\\npython3 tools/a.py\n"})
        self.assertEqual(set(scripts), {"tools/a.py"})
        with self.assertRaisesRegex(COV.CoverageError, "tools/gone.py names no file"):
            scan({"tools/check.sh": "x=1  # trailing \\\npython3 tools/gone.py\n"})
        # a Makefile recipe line is the shell's; a comment in make's own text goes on, as make reads it
        scripts, _ = scan({"Makefile": "x:\n\t# note \\\n\tpython3 tools/a.py\n# make text \\\n  tools/gone.py\n"},
                          ("Makefile",))
        self.assertEqual(set(scripts), {"tools/a.py"})
        # a continued line of code still joins, a quoted # included
        scripts, _ = scan({"tools/check.sh": 'echo "# kept \\\n  tools/b.sh" \\\n  tools/a.py\n'})
        self.assertEqual(set(scripts), {"tools/a.py", "tools/b.sh"})

    def test_an_apostrophe_in_a_word_opens_no_quote(self) -> None:
        """Review finding (#1168): `don't` in a heredoc or make's text hid the comment after it, so a path in it failed."""
        text = ("cat <<EOF\nDon't run it  # was tools/gone.py\nEOF\npython3 tools/a.py\n"
                "echo done' here  # tools/gone.py\n")
        scripts, _ = scan({"tools/check.sh": text})
        self.assertEqual(set(scripts), {"tools/a.py"})
        # a real quote still keeps its # and its path, and an escaped quote opens none
        scripts, _ = scan({"tools/check.sh": "echo 'a # b' tools/a.py\necho \\' tools/b.sh # tools/gone.py\n"})
        self.assertEqual(set(scripts), {"tools/a.py", "tools/b.sh"})
        # review finding: only a single quote is an apostrophe; a double quote between letters still opens a quote
        scripts, _ = scan({"tools/check.sh": 'echo a"b # tools/a.py"c\n'})
        self.assertEqual(set(scripts), {"tools/a.py"})

    def test_every_pythonpath_entry_is_read_and_the_first_holder_wins(self) -> None:
        """Review finding (#1168): only the first PYTHONPATH entry was read."""
        scripts, _ = scan({"tools/check.sh": "PYTHONPATH=tools:lib/src python3 -m pkg.mod\n"
                                             'X="$(PYTHONPATH="$ROOT/out:$ROOT/lib/src${PYTHONPATH:+:$PYTHONPATH}" '
                                             'python3 -m pkg.mod)"\n'})
        self.assertEqual(set(scripts), {"lib/src/pkg/mod.py"})
        with self.assertRaisesRegex(COV.CoverageError, "pkg.gone with PYTHONPATH=lib/src finds no lib/src/pkg/gone.py"):
            scan({"tools/check.sh": "PYTHONPATH=tools:lib/src:$dest/x python3 -m pkg.gone\n"})
        # review finding: an entry the checkout cannot see may hold pkg at run time, so a call behind one is a host's
        self.assertEqual(scan({"tools/check.sh": "PYTHONPATH=$dest/x:lib/src python3 -m pkg.gone\n"}), ({}, {}))
        # Python takes pkg from the first entry that holds it: a later entry's pkg.mod does not stand in
        files = FILES | {"alt/pkg/__init__.py"}
        with self.assertRaisesRegex(COV.CoverageError, "PYTHONPATH=alt finds no alt/pkg/mod.py"):
            scan({"tools/check.sh": "PYTHONPATH=alt:lib/src python3 -m pkg.mod\n"}, files=files)

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


class ScriptRuleTest(unittest.TestCase):
    """The every-script rule (owner, 2026-11-25): a node of its own, or under a folder node FAMILIES names."""
    FAMILIES = {"lib/src/pkg": "a library"}

    def gaps(self, scripts, node_paths, ids=None, families=None):
        ids = ids if ids is not None else node_paths.values()
        return COV.script_gaps(scripts, node_paths, ids, families if families is not None else self.FAMILIES,
                               "g.json")

    def test_covered_by_its_own_node(self) -> None:
        self.assertEqual(self.gaps(["tools/a.py", "lib/src/pkg/mod.py"],
                                   {"tools/a.py": "a", "lib/src/pkg": "pkg"}), [])

    def test_covered_by_a_box_named_after_it(self) -> None:
        """panels.toml's `box`: approval.py's box has the script's path as its id and check_approved.py as its path."""
        self.assertEqual(self.gaps(["tools/approval.py", "lib/src/pkg/mod.py"],
                                   {"tools/check_approved.py": "tools/approval.py", "lib/src/pkg": "pkg"}), [])

    def test_covered_by_a_family_folder(self) -> None:
        self.assertEqual(self.gaps(["lib/src/pkg/mod.py", "lib/src/pkg/sub/deep.py"], {"lib/src/pkg": "pkg"}), [])

    def test_a_folder_node_not_in_families_fails_naming_both_fixes(self) -> None:
        [p] = self.gaps(["tools/hosts/x.sh", "lib/src/pkg/mod.py"], {"tools/hosts": "hosts", "lib/src/pkg": "pkg"})
        self.assertIn("script tools/hosts/x.sh is only under folder node 'hosts' (tools/hosts)", p)
        self.assertIn("add a node for the script", p)
        self.assertIn("add tools/hosts to FAMILIES", p)

    def test_an_uncovered_script_fails(self) -> None:
        [p] = self.gaps(["tools/a.py", "lib/src/pkg/mod.py"], {"lib/src/pkg": "pkg"})
        self.assertIn("script tools/a.py is not in the map: add a node for it", p)

    def test_excluded_folders_and_tests_are_not_checked(self) -> None:
        files = ["archive/old.py", "external/sub/x.py", "reference/v.sh", "tools/cats/src-repo/a.py",
                 "tools/tests/helper.py", "tools/test/run.sh", "tools/test_a.py",
                 "tools/conftest.py", "tools/a.py", "tools/b.sh", "tools/c.js", "tools/archive/kept.py"]
        self.assertEqual(COV.rule_scripts(files), ["tools/a.py", "tools/archive/kept.py", "tools/b.sh"])

    def test_scripts_named_like_tests_are_checked(self) -> None:
        """Review finding: panelpro_smoke_test.py (make panelpro-test) and stop_test.py are pipeline scripts."""
        files = ["jmri/layouts/hart/scripts/panelpro_smoke_test.py", "jmri/layouts/hart/scripts/run_panelpro_smoke_test.sh",
                 "jmri/layouts/hart/scripts/speedmatch/jython/stop_test.py", "tools/test_run.sh"]
        self.assertEqual(COV.rule_scripts(files), sorted(files))

    def test_a_new_untracked_script_is_checked_before_the_commit(self) -> None:
        """Review finding: the rule reads new files too, so a check before `git add` fails as it would after."""
        real = COV._git_files

        def files(*args):
            return real(*args) + (["tools/hosts/pi/brand_new_unmapped.sh"] if args else [])
        with mock.patch.object(COV, "_git_files", side_effect=files):
            problems = COV.check(COV.BUILD.GRAPH)
        self.assertTrue(any(p.startswith("script tools/hosts/pi/brand_new_unmapped.sh is only under folder node")
                            for p in problems), problems)

    def test_families_entries_cannot_go_stale(self) -> None:
        [p] = self.gaps([], {}, families={"lib/gone": "a library"})
        self.assertIn("FAMILIES entry lib/gone in", p)
        self.assertIn("is no node's path", p)
        [p] = self.gaps(["tools/a.py"], {"tools/a.py": "a", "lib/src/pkg": "pkg"})
        self.assertIn("FAMILIES entry lib/src/pkg in", p)
        self.assertIn("covers no script", p)
        problems = self.gaps(["lib/src/pkg/mod.py"], {"lib/src/pkg": "pkg"}, families={"lib/src/pkg": " "})
        self.assertEqual(len(problems), 1)
        self.assertIn("has no reason", problems[0])

    def test_listing_says_what_covers_each_script(self) -> None:
        listing: list[str] = []
        COV.script_gaps(["tools/a.py", "lib/src/pkg/mod.py", "tools/b.sh"], {"tools/a.py": "a", "lib/src/pkg": "pkg"},
                        ["a", "pkg"], self.FAMILIES, "g.json", listing)
        self.assertEqual([line.split()[-1] for line in listing], ["a", "lib/src/pkg", "MISSING"])

    def test_the_repo_families_are_the_owners_list(self) -> None:
        """Owner, 2026-11-25: only libraries and families of generators; deploy, Jython, speed matching and pipeline
        steps are a node per file."""
        self.assertEqual(set(COV.FAMILIES), {
            "tools/hartlib/src/hartlib", "ops/hart-ops/card_pipeline", "ops/hart-ops/publications",
            "ops/station_maps/scripts", "tools/hosts/pi-os"})


class RepoTest(unittest.TestCase):
    def test_new_files_not_yet_added_count_as_in_the_checkout(self) -> None:
        """Review finding: check.sh runs before the commit, so an unstaged new script is not 'gone'."""
        real = COV._git_files
        with mock.patch.object(COV, "_git_files", side_effect=real) as files:
            COV.check(COV.BUILD.GRAPH)
        self.assertIn(mock.call("--others", "--exclude-standard"), files.call_args_list)

    def test_check_sh_is_no_entry_file_since_the_map_draws_its_steps(self) -> None:
        """ADR-037 stage 3: check.sh's checks are boxes by construction (the manifest lane), so coverage neither
        scans check.sh nor counts the manifest's scripts, and none of them is ALLOWED."""
        self.assertNotIn("tools/check.sh", COV.ENTRY_FILES)
        self.assertFalse(hasattr(COV, "MANIFEST"))
        lane = COV.BUILD.MANIFEST_LANE
        steps = lane.MANIFEST.load()
        graph = COV.BUILD.load(COV.BUILD.GRAPH)
        boxes = {n["path"]: n for n in graph["nodes"] if n.get("path")}
        for step in steps:
            with self.subTest(step=step.name):
                self.assertIn(step.script, boxes)
                self.assertNotIn(step.script, COV.ALLOWED)
                want = None if step.name in lane.HAND_KEPT_STEPS else lane.GEN
                self.assertEqual(boxes[step.script].get("gen"), want)

    def test_build_panels_sh_is_no_entry_file_since_the_map_draws_its_steps(self) -> None:
        """ADR-037 stage 5: make panels' steps are tools/pipeline/panels.toml's, each drawn in a generated box."""
        self.assertNotIn("tools/schematic/build_panels.sh", COV.ENTRY_FILES)
        lane = COV.BUILD.MANIFEST_LANE
        graph = COV.BUILD.load(COV.BUILD.GRAPH)
        boxes = {n["path"]: n for n in graph["nodes"] if n.get("path")}
        for step in lane.MANIFEST.load_panels():
            with self.subTest(step=step.name):
                self.assertEqual(boxes[step.script].get("gen"), lane.GEN)
                self.assertNotIn(step.script, COV.ALLOWED)
        self.assertTrue(boxes[lane.MANIFEST.PANELS_RUNNER].get("runner"))

    def test_the_repo_map_knows_every_pipeline_file(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            code = COV.main([])
        self.assertEqual(code, 0, err.getvalue())


if __name__ == "__main__":
    unittest.main()
