#!/usr/bin/env python3
"""Fail if study text uses AI-speak: filler and stock phrases that add tone but no facts.

The C&E study deck (``www/exam/index.html``) holds the guide prose, the flashcards and the
practice questions. Its text should state rules and facts in plain words. This check
flags the phrasings that crept in when it was drafted, for example "People mix the two
up; the exam won't." or "The terms are often confused.": claims about readers or the
exam that the OPSIG guides never make.

Each pattern names what is wrong with it. Rewrite the sentence (usually by deleting the
clause); there is no suppression marker. Pass paths to check other files.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILES = ("www/exam/index.html",)

# (pattern, why it is flagged). Case-insensitive, matched per line.
PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(people|students|crews|readers|many|most)\b[^.;]{0,20}\b(mix|confuse|muddle)", "claim about readers' mistakes"),
    (r"\b(often|commonly|easily|frequently) (confused|mixed up|misread|forgotten)", "claim about readers' mistakes"),
    (r"\bthe (exam|test|quiz)\b[^.;]{0,25}\b(won't|will not|doesn't|does not|loves|likes|expects|wants)\b", "speaking for the exam"),
    (r"\b(questions?|answers?) (often |usually |mostly )?turns? on\b", "speaking for the exam"),
    (r"\bthink of (it|the|this|them)\b", "coaching aside"),
    (r"(^|[.>]\s*)picture (this|a|an|eastbound|westbound|northbound|southbound)\b", "coaching aside"),
    (r"\bso learn (these|this|them|which)\b", "coaching aside"),
    (r"\bthe (key|trick|catch|secret) (is|here)\b", "stock phrase"),
    (r"\bhere'?s (the|what|why|how)\b", "stock phrase"),
    (r"\bit'?s (not just|all about)\b", "stock phrase"),
    (r"\b(in short|simply put|put simply|at its core|bottom line|in a nutshell|long story short)\b", "stock phrase"),
    (r"\b(crucial(ly)?|essentially|delve|seamless(ly)?|robust|leverage|tapestry|nuanced?)\b", "stock word"),
    (r"\b(worth noting|it should be noted|keep in mind|remember that)\b", "stock phrase"),
    (r"\b(waiting|wait|run|going) forever\b", "invented colour"),
    (r"\bexplains the ideas\b|\b(cards|tests) (and tests |and cards )?check (them|it)\b", "closing summary line"),
)
COMPILED = tuple((re.compile(p, re.I), why) for p, why in PATTERNS)
STYLE = re.compile(r"<style\b.*?</style>", re.I | re.S)


def strip_style(text: str) -> str:
    """Blank CSS blocks but keep their newlines so line numbers still match."""
    return STYLE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def find(text: str) -> list[tuple[int, str, str]]:
    """(line number, matched text, reason) for each hit."""
    hits = []
    for n, line in enumerate(strip_style(text).splitlines(), 1):
        for rx, why in COMPILED:
            for m in rx.finditer(line):
                hits.append((n, m.group(0).strip(" .>"), why))
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", help=f"files to check (default: {', '.join(DEFAULT_FILES)})")
    args = ap.parse_args(argv)
    paths = [Path(p) for p in args.paths] or [ROOT / f for f in DEFAULT_FILES]
    bad = 0
    for path in paths:
        for n, hit, why in find(path.read_text(encoding="utf-8")):
            rel = path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT) else path
            print(f"{rel}:{n}: {why}: “{hit}”")
            bad += 1
    if bad:
        print(f"{bad} AI-speak phrase(s). State the rule or fact plainly; drop the aside.")
        return 1
    print(f"ai-speak: {len(paths)} file(s) clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
