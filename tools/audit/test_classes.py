#!/usr/bin/env python3
"""Print the test classes of one unittest file that hold tests, one per line, as discover finds them.

    python3 tools/audit/test_classes.py tools/audit/tests/test_worktrees.py

tools/check.sh runs a file it names in BY_CLASS as one job per class this prints. Exit 1 when the file
cannot be loaded or holds no tests, so check.sh never drops a file's tests by listing nothing.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


def ids(suite) -> list[str]:
    out = []
    for item in suite:
        out += ids(item) if isinstance(item, unittest.TestSuite) else [item.id()]
    return out


def main(argv: list[str]) -> int:
    path = Path(argv[1])
    suite = unittest.defaultTestLoader.discover(str(path.parent), pattern=path.name)
    tests = ids(suite)
    failed = [t for t in tests if t.startswith("unittest.loader._FailedTest")]
    if failed or not tests:
        print(f"{path}: {'cannot be loaded' if failed else 'holds no tests'}", file=sys.stderr)
        return 1
    classes = dict.fromkeys(t.split(".")[-2] for t in tests)
    print("\n".join(classes))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
