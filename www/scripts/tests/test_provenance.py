"""Every public page says whether it is real history, fiction or layout documentation."""
import json
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import provenance  # noqa: E402

PORTAL = Path(__file__).resolve().parents[2]
SITE = "https://example.invalid/"
DATA = {
    "site": {"name": "Test", "summary": "S.", "notes": ["N."],
             "setting": {"@type": "Place", "name": "Neville Island"}},
    "classes": {c: c.title() for c in provenance.CLASSES},
    "rules": {
        "history/": {"class": "prototype", "citation": ["A source", "/library/a.html"]},
        "crew/": {"class": "fiction"},
        "crew/maps/": {"class": "hobby"},
        "crew/maps/odd.html": {"class": "fiction", "note": "In-world map."},
        "library/mix.html": {"class": "mixed", "parts": [{"section": "Plant", "class": "prototype"},
                                                         {"section": "HART", "class": "fiction"}]},
    },
}


def ld(rel, data=DATA):
    tag = provenance.json_ld(Path(rel), "T", SITE, "D", data)
    body = tag.split(">", 1)[1].rsplit("</script>", 1)[0]
    return json.loads(body)["mainEntity"]


class Rules(unittest.TestCase):
    def test_exact_path_beats_folder_and_longer_folder_beats_shorter(self):
        self.assertEqual(provenance.rule_for(Path("crew/maps/odd.html"), DATA)["class"], "fiction")
        self.assertEqual(provenance.rule_for(Path("crew/maps/x.html"), DATA)["class"], "hobby")
        self.assertEqual(provenance.rule_for(Path("crew/ck1/index.html"), DATA)["class"], "fiction")

    def test_folder_rule_needs_the_slash(self):
        self.assertIsNone(provenance.rule_for(Path("history.html"), DATA))

    def test_meta_tags_match_in_any_order_and_quoting(self):
        self.assertTrue(provenance.skipped("<meta content='noindex, nofollow' name='ROBOTS'>"))
        self.assertTrue(provenance.skipped("<meta content=0 http-equiv=Refresh>"))
        self.assertFalse(provenance.skipped('<meta name="robots" content="index">'))

    def test_url_path_only_folds_a_real_index(self):
        self.assertEqual(provenance.url_path(Path("index.html")), "")
        self.assertEqual(provenance.url_path(Path("crew/index.html")), "crew/")
        self.assertEqual(provenance.url_path(Path("library/reindex.html")), "library/reindex.html")

    def test_unclassified_ignores_redirects_and_noindex(self):
        pages = {
            Path("nowhere/a.html"): "<head><title>a</title></head>",
            Path("nowhere/r.html"): '<meta http-equiv="refresh" content="0; url=x">',
            Path("404.html"): '<meta name="robots" content="noindex">',
        }
        self.assertEqual(provenance.unclassified(pages, DATA), ["nowhere/a.html"])

    def test_bad_map_is_refused(self):
        bad = dict(DATA, rules={"x/": {"class": "mixed"}})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.json"
            p.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                provenance.load(p)


class JsonLd(unittest.TestCase):
    def test_fiction_is_a_creative_work_based_on_the_real_place(self):
        work = ld("crew/ck1/index.html")
        self.assertEqual((work["@type"], work["genre"]), ("CreativeWork", "Fiction"))
        self.assertEqual(work["isBasedOn"]["name"], "Neville Island")
        self.assertEqual(work["additionalProperty"]["value"], "fiction")

    def test_prototype_is_history_with_its_citations(self):
        work = ld("history/index.html")
        self.assertEqual((work["@type"], work["genre"]), ("Article", "History"))
        self.assertEqual(work["citation"], ["A source", SITE + "library/a.html"])
        self.assertNotIn("isBasedOn", work)

    def test_mixed_names_each_part(self):
        parts = ld("library/mix.html")["hasPart"]
        self.assertEqual([(p["name"], p["genre"]) for p in parts], [("Plant", "History"), ("HART", "Fiction")])

    def test_script_close_in_text_cannot_end_the_tag(self):
        tag = provenance.json_ld(Path("crew/a.html"), "</script><b>", SITE, "D", DATA)
        self.assertIn(f'"isPartOf": {{"@type": "WebSite", "name": "Test", "url": "{SITE}"}}', tag)
        self.assertEqual(tag.count("</script>"), 1)


class Sources(unittest.TestCase):
    def test_reads_the_list_under_a_sources_heading_only(self):
        page = ("<h2>Intro</h2><ul><li>not a source</li></ul>"
                "<h2>Sources</h2><ul><li><a href='x'>Post-Gazette</a>, 1990</li><li>EPA <em>report</em></li></ul>"
                "<h2>More</h2><ul><li>after</li></ul>")
        self.assertEqual(provenance.sources(page), ["Post-Gazette, 1990", "EPA report"])

    def test_page_sources_join_the_map_citations(self):
        tag = provenance.json_ld(Path("history/a.html"), "T", SITE, "D", DATA, ["B source", "A source"])
        self.assertIn(f'"citation": ["A source", "{SITE}library/a.html", "B source"]', tag)

    def test_prose_sources_section_does_not_borrow_a_later_list(self):
        page = "<h2>Sources</h2><p>Post-Gazette, 1990.</p><footer><ul><li>Home</li></ul></footer>"
        self.assertEqual(provenance.sources(page), [])

    def test_no_heading_no_sources(self):
        self.assertEqual(provenance.sources("<ul><li>x</li></ul>"), [])


class RootFiles(unittest.TestCase):
    def test_llms_txt_groups_pages_by_class(self):
        pages = {Path("crew/ck1/index.html"): ("CK1", "Crew sheet"), Path("history/index.html"): ("History", "")}
        text = provenance.llms_txt(pages, DATA, SITE)
        self.assertTrue(text.startswith("# Test\n\n> S."))
        self.assertLess(text.index("## Prototype"), text.index("## Fiction"))
        self.assertIn(f"- [CK1]({SITE}crew/ck1/): Crew sheet", text)

    def test_robots_points_at_the_sitemap(self):
        self.assertIn(f"Sitemap: {SITE}sitemap.xml", provenance.robots_txt(SITE))

    def test_sitemap_uses_folder_urls(self):
        xml = provenance.sitemap_xml([Path("index.html"), Path("crew/index.html")], SITE)
        self.assertIn(f"<loc>{SITE}</loc>", xml)
        self.assertIn(f"<loc>{SITE}crew/</loc>", xml)


class BuildPass(unittest.TestCase):
    """_add_provenance on a small built tree: where the tag goes, what is left out, the root files."""

    def test_tags_pages_and_writes_root_files(self):
        sys.path.insert(0, str(PORTAL / "scripts"))
        import prepare_github_pages as pgp
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "crew").mkdir()
            (root / "crew/index.html").write_text("<html><head><title>Crew — HART</title></head><body></body></html>")
            (root / "crew/sheet.html").write_text("<!doctype html><meta charset=utf-8><title>Sheet</title><p>x</p>")
            (root / "crew/old.html").write_text('<meta http-equiv="refresh" content="0; url=index.html"><title>Moved</title>')
            (root / "404.html").write_text("<head><title>Lost</title></head>")
            self.assertEqual(pgp._add_provenance(root), [])
            head = (root / "crew/index.html").read_text()
            self.assertLess(head.index("application/ld+json"), head.index("</head>"))
            implied = (root / "crew/sheet.html").read_text()
            self.assertLess(implied.index("</title>"), implied.index("application/ld+json"), implied.index("<p>"))
            self.assertNotIn("ld+json", (root / "crew/old.html").read_text())
            self.assertNotIn("ld+json", (root / "404.html").read_text())
            sitemap = (root / "sitemap.xml").read_text()
            self.assertIn(f"{pgp.portal_common.SITE_URL}crew/</loc>", sitemap)
            self.assertNotIn("old.html", sitemap)
            self.assertIn("- [Crew](", (root / "llms.txt").read_text())
            self.assertTrue((root / "robots.txt").is_file())

    def test_unclassified_page_is_reported(self):
        sys.path.insert(0, str(PORTAL / "scripts"))
        import prepare_github_pages as pgp
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "nowhere").mkdir()
            (root / "nowhere/a.html").write_text("<head><title>a</title></head>")
            self.assertEqual(pgp._add_provenance(root), ["nowhere/a.html"])
            self.assertFalse((root / "sitemap.xml").exists())


class RealMap(unittest.TestCase):
    # Tracked pages minus the build's skip lists: a superset of what is published (data-local-only
    # pages are stripped later), so a page passing here is classified in the build too.
    def test_every_published_page_is_classified(self):
        data = provenance.load()
        out = subprocess.run(["git", "-C", str(PORTAL), "ls-files", "*.html"], capture_output=True, text=True, check=True)
        sys.path.insert(0, str(PORTAL / "scripts"))
        import prepare_github_pages as pgp
        pages = {}
        for name in out.stdout.split():
            rel = Path(name)
            if rel in pgp.SKIP_FILES or any(d in rel.parents for d in pgp.SKIP_DIRS) or not (PORTAL / rel).is_file():
                continue
            if rel.as_posix() in pgp.INDEX_SKIP_PAGES:  # the build's provenance step leaves these out too
                continue
            pages[rel] = (PORTAL / rel).read_text(encoding="utf-8")
        self.assertEqual(provenance.unclassified(pages, data), [])


if __name__ == "__main__":
    unittest.main()
