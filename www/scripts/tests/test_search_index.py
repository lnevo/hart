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


GLOSSARY = (
    "<h1>Glossary</h1><p>" + INTRO + "</p><dl>"
    "<dt id='waybill'>Waybill</dt><dd>Goes with the car card &amp; says where the car goes next.</dd>"
    "<dt>No id</dt><dd>Skipped.</dd>"
    "<dt id='nvl'>NVL</dt><dd>The Neville Island Turn.</dd></dl>"
)
CREW = {
    "jobs": [{"id": "nvl", "code": "NVL", "name": "Neville Island Turn", "title": "Crew Instructions", "pub": "CI-NVL",
              "engine": {"label": "POHC 2091", "img": "assets/crew/secret-thumb.jpg"}, "summary": "Work the island.",
              "steps": ["Assign on the train."], "talk": [{"who": "Dispatcher", "why": "Clearance."}],
              "source": "docs-ops/Secret_Crew.docx", "revision": "D"}],
    "timetable": {"pub": "TT-23", "title": "Route 23 Timetable", "summary": "Station times.", "rows": [["9:00", "Barn", "5:00 PM"]],
                  "source": "docs-ops/tt.pptx"},
    "scale": {"pub": "EQ-01", "title": "Scale Operating Instructions", "summary": "Weigh cars.",
              "sections": [{"heading": "Section 1", "parts": [{"h": "1.1 Approach", "items": ["Stop well short."]}]}]},
    "colors": [{"id": "blue", "label": "BLUE", "hex": "#0000CD", "dest": "Demmler Yard", "train": "D749"}],
    "overview": {"pub": "SM-01", "title": "Subdivision Diagram", "what": "The whole railroad.", "alt": "Diagram.", "img": "assets/maps/a.png"},
    "maps": [{"id": "west-yard", "pub": "SM-02", "title": "West Yard", "what": "Where D749 ties down.", "tracks": [{"track": "W-1", "purpose": "Yard track"}]}],
    "spotsheet": {
        "industries": [{"id": "shenango", "name": "Shenango Coke Works", "traffic": "Coke out.", "history": ["Founded 1900."],
                        "spots": [["1", "Coke Loading", "Hopper", "Empty", "Coke"]]}],
        "offline": [{"id": "scully", "name": "Scully Yard", "about": ["POHC gateway."], "inbound": ["Exxon Chemical"], "inLabel": "Inbound"}],
        "desk": [{"id": "south-yard-notes", "name": "South Yard"}],
    },
}
INDUSTRIES = {"industries": [
    {"name": "Shenango Coke Works", "blurb": "Coke for steel customers.", "commodities": ["Coke"], "spot": "shenango", "logo": "ops-logo.png"},
    {"name": "Interchange", "blurb": "Off-island shippers.", "spot": "scully"},
    {"name": "Orphan", "blurb": "No sheet.", "spot": "nowhere"},
]}


def _extra_site() -> Path:
    pages = {"operators/glossary/index.html": _page("Glossary — HART", GLOSSARY)}
    for url in ("nvl", "tt23", "scale", "colors", "maps", "maps/west-yard", "industries"):
        pages[f"crew/{url}/index.html"] = _page(f"{url} — HART", "<h1>Sheet</h1><p>Loading…</p>")
    root = _site(pages)
    (root / "data").mkdir()
    (root / "data/crew.json").write_text(json.dumps(CREW))
    (root / "data/industries.json").write_text(json.dumps(INDUSTRIES))
    return root


class ExtraKinds(unittest.TestCase):
    """Glossary term, industry and crew-sheet records, and the drawn-anchor check."""

    def setUp(self):
        self.root = _extra_site()
        self.recs = _index(self.root)["records"]

    def kind(self, kind):
        return [r for r in self.recs if r["kind"] == kind]

    def test_glossary_terms_link_to_their_ids_and_skip_terms_without_one(self):
        terms = {r["title"]: r for r in self.kind("term")}
        self.assertEqual(sorted(terms), ["NVL", "Waybill"])
        self.assertEqual(terms["Waybill"]["url"], "operators/glossary/index.html#waybill")
        self.assertEqual(terms["Waybill"]["snippet"], "Goes with the car card & says where the car goes next.")
        self.assertTrue(any(r["kind"] == "page" and r["url"] == "operators/glossary/index.html" for r in self.recs))

    def test_industries_merge_card_and_sheet_and_drop_cards_without_a_sheet(self):
        inds = {r["title"]: r for r in self.kind("industry")}
        self.assertEqual(sorted(inds), ["Scully Yard", "Shenango Coke Works"])
        shen = inds["Shenango Coke Works"]
        self.assertEqual(shen["url"], "crew/industries/index.html#shenango")
        self.assertEqual(shen["snippet"], "Coke for steel customers.")
        for word in ("Founded 1900.", "Coke out.", "Coke Loading"):
            self.assertIn(word, shen["text"])
        self.assertIn("Exxon Chemical", inds["Scully Yard"]["text"])

    def test_crew_records_one_per_job_or_publication(self):
        crew = {r["url"]: r for r in self.kind("crew")}
        self.assertEqual(sorted(crew), ["crew/colors/index.html", "crew/maps/index.html", "crew/maps/west-yard/index.html",
                                        "crew/nvl/index.html", "crew/scale/index.html", "crew/tt23/index.html"])
        self.assertEqual(crew["crew/nvl/index.html"]["title"], "NVL Neville Island Turn")
        self.assertIn("Assign on the train.", crew["crew/nvl/index.html"]["text"])
        self.assertIn("Stop well short.", crew["crew/scale/index.html"]["text"])
        self.assertIn("Demmler Yard", crew["crew/colors/index.html"]["text"])
        self.assertIn("W-1", crew["crew/maps/west-yard/index.html"]["text"])

    def test_no_paths_sources_images_or_hex_in_any_record(self):
        for rec in self.recs:
            body = " ".join((rec["title"], rec["snippet"], rec["text"]))
            for bad in ("Secret", ".docx", ".pptx", "assets/", "docs-ops", "#0000CD", "ops-logo"):
                self.assertNotIn(bad, body, rec["url"])

    def test_sheet_record_replaces_the_bare_page_record(self):
        self.assertEqual([r["kind"] for r in self.recs if r["url"] == "crew/nvl/index.html"], ["crew"])

    def test_every_record_passes_the_build_check_including_drawn_anchors(self):
        self.assertEqual(check.index_problems(self.root), [])

    def test_drawn_anchor_must_exist_in_the_data(self):
        data = json.loads((self.root / "search-index.json").read_text())
        data["records"].append({"title": "t", "url": "crew/industries/index.html#nowhere", "kind": "industry", "snippet": "s", "text": ""})
        (self.root / "search-index.json").write_text(json.dumps(data))
        bad = check.index_problems(self.root)
        self.assertEqual(len(bad), 1)
        self.assertIn("#nowhere", bad[0])

    def test_site_without_the_data_still_builds(self):
        self.assertEqual([r["kind"] for r in _index(_site({"a/index.html": _page()}))["records"]], ["page"])

# The Photos page's own album-hash map, which the check reads for the chip names.
PHOTOS_CATS = '<script>var CATS = { "rolling-stock": { chips: "#album-bar", attr: "data-album", subs: { locomotives: "locos", freight: "freight", mow: "mow" } } };</script>'


def _fleet_site(items: list[dict]) -> Path:
    """A built tree holding data/fleet-gallery.json (as the build leaves it) and the Photos page."""
    root = _site({"photos/index.html": _page(title="Photos — HART", body=f"<h1>Photos</h1><p>{INTRO}</p>" + PHOTOS_CATS)})
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

    def test_item_without_id_is_skipped(self):
        items = [_car("", "A 1")]
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


class FleetIdGuards(unittest.TestCase):
    def test_album_name_as_an_item_id_is_refused(self):
        root = _site({"index.html": _page(), "photos/index.html": _page(body=PHOTOS_CATS)})
        (root / "data").mkdir()
        items = [{"id": "freight", "title": "Freight"}, {"id": "csx-2738", "title": "CSX 2738"}]
        (root / "data" / "fleet-gallery.json").write_text(json.dumps({"items": items}), encoding="utf-8")
        self.assertEqual(len(check.fleet_id_problems(root)), 1)


class ReviewFixesStage2(unittest.TestCase):
    """Behaviour changed after the PR #392 review."""

    def test_album_slugs_come_from_the_photos_page(self):
        root = _site({"photos/index.html": _page(body=PHOTOS_CATS)})
        self.assertEqual(check.fleet_album_slugs(root), {"locomotives", "freight", "mow"})

    def test_offline_sheet_with_only_about_gets_a_record(self):
        root = _site({"crew/industries/index.html": _page()})
        (root / "data").mkdir()
        sheet = {"spotsheet": {"offline": [{"id": "demmler", "name": "Demmler Yard", "about": ["Where D749 goes."]}]}}
        (root / "data" / "crew.json").write_text(json.dumps(sheet), encoding="utf-8")
        (root / "data" / "industries.json").write_text('{"industries": []}', encoding="utf-8")
        self.assertEqual([r["title"] for r in build._industry_records(root)], ["Demmler Yard"])

    def test_crew_link_labels_are_indexed_but_not_their_paths(self):
        root = _site({"crew/ck1/index.html": _page()})
        (root / "data").mkdir()
        job = {"id": "ck1", "code": "CK1", "name": "Coke Transfer", "summary": "Coke.",
               "links": [{"label": "Scale Operating Instructions (EQ-01)", "href": "crew/scale/index.html"}]}
        (root / "data" / "crew.json").write_text(json.dumps({"jobs": [job]}), encoding="utf-8")
        (rec,) = build._crew_records(root)
        self.assertIn("EQ-01", rec["text"])
        self.assertNotIn("index.html", rec["text"])


# All three tabs' chip maps, as photos/index.html writes them.
ALL_CATS = (
    '<script>var CATS = {'
    ' historical: { chips: "#archive-kinds", attr: "data-kind", subs: { photos: "photo", ads: "ad", maps: "map" } },'
    ' layout: { chips: "#layout-albums", attr: "data-album", subs: { "session-night": "layout", panels: "panels", build: "progress" } },'
    ' "rolling-stock": { chips: "#album-bar", attr: "data-album", subs: { locomotives: "locos", freight: "freight" } } };</script>'
)


def _photos_site(archive=None, gallery=None, fleet=None, files=()) -> Path:
    """A built tree with the Photos page, any of the three data files, and small files at the given paths."""
    root = _site({"photos/index.html": _page(title="Photos — HART", body=f"<h1>Photos</h1><p>{INTRO}</p>" + ALL_CATS)})
    (root / "data").mkdir(exist_ok=True)
    for name, items, extra in (("archive.json", archive, {"kinds": [{"id": "ad", "label": "Advertisement"}]}),
                               ("gallery.json", gallery, {"albums": [{"id": "layout", "label": "Session night"}]}),
                               ("fleet-gallery.json", fleet, {})):
        if items is not None:
            (root / "data" / name).write_text(json.dumps({**extra, "items": items}), encoding="utf-8")
    for rel in files:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"x")
    return root


def _arch(aid="ad-1", **extra):
    return {"id": aid, "bucket": "curated", "kind": "ad", "title": "Isle of Chemicals", "caption": "A 1949 advertisement.",
            "date": "1949-05", "tags": ["neville-island", "chemicals"], "credit": "Chemical Society journal",
            "src": f"assets/archive/{aid}.jpg", "thumb": f"assets/archive/thumbs/{aid}.jpg",
            "source_url": "https://doi.org/10.1/x", "credit_confidence": "verified", "rights": "Trade advertisement",
            "reason": "kept for the plant view", "origin": "Desktop/private folder", **extra}


def _pic(pid="layout-crew-lounge", **extra):
    return {"id": pid, "album": "layout", "src": f"assets/gallery/layout/{pid}.jpg", "thumb": f"assets/gallery/thumbs/layout/{pid}.jpg",
            "title": "Crew lounge", "caption": "Where operators gather.", "credit": "Layout photos", **extra}


def _kind(index, kind):
    return [r for r in index["records"] if r["kind"] == kind]


class ArchiveRecords(unittest.TestCase):
    def test_curated_item_record_and_thumb(self):
        root = _photos_site(archive=[_arch()], files=["assets/archive/thumbs/ad-1.jpg"])
        (rec,) = _kind(_index(root), "archive")
        self.assertEqual(rec["url"], "photos/index.html#historical/ad-1")
        self.assertEqual(rec["thumb"], "assets/archive/thumbs/ad-1.jpg")
        self.assertEqual(rec["title"], "Isle of Chemicals")
        for word in ("1949-05", "Advertisement", "neville island", "Chemical Society journal", "A 1949 advertisement."):
            self.assertIn(word, rec["text"])
        self.assertEqual(check.index_problems(root), [])

    def test_hidden_buckets_and_private_items_are_left_out(self):
        items = [_arch("a"), _arch("b", bucket="discard"), _arch("c", bucket="review"), _arch("d", public=False), _arch("e", bucket=None)]
        (rec,) = _kind(_index(_photos_site(archive=items)), "archive")
        self.assertTrue(rec["url"].endswith("/a"))

    def test_internal_fields_never_appear(self):
        (rec,) = _kind(_index(_photos_site(archive=[_arch()])), "archive")
        blob = json.dumps(rec)
        for leak in ("kept for the plant view", "Desktop", "Trade advertisement", "verified", "doi.org", "assets/archive/ad-1", ".jpg"):
            self.assertNotIn(leak, blob)

    def test_credit_with_contact_details_is_dropped(self):
        for credit in ("Jo Smith jo@example.com", "Call 412-555-0100", "see https://example.com/me"):
            (rec,) = _kind(_index(_photos_site(archive=[_arch(credit=credit)])), "archive")
            self.assertNotIn(credit, rec["text"])
        (rec,) = _kind(_index(_photos_site(archive=[_arch(credit="Smith collection, 1921-1935")])), "archive")
        self.assertIn("1921-1935", rec["text"])

    def test_missing_thumb_file_means_no_thumb_field(self):
        (rec,) = _kind(_index(_photos_site(archive=[_arch()])), "archive")
        self.assertNotIn("thumb", rec)

    def test_item_without_id_is_skipped(self):
        self.assertEqual(_kind(_index(_photos_site(archive=[_arch("")])), "archive"), [])


class PhotoRecords(unittest.TestCase):
    def test_record_url_text_and_thumb(self):
        root = _photos_site(gallery=[_pic()], files=["assets/gallery/thumbs/layout/layout-crew-lounge.jpg"])
        (rec,) = _kind(_index(root), "photo")
        self.assertEqual(rec["url"], "photos/index.html#layout/layout-crew-lounge")
        self.assertEqual(rec["thumb"], "assets/gallery/thumbs/layout/layout-crew-lounge.jpg")
        for word in ("Where operators gather.", "Session night", "Layout photos"):
            self.assertIn(word, rec["text"])
        self.assertEqual(check.index_problems(root), [])

    def test_no_thumb_without_the_file_and_no_id_no_record(self):
        index = _index(_photos_site(gallery=[_pic(), _pic("")]))
        (rec,) = _kind(index, "photo")
        self.assertNotIn("thumb", rec)


class FleetThumbs(unittest.TestCase):
    def test_existing_thumb_is_carried_and_a_missing_one_is_not(self):
        fleet = [_car("a-1", "A 1", thumb="assets/fleet/thumbs/a-1.jpg"), _car("a-2", "A 2", thumb="assets/fleet/thumbs/gone.jpg")]
        recs = {r["title"]: r for r in _fleet(_index(_photos_site(fleet=fleet, files=["assets/fleet/thumbs/a-1.jpg"])))}
        self.assertEqual(recs["A 1"]["thumb"], "assets/fleet/thumbs/a-1.jpg")
        self.assertNotIn("thumb", recs["A 2"])

    def test_thumb_outside_the_build_is_refused(self):
        root = _photos_site(fleet=[_car("a-1", "A 1", thumb="../secret.jpg")], files=["../secret.jpg"])
        (rec,) = _fleet(_index(root))
        self.assertNotIn("thumb", rec)


class ArticleKind(unittest.TestCase):
    def test_only_listed_library_pages_are_articles(self):
        body = f"<h1>History</h1><p>{INTRO}</p>"
        root = _site({"library/a.html": _page(body=body), "library/b.html": _page(body=body), "plants/index.html": _page(body=body)})
        (root / "data").mkdir()
        listed = [{"id": "a", "href": "library/a.html"}, {"id": "p", "href": "plants/index.html"}]
        (root / "data" / "articles.json").write_text(json.dumps({"items": listed}), encoding="utf-8")
        kinds = {r["url"]: r["kind"] for r in _index(root)["records"]}
        self.assertEqual(kinds, {"library/a.html": "article", "library/b.html": "page", "plants/index.html": "page"})


class PhotoCheck(unittest.TestCase):
    def _with(self, root, rec_fields):
        index = _index(root)
        index["records"].append({"title": "t", "snippet": "s", "text": "", "kind": "photo", **rec_fields})
        (root / "search-index.json").write_text(json.dumps(index), encoding="utf-8")
        return check.index_problems(root)

    def test_thumb_must_be_a_built_string_path(self):
        root = _photos_site(archive=[_arch()], files=["assets/ok.jpg"])
        self.assertEqual(self._with(root, {"url": "photos/index.html", "thumb": "assets/ok.jpg"}), [])
        self.assertIn("thumb", " ".join(self._with(root, {"url": "photos/index.html", "thumb": "assets/gone.jpg"})))
        self.assertIn("thumb", " ".join(self._with(root, {"url": "photos/index.html", "thumb": "/assets/ok.jpg"})))
        self.assertIn("string", " ".join(self._with(root, {"url": "photos/index.html", "thumb": 5})))

    def test_other_extra_fields_are_still_refused(self):
        root = _photos_site()
        self.assertIn("exactly", " ".join(self._with(root, {"url": "photos/index.html", "extra": "x"})))

    def test_anchors_for_all_three_tabs_are_checked_against_the_data(self):
        root = _photos_site(archive=[_arch()], gallery=[_pic()], fleet=[_car("a-1", "A 1")])
        good = ["historical/ad-1", "layout/layout-crew-lounge", "rolling-stock/a-1", "historical/ads", "layout/session-night"]
        for anchor in good:
            self.assertEqual(self._with(root, {"url": f"photos/index.html#{anchor}"}), [], anchor)
        for anchor in ("historical/gone", "layout/ad-1", "historical/a-1"):
            self.assertIn("not an item id", " ".join(self._with(root, {"url": f"photos/index.html#{anchor}"})), anchor)

    def test_a_hidden_bucket_id_is_not_a_public_anchor(self):
        root = _photos_site(archive=[_arch(), _arch("hid", bucket="discard")])
        self.assertIn("not an item id", " ".join(self._with(root, {"url": "photos/index.html#historical/hid"})))

    def test_id_guards_for_every_tab(self):
        root = _photos_site(archive=[_arch("ads"), _arch("x"), _arch("x")], gallery=[_pic("panels"), _pic("")])
        joined = " ".join(check.tab_id_problems(root, "historical") + check.tab_id_problems(root, "layout"))
        self.assertIn("id ads is a chip name", joined)
        self.assertIn("id x is used twice", joined)
        self.assertIn("id panels is a chip name", joined)
        self.assertIn("has no id", joined)

    def test_slugs_are_read_for_each_tab(self):
        root = _photos_site()
        self.assertEqual(check.tab_slugs(root, "layout"), {"session-night", "panels", "build"})
        self.assertEqual(check.tab_slugs(root, "historical"), {"photos", "ads", "maps"})


class SourceDataIds(unittest.TestCase):
    def test_source_gallery_and_archive_ids_are_unique_and_not_chip_names(self):
        page = (SCRIPTS.parent / "photos" / "index.html").read_text(encoding="utf-8")
        root = _site({"photos/index.html": page})
        for name, tab in (("gallery.json", "layout"), ("archive.json", "historical")):
            items = json.loads((SCRIPTS.parent / "data" / name).read_text())["items"]
            ids = [i.get("id") for i in items]
            self.assertTrue(all(ids), name)
            self.assertEqual(len(ids), len(set(ids)), name)
            self.assertTrue(check.tab_slugs(root, tab), name)  # the page's real CATS map was found
            self.assertFalse(set(ids) & check.tab_slugs(root, tab), name)

    def test_new_layout_items_get_a_numbered_slug(self):
        import serve_portal
        self.assertEqual(serve_portal._gallery_id("layout", "Dispatcher's desk", set()), "layout-dispatcher-s-desk")
        self.assertEqual(serve_portal._gallery_id("layout", "Crew lounge", {"layout-crew-lounge"}), "layout-crew-lounge-2")
        self.assertEqual(serve_portal._gallery_id("layout", "", set()), "layout")
