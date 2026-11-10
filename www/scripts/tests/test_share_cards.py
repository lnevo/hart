"""Per-page share thumbnails: the build names the page's own card, and gaps are reported."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import prepare_github_pages as build  # noqa: E402
import share_cards  # noqa: E402

SITE = {"nav": [{"id": "operators", "pages": ["operators", "guide", "crew"]}, {"id": "behind"}, {"id": "history", "pages": ["articles"]}]}


def _portal(tmp: str) -> Path:
    root = Path(tmp)
    (root / "data").mkdir()
    (root / "data" / "site.json").write_text(json.dumps(SITE), encoding="utf-8")
    pages = {
        "guides/a.html": '<title>A — HART</title><script>HartNav.mountChrome("guide")</script>',
        "guides/moved.html": '<title>Moved — HART</title><script>HartNav.mountChrome("guide")</script>',
        "library/h.html": '<title>H — HART</title><script>HartNav.mountChrome("articles")</script>',
        "crew/ck1/index.html": '<title>CK1 — HART</title><script>HartNav.mountChrome("crew")</script>',
        "roster/index.html": "<title>Roster — HART</title>",
        "guides/index.html": '<title>Guides — HART</title><script>HartNav.mountChrome("guide")</script>',
    }
    for name, text in pages.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


class HeadTags(unittest.TestCase):
    def test_page_with_a_card_gets_its_own_image(self):
        cards = {"guides/a.html": {"image": "assets/share/a.jpg", "alt": 'The "A" board'}}
        orig = share_cards.load
        share_cards.load = lambda *a: cards
        try:
            own = build._head_tags(Path("guides/a.html"), "A")
            other = build._head_tags(Path("guides/b.html"), "B")
        finally:
            share_cards.load = orig
        self.assertIn(f'og:image" content="{build.SITE_URL}assets/share/a.jpg"', own)
        self.assertIn('og:image:alt" content="The &quot;A&quot; board"', own)
        self.assertIn("assets/icons/share-card.jpg", other)

    def test_the_404_page_gets_site_root_icon_links(self):
        tags = build._head_tags(Path("404.html"), "Page not found")
        self.assertIn('href="/favicon.ico"', tags)
        self.assertIn('href="/assets/icons/apple-touch-icon.png"', tags)
        self.assertIn('href="../favicon.ico"', build._head_tags(Path("guides/a.html"), "A"))

    def test_every_card_in_the_repo_is_sound(self):
        missing, faults = share_cards.review(share_cards.tracked_pages(), share_cards.load())
        self.assertEqual(faults, [])


class Review(unittest.TestCase):
    def test_lists_section_pages_without_a_card_and_skips_stubs_and_other_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _portal(tmp)
            pages = [p.relative_to(root) for p in sorted(root.rglob("*.html"))]
            share_cards.NO_CARD_PAGES, orig = {"crew/ck1/index.html"}, share_cards.NO_CARD_PAGES
            try:
                missing, faults = share_cards.review(pages, {}, root)
            finally:
                share_cards.NO_CARD_PAGES = orig
        self.assertEqual(missing, ["guides/a.html", "guides/index.html", "roster/index.html"])  # crew/ck1 is exempt here
        self.assertEqual(faults, [])

    def test_faults_a_missing_image_and_a_picture_used_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _portal(tmp)
            (root / "assets" / "share").mkdir(parents=True)
            (root / "assets" / "share" / "a.jpg").write_bytes(b"")
            share_cards._image_size, orig = (lambda p: share_cards.SIZE), share_cards._image_size
            try:
                cards = {
                    "guides/a.html": {"image": "assets/share/a.jpg", "alt": "A", "from": "photo.jpg"},
                    "crew/ck1/index.html": {"image": "assets/share/gone.jpg", "alt": "CK1", "from": "photo.jpg"},
                }
                missing, faults = share_cards.review([], cards, root)
            finally:
                share_cards._image_size = orig
        self.assertEqual(len(faults), 2)
        self.assertIn("assets/share/gone.jpg is not a file", faults[0])
        self.assertIn("same source picture as guides/a.html", faults[1])

    def test_pages_marked_shared_may_use_one_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _portal(tmp)
            (root / "assets" / "share").mkdir(parents=True)
            (root / "assets" / "share" / "a.jpg").write_bytes(b"")
            share_cards._image_size, orig = (lambda p: share_cards.SIZE), share_cards._image_size
            try:
                one = {"image": "assets/share/a.jpg", "alt": "A", "from": "photo.jpg", "shared": True}
                missing, faults = share_cards.review([], {"guides/a.html": dict(one), "crew/ck1/index.html": dict(one)}, root)
            finally:
                share_cards._image_size = orig
        self.assertEqual(faults, [])


class CardThumbs(unittest.TestCase):
    CARDS = {
        "ai/research.html": {"image": "assets/share/ai-research.jpg", "alt": "R"},
        "operators/sheet.html": {"image": "assets/share/ops.jpg", "alt": "S", "shared": True},
        "operators/yard.html": {"image": "assets/share/ops.jpg", "alt": "Y", "shared": True},
        "ai/construction.html": {"image": "assets/share/ai-construction.jpg", "alt": "C", "shared": True},
        "guides/index.html": {"image": "assets/share/guides.jpg", "alt": "G"},
    }
    HUB = (
        '<div class="card-grid" data-card-thumbs>\n'
        '  <a class="card" href="research.html"><div><h3>R</h3></div></a>\n'
        '  <a class="card" href="../operators/sheet.html"><h3>S</h3></a>\n'
        '  <a class="card" href="nowhere.html"><h3>N</h3></a>\n'
        '  <a class="card" href="../guides/"><h3>G</h3></a>\n'
        '  <a class="card" href="../operators/yard.html"><h3>Y</h3></a>\n'
        '  <a class="card" href="construction.html#plans"><h3>C</h3></a>\n'
        '  <a class="card" href="https://github.com/x/y" target="_blank"><h3>X</h3></a>\n'
        "</div>\n"
        '<div class="card-grid"><a class="card" href="research.html"><h3>Unmarked</h3></a></div>'
    )

    def test_marked_grid_cards_get_their_own_picture(self):
        out, thumbs = share_cards.add_card_thumbs(self.HUB, "ai/index.html", self.CARDS, {})
        self.assertIn(
            '<a class="card has-thumb" href="research.html"><img class="card-thumb" '
            'src="../assets/share/thumbs/ai-research.jpg" alt="" loading="lazy">',
            out,
        )
        self.assertIn('src="../assets/share/thumbs/guides.jpg"', out)  # folder link resolves to index.html
        self.assertEqual(
            thumbs,
            {"assets/share/thumbs/ai-research.jpg": "assets/share/ai-research.jpg",
             "assets/share/thumbs/guides.jpg": "assets/share/guides.jpg",
             "assets/share/thumbs/ai-construction.jpg": "assets/share/ai-construction.jpg"},
        )

    def test_repeated_missing_and_unmarked_cards_stay_text_only(self):
        out, _ = share_cards.add_card_thumbs(self.HUB, "ai/index.html", self.CARDS, {})
        self.assertIn('<a class="card no-thumb" href="../operators/sheet.html">', out)
        self.assertIn('<a class="card no-thumb" href="../operators/yard.html">', out)
        self.assertIn('<a class="card no-thumb" href="nowhere.html">', out)
        self.assertIn('<a class="card no-thumb" href="https://github.com/x/y" target="_blank">', out)
        self.assertIn('<div class="card-grid"><a class="card" href="research.html"><h3>Unmarked', out)
        self.assertEqual(out.count('class="card-thumb"'), 3)  # a shared picture used once in the grid is shown

    def test_card_target_drops_the_anchor_and_skips_off_site_links(self):
        self.assertEqual(share_cards.card_target("behind/index.html", "../build/index.html#staging"), "build/index.html")
        self.assertEqual(share_cards.card_target("operators/index.html", "../photos/#historical"), "photos/index.html")
        self.assertIsNone(share_cards.card_target("behind/index.html", "https://github.com/x/y"))
        self.assertIsNone(share_cards.card_target("behind/index.html", "#top"))

    def test_a_link_entry_gives_a_section_or_off_site_card_its_own_picture(self):
        links = {
            "build/index.html#staging": {"image": "assets/share/staging.jpg", "alt": "S"},
            "https://github.com/x/y": {"image": "assets/share/gh.jpg", "alt": "G"},
        }
        cards = {"build/index.html": {"image": "assets/share/build.jpg", "alt": "B"}}
        hub = (
            '<div class="card-grid" data-card-thumbs>'
            '<a class="card" href="../build/index.html#staging">S</a>'
            '<a class="card" href="../build/index.html#main-level">M</a>'
            '<a class="card" href="https://github.com/x/y">G</a></div>'
        )
        out, thumbs = share_cards.add_card_thumbs(hub, "behind/index.html", cards, links)
        self.assertIn('href="../build/index.html#staging"><img class="card-thumb" src="../assets/share/thumbs/staging.jpg"', out)
        self.assertIn('href="../build/index.html#main-level"><img class="card-thumb" src="../assets/share/thumbs/build.jpg"', out)
        self.assertIn('href="https://github.com/x/y"><img class="card-thumb" src="../assets/share/thumbs/gh.jpg"', out)
        self.assertEqual(len(thumbs), 3)

    def test_link_entries_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _portal(tmp)
            (root / "assets" / "share").mkdir(parents=True)
            (root / "assets" / "share" / "s.jpg").write_bytes(b"")
            faults = share_cards.review_links({
                "guides/a.html#top": {"image": "assets/share/s.jpg", "alt": "A"},
                "guides/gone.html#x": {"image": "assets/share/s.jpg", "alt": "A"},
                "https://github.com/x/y": {"image": "assets/share/none.jpg", "alt": ""},
            }, root)
        self.assertEqual(len(faults), 3)
        self.assertIn("guides/gone.html#x: no such page", faults[0])

    def test_page_without_a_marked_grid_is_unchanged(self):
        text = '<div class="card-grid"><a class="card" href="research.html">R</a></div>'
        self.assertEqual(share_cards.add_card_thumbs(text, "ai/index.html", self.CARDS, {}), (text, {}))


if __name__ == "__main__":
    unittest.main()
