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
                {"id": "jobs", "heading": "Jobs", "jobs": [{"code": "D749", "name": "Switcher", "blurb": "<x>"}]},
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
        for href in ("../operators/glossary/index.html", "../crew/s.pdf", "../crew/tt23/index.html", "../library/h.html"):
            self.assertIn(f'href="{href}"', ns)

    def test_no_primer_page_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(portal_nojs.add_primer_text(Path(tmp)))


class RealTree(unittest.TestCase):
    """The stage matches markup by pattern; these fail when the pages or nav.js move away from it."""

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
