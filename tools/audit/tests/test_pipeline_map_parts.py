"""The files the pipeline map page is made from (tools/ops/build_pipeline_map.py): the page template and the viewer
scripts, read and checked before a page is drawn. The pages themselves are tested in test_pipeline_map.py."""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_pipeline_map", ROOT / "tools/ops/build_pipeline_map.py")
MAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MAP)
CACHED = (MAP.script_parts, MAP.script_text, MAP.page_template)
NODE = shutil.which("node")
NAMES = ("pipeline_map_layout.js", "pipeline_map_helpers.js", "pipeline_map_facets.js", "pipeline_map_view.js",
         "pipeline_map_view_frame.js", "pipeline_map_view_lanes.js", "pipeline_map_view_rail.js", "pipeline_map_view_nav.js",
         "pipeline_map_view_input.js")


class PagePartsTest(unittest.TestCase):
    def setUp(self) -> None:
        for fn in CACHED:
            fn.cache_clear()
        self.addCleanup(lambda: [fn.cache_clear() for fn in CACHED])
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def broken(self, name: str, content: str | None) -> Path:
        """A copy of the part `name` with this content, or none at all (None)."""
        path = self.tmp / name
        path.unlink(missing_ok=True)
        if content is not None:
            path.write_text(content, encoding="utf-8")
        for fn in CACHED:
            fn.cache_clear()
        return path

    def test_a_missing_or_empty_viewer_script_stops_the_build_naming_it(self) -> None:
        for index, name in enumerate(NAMES):
            for content, why in ((None, f"cannot read the viewer script {name}: "), ("  \n", f"the viewer script {name} is empty")):
                scripts = list(MAP.SCRIPTS)
                scripts[index] = self.broken(name, content)
                with self.subTest(name=name, why=why), unittest.mock.patch.object(MAP, "SCRIPTS", tuple(scripts)), \
                        self.assertRaisesRegex(MAP.GraphError, re.escape(why)):
                    MAP.script_text()

    def test_a_missing_empty_or_unfilled_template_stops_the_build(self) -> None:
        text = MAP.TEMPLATE.read_text(encoding="utf-8")
        for content, why in ((None, "cannot read the page template pipeline_map_page.html"),
                             ("\n", "the page template pipeline_map_page.html is empty"),
                             (text.replace("__LEGEND__", ""), r"each placeholder once: __LEGEND__ \(0 times\)"),
                             (text + "__DATA__", r"each placeholder once: __DATA__ \(2 times\)")):
            path = self.broken("pipeline_map_page.html", content)
            with self.subTest(why=why), unittest.mock.patch.object(MAP, "TEMPLATE", path), \
                    self.assertRaisesRegex(MAP.GraphError, why):
                MAP.page_template()

    def test_the_real_template_holds_each_placeholder_once(self) -> None:
        text = MAP.page_template()
        self.assertEqual({p: text.count(p) for p in MAP.PLACEHOLDERS}, dict.fromkeys(MAP.PLACEHOLDERS, 1))

    def test_the_script_is_the_layout_then_the_viewer(self) -> None:
        """One script, layout first, then its helpers and the filters' pure functions: the viewer uses their functions
        and the "use strict" directive. The viewer is app() cut into six files, joined in order: the first opens app(),
        the last closes and calls it."""
        layout, helpers, facets, view, frame, lanes, rail, nav, end = (path.read_text(encoding="utf-8") for path in MAP.SCRIPTS)
        self.assertEqual(MAP.SCRIPTS, (MAP.LAYOUT_JS, MAP.HELPERS_JS, MAP.FACETS_JS, MAP.VIEW_JS, MAP.VIEW_FRAME_JS,
                                       MAP.VIEW_LANES_JS, MAP.VIEW_RAIL_JS, MAP.VIEW_NAV_JS, MAP.VIEW_INPUT_JS))
        self.assertEqual(MAP.script_text(), layout + helpers + facets + view + frame + lanes + rail + nav + end)
        self.assertEqual([name for name, _ in MAP.script_parts()], list(NAMES))
        self.assertNotIn("app()", helpers)
        self.assertNotIn("app()", facets)
        self.assertIn("\nfunction app() {\n", view)
        for part in (view, frame, lanes, rail, nav):
            self.assertNotIn("\napp();", part)
        view = view + frame + lanes + rail + nav + end
        self.assertTrue(re.sub(r"^/\*.*?\*/\s*", "", layout, flags=re.S).startswith('"use strict";'))
        self.assertNotIn('\n"use strict";', view)
        self.assertNotIn("app()", layout)
        self.assertTrue(view.rstrip().endswith("\napp();"))

    @unittest.skipUnless(NODE, "node is not installed")
    def test_the_layout_loads_under_node_without_the_viewer(self) -> None:
        """Under node the layout only exports: it must not start the page (app is the viewer's, and not defined here)."""
        out = subprocess.run([NODE, "-e", "const m = require(process.argv[1]); console.log(typeof m.layout, typeof app)",
                              str(MAP.LAYOUT_JS)], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.split(), ["function", "undefined"])

    @unittest.skipUnless(NODE, "node is not installed")
    def test_the_joined_script_parses_and_needs_app_s_first_and_last_part(self) -> None:
        """The inlined script, the view parts joined, is valid JavaScript; without the part that opens app() or the one
        that closes it, it is not. (A middle part left out can still parse: the build stops on a missing part instead,
        test_a_missing_or_empty_viewer_script_stops_the_build_naming_it.)"""
        def parses(text: str) -> bool:
            path = self.tmp / "joined.js"
            path.write_text(text, encoding="utf-8")
            return subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True).returncode == 0
        parts = MAP.script_parts()
        self.assertTrue(parses(MAP.script_text()))
        for index in (NAMES.index("pipeline_map_view.js"), len(parts) - 1):
            with self.subTest(left_out=parts[index][0]):
                self.assertFalse(parses("".join(text for i, (_, text) in enumerate(parts) if i != index)))


if __name__ == "__main__":
    unittest.main()
