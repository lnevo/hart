"""xml_need.need: the element a path names, or an AssertionError naming the path."""
from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from xml_need import need


class Need(unittest.TestCase):
    def test_returns_the_element_or_names_the_missing_path(self) -> None:
        root = ET.fromstring("<a><b><c /></b></a>")
        self.assertEqual("c", need(root, "b/c").tag)
        with self.assertRaisesRegex(AssertionError, "no b/d under <a>"):
            need(root, "b/d")


if __name__ == "__main__":
    unittest.main()
