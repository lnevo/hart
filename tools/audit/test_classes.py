#!/usr/bin/env python3
"""Print the test classes of one unittest file that hold tests, as module.Class, one per line, as discover finds them.

    python3 tools/audit/test_classes.py tools/audit/tests/test_worktrees.py

tools/check.sh runs a file it names in BY_CLASS as one job per class this prints, selecting it with
unittest -k "module.Class." (the test ids' own prefix, so a class imported from another module is still
found). With `--methods module.Class` it prints that class's test ids instead (check.sh's BY_METHOD: one job per
test, selected with -k "module.Class.test_name"). Exit 1 when the file cannot be loaded or holds no tests, so check.sh never drops a file's tests
by listing nothing.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


def ids(suite: unittest.TestSuite) -> list[str]:
    out: list[str] = []
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
    if "--methods" in argv:
        cls = argv[argv.index("--methods") + 1]
        mine = [t for t in tests if t.rsplit(".", 1)[0] == cls]
        if not mine:
            print(f"{path}: no tests in {cls}", file=sys.stderr)
            return 1
        print("\n".join(mine))
        return 0
    classes = dict.fromkeys(t.rsplit(".", 1)[0] for t in tests)
    print("\n".join(classes))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
