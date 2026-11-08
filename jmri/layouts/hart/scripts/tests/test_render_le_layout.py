"""render_le_layout.load_geometry skips hidden track segments."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import render_le_layout  # noqa: E402
except ModuleNotFoundError as exc:  # CI has no Pillow
    raise unittest.SkipTest(f"render_le_layout needs {exc.name}")

PANEL = """<?xml version="1.0" encoding="UTF-8"?>
<layout-config>
  <LayoutEditor name="HART Railroad" class="jmri.jmrit.display.layoutEditor.configurexml.LayoutEditorXml">
    <positionablepoint ident="A1" type="ANCHOR" x="0.0" y="0.0" />
    <positionablepoint ident="A2" type="ANCHOR" x="10.0" y="0.0" />
    <positionablepoint ident="A3" type="ANCHOR" x="10.0" y="10.0" />
    <tracksegment ident="F1" blockname="Track K-1" connect1name="A1" type1="POS_POINT" connect2name="A2" type2="POS_POINT" mainline="no" hidden="no" />
    <tracksegment ident="F2" blockname="Track K-1" connect1name="A2" type1="POS_POINT" connect2name="A3" type2="POS_POINT" mainline="no" hidden="yes" />
  </LayoutEditor>
</layout-config>
"""


class HiddenSegments(unittest.TestCase):
    def test_hidden_segment_is_not_drawn(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "panel.xml"
            src.write_text(PANEL)
            pp, _legs, _turnouts, segs, _signals, _stations = render_le_layout.load_geometry(src)
        self.assertEqual([(a, b) for a, b, _m, _blk in segs], [((0.0, 0.0), (10.0, 0.0))])
        # the anchor only the hidden segment reaches is not drawn either
        self.assertEqual(sorted(pp), ["A1", "A2"])


if __name__ == "__main__":
    unittest.main()
