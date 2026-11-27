"""plugin_needed.skip_or_fail: a skip without SCHEMATIC_REQUIRED, a failure naming what needs the plugin with it."""
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plugin_needed import skip_or_fail  # noqa: E402


class SkipOrFail(unittest.TestCase):
    def test_without_the_requirement_the_test_skips(self):
        exc = RuntimeError("plugin not found")
        with unittest.mock.patch.dict("os.environ", {"SCHEMATIC_REQUIRED": ""}), \
                self.assertRaisesRegex(unittest.SkipTest, "^plugin not found$") as skip:
            skip_or_fail(exc)
        self.assertIs(skip.exception.__cause__, exc)

    def test_with_the_requirement_the_test_fails_naming_what_needs_the_plugin(self):
        exc = RuntimeError("plugin not found")
        with unittest.mock.patch.dict("os.environ", {"SCHEMATIC_REQUIRED": "1"}), \
                self.assertRaisesRegex(AssertionError, r"^the block pins need the plugin \(SCHEMATIC_REQUIRED=1\): "
                                                       "plugin not found$") as stop:
            skip_or_fail(exc, "the block pins")
        self.assertIs(stop.exception.__cause__, exc)


if __name__ == "__main__":
    unittest.main()
