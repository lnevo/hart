#!/usr/bin/env python3
"""Tests for the MRE Electrical SOQ build (no Chrome or Keynote needed; the member-copy fill test needs PyMuPDF).

    python3 -m unittest docs/ap/electrical/test_build_soq.py
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_soq  # noqa: E402
import make_drawings  # noqa: E402


class GenericLabels(unittest.TestCase):
    def test_every_detected_section_has_a_generic_label(self):
        table = build_soq.appendix_b()
        self.assertEqual(table.count("<tr><td>"), 43)
        self.assertNotIn("S-R</td><td>S-R", table)

    def test_yard_and_engine_tracks(self):
        self.assertEqual(build_soq.generic("S-R"), "Yard track Y1")
        self.assertEqual(build_soq.generic("EH-3"), "Engine storage E3")
        self.assertEqual(build_soq.generic("OS Switch 23b"), "Turnout 23 (crossover half b)")

    def test_stub_named_as_subtracted_is_added_back(self):
        lengths = {s["name"]: s["inches"] for s in make_drawings.detected_sections()}
        self.assertAlmostEqual(lengths["K-1"], 108.0 + 15.748, places=2)    # "detector length minus Track K-1 West"
        self.assertAlmostEqual(lengths["K-2"], 113.6, places=2)             # no stub named

    def test_footer_has_no_glyph_base14_helvetica_lacks(self):
        self.assertNotIn("–", build_soq.FOOTER)

    def test_unknown_section_stops_the_build(self):
        with self.assertRaises(SystemExit):
            build_soq.generic("Track Nowhere")


class Numbering(unittest.TestCase):
    def setUp(self):
        self.doc, self.toc, self.figs, self.tabs, self.labels = build_soq.render("1 January 2026")

    def test_quoted_section_numbers_hold(self):
        for key, num in build_soq.EXPECTED.items():
            self.assertTrue(self.labels[key].endswith(num), key)

    def test_every_cross_reference_is_filled(self):
        self.assertNotRegex(self.doc, r'<a class="xref" href="#[^"]+"></a>')

    def test_drawings_are_labelled_from_their_captions(self):
        self.assertEqual([lab for _, lab, _, _ in self.figs if lab.startswith("Drawing")],
                         [f"Drawing D{n}" for n in range(1, 7)])

    def test_placeholders_name_a_punch_list_item(self):
        punch = build_soq.punch_items()
        for m in re.finditer(r"Photograph pending · (PL-\d\d)</strong>.*?File: photos/([^<]+)</div>", self.doc):
            self.assertIn(m.group(2), punch[m.group(1)])


class PlanClips(unittest.TestCase):
    def test_layout_names_are_removed_from_the_schematic_copy(self):
        group = make_drawings.staging_group()
        texts = re.findall(r">([^<]+)</text>", group)
        self.assertTrue(texts)
        for t in texts:
            self.assertRegex(t, r"^\d{1,2}[ab]?$")
        for name in ("MAIN WEST", "PRINCESS", "SOUTH YARD", "EH-1"):
            self.assertNotIn(name, group)

    def test_highlights_sit_on_the_schematic_track(self):
        make_drawings.check_overlays()
        saved = make_drawings.RS_GAPS
        try:
            make_drawings.RS_GAPS = saved + [(5, 5)]
            with self.assertRaises(SystemExit):
                make_drawings.check_overlays()
        finally:
            make_drawings.RS_GAPS = saved

    def test_figures_draw(self):
        for name, fn in make_drawings.FIGURES:
            svg = fn()
            self.assertTrue(svg.startswith("<svg"), name)
            self.assertIn("<title", svg, name)


try:
    import fitz  # noqa: F401
    HAVE_FITZ = True
except ImportError:
    HAVE_FITZ = False


class MemberCopy(unittest.TestCase):
    """--member: the private filled copy (dummy data, temporary folders outside the repo)."""

    def write(self, folder: Path, body: str) -> Path:
        f = folder / "member.toml"
        f.write_text(body)
        return f

    @unittest.skipUnless(HAVE_FITZ, "needs PyMuPDF (root .venv)")
    def test_fills_the_member_fields_outside_the_repo(self):
        import tempfile
        import fitz
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "filled.pdf"
            f = self.write(Path(td), f'name = "Test Member"\nstreet = "1 Test St"\nfirst_award = true\noutput = "{out}"\n')
            build_soq.fill_member(f)
            with fitz.open(out) as d:
                fields = {w.field_name: w.field_value for p in list(d)[:2] for w in p.widgets()}
                title_text = d[build_soq.FORM_PAGES].get_text()
        self.assertEqual(fields["s Name"], "Test Member")
        self.assertIn("Test Member", title_text)
        self.assertNotIn(build_soq.title_member_placeholder(), title_text)
        self.assertEqual(fields["NAME"], "Test Member")
        self.assertEqual(fields["Street"], "1 Test St")
        self.assertNotIn(fields[build_soq.FIRST_AWARD], ("Off", "", None))

    @unittest.skipUnless(HAVE_FITZ, "needs PyMuPDF (root .venv)")
    def test_signature_lands_on_the_line_inside_the_box(self):
        import tempfile
        import fitz
        with tempfile.TemporaryDirectory() as td:
            sig = Path(td) / "sig.png"
            fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 100), 1).save(str(sig))      # wide 4:1 image
            out = Path(td) / "filled.pdf"
            f = self.write(Path(td), f'signature_image = "sig.png"\noutput = "{out}"\n')
            build_soq.fill_member(f)
            with fitz.open(out) as d:
                page = d[1]
                field = next(w.rect for w in page.widgets() if w.field_name == "SIGNATURE")
                (img,) = page.get_image_info()
                box = fitz.Rect(img["bbox"])
        self.assertGreaterEqual(box.x0, field.x0)
        self.assertLessEqual(box.x1, field.x1)
        self.assertAlmostEqual(box.y1, field.y1 + build_soq.SIG_DROP, delta=0.5)
        self.assertGreater(box.height, field.height)

    def test_signature_box_keeps_wide_images_inside(self):
        import types
        rect = types.SimpleNamespace(x0=100, y1=200, width=160, height=16)
        try:
            box = build_soq.signature_box(rect, 50.0)
        except ImportError:
            self.skipTest("needs PyMuPDF")
        self.assertLessEqual(box.x1, 100 + 160)

    def test_refuses_output_inside_the_repo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            f = self.write(Path(td), f'name = "X"\noutput = "{HERE / "filled.pdf"}"\n')
            with self.assertRaises(SystemExit):
                build_soq.fill_member(f)
        self.assertFalse((HERE / "filled.pdf").exists())

    def test_refuses_unknown_keys(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            f = self.write(Path(td), 'nam = "typo"\n')
            with self.assertRaises(SystemExit):
                build_soq.fill_member(f)


class DeckCache(unittest.TestCase):
    """export_decks reuses a cached export while the deck is unchanged, without starting Keynote."""

    def test_unchanged_deck_is_not_exported_again(self):
        import hashlib
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            deck = td / "deck.pptx"
            deck.write_bytes(b"deck v1")
            key = (b'tell application "Keynote" / open / export as PDF / close saving no'
                   + build_soq.DECK_EXPORT_VERSION.encode())
            cached = td / "build" / "decks" / f"layout-{hashlib.sha256(deck.read_bytes() + key).hexdigest()[:16]}.pdf"
            cached.parent.mkdir(parents=True)
            cached.write_bytes(b"%PDF cached")
            with mock.patch.object(build_soq, "DECKS", {"layout": deck}), \
                    mock.patch.object(build_soq, "BUILD", td / "build"), \
                    mock.patch.object(build_soq.subprocess, "run", side_effect=AssertionError("Keynote started")):
                out = build_soq.export_decks(td)
        self.assertEqual(out["layout"], cached)


class BuiltPdf(unittest.TestCase):
    """The committed, assembled PDF."""

    @unittest.skipUnless(HAVE_FITZ, "needs PyMuPDF (root .venv)")
    def test_built_pdf_numbers_its_pages_once(self):
        import fitz
        with fitz.open(build_soq.OUT_PDF) as d:
            labels = d.get_page_labels()
            last = d[d.page_count - 1].get_text()
            total = d.page_count
        self.assertEqual(labels, [{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 1}])
        self.assertIn(f"Page {total} of {total}", last)


if __name__ == "__main__":
    unittest.main()
