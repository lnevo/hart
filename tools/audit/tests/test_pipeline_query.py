"""tools/ops/pipeline_query.py on a small graph: a -> b -> c -> a (cycle), b -> d."""
from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("pipeline_query", ROOT / "tools/ops/pipeline_query.py")
Q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(Q)

DOMAINS = [{"id": "x", "label": "X", "color": "#000"}]


def n(nid: str, path: str = "", desc: str = "") -> dict:
    return {"id": nid, "label": nid, "kind": "generator", "status": "live", "domain": "x", "desc": desc,
            "path": path, "local": True}


NODES = [n("a", "src/a.py", "makes B"), n("b", "out/b.xml", "the Table"), n("c", "src/c.py"), n("d", "out/d.txt")]
EDGES = [{"from": "a", "to": "b", "label": "writes"}, {"from": "b", "to": "c", "label": "reads"},
         {"from": "c", "to": "a", "label": "loops"}, {"from": "b", "to": "d", "label": "feeds"}]


class QueryTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.graph_file = Path(tmp.name) / "g.json"
        self.graph_file.write_text(json.dumps({"domains": DOMAINS, "nodes": NODES, "edges": EDGES}))

    def run_q(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = Q.main(["--graph", str(self.graph_file), *args])
        return code, out.getvalue(), err.getvalue()

    def test_find_is_case_insensitive_over_desc(self):
        code, out, _ = self.run_q("find", "table")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip().splitlines(), ["out/b.xml | generator | live | the Table"])

    def test_find_no_match(self):
        self.assertIn("no node matches", self.run_q("find", "zzz")[1])

    def test_node_shows_inputs_and_outputs(self):
        code, out, _ = self.run_q("node", "out/b.xml")
        self.assertEqual(code, 0)
        self.assertIn("src/a.py [writes]", out)
        self.assertIn("src/c.py [reads]", out)
        self.assertIn("out/d.txt [feeds]", out)

    def test_node_by_id_and_dot_slash_path(self):
        self.assertEqual(self.run_q("node", "b")[1], self.run_q("node", "./out/b.xml")[1])

    def test_absolute_path_inside_repo(self):
        g = Q.Graph({"nodes": NODES, "edges": EDGES}, root=ROOT)
        self.assertEqual(g.resolve(str(ROOT / "out/b.xml")), "b")

    def test_absolute_path_outside_repo(self):
        g = Q.Graph({"nodes": NODES, "edges": EDGES}, root=ROOT)
        with self.assertRaises(Q.QueryError):
            g.resolve("/nowhere/else.txt")

    def test_depth_limit(self):
        _, out, _ = self.run_q("down", "a", "--depth", "1")
        self.assertIn("out/b.xml", out)
        self.assertNotIn("out/d.txt", out)
        _, out, _ = self.run_q("down", "a")
        self.assertIn("    out/d.txt", out)  # two levels in

    def test_up(self):
        _, out, _ = self.run_q("up", "d", "--depth", "2")
        self.assertEqual([x.strip().split(" ")[0] for x in out.splitlines()], ["out/d.txt", "out/b.xml", "src/a.py"])

    def test_cycle_terminates(self):
        _, out, _ = self.run_q("down", "a", "--depth", "9")
        self.assertIn("(shown above)", out)
        self.assertLess(len(out.splitlines()), 10)

    def test_unknown_node(self):
        code, out, err = self.run_q("node", "out/b.xm")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("closest: ", err)
        self.assertIn("out/b.xml", err)

    def test_negative_depth(self):
        code, _, err = self.run_q("down", "a", "--depth", "-1")
        self.assertEqual(code, 1)
        self.assertIn("--depth", err)

    def test_json(self):
        _, out, _ = self.run_q("--json", "down", "b", "--depth", "1")
        self.assertEqual([i["node"] for i in json.loads(out)["items"]], ["c", "d"])


if __name__ == "__main__":
    unittest.main()
