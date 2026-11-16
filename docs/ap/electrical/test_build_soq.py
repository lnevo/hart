#!/usr/bin/env python3
"""Tests for the MRE Electrical SOQ build (no Chrome, Keynote or PyMuPDF needed).

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


class MemberCopy(unittest.TestCase):
    """--member: the private filled copy (dummy data, temporary folders outside the repo)."""

    def write(self, folder: Path, body: str) -> Path:
        f = folder / "member.toml"
        f.write_text(body)
        return f

    def test_fills_the_member_fields_outside_the_repo(self):
        import tempfile
        import fitz
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "filled.pdf"
            f = self.write(Path(td), f'name = "Test Member"\nstreet = "1 Test St"\nfirst_award = true\noutput = "{out}"\n')
            build_soq.fill_member(f)
            fields = {w.field_name: w.field_value for p in list(fitz.open(out))[:2] for w in p.widgets()}
        self.assertEqual(fields["s Name"], "Test Member")
        self.assertEqual(fields["NAME"], "Test Member")
        self.assertEqual(fields["Street"], "1 Test St")
        self.assertNotIn(fields[build_soq.FIRST_AWARD], ("Off", "", None))

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


if __name__ == "__main__":
    unittest.main()
