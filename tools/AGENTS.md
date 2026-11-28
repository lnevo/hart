# Repo tools

Rules for CPython code under `tools/`, on top of the root [`AGENTS.md`](../AGENTS.md). Schematic and panel code also follows [`tools/schematic/AGENTS.md`](schematic/AGENTS.md).

- CPython tools import `hartlib` ([`tools/hartlib/README.md`](hartlib/README.md)); Jython scripts inside JMRI never do.
- Habits the 2026-11-26 review found, to avoid (`tools/audit/check_habits.py` ratchets some of them):
  - copying a helper instead of reusing it;
  - `str(exc) from None` (chain `from exc`);
  - `sys.exit` in library code;
  - dates or edit history in comments (decisions go in `wiki/`);
  - tests that search source instead of running it;
  - bare dicts or tuples for records (dataclass, TypedDict, NamedTuple, `Literal`);
  - annotations mypy would reject;
  - `exec` or `globals()` parts instead of real modules.
