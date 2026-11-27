"""For the data checks that run the builders through the schematic plugin: without the plugin they skip, as the
schematic checks do, and with SCHEMATIC_REQUIRED=1 (CI) a missing plugin fails them."""
from __future__ import annotations

import os
import unittest
from typing import NoReturn


def skip_or_fail(exc: Exception, what: str = "these checks") -> NoReturn:
    """Skip the test for `exc` (the plugin, or a builder it runs, could not load); under SCHEMATIC_REQUIRED=1 fail it,
    the message naming `what` needs the plugin."""
    if os.environ.get("SCHEMATIC_REQUIRED") == "1":
        raise AssertionError(f"{what} need the plugin (SCHEMATIC_REQUIRED=1): {exc}") from exc
    raise unittest.SkipTest(str(exc)) from exc
