#!/usr/bin/env python3
"""Superseded.

The 2026-08-19 Barn interlocking (T6 at 103 + virtual OS 116 / OS 104)
was reverted. Yard ladder is unsignaled / local; T6 sits on TO117.B again.

Use ``jmri/layouts/hart/scripts/revert_barn_ladder_signals.py``.
"""
import sys

print(
    "update_barn_signals.py is retired — "
    "run jmri/layouts/hart/scripts/revert_barn_ladder_signals.py",
    file=sys.stderr,
)
sys.exit(2)
