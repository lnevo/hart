"""hartlib.tables_build.master_beans by layer: each row's beans (its _layer_beans) and every row's problem reported
in one error, on rows made here."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import devices as D, tables, tables_build as tb  # noqa: E402
from hartlib.tables_sections import BLOCKS, HEADS, LAYOUT_BLOCKS, MASTS, MQTT_SENSORS  # noqa: E402


def row(**cells: str) -> dict[str, str]:
    out = {c: "" for c in D.COLUMNS}
    out.update({"level": "1", "assignment": "field", **cells})
    return out


BLOCK = row(layer="block", role="track", user_name="Track A", jmri_name="IB:T:1", layout_block="ILB:T:1",
            jmri_comment="Track A")
DETECTOR = row(layer="occupancy", role="track", user_name="BS Track A", jmri_name="M2S901", jmri_comment="A",
               blocks="Track A")
HEAD = row(layer="head", role="head", user_name="Head 9", jmri_name="IH901", jmri_comment="here")
MAST = row(layer="mast", role="home", user_name="Mast 9", jmri_name="IF$vsm:basic:one-low($9)", jmri_comment="here")


class ByLayer(unittest.TestCase):
    def test_each_layer_gives_its_beans_in_its_sections(self) -> None:
        beans = tb.master_beans([BLOCK, DETECTOR, HEAD, MAST], {"Track A": 10.0})
        self.assertEqual({("blocks-names",) + BLOCKS: ["IB:T:1"], BLOCKS: ["IB:T:1"], LAYOUT_BLOCKS: ["ILB:T:1"],
                          MQTT_SENSORS: ["M2S901"], HEADS: ["IH901"], MASTS: ["IF$vsm:basic:one-low($9)"]},
                         {k: [tables.system_name(e) for e in v] for k, v in beans.items()})
        full = beans[BLOCKS][0]
        self.assertEqual(("254.0", "BS Track A"), (full.get("length"), full.findtext("occupancysensor")))

    def test_a_row_with_assignment_none_gives_nothing(self) -> None:
        self.assertEqual({}, tb.master_beans([dict(HEAD, assignment="none")], {}))

    def test_every_row_s_problem_is_in_one_error(self) -> None:
        rows = [dict(BLOCK),                                              # two detectors
                dict(BLOCK, user_name="Track B", layout_block=""),        # no layout block
                dict(MAST, jmri_name="IF$dsm:x"),                         # neither mast kind
                row(layer="light", user_name="Lamp", jmri_name="IL1", jmri_comment="x"),
                dict(DETECTOR), dict(DETECTOR, user_name="BS Track A2", jmri_name="M2S902")]
        lengths = {"Track A": 1.0, "Track B": 5.0}
        with self.assertRaises(tb.TablesBuildError) as got:
            tb.master_beans(rows, lengths)
        text = str(got.exception)
        self.assertTrue(text.startswith("the device master: block 'Track A': detected by 2 occupancy rows"), text)
        for part in ("block 'Track B': no layout_block", "mast 'Mast 9': bean name 'IF$dsm:x' is neither",
                     "light 'Lamp': no bean for layer 'light'"):
            self.assertIn(part, text)
        with self.assertRaisesRegex(tb.TablesBuildError, "block 'Track A': no row in block_lengths.csv"):
            tb.master_beans([BLOCK], {})


if __name__ == "__main__":
    unittest.main()
