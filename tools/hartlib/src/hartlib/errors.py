"""hartlib's error classes: HartlibError is the base of every error hartlib raises on purpose.

Each module's own error (FactsError, TablesBuildError, SplitError and the rest) derives from HartlibError and keeps
its standard base (ValueError or RuntimeError), so a caller may catch either.
"""
from __future__ import annotations


class HartlibError(Exception):
    """An error hartlib raises on purpose; the message names the file, row or name it is about."""


class FactsError(HartlibError, ValueError):
    """A fact file that cannot be read as it stands: the message names the file and the row."""
