"""Load, look up and save JMRI tables.xml so that an unchanged save is byte-identical.

Format facts this module relies on (checked against the repo file and a raw PanelPro Store):

- JMRI (JDOM) and ElementTree write elements the same way: two-space indent kept as text,
  ``<x />`` for empty elements, double-quoted attributes in stored order, ``&amp;`` /
  ``&lt;`` / ``&gt;`` escapes, UTF-8, LF line ends.
- Except for a few character escapes. JDOM writes CR in text as ``&#xD;`` and CR, LF and
  tab in attributes as ``&#xD;`` / ``&#xA;`` / ``&#x9;``; ElementTree writes a raw CR in
  text and ``&#13;`` / ``&#10;`` / ``&#09;`` in attributes. ``save`` writes JDOM's forms,
  unless the loaded file already used ElementTree's (then it keeps those), so either kind
  of file comes back byte-identical.
- They differ only outside the root element: a PanelPro Store starts with
  ``<?xml version="1.0" encoding="UTF-8"?>`` and an ``<?xml-stylesheet ...?>`` line and
  ends with a newline; the repo file, last written by ElementTree, starts with
  ``<?xml version='1.0' encoding='UTF-8'?>`` and has no final newline. A Store also puts a
  ``<!--Written by JMRI ...-->`` comment inside the root.

So ``load`` keeps the bytes before and after the root element verbatim, parses the root
with comments and processing instructions kept, and ``save`` writes them back. Plain
``ET.parse`` + ``tree.write(..., xml_declaration=True)`` is byte-identical only for a file
ElementTree wrote last; on a fresh Store it drops the stylesheet line and the comment.

Pitfalls for lookups:

- There are several ``<sensors>`` and ``<turnouts>`` sections (one per connection: MQTT,
  internal, LCC). ``root.find("turnouts")`` returns only the first; use ``turnouts(root)``.
- JMRI writes every ``<block>`` twice: a names-only pass, then the full pass with length,
  sensor and paths. ``blocks(root)`` returns the full pass.
- Masts sit under ``<signalmasts>`` as ``<signalmast>`` (head, turnout, DCC ... masts, told
  apart by ``class`` or the system-name prefix) and ``<virtualsignalmast>``.
  ``root.iter("signalmast")`` misses the virtual ones; ``masts(root)`` returns both.
- Because comments are kept, ``for child in el`` and ``el.iter()`` with no tag can yield
  comment nodes whose ``tag`` is a function, not a string. Use ``elements(el)``.
- There are two Layout Editor panels, ``HART Railroad`` and ``Dispatcher System``.
  ``root.find("LayoutEditor")`` happens to return the main one today; use ``layout_editor``.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from . import paths

# Names the main Layout Editor panel has had; the first is the live one.
MAIN_PANEL_NAMES = ("HART Railroad", "HART", "My Layout")
DISPATCHER_PANEL_NAME = "Dispatcher System"

# jmri.Turnout constants, as Layout Editor stores continuingSense in ``continuing``.
UNKNOWN, CLOSED, THROWN = 1, 2, 4

MAST_TAGS = ("signalmast", "virtualsignalmast")

# Same pattern as .claude/hooks/main_guard.py: PanelPro, DecoderPro, DispatcherPro or CATS.
# One line, so tools/audit/tests/test_jmri_process_patterns.py can read it.
_JMRI_PROCESS = r"java .*(cats\.apps\.Crandic|apps\.PanelPro\.PanelPro|apps\.gui3\.dp3\.DecoderPro3|apps\.DecoderPro|apps\.DispatcherPro)"  # noqa: E501

_PROLOG_SKIP = re.compile(rb"\s+|<\?.*?\?>|<!--.*?-->|<!DOCTYPE[^\[>]*(\[.*?\])?\s*>", re.S)


# ---------------------------------------------------------------- load and save


@dataclass
class Tables:
    """A parsed tables file. ``root`` is an ordinary ElementTree element; edit it in place."""

    root: ET.Element
    path: Path | None = None
    prolog: bytes = b""
    epilog: bytes = b""
    original: bytes = field(default=b"", repr=False)
    escapes: str = "jdom"  # "jdom" or "elementtree": whose character escapes to write

    def tobytes(self) -> bytes:
        """The file as it would be saved now."""
        return self.prolog + _serialize(self.root, self.escapes) + self.epilog

    def changed(self) -> bool:
        return self.tobytes() != self.original

    def save(self, path: Path | str | None = None, *, allow_while_jmri_runs: bool = False) -> bool:
        """Write the file when its bytes differ from what is on disk. Returns True if written.

        Refuses to write a file named tables.xml outside the temp directory while PanelPro,
        DecoderPro, DispatcherPro or CATS is open (AGENTS.md), unless told otherwise.
        """
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("no path to save to")
        data = self.tobytes()
        try:
            if target.read_bytes() == data:
                return False
        except OSError:
            pass
        if not allow_while_jmri_runs and _guarded(target) and jmri_running():
            raise RuntimeError(f"{target}: PanelPro or CATS is open; close it before writing tables")
        _atomic_write(target, data)
        if target == self.path:
            self.original = data
        return True


def loads(data: bytes, path: Path | None = None) -> Tables:
    """Parse tables bytes, keeping everything outside the root element verbatim."""
    if isinstance(data, str):
        raise TypeError("loads takes bytes; read the file with read_bytes()")
    _check_encoding(data)
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    parser.feed(data)
    root = parser.close()
    start = _root_start(data)
    end = _root_end(data, root, start)
    escapes = "elementtree" if _ET_ESCAPES.search(data) and not _JDOM_ESCAPES.search(data) else "jdom"
    return Tables(root=root, path=path, prolog=data[:start], epilog=data[end:], original=data,
                  escapes=escapes)


def load(path: Path | str | None = None) -> Tables:
    """Load tables.xml (this checkout's by default) for editing; save with ``.save()``."""
    p = Path(path) if path is not None else paths.TABLES_XML
    return loads(p.read_bytes(), path=p)


def read(path: Path | str | None = None) -> ET.Element:
    """Root element of tables.xml for read-only scripts.

    Parsed the same way as load() (comments and processing instructions kept), but
    without keeping the original bytes or working out the escaping style, which only
    a save needs.
    """
    p = Path(path) if path is not None else paths.TABLES_XML
    data = p.read_bytes()
    _check_encoding(data)
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    parser.feed(data)
    return parser.close()


def jmri_running() -> bool:
    """True when PanelPro, DecoderPro, DispatcherPro or CATS runs for this user.

    ``HART_GUARD_JMRI_RUNNING=0`` or ``=1`` overrides the check, as for the repo hook.
    """
    forced = os.environ.get("HART_GUARD_JMRI_RUNNING")
    if forced in ("0", "1"):
        return forced == "1"
    try:
        done = subprocess.run(["pgrep", "-u", str(os.getuid()), "-f", _JMRI_PROCESS],
                              capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError, AttributeError):
        return False
    return done.returncode == 0


def _guarded(target: Path) -> bool:
    """A tables.xml (by its own name or a symlink's target) outside the temp directory."""
    real = Path(os.path.realpath(target))
    if "tables.xml" not in (target.name, real.name):
        return False
    tmp = Path(tempfile.gettempdir()).resolve()
    try:
        real.relative_to(tmp)
        return False
    except ValueError:
        return True


def _atomic_write(target: Path, data: bytes) -> None:
    """Replace the file the path names. A symlink stays a symlink (its target is written);
    a hard-linked file is rewritten in place so every link sees the new bytes."""
    target = Path(os.path.realpath(target))
    try:
        hard_linked = target.stat().st_nlink > 1
    except OSError:
        hard_linked = False
    if hard_linked:
        with open(target, "r+b") as handle:
            handle.write(data)
            handle.truncate()
        return
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        try:
            os.chmod(tmp, target.stat().st_mode & 0o7777)
        except OSError:
            os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# Character escapes, as JDOM (JMRI) and ElementTree write them.
_ET_ESCAPES = re.compile(rb"&#(?:13|10|09);")
_JDOM_ESCAPES = re.compile(rb"&#x[DA9];")
_SERIALIZE_LOCK = threading.Lock()


def _jdom_cdata(text: str) -> str:
    """JDOM2 Format.escapeText: & < > and CR (LF stays the line separator)."""
    try:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\r", "&#xD;"))
    except (TypeError, AttributeError):
        raise TypeError(f"cannot serialize {text!r} (type {type(text).__name__})") from None


def _jdom_attrib(text: str) -> str:
    """JDOM2 Format.escapeAttribute: & < > " and CR, tab, LF."""
    try:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;").replace("\r", "&#xD;").replace("\t", "&#x9;")
                .replace("\n", "&#xA;"))
    except (TypeError, AttributeError):
        raise TypeError(f"cannot serialize {text!r} (type {type(text).__name__})") from None


def _serialize(root: ET.Element, escapes: str) -> bytes:
    """``root`` without its tail, with JDOM's or ElementTree's character escapes.

    ElementTree's serializer looks its escape helpers up as module globals, so JDOM's are
    swapped in for the call (under a lock). tests/test_tables.py fails if that stops working.
    """
    tail, root.tail = root.tail, None
    try:
        if escapes == "elementtree":
            return ET.tostring(root, encoding="unicode").encode("utf-8")
        with _SERIALIZE_LOCK:
            saved = ET._escape_cdata, ET._escape_attrib
            ET._escape_cdata, ET._escape_attrib = _jdom_cdata, _jdom_attrib
            try:
                return ET.tostring(root, encoding="unicode").encode("utf-8")
            finally:
                ET._escape_cdata, ET._escape_attrib = saved
    finally:
        root.tail = tail


def _check_encoding(data: bytes) -> None:
    m = re.match(rb"<\?xml[^>]*encoding=['\"]([^'\"]+)['\"]", data)
    if m and m.group(1).decode("ascii", "replace").lower().replace("_", "-") not in ("utf-8", "utf8"):
        raise ValueError(f"tables files are UTF-8; this one declares {m.group(1)!r}")


def _root_start(data: bytes) -> int:
    pos = 0
    if data.startswith(b"\xef\xbb\xbf"):
        pos = 3
    while True:
        m = _PROLOG_SKIP.match(data, pos)
        if not m or m.end() == pos:
            return pos
        pos = m.end()


def _root_end(data: bytes, root: ET.Element, start: int) -> int:
    if not isinstance(root.tag, str) or "}" in root.tag:
        raise ValueError("tables root must be a plain element")
    close = b"</" + root.tag.encode("utf-8")
    idx = data.rfind(close)
    if idx >= start:
        gt = data.index(b">", idx)
        return gt + 1
    # Self-closing root: the start tag is the whole element.
    return data.index(b">", start) + 1


# ---------------------------------------------------------------- generic helpers


def elements(el: ET.Element) -> Iterator[ET.Element]:
    """Child elements of ``el``, skipping comments and processing instructions."""
    return (child for child in el if isinstance(child.tag, str))


def text(el: ET.Element | None, child: str) -> str:
    """Stripped text of ``el``'s ``child``; "" when either is missing."""
    if el is None:
        return ""
    return (el.findtext(child) or "").strip()


def system_name(el: ET.Element) -> str:
    """A bean's system name: the ``<systemName>`` child, else the ``systemName`` attribute."""
    return text(el, "systemName") or (el.get("systemName") or "").strip()


def user_name(el: ET.Element) -> str:
    return text(el, "userName")


def by_system_name(beans: Iterable[ET.Element]) -> dict[str, ET.Element]:
    """Map system name -> bean. Later duplicates win, as JMRI's managers do on load."""
    return {sn: el for el in beans if (sn := system_name(el))}


def by_user_name(beans: Iterable[ET.Element]) -> dict[str, ET.Element]:
    """Map user name -> bean, for beans that have one."""
    return {un: el for el in beans if (un := user_name(el))}


def by_any_name(beans: Iterable[ET.Element]) -> dict[str, ET.Element]:
    """Map both system and user names -> bean, as JMRI resolves a name typed in a table."""
    out: dict[str, ET.Element] = {}
    for el in beans:
        for name in (system_name(el), user_name(el)):
            if name:
                out.setdefault(name, el)
    return out


def section(root: ET.Element, container: str, tag: str) -> list[ET.Element]:
    """Every ``<tag>`` directly under every top-level ``<container>`` (all connections)."""
    return [el for box in root.findall(container) for el in box.findall(tag)]


# ---------------------------------------------------------------- beans


def turnouts(root: ET.Element) -> list[ET.Element]:
    """Every table turnout, across the MQTT, internal and LCC managers."""
    return section(root, "turnouts", "turnout")


def sensors(root: ET.Element) -> list[ET.Element]:
    """Every table sensor, across the MQTT and internal managers."""
    return section(root, "sensors", "sensor")


def signal_heads(root: ET.Element) -> list[ET.Element]:
    return section(root, "signalheads", "signalhead")


def masts(root: ET.Element, tags: Iterable[str] = MAST_TAGS) -> list[ET.Element]:
    """Signal masts in file order, ``<signalmast>`` and ``<virtualsignalmast>`` by default."""
    want = tuple(tags)
    return [el for box in root.findall("signalmasts") for el in elements(box) if el.tag in want]


def blocks(root: ET.Element, *, full: bool = True) -> list[ET.Element]:
    """``<block>`` beans. ``full=True``: the full pass (one per block, with length, sensor
    and paths); ``full=False``: the names-only first pass JMRI writes before it."""
    out = []
    for el in section(root, "blocks", "block"):
        names_only = {child.tag for child in elements(el)} <= {"systemName", "userName"}
        if names_only != full:
            out.append(el)
    return out


def layout_blocks(root: ET.Element) -> list[ET.Element]:
    return section(root, "layoutblocks", "layoutblock")


# ---------------------------------------------------------------- Layout Editor


def layout_editors(root: ET.Element) -> list[ET.Element]:
    return root.findall("LayoutEditor")


def layout_editor(root: ET.Element, name: str | Iterable[str] | None = None) -> ET.Element | None:
    """The Layout Editor panel named ``name`` (default: the main panel, ``MAIN_PANEL_NAMES``)."""
    names = MAIN_PANEL_NAMES if name is None else ((name,) if isinstance(name, str) else tuple(name))
    for panel in layout_editors(root):
        if (panel.get("name") or "").strip() in names:
            return panel
    return None


def layout_turnouts(panel: ET.Element) -> list[ET.Element]:
    """``<layoutturnout>`` elements (turnouts and crossovers) on one panel."""
    return panel.findall("layoutturnout")


def continuing_sense(layout_turnout: ET.Element) -> int:
    """CLOSED (2), THROWN (4) or UNKNOWN (1): which table state is the straight-through leg.

    Missing means CLOSED, JMRI's default. UNKNOWN draws both legs and ignores the turnout.
    """
    raw = (layout_turnout.get("continuing") or "").strip()
    try:
        return int(raw) if raw else CLOSED
    except ValueError:
        return UNKNOWN


# ---------------------------------------------------------------- signal mast logic


def mast_logics(root: ET.Element) -> list[ET.Element]:
    """``<signalmastlogic>`` elements, one per source mast."""
    return section(root, "signalmastlogics", "signalmastlogic")


def mast_logic_sources(root: ET.Element) -> dict[str, ET.Element]:
    """Source mast name -> its ``<signalmastlogic>``."""
    return {
        src: logic
        for logic in mast_logics(root)
        if (src := text(logic, "sourceSignalMast") or (logic.get("source") or "").strip())
    }


def mast_logic_pairs(root: ET.Element) -> list[tuple[str, str, ET.Element]]:
    """(source mast, destination mast, ``<destinationMast>``) for every SML pair, in file order."""
    out = []
    for logic in mast_logics(root):
        src = text(logic, "sourceSignalMast") or (logic.get("source") or "").strip()
        for dest in logic.findall("destinationMast"):
            dst = text(dest, "destinationSignalMast") or (dest.get("destination") or "").strip()
            out.append((src, dst, dest))
    return out
