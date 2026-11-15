#!/usr/bin/env python3
"""Fail if site prose uses AI-speak: filler and stock phrases that add tone but no facts.

Covers the article pages (``DEFAULT_GLOBS``): the AI topics, library, behind-the-scenes,
guides, Achievement Program pages and the C&E study deck. Their text should state facts in
plain words. This check flags the phrasings that crept in when they were drafted, for example "People mix the two
up; the exam won't." or "The terms are often confused.": claims about readers or the
exam that the OPSIG guides never make.

Each pattern names what is wrong with it. Rewrite the sentence (usually by deleting the
clause); there is no suppression marker. Pass paths to check other files.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

ROOT = paths.REPO_ROOT
DEFAULT_GLOBS = ("www/ai/*.html", "www/library/*.html", "www/behind/*.html",
                 "www/guides/*.html", "www/ap/*.html", "www/exam/index.html")

# (pattern, why it is flagged). Case-insensitive, matched on the text with tags removed,
# entities decoded, curly apostrophes made straight and line breaks joined.
PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(people|students|crews|readers|many|most)\b[^.;]{0,20}\b(mix(es|ed)? (up|them|the)|confuse|muddle)", "claim about readers' mistakes"),
    (r"\b(often|commonly|easily|frequently) (confused|mixed up|misread|forgotten)", "claim about readers' mistakes"),
    (r"\bthe (exam|quiz)\b[^.;]{0,25}\b(won't|will not|doesn't|does not|loves|likes|expects|wants)\b", "speaking for the exam"),
    (r"\b(questions?|answers?) (often |usually |mostly )?turns? on\b", "speaking for the exam"),
    (r"\bthink of (it|the|this|them)\b", "coaching aside"),
    (r"(?<![\w-])picture (this|a|an|eastbound|westbound|northbound|southbound)\b", "coaching aside"),
    (r"\bso learn (these|this|them|which)\b", "coaching aside"),
    (r"\bthe (key|trick|catch|secret) (is|here)\b", "stock phrase"),
    (r"\bhere'?s (the|what|why|how)\b", "stock phrase"),
    (r"\bit'?s (not just|all about)\b", "stock phrase"),
    (r"\b(in short|simply put|put simply|at its core|bottom line|in a nutshell|long story short)\b", "stock phrase"),
    (r"\b(crucial(ly)?|essentially|delve|seamless(ly)?|robust|leverage|tapestry|nuanced?)\b", "stock word"),
    (r"\b(worth noting|it should be noted|keep in mind|remember that)\b", "stock phrase"),
    (r"\b(waiting|wait|run|going) forever\b", "invented colour"),
    (r"\bis only as good as\b", "tidy moral"),
    (r"\bso a spare (evening|weekend|afternoon)\b", "speaking for the reader"),
    (r"\ba good place to start\b", "coaching aside"),
    (r"\bthe rule (also )?works the other way\b", "stock phrase"),
    (r"\bexplains the ideas\b|\b(cards|tests) (and tests |and cards )?check (them|it)\b", "closing summary line"),
)
COMPILED = tuple((re.compile(p, re.I), why) for p, why in PATTERNS)
STYLE = re.compile(r"<style\b.*?</style>", re.I | re.S)
TAG = re.compile(r"<[^>]*>")
APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})


def plain(text: str) -> tuple[str, list[int]]:
    """Text to match (whitespace runs, including newlines, become one space) and the
    source line of each of its characters. CSS and tags are dropped; entities decoded."""
    text = STYLE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    text = TAG.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    out: list[str] = []
    lines: list[int] = []
    line = 1
    for chunk in re.split(r"(\s+)", text):
        if not chunk:
            continue
        if chunk.isspace():
            if out and out[-1] != " ":
                out.append(" ")
                lines.append(line)
            line += chunk.count("\n")
            continue
        for ch in html.unescape(chunk).translate(APOSTROPHES):
            out.append(ch)
            lines.append(line)
    return "".join(out), lines


def find(text: str) -> list[tuple[int, str, str]]:
    """(line number, matched text, reason) for each hit, in source order."""
    flat, lines = plain(text)
    hits = []
    for rx, why in COMPILED:
        for m in rx.finditer(flat):
            hits.append((lines[m.start()], m.group(0).strip(" .>"), why))
    return sorted(hits)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", help=f"files to check (default: {', '.join(DEFAULT_GLOBS)})")
    args = ap.parse_args(argv)
    paths = [Path(p) for p in args.paths] or sorted(p for g in DEFAULT_GLOBS for p in ROOT.glob(g))
    bad = 0
    missing = [p for p in paths if not p.is_file()]
    if missing:
        print("no such file: " + ", ".join(map(str, missing)))
        return 2
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
