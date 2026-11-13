"""search-index.json: record shape, which pages are skipped, the leak guard, and the build check's link test."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import check_portal_build as check  # noqa: E402
import prepare_github_pages as build  # noqa: E402

INTRO = "Everything on the clipboard, readable on a phone, with a page for each job."


def _page(title="Session paperwork — HART", body=None, head=""):
    body = body if body is not None else f"<h1>Session paperwork</h1><p>{INTRO}</p><h2 id='jobs'>Crew sheets</h2>"
    return f"<!doctype html><html><head><title>{title}</title>{head}</head><body><header><p>Menu chrome that is not indexed.</p></header><main>{body}</main></body></html>"


def _site(pages: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for name, text in pages.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


def _index(root: Path) -> dict:
    return build.build_search_index(root)


class Shape(unittest.TestCase):
    def test_record_fields_and_limits(self):
        root = _site({"crew/index.html": _page(body=f"<h1>Session paperwork</h1><p>{INTRO * 6}</p><h2>Crew sheets</h2>" + f"<p>{INTRO * 6}</p>")})
        index = _index(root)
        self.assertEqual((index["version"], sorted(index)), (1, ["generated", "records", "version"]))
        self.assertRegex(index["generated"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        (rec,) = index["records"]
        self.assertEqual(set(rec), {"title", "url", "kind", "snippet", "text"})
        self.assertEqual((rec["title"], rec["url"], rec["kind"]), ("Session paperwork", "crew/index.html", "page"))
        self.assertLessEqual(len(rec["snippet"]), 160)
        self.assertLessEqual(len(rec["text"]), 300)
        self.assertTrue(rec["snippet"].endswith("…"))
        self.assertEqual(json.loads((root / "search-index.json").read_text())["records"], index["records"])

    def test_headings_are_searchable_and_chrome_is_not(self):
        (rec,) = _index(_site({"a/index.html": _page()}))["records"]
        self.assertEqual(rec["snippet"], INTRO)
        self.assertIn("Crew sheets", rec["text"])
        self.assertNotIn("Menu chrome", rec["snippet"] + rec["text"])

    def test_no_markup_and_entities_decoded(self):
        body = "<h1>Cars &amp; waybills</h1><p>Each <b>car</b> carries a card &amp; a waybill, read <a href='x'>here</a>.</p>"
        (rec,) = _index(_site({"a/index.html": _page(body=body)}))["records"]
        self.assertEqual(rec["snippet"], "Each car carries a card & a waybill, read here.")

    def test_inline_svg_title_does_not_join_the_page_title(self):
        body = f"<h1>Route</h1><p>{INTRO}</p><svg><title>Track diagram</title></svg>"
        (rec,) = _index(_site({"a/index.html": _page(body=body)}))["records"]
        self.assertEqual(rec["title"], "Session paperwork")

    def test_script_rendered_page_falls_back_to_description(self):
        body = '<h1>About HART</h1><p class="muted">Loading…</p>'
        head = '<meta name="description" content="Neville Island, the layout and the people who run it.">'
        (rec,) = _index(_site({"about/index.html": _page("About — HART", body, head)}))["records"]
        self.assertEqual(rec["snippet"], "Neville Island, the layout and the people who run it.")


class SkipRules(unittest.TestCase):
    def test_skipped_pages(self):
        pages = {
            "404.html": _page("Train order annulled — HART"),
            "fleet/index.html": _page("Moved — HART", head='<meta http-equiv="refresh" content="0; url=../photos/">', body="<h1>Redirecting</h1>"),
            "docs/html/old.html": _page("Moved — HART", body="<h1>Moved</h1><p>This publication now has its own page: x.</p>"),
            "x/index.html": _page(head='<meta name="robots" content="noindex">'),
            "keep/index.html": _page(),
        }
        self.assertEqual([r["url"] for r in _index(_site(pages))["records"]], ["keep/index.html"])

    def test_data_heavy_pages_keep_only_title_and_intro(self):
        body = f"<h1>Wiring viewer</h1><p>{INTRO}</p><h2>Radio node 12</h2><p>{INTRO} Pin B4 to the east throat motor.</p>"
        (rec,) = _index(_site({"behind/wiring.html": _page("Wiring viewer — HART", body)}))["records"]
        self.assertEqual(rec["text"], INTRO)
        self.assertNotIn("Radio node", rec["text"])

    def test_page_with_nothing_to_read_is_left_out(self):
        self.assertEqual(_index(_site({"a/index.html": _page(body="")}))["records"], [])


class LeakGuard(unittest.TestCase):
    def test_local_host_in_the_index_fails_the_build_and_leaves_no_file(self):
        root = _site({"a/index.html": _page(body="<h1>Tools</h1><p>Open the service at http://localhost:8760 on the layout PC.</p>")})
        with self.assertRaises(SystemExit) as raised:
            _index(root)
        self.assertNotIn("localhost", str(raised.exception))  # the text is not echoed
        self.assertIn("a/index.html", str(raised.exception))
        self.assertFalse((root / "search-index.json").exists())

    def test_private_name_check_runs_over_every_field(self):
        root = _site({"a/index.html": _page()})
        with mock.patch.object(build, "contains_private_name", side_effect=lambda t: t == "Session paperwork") as m:
            with self.assertRaises(SystemExit) as raised:
                _index(root)
        self.assertIn("(title)", str(raised.exception))
        self.assertTrue(m.called)
        self.assertFalse((root / "search-index.json").exists())

    def test_clean_index_passes_the_real_name_check(self):
        self.assertEqual(len(_index(_site({"a/index.html": _page()}))["records"]), 1)


class LinkCheck(unittest.TestCase):
    def _root(self, urls, extra=None):
        pages = {"a/index.html": _page(body="<h1 id='top'>A</h1><p>" + INTRO + "</p><h2 id='jobs'>Jobs</h2>"), "b.html": _page()}
        root = _site({**pages, **(extra or {})})
        recs = [{"title": "t", "url": u, "kind": "page", "snippet": "s", "text": ""} for u in urls]
        (root / "search-index.json").write_text(json.dumps({"version": 1, "generated": "2026-01-01T00:00:00Z", "records": recs}))
        return root

    def test_good_urls_and_anchor_pass(self):
        self.assertEqual(check.index_problems(self._root(["a/index.html", "b.html", "a/index.html#jobs", "a/"])), [])

    def test_missing_file_and_missing_anchor_are_reported(self):
        bad = check.index_problems(self._root(["nope/index.html", "a/index.html#gone"]))
        self.assertEqual(len(bad), 2)
        self.assertIn("does not resolve", bad[0])
        self.assertIn("#gone", bad[1])

    def test_leading_slash_is_refused(self):
        self.assertIn("no leading slash", check.index_problems(self._root(["/b.html"]))[0])

    def test_missing_index_and_bad_shape_are_reported(self):
        self.assertIn("missing", check.index_problems(_site({"b.html": _page()}))[0])
        root = self._root(["b.html"])
        data = json.loads((root / "search-index.json").read_text())
        data["records"][0]["snippet"] = "x" * 161
        (root / "search-index.json").write_text(json.dumps(data))
        self.assertIn("over 160", check.index_problems(root)[0])


if __name__ == "__main__":
    unittest.main()
