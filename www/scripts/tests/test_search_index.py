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
        self.assertLessEqual(len(rec["text"]), 8000)
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


class ReviewFixes(unittest.TestCase):
    """Behaviour changed after the PR #388 review."""

    def test_publication_header_is_not_the_snippet(self):
        body = f"<h1>East End</h1><p>Publication SM-02 · Revision A · Effective 23 July 2026</p><p>{INTRO}</p>"
        (rec,) = _index(_site({"crew/maps/east-end/index.html": _page(body=body)}))["records"]
        self.assertEqual(rec["snippet"], INTRO)
        self.assertNotIn("Revision A", rec["text"])

    def test_list_items_and_definitions_are_searchable(self):
        body = f"<h1>Glossary</h1><p>{INTRO}</p><dl><dt>Waybill</dt><dd>Goes with the car card.</dd></dl><ul><li>Short item</li></ul>"
        (rec,) = _index(_site({"operators/glossary/index.html": _page(body=body)}))["records"]
        for word in ("Waybill", "Goes with the car card.", "Short item"):
            self.assertIn(word, rec["text"])

    def test_reading_location_is_not_a_redirect(self):
        body = f"<h1>Roster</h1><p>{INTRO}</p><script>var h = window.location.hash;</script>"
        self.assertEqual(len(_index(_site({"roster/index.html": _page(body=body)}))["records"]), 1)
        stub = "<h1>Roster</h1><p>Short.</p><script>location.href = 'new/';</script>"
        self.assertEqual(_index(_site({"old/index.html": _page(body=stub)}))["records"], [])

    def test_quoted_tags_are_dropped_from_text(self):
        body = f"<h1>Standards</h1><p>{INTRO}</p><p>Use &lt;title&gt; on every page.</p>"
        (rec,) = _index(_site({"docs/std.html": _page(body=body)}))["records"]
        self.assertNotIn("<", rec["text"])

    def test_non_object_index_is_reported_not_crashed(self):
        for bad in ("[]", '{"version": 1, "generated": "x", "records": [3]}'):
            root = _site({"index.html": _page()})
            (root / "search-index.json").write_text(bad, encoding="utf-8")
            self.assertTrue(check.index_problems(root))

    def test_built_pages_carry_the_search_marker(self):
        self.assertIn('name="hart-search"', build._head_tags(Path("crew/index.html"), "Crew"))


def _fleet_site(items: list[dict]) -> Path:
    """A built tree holding data/fleet-gallery.json (as the build leaves it) and the Photos page."""
    root = _site({"photos/index.html": _page(title="Photos — HART", body=f"<h1>Photos</h1><p>{INTRO}</p>")})
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "fleet-gallery.json").write_text(json.dumps({"albums": [], "items": items}), encoding="utf-8")
    return root


def _car(fid, title, album="freight", type_="Boxcar", **extra):
    road, _, number = title.rpartition(" ")
    return {"id": fid, "album": album, "src": f"assets/fleet/{album}/{fid}.jpg", "thumb": "t.jpg", "title": title,
            "caption": f"{road} · {type_} · 40' steel", "credit": "Car roster", "road": road, "number": number,
            "type": type_, **extra}


def _fleet(index):
    return [r for r in index["records"] if r["kind"] != "page"]


class FleetRecords(unittest.TestCase):
    def test_kinds_urls_and_text(self):
        root = _fleet_site([
            _car("csx-2738", "CSX 2738", "locos", "Locomotive"),
            _car("c-o-w86", "C&O W86", "mow", "MOW"),
            _car("ttc-4678", "TTC 4678", "mow", "Streetcar"),
            _car("b-o-4674", "B&O 4674", "freight", "Hopper"),
        ])
        recs = {r["title"]: r for r in _fleet(_index(root))}
        self.assertEqual({t: r["kind"] for t, r in recs.items()},
                         {"CSX 2738": "locomotive", "C&O W86": "mow", "TTC 4678": "mow", "B&O 4674": "car"})
        self.assertEqual(recs["B&O 4674"]["url"], "photos/index.html#rolling-stock/b-o-4674")
        self.assertEqual(set(recs["B&O 4674"]), {"title", "url", "kind", "snippet", "text"})
        for word in ("B&O", "4674", "Hopper", "40' steel"):
            self.assertIn(word, recs["B&O 4674"]["text"])

    def test_only_public_display_fields_are_used(self):
        item = _car("csx-2738", "CSX 2738", rights="all rights reserved", internal="ops/car-cards/secret")
        item["src"] = "../ops/car-cards/car-images/IMG_1.png"
        (rec,) = _fleet(_index(_fleet_site([item])))
        blob = json.dumps(rec)
        for leak in ("ops/car-cards", "assets/fleet", "t.jpg", "rights", "secret", "Car roster", ".png", ".jpg"):
            self.assertNotIn(leak, blob)

    def test_long_captions_are_clipped(self):
        item = _car("a-1", "A 1")
        item["caption"] = "A · Boxcar · " + "long note " * 40
        (rec,) = _fleet(_index(_fleet_site([item])))
        self.assertLessEqual(len(rec["snippet"]), 160)

    def test_dropped_items_have_no_record(self):
        # The build's filter has already removed items whose photo is missing; the index reads what is left.
        root = _fleet_site([_car("a-1", "A 1")])
        self.assertEqual(len(_fleet(_index(root))), 1)
        (root / "data" / "fleet-gallery.json").write_text(json.dumps({"items": []}))
        self.assertEqual(_fleet(_index(root)), [])

    def test_item_without_id_or_private_is_skipped(self):
        items = [_car("", "A 1"), _car("a-2", "A 2", public=False)]
        self.assertEqual(_fleet(_index(_fleet_site(items))), [])

    def test_no_data_file_no_records(self):
        self.assertEqual(_fleet(_index(_site({"photos/index.html": _page()}))), [])

    def test_check_accepts_known_ids_and_album_chips(self):
        root = _fleet_site([_car("a-1", "A 1")])
        index = _index(root)
        index["records"].append(dict(index["records"][-1], url="photos/index.html#rolling-stock/freight"))
        (root / "search-index.json").write_text(json.dumps(index), encoding="utf-8")
        self.assertEqual(check.index_problems(root), [])

    def test_check_rejects_an_id_not_in_the_data(self):
        root = _fleet_site([_car("a-1", "A 1")])
        index = _index(root)
        index["records"][-1]["url"] = "photos/index.html#rolling-stock/gone"
        (root / "search-index.json").write_text(json.dumps(index), encoding="utf-8")
        (problem,) = check.index_problems(root)
        self.assertIn("not an item id", problem)

    def test_check_flags_missing_and_duplicate_ids(self):
        root = _fleet_site([_car("a-1", "A 1"), _car("a-1", "A 2"), _car("", "A 3")])
        _index(root)
        joined = " ".join(check.index_problems(root))
        self.assertIn("used twice", joined)
        self.assertIn("has no id", joined)

    def test_source_data_has_unique_ids(self):
        items = json.loads((SCRIPTS.parent / "data" / "fleet-gallery.json").read_text())["items"]
        ids = [i.get("id") for i in items]
        self.assertTrue(all(ids))
        self.assertEqual(len(ids), len(set(ids)))
