"""The share-card recipes' pure parts: the bridge function found by name, the roster rows and their errors."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_share_cards  # noqa: E402,F401  (loads the kit before the recipes, as the package does)
from share_card_recipes.editor_view import SHOWN_FUNCTION, function_lines, shown_lines  # noqa: E402
from share_card_recipes import CardError  # noqa: E402
from share_card_recipes.panel_image import ROSTER_ROWS, roster_rows  # noqa: E402

SOURCE = """#include "x.h"
static bool helper(void);

/**
 * Map appearance name to aspect.
 */
static bool appearanceToLcosAspect(const char *name, byte *aspect_out) {
  if (name == NULL) {
    return false;
  }
  return true;
}

static bool helper(void) { return true; }
""".splitlines()


class FunctionLines(unittest.TestCase):
    def test_doc_comment_to_closing_brace(self) -> None:
        self.assertEqual(function_lines(SOURCE, SHOWN_FUNCTION), (4, 12))

    def test_lines_move_with_the_source(self) -> None:
        self.assertEqual(function_lines(["// new line", ""] + SOURCE, SHOWN_FUNCTION), (6, 14))

    def test_a_function_without_a_doc_comment_starts_at_its_definition(self) -> None:
        self.assertEqual(function_lines(SOURCE[6:], SHOWN_FUNCTION), (1, 6))

    def test_missing_function_is_a_card_error(self) -> None:
        with self.assertRaisesRegex(CardError, "0 times"):
            function_lines(SOURCE, "noSuchFunction")

    def test_unclosed_function_is_a_card_error(self) -> None:
        with self.assertRaisesRegex(CardError, "no closing brace"):
            function_lines(SOURCE[:9], SHOWN_FUNCTION)


class ShownLines(unittest.TestCase):
    def test_a_function_longer_than_the_code_area_is_cut_at_its_last_row(self):
        self.assertEqual(shown_lines(SOURCE, SHOWN_FUNCTION, rows=5), (4, 8))

    def test_a_function_that_fits_is_shown_whole(self):
        self.assertEqual(shown_lines(SOURCE, SHOWN_FUNCTION, rows=25), (4, 12))


class RosterRows(unittest.TestCase):
    def test_every_row_drawn_in_order(self) -> None:
        items = [{"kind": k, "publicName": n, "cp": "CP 1", "hardware": "<LCC>"} for k, n in ROSTER_ROWS]
        html = roster_rows(items)
        self.assertEqual(html.count("<tr>"), len(ROSTER_ROWS))
        self.assertIn("&lt;LCC&gt;", html)
        self.assertLess(html.index("Switch 1"), html.index("OS Switch 3"))

    def test_missing_rows_are_named(self) -> None:
        with self.assertRaisesRegex(CardError, "no signal Mast 2L, signal Mast 4RA"):
            roster_rows([{"kind": k, "publicName": n} for k, n in ROSTER_ROWS if k != "signal"])


if __name__ == "__main__":
    unittest.main()
