#!/usr/bin/env python3
"""The render stamp a layout index builder writes into its committed PNG, and the PNG's size.

The layout index JSON files are built where they are used, not committed (ADR-036), so the hash of what each PNG is
drawn from (build_layout_index.render_inputs_sha256, build_cats_layout_index.render_inputs_sha256) is kept in the
PNG itself, as a tEXt chunk named KEY, written right after the renderer draws it. --check compares it with the
hash of the current inputs: a PNG drawn from older inputs, or never stamped, fails. Standard library only, so the
check needs no Pillow.
"""
from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

SIGNATURE = b"\x89PNG\r\n\x1a\n"
KEY = b"render-inputs-sha256"


class PngError(Exception):
    """A PNG that cannot be read or stamped; the message names the file."""


def _chunks(data: bytes, path: Path) -> list[tuple[bytes, bytes]]:
    """(type, body) of each chunk, checked: the signature, every length and CRC, IHDR first and IEND last."""
    if not data.startswith(SIGNATURE):
        raise PngError(f"{path} is not a PNG")
    out, i = [], len(SIGNATURE)
    while i < len(data):
        if i + 8 > len(data):
            raise PngError(f"{path}: a chunk header is cut off at byte {i}")
        (n,), kind = struct.unpack(">I", data[i:i + 4]), data[i + 4:i + 8]
        body, crc = data[i + 8:i + 8 + n], data[i + 8 + n:i + 12 + n]
        if len(body) != n or len(crc) != 4 or struct.unpack(">I", crc)[0] != zlib.crc32(kind + body):
            raise PngError(f"{path}: chunk {kind!r} at byte {i} is cut off or its CRC is wrong")
        out.append((kind, body))
        i += 12 + n
    if not out or out[0][0] != b"IHDR" or out[-1][0] != b"IEND":
        raise PngError(f"{path}: no IHDR first or no IEND last")
    return out


def _read(path: Path) -> list[tuple[bytes, bytes]]:
    try:
        data = Path(path).read_bytes()
    except OSError as err:
        raise PngError(f"cannot read {path}: {err.strerror or err}") from err
    return _chunks(data, Path(path))


def size(path: Path) -> tuple[int, int]:
    """(width, height) from the PNG's IHDR."""
    return struct.unpack(">II", _read(path)[0][1][:8])


def stamp(path: Path) -> str | None:
    """The render stamp written into the PNG, or None when it has none."""
    found = [body[len(KEY) + 1:] for kind, body in _read(path) if kind == b"tEXt" and body.startswith(KEY + b"\0")]
    if len(found) > 1:
        raise PngError(f"{path} has {len(found)} {KEY.decode()} stamps")
    return found[0].decode("latin-1") if found else None


def write_stamp(path: Path, value: str) -> None:
    """Write `value` as the PNG's render stamp (replacing an older one) and read it back."""
    if not value or not value.isascii() or "\0" in value:
        raise PngError(f"a render stamp is a non-empty ASCII text, not {value!r}")
    path = Path(path)
    body = KEY + b"\0" + value.encode("ascii")
    kept = [(k, b) for k, b in _read(path) if not (k == b"tEXt" and b.startswith(KEY + b"\0"))]
    kept.insert(len(kept) - 1, (b"tEXt", body))  # before IEND
    data = SIGNATURE + b"".join(struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b))
                                for k, b in kept)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError as err:
        raise PngError(f"cannot write {path}: {err.strerror or err}") from err
    if stamp(path) != value:
        raise PngError(f"{path} reads back without the stamp just written")
