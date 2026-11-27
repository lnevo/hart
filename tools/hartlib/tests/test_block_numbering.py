"""hartlib.block_numbering: block_numbering.csv's reader and the rule that numbers the main and upper blocks
(naming-layers step 8). The builder copies these numbers into the block rows; the committed rows must hold them."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from hartlib import block_numbering as bn, devices  # noqa: E402

HEADER = ",".join(bn.COLUMNS) + "\n"
NAMES = {("2", "block:107B-107C#1"): "Track 107 Loop 1", ("2", "block:107B-107C#2"): "Track 107 Loop 2"}
BLOCKS = ["OS Switch 105", "Track 105-109", "Track 107 Loop 1", "Track 107 Loop 2", "OS Switch 201"]


def numbering(text: str, names=NAMES) -> bn.Numbering:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / bn.PATH.name
        path.write_text(HEADER + text, encoding="utf-8")
        return bn.read(path, names)


class Rule(unittest.TestCase):
    def test_os_blocks_first_then_by_number_appended_last_retired_held(self):
        n = numbering("block:107B-107C#1,Track 107 Loop,,,\nblock:107B-107C#2,,1,,\n,,,Track 106 Gone,\n")
        self.assertEqual(n, bn.Numbering({"Track 107 Loop 1": "Track 107 Loop"}, ("Track 107 Loop 2",),
                                         ("Track 106 Gone",)))
        self.assertEqual(bn.bean_names(BLOCKS, n), {
            "OS Switch 105": ("IB:C3:0001", "ILB1001"), "OS Switch 201": ("IB:C3:0002", "ILB1002"),
            # Track 106 Gone holds 0003
            "Track 107 Loop 1": ("IB:C3:0004", "ILB1004"), "Track 105-109": ("IB:C3:0005", "ILB1005"),
            "Track 107 Loop 2": ("IB:C3:0006", "ILB1006")})

    def test_a_row_moves_a_number(self):
        """A block takes its numbers from the file: numbered_as gives it another's sort place."""
        n = numbering("block:107B-107C#1,OS Switch 106,,,\nblock:107B-107C#2,,1,,\n")
        self.assertEqual(bn.bean_names(BLOCKS, n)["Track 107 Loop 1"], ("IB:C3:0002", "ILB1002"))

    def test_problems_stop(self):
        with self.assertRaisesRegex(bn.NumberingError, "no main or upper device"):
            numbering("block:9X-9Y,,1,,\n")
        with self.assertRaisesRegex(bn.NumberingError, "exactly one of numbered_as, append_order"):
            numbering("block:107B-107C#1,Track 107 Loop,1,,\n")
        with self.assertRaisesRegex(bn.NumberingError, "without a gap"):
            numbering("block:107B-107C#2,,2,,\n")
        with self.assertRaisesRegex(bn.NumberingError, "retired blocks drawn again: Track 105-109"):
            bn.bean_names(BLOCKS, numbering(",,,Track 105-109,\n"))
        with self.assertRaisesRegex(bn.NumberingError, "no longer have"):
            bn.bean_names(["OS Switch 105"], numbering("block:107B-107C#2,,1,,\n"))

    def test_a_message_names_the_file_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "numbers_copy.csv"
            path.write_text(HEADER + ",,,Track 105-109,\n", encoding="utf-8")
            n = bn.read(path, NAMES)
        self.assertEqual(n.source, path)
        with self.assertRaisesRegex(bn.NumberingError, "out of numbers_copy.csv's retired rows"):
            bn.bean_names(BLOCKS, n)
        with self.assertRaisesRegex(bn.NumberingError, "^numbers_copy.csv names Track 105-109"):
            bn.order(["OS Switch 105"], n, require_listed=True)


class CommittedRows(unittest.TestCase):
    def test_every_main_and_upper_block_row_has_the_files_numbers(self):
        """The committed device master: each main and upper block row but a helix block's carries the names the rule
        gives over block_numbering.csv and the generated names (as build_device_map.block_beans numbers them, so an
        owner's rename keeps them), and only those rows have them."""
        rows = [r for r in devices.load() if r.level_cell in bn.LEVELS and r.layer == "block"]
        numbered = [r for r in rows if r.role != "helix"]
        generated = {(r["level"], r["id"]): r["user_name"] for r in devices.generated_rows()
                     if r["level"] in bn.LEVELS and r["layer"] == "block" and r["role"] != "helix"}
        want = bn.bean_names(generated.values(), bn.read(bn.PATH, generated))
        self.assertEqual({(r.level_cell, r.id): (r.jmri_name, r.layout_block) for r in numbered},
                         {k: want[name] for k, name in generated.items()})
        self.assertEqual({r.assignment for r in numbered}, {"virtual"})
        self.assertEqual([(r.jmri_name, r.layout_block) for r in rows if r.role == "helix"],
                         [("", "")] * 2)


if __name__ == "__main__":
    unittest.main()
