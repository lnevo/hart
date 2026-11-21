"""The agent-doc lane of the pipeline map (tools/ops/agent_docs_map.py), the shared parser it reads links with
(tools/audit/check_agent_docs.py) and the coverage check for new agent docs (tools/ops/pipeline_map_coverage.py)."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DOCS = _load("check_agent_docs", "tools/audit/check_agent_docs.py")
GEN = _load("agent_docs_map", "tools/ops/agent_docs_map.py")
MAP = _load("build_pipeline_map", "tools/ops/build_pipeline_map.py")
COV = _load("pipeline_map_coverage", "tools/ops/pipeline_map_coverage.py")


def targets(rel: str, text: str) -> list[tuple[str, str | None]]:
    return [(r.kind, r.target) for r in DOCS.references(rel, text)]


class ReferencesTest(unittest.TestCase):
    def test_link_is_read_from_the_linking_files_folder(self) -> None:
        self.assertEqual(targets(".cursor/rules/x.mdc", "Follow [`AGENTS.md`](../../AGENTS.md)."),
                         [("link", "AGENTS.md"), ("code", "AGENTS.md")])
        self.assertEqual(targets("wiki/home.md", "[s](./STATUS.md#counts)"), [("link", "wiki/STATUS.md")])

    def test_link_that_climbs_out_or_is_absolute_has_no_target(self) -> None:
        self.assertEqual(targets("wiki/home.md", "[x](../../outside.md) [y](/etc/hosts)"),
                         [("link", None), ("link", None)])

    def test_web_mail_anchor_and_comment_are_skipped(self) -> None:
        text = "[a](https://x.org/a.md) [b](mailto:a@example.invalid) [c](#top)\n<!-- [d](wiki/STATUS.md)\n`wiki/x` -->"
        self.assertEqual(targets("AGENTS.md", text), [])

    def test_angle_bracket_link_and_title(self) -> None:
        self.assertEqual(targets("AGENTS.md", '[a](<wiki/my page.md>) [b](wiki/home.md "Home")'),
                         [("link", "wiki/my page.md"), ("link", "wiki/home.md")])

    def test_backticked_path_with_dot_slash_and_trailing_slash(self) -> None:
        self.assertEqual(targets("AGENTS.md", "`./tools/check.sh` `wiki/projects/` `tools/../wiki/home.md`"),
                         [("code", "tools/check.sh"), ("code", "wiki/projects"), ("code", "wiki/home.md")])

    def test_path_or_link_that_climbs_out_is_reported(self) -> None:
        self.assertEqual(DOCS.problems_in("wiki/x.md", "`tools/../../secret/x.py` [a](../../out.md) `tools/check.sh`"),
                         ["wiki/x.md: link ../../out.md leaves the repo",
                          "wiki/x.md: path tools/../../secret/x.py leaves the repo"])

    def test_git_failure_is_a_clear_error(self) -> None:
        with self.assertRaisesRegex(DOCS.AgentDocsError, "git ls-files --no-such-flag failed"):
            DOCS._git("ls-files", "--no-such-flag")


class ReadingOrderTest(unittest.TestCase):
    def test_back_and_sideways_links_are_dropped(self) -> None:
        pairs = {("A", "b"), ("A", "c"), ("b", "A"), ("b", "c"), ("c", "d"), ("d", "b")}
        self.assertEqual(GEN.reading_order(pairs, "A"), [("A", "b"), ("A", "c"), ("c", "d")])

    def test_a_box_start_cannot_reach_keeps_its_links(self) -> None:
        self.assertEqual(GEN.reading_order({("A", "b"), ("z", "A"), ("z", "b")}, "A"),
                         [("A", "b"), ("z", "A"), ("z", "b")])


class FrontMatterTest(unittest.TestCase):
    def test_one_line_description(self) -> None:
        self.assertEqual(GEN.front_description("s.md", "---\nname: x\ndescription: \"Use when x.\"\n---\nbody"),
                         "Use when x.")

    def test_bad_front_matter_is_named(self) -> None:
        for text, why in (("# no front matter", "no front matter"),
                          ("---\nname: x\n---\n", "has no description"),
                          ("---\ndescription: >\n  folded\n---\n", "several lines"),
                          ("---\ndescription: first\n  second\n---\n", "several lines"),
                          ("---\ndescription:\n---\n", "empty")):
            with self.subTest(text=text), self.assertRaisesRegex(GEN.AgentDocsMapError, why):
                GEN.front_description("s.md", text)

    def test_quoted_descriptions(self) -> None:
        for raw, want in (("Use with the 'deploy'", "Use with the 'deploy'"), ("'it''s'", "it's"),
                          ('"say \\"hi\\""', 'say "hi"'), ("'x'", "x")):
            with self.subTest(raw=raw):
                self.assertEqual(GEN.front_description("s.md", f"---\ndescription: {raw}\n---\n"), want)
        for raw in ('"open', '"bad \\q"'):
            with self.subTest(raw=raw), self.assertRaises(GEN.AgentDocsMapError):
                GEN.front_description("s.md", f"---\ndescription: {raw}\n---\n")

    def test_nested_agents_md_is_in_the_set(self) -> None:
        self.assertTrue(any(GEN.matches("ops/hart-ops/AGENTS.md", g) for g in GEN.GLOBS))
        self.assertTrue(any(GEN.matches("cats/AGENTS.md", g) for g in GEN.GLOBS))

    def test_unreadable_doc_is_a_clear_error(self) -> None:
        with self.assertRaisesRegex(GEN.AgentDocsMapError, "no/such.md is in git but cannot be read"):
            GEN._read_file("no/such.md")

    def test_glob_star_stays_in_one_folder(self) -> None:
        self.assertTrue(GEN.matches(".claude/skills/a/SKILL.md", ".claude/skills/*/SKILL.md"))
        self.assertFalse(GEN.matches(".claude/skills/a/b/SKILL.md", ".claude/skills/*/SKILL.md"))
        self.assertFalse(GEN.matches("ops/hart-ops/AGENTS.md", "*/AGENTS.md"))   # "*/*/AGENTS.md" covers it


FILES = {
    "AGENTS.md": "Read [home](wiki/home.md). Agents: `panel-tracer`. `/done` closes. [`x` skill](.claude/skills/x/SKILL.md)",
    "wiki/home.md": "Back to [AGENTS](../AGENTS.md); projects in [p](projects/a.md); status `wiki/STATUS.md`",
    "wiki/AGENTS_GIT.md": "See `AGENTS.md`.",
    "wiki/STATUS_LOG.md": "old",
    "wiki/not-pending.md": "[s](STATUS.md)",
    "wiki/STATUS.md": "[log](STATUS_LOG.md) [np](not-pending.md) [git](AGENTS_GIT.md)",
    "wiki/decisions/README.md": "[h](../home.md)", "wiki/pipelines/README.md": "[h](../home.md)",
    "wiki/projects/a.md": "[d](../decisions/README.md) [pl](../pipelines/README.md)",
    ".cursor/rules/r.mdc": "[a](../../AGENTS.md)",
    ".claude/skills/x/SKILL.md": "---\ndescription: Use for x.\n---\n",
    ".claude/agents/panel-tracer.md": "---\ndescription: Traces.\n---\n",
    ".claude/commands/done.md": "---\ndescription: Close out.\n---\n",
    "cats/AGENTS.md": "cats rules",
    "docs/INDEX.md": "", "docs/pipeline-map/pipeline_map.json": "", "tools/ops/pipeline_query.py": "",
    "tools/audit/check_agent_docs.py": "",
}
HAND = [{"id": p, "label": p, "kind": "output", "status": "live", "domain": "extras", "desc": "", "path": p}
        for p in (*GEN.HAND_KEPT, GEN.CHECKER)]


def regen(nodes=None, edges=None, domains=None, files=FILES):
    data = {"domains": domains or [{"id": "extras"}, {"id": "agents"}], "nodes": nodes or list(HAND),
            "edges": edges or []}
    return GEN.regenerate(data, tracked=frozenset(files), read=files.__getitem__,
                          checked=["AGENTS.md", ".claude/skills/x/SKILL.md", ".cursor/rules/r.mdc", "cats/AGENTS.md"])


class RegenerateTest(unittest.TestCase):
    def test_boxes_and_links(self) -> None:
        out = regen()
        gen = {n["id"]: n for n in out["nodes"] if n.get("gen") == GEN.GEN}
        self.assertEqual(gen[".claude/skills/x/SKILL.md"]["label"], "skill: x")
        self.assertEqual(gen[".claude/skills/x/SKILL.md"]["desc"], "Use for x.")
        self.assertEqual(gen[".claude/commands/done.md"]["label"], "/done")
        self.assertIn(".cursor", gen)
        self.assertNotIn(".cursor/rules/r.mdc", gen)
        links = {(e["from"], e["to"], e["label"]) for e in out["edges"]}
        for want in (("AGENTS.md", "wiki/home.md", "points to"),
                     ("AGENTS.md", ".claude/agents/panel-tracer.md", "points to"),   # backticked subagent name
                     ("AGENTS.md", ".claude/commands/done.md", "points to"),         # backticked /command
                     ("wiki/home.md", "wiki/projects", "points to"),                 # into a folder box
                     ("wiki/home.md", "wiki/STATUS.md", "points to"),                # a hand-kept box
                     ("wiki/projects", "wiki/decisions", "points to"),
                     (".cursor", GEN.CHECKER, "check"), ("AGENTS.md", GEN.CHECKER, "check")):
            self.assertIn(want, links)
        self.assertNotIn(("wiki/home.md", "AGENTS.md", "points to"), links)    # back up the reading order
        self.assertIn((".cursor", "AGENTS.md", "points to"), links)    # AGENTS.md does not reach .cursor here: kept

    def test_regenerate_replaces_only_generated_parts(self) -> None:
        hand_edge = {"from": "docs/INDEX.md", "to": GEN.CHECKER, "label": "hand"}
        first = regen(edges=[hand_edge])
        stale_nodes = [n for n in first["nodes"] if n["id"] != "wiki/STATUS_LOG.md"]
        stale_edges = [e for e in first["edges"] if e.get("gen")][1:] + [hand_edge]
        again = regen(nodes=stale_nodes, edges=stale_edges)
        self.assertEqual(again["nodes"], first["nodes"])
        self.assertEqual(again["edges"], first["edges"])
        self.assertEqual(again["edges"][0], hand_edge)

    def test_errors_are_named(self) -> None:
        with self.assertRaisesRegex(GEN.AgentDocsMapError, "no 'agents' domain"):
            regen(domains=[{"id": "extras"}])
        clash = [*HAND, {"id": "home", "label": "h", "kind": "output", "status": "live", "domain": "extras",
                         "path": "wiki/home.md"}]
        with self.assertRaisesRegex(GEN.AgentDocsMapError, "wiki/home.md: generated by"):
            regen(nodes=clash)
        with self.assertRaisesRegex(GEN.AgentDocsMapError, "no hand-kept box for docs/INDEX.md"):
            regen(nodes=[n for n in HAND if n["path"] != "docs/INDEX.md"])
        with self.assertRaisesRegex(GEN.AgentDocsMapError, "hand-kept links that the agent-doc lane now generates"):
            regen(edges=[{"from": "AGENTS.md", "to": "wiki/home.md"}])
        missing = {k: v for k, v in FILES.items() if k != "wiki/not-pending.md"}
        with self.assertRaisesRegex(GEN.AgentDocsMapError, "wiki/not-pending.md is in DOCS"):
            regen(files=missing)
        bad = dict(FILES, **{".claude/agents/panel-tracer.md": "no front matter"})
        with self.assertRaisesRegex(GEN.AgentDocsMapError, "panel-tracer.md has no front matter"):
            regen(files=bad)


class BuildCheckTest(unittest.TestCase):
    def test_check_fails_when_the_generated_lane_is_stale(self) -> None:
        data = json.loads(MAP.GRAPH.read_text())
        data["edges"] = [e for e in data["edges"] if not (e.get("gen") and e["label"] == "check")]
        with tempfile.TemporaryDirectory() as tmp:
            graph, out = Path(tmp) / "g.json", Path(tmp) / "m.html"
            graph.write_text(json.dumps(data))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(MAP.main(["--graph", str(graph), "--out", str(out), "--check"]), 1)
            self.assertIn("agent-doc lane is generated", err.getvalue())
            self.assertEqual(json.loads(graph.read_text()), data)    # --check writes nothing

    def test_only_the_plain_build_writes_the_graph(self) -> None:
        data = json.loads(MAP.GRAPH.read_text())
        data["edges"] = [e for e in data["edges"] if not (e.get("gen") and e["label"] == "check")]
        with tempfile.TemporaryDirectory() as tmp:
            graph, out = Path(tmp) / "g.json", Path(tmp) / "m.html"
            graph.write_text(json.dumps(data))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(MAP.main(["--graph", str(graph), "--public", "--out", str(out)]), 1)
            self.assertEqual(json.loads(graph.read_text()), data)
            self.assertFalse(out.exists())
            self.assertIn(f"python3 tools/ops/build_pipeline_map.py --graph {graph}", err.getvalue())
            self.assertIn(MAP.SITE_BUILD, err.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(MAP.main(["--graph", str(graph), "--out", str(out)]), 0)
            self.assertEqual(graph.read_text(), MAP.GRAPH.read_text())

    def test_malformed_entries_are_graph_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "g.json"
            for nodes, why in ((["x"], "every entry of 'nodes' must be an object"),
                               ([{"id": "x", "path": 5}], "path must be text")):
                bad.write_text(json.dumps({"domains": [], "nodes": nodes, "edges": []}))
                with self.subTest(why=why), self.assertRaisesRegex(MAP.GraphError, why):
                    MAP.read(bad)

    def test_committed_graph_is_current(self) -> None:
        self.assertEqual(MAP.graph_text(MAP.validate(MAP.regenerate(MAP.read(MAP.GRAPH)))), MAP.GRAPH.read_text())

    def test_unreadable_graph_is_a_graph_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "g.json"
            bad.write_text("{not json")
            with self.assertRaisesRegex(MAP.GraphError, "not valid JSON"):
                MAP.read(bad)
            with self.assertRaisesRegex(MAP.GraphError, "cannot read the graph"):
                MAP.read(Path(tmp) / "missing.json")


class CoverageTest(unittest.TestCase):
    def test_new_agent_doc_not_in_the_map_fails(self) -> None:
        problems = COV.agent_doc_gaps([".claude/skills/new/SKILL.md", ".claude/agents/a.md"],
                                      {".claude/agents/a.md": "a"}, "g.json")
        self.assertEqual(len(problems), 1)
        self.assertIn("agent doc .claude/skills/new/SKILL.md is not in the map: git add it", problems[0])

    def test_every_agent_doc_in_the_repo_is_a_box(self) -> None:
        data = MAP.load(MAP.GRAPH)
        paths = {n["path"]: n["id"] for n in data["nodes"] if n.get("path")}
        self.assertEqual(COV.agent_doc_gaps(GEN.glob_files(), paths, "g"), [])


if __name__ == "__main__":
    unittest.main()
