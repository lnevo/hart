"""The scanners' declarations in tools/pipeline/checks.toml (ADR-037 stage 4c): a check that walks a folder by design
declares the files it reads as quiet_inputs globs, and each list is the script's own scan list (its SCAN_GLOBS, or what
it lists), so the trace audit's cover for a scanner is exactly what the scanner reads and no wider. Also the loader's
rules for those globs, and that git's glob pathspecs, which the scripts list with, match what the manifest's globs
match."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load(name: str, rel: str):
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / rel)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module      # the manifest's dataclasses look their module up while the class is made
        spec.loader.exec_module(module)
    return sys.modules[name]


M = load("pipeline_manifest", "tools/pipeline/manifest.py")
REPO = M.repo()
STEPS = {s.name: s for s in M.load(where=REPO)}

# job -> the script's scan list, as repo globs
SCANS = {
    "public-text": lambda: load("check_public_text", "tools/audit/check_public_text.py").SCAN_GLOBS,
    "name-copies": lambda: load("check_name_copies", "tools/audit/check_name_copies.py").SCAN_GLOBS,
    "ai-speak": lambda: load("check_ai_speak", "tools/audit/check_ai_speak.py").DEFAULT_GLOBS,
    "agent-docs": lambda: load("check_agent_docs", "tools/audit/check_agent_docs.py").SCAN_GLOBS,
    "habits": lambda: load("check_habits", "tools/audit/check_habits.py").SCAN_GLOBS,
    "devices-one-path": lambda: load("check_devices_one_path", "tools/audit/check_devices_one_path.py").SCAN_GLOBS,
    "data-readers": lambda: load("check_data_readers", "tools/audit/check_data_readers.py").SCAN_GLOBS,
    "data-schemas": lambda: load("check_data", "tools/ops/check_data.py").SCAN_GLOBS,
    "py-sizes": lambda: load("check_py_sizes", "tools/audit/check_py_sizes.py").SCAN_GLOBS,
    # its scripts, then the CSV masters it reads the railroad's names from (hartlib.hand_tables.master_files)
    "hand-tables": lambda: (lambda m: (*m.SCAN_GLOBS, *m.hand_tables.master_files()))(
        load("check_hand_tables", "tools/audit/check_hand_tables.py")),
    # the agent-doc lane, then .gitmodules, which build_pipeline_map.py reads for the submodule boxes
    "pipeline-map": lambda: (*load("agent_docs_map", "tools/ops/agent_docs_map.py").scan_globs(), ".gitmodules"),
}
# the steps whose pages the site build makes, in the order the portal step lists their reads
PORTAL_PAGES = ("tables-browser", "repo-guide", "jmri-additions", "pipeline-map", "layout-index", "layout-index-cats",
                "wiring-json")
# what the site's data names outside www/ and the build copies in (prepare_github_pages._vendor_logo, MIRROR_PREFIXES)
PORTAL_VENDORED = ("ops/hart-ops/operator_logos/**", "external/sts-docker-data/Rolling Stock photos/*.jpg")


def declared_scan(step, scan) -> set[str]:
    """What the step declares of a scan list: its quiet_inputs, and those of its drawn inputs that are in the list (an
    agent doc drawn as a box is not also quiet: the loader refuses a path in both)."""
    return set(step.quiet_inputs) | ({e.path for e in step.inputs} & set(scan))


def git_list(*globs: str) -> set[str]:
    out = subprocess.run(["git", "ls-files", "-z", "--", *(f":(glob){g}" for g in globs)], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return {p for p in out.split("\0") if p}


class ScanListsTest(unittest.TestCase):
    def test_each_scanner_declares_its_own_scan_list(self) -> None:
        for job, scan in SCANS.items():
            with self.subTest(job=job):
                globs = scan()
                # a path in the manifest must match a tracked file, or be a map node marked local (a built page)
                live = {g for g in globs if REPO.matches_file(g) or g in REPO.local}
                self.assertEqual(declared_scan(STEPS[job], globs), live,
                                 f"{job}: its quiet_inputs in tools/pipeline/checks.toml differ from its script's "
                                 f"scan list (globs that match a tracked file)")
                self.assertTrue(live, job)

    def test_only_public_text_reads_the_whole_repo(self) -> None:
        whole = {name for name, s in STEPS.items() if set(s.quiet_inputs) & set(M.WHOLE_REPO)}
        self.assertEqual(whole, {"public-text"})
        self.assertTrue(STEPS["public-text"].reads_all)

    def test_the_scripts_list_what_their_globs_match(self) -> None:
        """The scripts list with git's :(glob) pathspecs; the manifest's globs must match the same files, or the
        equality above would not mean the audit covers what the script reads."""
        tracked = M.tracked_files()
        for job, scan in SCANS.items():
            for g in scan():
                with self.subTest(job=job, glob=g):
                    rx = M.glob_regex(g)
                    self.assertEqual({p for p in git_list(g) if p in tracked}, {p for p in tracked if rx.fullmatch(p)})

    def test_docs_index_reads_its_declared_folder(self) -> None:
        bdi = load("build_docs_index", "tools/ops/build_docs_index.py")
        self.assertIn(bdi.DOCS_DIR, {e.path for e in STEPS["docs-index"].inputs})

    def test_pipeline_map_coverage_declares_its_entry_files(self) -> None:
        cov = load("pipeline_map_coverage", "tools/ops/pipeline_map_coverage.py")
        step = STEPS["pipeline-map-coverage"]
        drawn = {e.path for e in step.inputs}
        for entry in cov.ENTRY_FILES:
            with self.subTest(entry=entry):
                want = entry if entry in REPO.files else f"{entry}/*.sh"      # a folder: the .sh files in it
                self.assertIn(want, drawn | set(step.quiet_inputs))

    def test_the_portal_declares_the_site_its_sources_and_the_pages_it_builds(self) -> None:
        published = json.loads((ROOT / "www/scripts/published-files.json").read_text(encoding="utf-8"))
        want = ["www/**", *sorted({f"{os.path.dirname(src)}/*{os.path.splitext(src)[1]}" for src in published.values()}),
                *PORTAL_VENDORED]
        for name in PORTAL_PAGES:
            s = STEPS[name]
            want += [p for p in (*(e.path for e in s.inputs), *s.quiet_inputs) if p not in want]
        want = [p for p in want if p == "www/**" or not M.covers("www/**", p)]
        drawn = {e.path for e in STEPS["portal"].inputs}
        self.assertEqual(list(STEPS["portal"].quiet_inputs), [p for p in want if p not in drawn])
        for src in published.values():
            self.assertTrue(any(M.covers(g, src) for g in STEPS["portal"].quiet_inputs), src)

    def test_the_portal_pages_are_the_ones_the_site_build_makes(self) -> None:
        # the site build imports the page fills itself and its built files' builders through site_views (ADR-036)
        sources = [(ROOT / f"www/scripts/{f}").read_text(encoding="utf-8")
                   for f in ("prepare_github_pages.py", "site_views.py")]
        imported = {a.name for source in sources for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Import)
                    for a in node.names}
        made = {name for name, s in STEPS.items() if s.script.startswith("www/scripts/")
                and Path(s.script).stem in imported}
        self.assertIn(f'_load_tool("{STEPS["pipeline-map"].script}")', sources[1])
        self.assertEqual(made | {"pipeline-map"}, set(PORTAL_PAGES))


TRACKED = {"tools/a.py", "data/x.csv", "data/sub/y.csv", "www/index.html"}
GRAPH = {"domains": [{"id": "layout"}], "nodes": [], "edges": []}


def refused(**fields) -> str:
    base = {"name": '"one"', "runner": '"check"', "cmd": '["python3", "tools/a.py"]', "domain": '"layout"',
            "label": '"a.py"', "desc": '"First."', "git": "[]", **fields}
    text = "[[step]]\n" + "".join(f"{k} = {v}\n" for k, v in base.items())
    try:
        M.parse(tomllib.loads(text), "t.toml", M.repo_from(TRACKED, GRAPH))
    except M.ManifestError as err:
        return str(err)
    return ""


class ScanGlobRulesTest(unittest.TestCase):
    def test_a_narrow_glob_that_matches_a_file_loads(self) -> None:
        self.assertEqual(refused(quiet_inputs='["data/**/*.csv", "www/*.html"]'), "")

    def test_a_glob_that_matches_nothing_or_only_folders_is_refused(self) -> None:
        self.assertIn("quiet_inputs: data/*.txt names no tracked file or folder", refused(quiet_inputs='["data/*.txt"]'))
        self.assertIn("quiet_inputs: dat? matches tracked folders only, no file", refused(quiet_inputs='["dat?"]'))

    def test_the_whole_repo_needs_reads_all_and_reads_all_needs_it(self) -> None:
        for glob in (*M.WHOLE_REPO, "**/**", "*/**/*.*"):      # the last two name every file of TRACKED too
            with self.subTest(glob=glob):
                self.assertIn(f"quiet_inputs: {glob} is the whole repo", refused(quiet_inputs=f'["{glob}"]'))
                self.assertEqual(refused(quiet_inputs=f'["{glob}"]', reads_all='"every file"'), "")
        self.assertIn("reads_all is set, so quiet_inputs must hold **/*",
                      refused(quiet_inputs='["data/x.csv"]', reads_all='"every file"'))
        self.assertIn("reads_all: must be a str with text", refused(quiet_inputs='["**/*"]', reads_all='""'))
        self.assertEqual(refused(quiet_inputs='["**/*.csv"]'), "")      # most of the files, not all: a scan glob


if __name__ == "__main__":
    unittest.main()
