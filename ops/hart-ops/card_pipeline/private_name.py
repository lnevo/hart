"""Detect the railroad's private name without writing it down.

The repo and website are public, so the name is never spelled out in a file (AGENTS.md).
Text is checked by hashing each pair of neighbouring words, lower-cased with punctuation
removed, against the SHA-256 fingerprints below.
"""
from __future__ import annotations

import hashlib
import re

FINGERPRINTS = frozenset({
    "45b8cb45ddecb0c43a71c461efc667c743d6e69a08c4f0ee0f13f8d90affa0a0",
    "258b7b3e017e41b911ad07028b9780146ff721653ea37c10ec96e097b76bcd71",  # short form
})
WORD = re.compile(r"[a-z0-9]+")


def word_pairs(text: str):
    words = WORD.findall(text.lower())
    return (f"{a} {b}" for a, b in zip(words, words[1:]))


def contains_private_name(text: str) -> bool:
    return any(hashlib.sha256(p.encode()).hexdigest() in FINGERPRINTS for p in word_pairs(text or ""))
