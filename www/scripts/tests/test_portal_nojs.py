"""portal_nojs.py (stage 7b of prepare_github_pages.py): the static header, footer and primer text a visitor without
JavaScript sees, on a fixture tree, plus checks that the real pages and nav.js still match what the stage expects."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portal_nojs  # noqa: E402
import portal_nojs_crew  # noqa: E402

WWW = Path(__file__).resolve().parents[2]

SITE = {
    "nav": [
        {"id": "home", "href": "index.html", "label": "Home"},
        {"id": "history", "href": "history/index.html", "label": "Prototype"},
        {"id": "ops", "href": "operators/index.html", "label": "Operations"},
        {"id": "about", "href": "about/index.html", "label": "About & <more>"},
    ],
    "channels": {"youtube": "https://example.org/yt", "tiktok": ""},
    "engDesk": "",
    "public": True,
}


def page(nav_src: str, body: str = "") -> str:
    return (
        "<!DOCTYPE html><html><head><title>T</title></head><body>"
        '<header class="site-header" data-ops-header></header><main>' + body + "</main>"
        '<footer class="site-footer" data-ops-footer></footer>'
        + (f'<script src="{nav_src}"></script>' if nav_src else "") + "</body></html>"
    )


class Chrome(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name)
        (self.dest / "data").mkdir()
        (self.dest / "data" / "site.json").write_text(json.dumps(SITE), encoding="utf-8")
        files = {
            "index.html": page("js/nav.js"),
            "crew/d749/index.html": page("../../js/nav.js"),
            "404.html": page("/js/nav.js"),
            "stub.html": page(""),  # no nav.js: left alone
        }
        for rel, text in files.items():
            (self.dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.dest / rel).write_text(text, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def read(self, rel: str) -> str:
        return (self.dest / rel).read_text(encoding="utf-8")

    def test_header_has_brand_and_section_links_from_the_page_base(self) -> None:
        self.assertEqual(portal_nojs.add_static_chrome(self.dest), 3)
        deep = self.read("crew/d749/index.html")
        self.assertIn('<a class="brand" href="../../index.html">HART<span>Railroad · Neville Island</span></a>', deep)
        m = re.search(r"<noscript>(.*?)</noscript>", deep)
        assert m is not None
        links = m.group(1)
        self.assertEqual(re.findall(r'href="([^"]+)"', links),
                         ["../../history/index.html", "../../operators/index.html", "../../about/index.html"])
        self.assertIn("About &amp; &lt;more&gt;", links)   # labels escaped; Home is the brand, not a link
        self.assertIn('href="/history/index.html"', self.read("404.html"))
        self.assertIn('href="index.html">HART', self.read("index.html"))
        self.assertEqual(self.read("stub.html"), page(""))

    def test_footer_is_the_line_nav_js_writes(self) -> None:
        portal_nojs.add_static_chrome(self.dest)
        f = re.search(r"<footer[^>]*>(.*?)</footer>", self.read("crew/d749/index.html"))
        assert f is not None
        foot = f.group(1)
        self.assertEqual(foot, 'HART Railroad · Neville Island · <a href="../../about/index.html">About</a>'
                               ' · Follow along: <a href="https://example.org/yt">YouTube</a>')

    def test_skip_link_targets_main(self) -> None:
        (self.dest / "kept.html").write_text(page("js/nav.js").replace("<main>", '<main id="body" class="x">'),
                                             encoding="utf-8")
        (self.dest / "nomain.html").write_text(page("js/nav.js").replace("<main>", "<div>").replace("</main>", "</div>"),
                                               encoding="utf-8")
        portal_nojs.add_static_chrome(self.dest)
        deep = self.read("crew/d749/index.html")
        self.assertIn('data-ops-header><a class="skip-link" href="#main">Skip to content</a>', deep)
        self.assertIn('<main id="main">', deep)
        kept = self.read("kept.html")
        self.assertIn('href="#body">Skip to content', kept)   # an existing id is the target, left as it is
        self.assertIn('<main id="body" class="x">', kept)
        self.assertNotIn("skip-link", self.read("nomain.html"))

    def test_sub_entries_follow_their_section(self) -> None:
        site = json.loads(json.dumps(SITE))
        site["nav"][2]["sub"] = [{"id": "crew", "href": "crew/index.html", "label": "Crew sheets"}]
        links = re.findall(r'href="([^"]+)"', re.search(r"<noscript>(.*?)</noscript>",
                                                       portal_nojs.header_html(site, "")).group(1))
        self.assertEqual(links, ["history/index.html", "operators/index.html", "crew/index.html", "about/index.html"])

    def test_second_run_adds_nothing(self) -> None:
        portal_nojs.add_static_chrome(self.dest)
        before = self.read("index.html")
        self.assertEqual(portal_nojs.add_static_chrome(self.dest), 0)
        self.assertEqual(self.read("index.html"), before)


class Primer(unittest.TestCase):
    def test_primer_text_in_a_noscript(self) -> None:
        data = {
            "lede": "Welcome & hello.",
            "firstNight": {"heading": "Your first night", "bullets": [{"label": "When", "text": "7 p.m."}],
                           "links": [{"label": "Glossary", "href": "operators/glossary/index.html"}]},
            "sections": [
                {"id": "industries", "heading": "Who We Switch", "placards": True, "exclude": ["b"]},
                {"id": "jobs", "heading": "Jobs", "jobs": [{"code": "D749", "name": "Switcher", "blurb": "<x>",
                                                             "href": "crew/d749/index.html"},
                                                            {"code": "YM", "name": "Yard", "blurb": "y"}]},
                {"id": "map", "heading": "Map", "figure": {"caption": "Schematic.", "pdf": "crew/s.pdf"}},
            ],
            "deeper": {"heading": "Deeper", "refs": [{"label": "TT-23", "href": "crew/tt23/index.html"}]},
            "links": [{"label": "History", "href": "../library/h.html"}],
        }
        industries = {"industries": [{"name": "Acme", "spot": "a"}, {"name": "Skip", "spot": "b"},
                                     {"name": "Interchange", "spot": "c", "category": "interchange"}]}
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "data").mkdir()
            (dest / "data" / "briefing.json").write_text(json.dumps(data), encoding="utf-8")
            (dest / "data" / "industries.json").write_text(json.dumps(industries), encoding="utf-8")
            (dest / "briefing").mkdir()
            (dest / "briefing" / "index.html").write_text(
                page("../js/nav.js", '<div id="briefing-body"><p class="muted">Loading…</p></div>'), encoding="utf-8")
            self.assertTrue(portal_nojs.add_primer_text(dest))
            text = (dest / "briefing" / "index.html").read_text(encoding="utf-8")
        body = re.search(r'<div id="briefing-body"><p class="muted">Loading…</p><noscript>(.*)</noscript></div>', text)
        assert body is not None, text
        ns = body.group(1)
        self.assertIn("Welcome &amp; hello.", ns)
        self.assertIn("<li>Acme</li>", ns)
        self.assertNotIn("Skip", ns)
        self.assertNotIn("Interchange", ns)
        self.assertIn("&lt;x&gt;", ns)
        # A job with a sheet links its code; one without stays plain.
        self.assertIn('<strong><a href="../crew/d749/index.html">D749</a></strong>', ns)
        self.assertIn("<strong>YM</strong>", ns)
        for href in ("../operators/glossary/index.html", "../crew/s.pdf", "../crew/tt23/index.html", "../library/h.html"):
            self.assertIn(f'href="{href}"', ns)

    def test_no_primer_page_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(portal_nojs.add_primer_text(Path(tmp)))


RED = {"id": "red", "label": "RED", "hex": "#c00", "ink": "#fff", "dest": "Dock & Co", "train": "NVL",
       "spot": "dock", "group": "island"}
BLUE = {"id": "blue", "label": "BLUE", "hex": "#00c", "ink": "#fff", "dest": "Scully", "train": "D749",
        "spot": "scully", "group": "interchange"}
CREW = {
    "colors": [RED, BLUE],
    "timetable": {"columns": ["Time", "Station", "Note"], "rows": [["7:00", "Neville", "-"]], "note": "Streetcar first."},
    "maps": [{"id": "west", "title": "West Yard", "pub": "SM-02", "img": "assets/w.png", "sheets": ["west"]}],
    "sheets": {"west": ["West Yard", "The yard ladder"]},
    "jobs": [
        {"id": "full", "code": "FULL", "name": "Every section", "pub": "CS-9", "revision": "A", "effective": "1999",
         "summary": "All of it.", "engine": {"label": "CR 1993", "img": "assets/e.png"}, "colors": ["red"],
         "priority": ["Streetcar", "FULL"], "steps": ["Pull <S-1>", "Shove"],
         "sequence": [{"n": 1, "train": "NVL", "action": "Build", "colors": ["red"]}],
         "lineup": [{"n": 1, "train": "D749", "action": "Arrive"}], "maps": ["west"],
         "talk": [{"who": "Yardmaster", "why": "Tracks"}], "links": [{"href": "crew/scale/index.html", "label": "Scale"}]},
        {"id": "bare", "code": "BARE", "name": "Summary only", "pub": "CS-8", "revision": "B", "effective": "2000",
         "summary": "Colors and the timetable.", "colors": ["red", "blue"]},
    ],
}


def crew_page(kind: str, pid: str) -> str:
    return (
        '<header class="site-header" data-ops-header></header><main><div class="sheet-head" id="sheet-head">'
        "<h1>Old</h1></div><noscript><style>#crew-root > p.muted { display: none; }</style><p>Needs JS</p></noscript>"
        '<div id="crew-root"><p class="muted">Loading…</p></div></main><script src="../../js/nav.js"></script>'
        f'<script src="../../js/crew.js"></script><script>HARTCrew.page("{kind}", "{pid}");</script>'
    )


class CrewPages(unittest.TestCase):
    def sheet(self, pid: str) -> str:
        out = portal_nojs_crew.render_page(crew_page("sheet", pid), CREW)
        assert out is not None
        return out

    def test_sheet_with_every_section(self) -> None:
        out = self.sheet("full")
        self.assertIn('<div id="crew-root" data-static><p class="sheet-summary">All of it.</p>', out)
        self.assertNotIn("Needs JS", out)        # the note goes once the sheet is there
        self.assertNotIn("<h1>Old</h1>", out)    # the head is the job's
        self.assertIn('<p class="sheet-code">FULL</p><div><h1>Every section</h1>', out)
        self.assertIn('src="../../assets/e.png"', out)
        for h in ("prio-h", "steps-h", "sequence-h", "lineup-h", "colors-h", "where-h", "talk-h"):
            self.assertIn(f'<a href="#{h}">', out)
            self.assertIn(f'id="{h}"', out)
        self.assertIn('<span>Pull &lt;S-1&gt;</span>', out)
        self.assertIn('type="checkbox" class="no-print" data-step="1"', out)
        self.assertIn("Your colors", out)        # one of two colors: the job's bright, the other dimmed
        self.assertIn('class="cchip is-dim"', out)
        self.assertIn('href="../../crew/maps/west/index.html"', out)
        self.assertIn('href="../../crew/scale/index.html">Scale</a>', out)
        self.assertIn('href="../../crew/industries/index.html#dock">Dock &amp; Co</a>', out)
        # nothing that needs JavaScript to do anything
        self.assertNotIn("<button", out)

    def test_sheet_without_optional_sections(self) -> None:
        out = self.sheet("bare")
        for h in ("prio-h", "steps-h", "sequence-h", "lineup-h", "where-h", "talk-h"):
            self.assertNotIn(h, out)
        self.assertNotIn('class="jump', out)     # under three sections: no jump row
        self.assertNotIn("sheet-engine", out)
        self.assertIn("Destination colors", out)
        self.assertIn('<th scope="row">Neville</th>', out)
        self.assertIn('href="../../crew/index.html">All sheets</a>', out)

    def test_map_page_links_its_drawing(self) -> None:
        out = portal_nojs_crew.render_page(crew_page("map", "west"), CREW)
        assert out is not None
        self.assertIn('<a class="map-open" href="../../crew/maps/generated-sheets/west.svg"><img', out)
        self.assertIn("<h1>Old</h1>", out)       # a map page keeps its own head

    def test_unknown_page_is_left_alone(self) -> None:
        self.assertIsNone(portal_nojs_crew.render_page(crew_page("sheet", "nope"), CREW))
        self.assertIsNone(portal_nojs_crew.render_page("<p>no call</p>", CREW))

    def test_shelf(self) -> None:
        data = {"groups": [{"id": "g", "label": "Sheets", "note": "N"}, {"id": "empty", "label": "None"}],
                "items": [{"group": "g", "pub": "SM-01", "revision": "19", "title": "Schematic", "blurb": "B",
                           "page": "crew/maps/index.html", "printable": True, "pdf": "a b.pdf", "source": "x.docx"}]}
        out = portal_nojs_crew.shelf_html(data, "../")
        self.assertIn('<p class="pub-no">SM-01<small>Rev 19</small></p>', out)
        self.assertIn('href="../a%20b.pdf">Download PDF</a>', out)
        self.assertNotIn("x.docx", out)
        self.assertNotIn("#print", out)
        self.assertNotIn("None", out)


class RealTree(unittest.TestCase):
    """The stage matches markup by pattern; these fail when the pages or nav.js move away from it."""

    def test_every_crew_page_renders_from_the_real_data(self) -> None:
        data = json.loads((WWW / "data" / "crew.json").read_text(encoding="utf-8"))
        for p in (WWW / "crew").rglob("*.html"):
            text = p.read_text(encoding="utf-8")
            if "HARTCrew.page(" in text:
                out = portal_nojs_crew.render_page(text, data)
                self.assertIsNotNone(out, p)
                self.assertNotIn("Loading…", out or "", p)

    def test_docs_shelf_has_its_loading_line(self) -> None:
        self.assertRegex((WWW / portal_nojs_crew.DOCS_REL).read_text(encoding="utf-8"), portal_nojs_crew._PUB_ROOT)
        self.assertRegex((WWW / portal_nojs_crew.DOCS_REL).read_text(encoding="utf-8"), portal_nojs_crew._PUB_NOTE)

    def test_every_page_with_chrome_has_the_empty_header_and_footer(self) -> None:
        for p in WWW.rglob("*.html"):
            # The pipeline map is a built page (ADR-036) a local preview may leave in www/; it draws its own chrome.
            if "scripts" in p.relative_to(WWW).parts or p.relative_to(WWW).as_posix() == "library/pipeline-map.html":
                continue
            text = p.read_text(encoding="utf-8")
            if "data-ops-header" in text:
                self.assertRegex(text, portal_nojs._EMPTY_HEADER, p)
                self.assertRegex(text, portal_nojs._EMPTY_FOOTER, p)
                self.assertRegex(text, portal_nojs._NAV_SRC, p)

    def test_primer_page_has_its_loading_line(self) -> None:
        self.assertRegex((WWW / portal_nojs.PRIMER_REL).read_text(encoding="utf-8"), portal_nojs._PRIMER_BODY)

    def test_brand_and_footer_match_nav_js(self) -> None:
        nav = (WWW / "js" / "nav.js").read_text(encoding="utf-8")
        self.assertIn("'index.html\">HART<span>Railroad · Neville Island</span></a>'", nav)
        self.assertIn('"HART Railroad · Neville Island"', nav)


if __name__ == "__main__":
    unittest.main()
