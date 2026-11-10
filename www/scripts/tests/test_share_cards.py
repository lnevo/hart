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

SITE = {"nav": [{"id": "operators", "pages": ["operators", "guide"]}, {"id": "history", "pages": ["articles"]}]}


def _portal(tmp: str) -> Path:
    root = Path(tmp)
    (root / "data").mkdir()
    (root / "data" / "site.json").write_text(json.dumps(SITE), encoding="utf-8")
    pages = {
        "guides/a.html": '<title>A — HART</title><script>HartNav.mountChrome("guide")</script>',
        "guides/moved.html": '<title>Moved — HART</title><script>HartNav.mountChrome("guide")</script>',
        "library/h.html": '<title>H — HART</title><script>HartNav.mountChrome("articles")</script>',
        "crew/ck1/index.html": "<title>CK1 — HART</title>",
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

    def test_every_card_in_the_repo_is_sound(self):
        missing, faults = share_cards.review(share_cards.tracked_pages(), share_cards.load())
        self.assertEqual(faults, [])


class Review(unittest.TestCase):
    def test_lists_section_pages_without_a_card_and_skips_stubs_and_other_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _portal(tmp)
            pages = [p.relative_to(root) for p in sorted(root.rglob("*.html"))]
            missing, faults = share_cards.review(pages, {}, root)
        self.assertEqual(missing, ["crew/ck1/index.html", "guides/a.html"])
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


if __name__ == "__main__":
    unittest.main()
