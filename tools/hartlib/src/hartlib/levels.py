"""The railroad's levels: 1 staging, 2 main, 3 upper. One type and one parser for every fact file."""
from __future__ import annotations

from collections.abc import Collection
from typing import Literal, cast

from .errors import FactsError

Level = Literal[1, 2, 3]
# A level as text: the device master's level column, and Switch.level, which callers compare with "1".
LevelText = Literal["1", "2", "3"]

STAGING: Level = 1
ALL_LEVELS: tuple[Level, ...] = (1, 2, 3)
MAIN_UPPER: tuple[Level, ...] = (2, 3)
NAMES: dict[int, str] = {1: "staging", 2: "main", 3: "upper"}


def parse_level(value: str | int, where: str, allowed: Collection[Level] = ALL_LEVELS) -> Level:
    """value (a cell's text or a number) as a Level that is one of allowed; FactsError naming `where` otherwise."""
    try:
        level = int(value)
    except ValueError as exc:
        raise FactsError(f"{where}: level is a whole number, not {value!r}") from exc
    if level not in allowed:
        ok = sorted(allowed)
        words = " or ".join([", ".join(map(str, ok[:-1])), str(ok[-1])]) if len(ok) > 1 else str(ok[0])
        raise FactsError(f"{where}: level is {words} ({', '.join(NAMES[n] for n in ok)}), not {level}")
    return cast(Level, level)


def level_text(level: Level) -> LevelText:
    """level as the text the device master writes."""
    return cast(LevelText, str(level))
