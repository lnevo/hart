"""Edits to a JMRI profile's own files: profile.xml's Start Up list and user-interface.xml's saved panel windows.

Start Up (profile.xml): insert or remove a PerformScript entry, point script entries at preference:jython/, point
the tables load at a path. Each edit keeps the attribute order of the neighbouring entry, rewrites nothing else, and
replaces the file through a temporary file in its folder.

Panel windows (user-interface.xml): JMRI keeps every window's size, position and zoom in <windowDetails>, one
<window class="jmri.jmrit.display.layoutEditor.LayoutEditor:<panel>"> per panel, saved whenever a window moves, and
uses it over the panel's windowwidth / windowheight in tables.xml whenever it opens the panel. A size set in
tables.xml (the band panels' heights, band_panels.py) therefore reaches a host only through this file. resize() sets
each saved panel window's width and height to the tables'; position and zoom stay as they were. Every Layout Editor
panel in the tables is read, so a new panel needs no change here. A panel with no saved window is left out (JMRI
opens it at the tables' size anyway). Only the width and height attributes are edited, so the rest of the file stays
as JMRI wrote it. JMRI rewrites the file when a window moves and when it quits: edit it with JMRI closed.

The deploy ships this module to the hosts with errors.py, files.py and __init__.py only (HARTLIB_HOST_MODULES in
tools/hosts/deploy/common.sh), where there is no checkout for hartlib.paths to find, so it imports nothing else from
hartlib (files.py imports only errors.py) and reads tables.xml with ElementTree directly. The command lines are
cats/scripts/patch_jmri_startup.py and tools/hosts/panel_window_sizes.py.
"""
from __future__ import annotations

import html
import math
import re
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

from .errors import HartlibError
from .files import write_atomic

PANEL_WINDOW_PREFIX = "jmri.jmrit.display.layoutEditor.LayoutEditor:"
_WINDOW = re.compile(r'<window\b[^>]*\bclass="' + re.escape(PANEL_WINDOW_PREFIX) + r'(?P<name>[^"]*)"[^>]*>')
BACKUP_STAMP = "%Y%m%d-%H%M%S"
BACKUPS_KEPT = 5    # write_user_interface keeps this many <name>.hart-<stamp>.bak copies beside the file


class StartupPatchError(HartlibError, ValueError):
    """profile.xml does not hold the Start Up entry the edit needs, or holds it in a form the edit cannot change."""


class WindowSizesError(HartlibError, ValueError):
    """tables.xml or user-interface.xml cannot be read, or holds no panel sizes to set."""


class WindowChange(NamedTuple):
    """One saved panel window whose size changed; sizes as "WxH", as the file writes them."""
    panel: str
    before: str
    after: str


# ---- Start Up (profile.xml) ----

def _perform_for(sample: str, script_path: str) -> str:
    if "xmlns=" in sample:
        return (
            '        <perform xmlns="" class="jmri.util.startup.configurexml.PerformScriptModelXml" '
            f'enabled="yes" name="{script_path}" type="ScriptFile"/>'
        )
    return (
        f'        <perform name="{script_path}" type="ScriptFile" enabled="yes" '
        'class="jmri.util.startup.configurexml.PerformScriptModelXml"/>'
    )


def _script_basename(path: str) -> str:
    return Path(path).name


# A Start Up entry with the whitespace before it, so removing one leaves no blank line.
_PERFORM = re.compile(r"\n?[ \t]*<perform\b[^>]*/>")
_NAME = re.compile(r'\bname="([^"]*)"')


def _names(tag: str, name: str) -> bool:
    """True when the name= of the <perform> `tag` is `name`, or its part after the last /, \\ or : is `name`
    (preference:jython/x.py and C:\\jython\\x.py name x.py; old_x.py does not)."""
    found = _NAME.search(tag)
    return found is not None and name in (found.group(1), re.split(r"[/\\:]", found.group(1))[-1])


def _runs(tag: str, basename: str) -> bool:
    """True when the <perform> `tag` is a PerformScript entry whose name= runs the file `basename` (_names)."""
    return "PerformScriptModelXml" in tag and _names(tag, basename)


def _script_entries(txt: str, basename: str) -> list[str]:
    """The Start Up entries in `txt` that run the file `basename` (a mention elsewhere in the file is not one)."""
    return [m.group(0) for m in _PERFORM.finditer(txt) if _runs(m.group(0), basename)]


def _write_profile(profile: Path, text: str) -> None:
    """Replace profile.xml through a temporary file in its folder (hartlib.files.write_atomic), so JMRI or a stopped
    deploy never finds half a Start Up list."""
    try:
        write_atomic(profile, text)
    except OSError as exc:
        raise StartupPatchError(f"cannot write {profile}: {exc}") from exc


def insert_after(profile: Path, script_path: str, after: str) -> str:
    """Add a Start Up entry running `script_path` on the line after the one Start Up entry whose name= is `after`
    (the whole name, or the file name after its last /, \\ or :): "inserted", or "already" when a Start Up entry
    runs the script. No such entry, or more than one, is a StartupPatchError."""
    if not after:
        raise StartupPatchError(f"{profile}: no Start Up entry given to insert {script_path} after")
    txt = profile.read_text(encoding="utf-8")
    needle = _script_basename(script_path)
    if _script_entries(txt, needle):
        return "already"
    anchors = [m for m in _PERFORM.finditer(txt) if _names(m.group(0), after)]
    if not anchors:
        raise StartupPatchError(f"{profile}: no Start Up entry named {after!r} to insert {needle} after")
    if len(anchors) > 1:
        raise StartupPatchError(f"{profile}: {len(anchors)} Start Up entries named {after!r}; cannot tell which one "
                                f"to insert {needle} after")
    end = anchors[0].end()
    new = txt[:end] + "\n" + _perform_for(anchors[0].group(0), script_path) + txt[end:]
    if len(_script_entries(new, needle)) != 1:
        raise StartupPatchError(f"{profile}: the entry for {needle} after {after!r} is not one Start Up entry")
    _write_profile(profile, new)
    return "inserted"


def remove_script(profile: Path, script_path: str) -> str:
    """Remove every Start Up entry running `script_path`: "removed", or "absent" when no entry runs it."""
    txt = profile.read_text(encoding="utf-8")
    needle = _script_basename(script_path)
    if not _script_entries(txt, needle):
        return "absent"
    new = _PERFORM.sub(lambda m: "" if _runs(m.group(0), needle) else m.group(0), txt)
    if _script_entries(new, needle):
        raise StartupPatchError(f"{profile}: could not remove {needle}")
    _write_profile(profile, new)
    return "removed"


def retarget_to_preference_jython(profile: Path, scripts: list[str]) -> list[str]:
    """Rewrite PerformScript name= to preference:jython/<basename>.

    Leaves ScriptButton / XmlFile / Action tags alone. Idempotent when the
    name is already preference:jython/.
    Also renames known retired basenames (e.g. sync_yard_ladder_buttons →
    panel_status) before retargeting.
    """
    txt = profile.read_text(encoding="utf-8")
    orig = txt
    notes: list[str] = []
    wanted = {_script_basename(s) for s in scripts}

    # Retired → current startup script basenames (must run after package rename).
    renames = {
        "sync_yard_ladder_buttons.py": "panel_status.py",
        "sync_turnout_buttons.py": "panel_status.py",
        "sync_layout_button.py": "panel_status.py",
        "mqtt_signalhead_publisher.py": "signal_coordinator.py",
    }
    for old, new in renames.items():
        if old in txt and new in wanted:
            txt2, n = re.subn(
                rf'(name="[^"]*){re.escape(old)}(")',
                rf"\1{new}\2",
                txt,
            )
            if n:
                notes.append(f"{old} -> {new} ({n} Start Up entr{'y' if n == 1 else 'ies'})")
                txt = txt2

    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        if "PerformScriptModelXml" not in tag:
            return tag
        name_m = re.search(r'\bname="([^"]*)"', tag)
        if name_m is None:
            return tag
        old = name_m.group(1)
        base = _script_basename(old)
        if base not in wanted:
            return tag
        target = f"preference:jython/{base}"
        if old == target:
            return tag
        notes.append(f"{old} -> {target}")
        return tag[: name_m.start()] + f'name="{target}"' + tag[name_m.end() :]

    txt = re.sub(r"<perform\b[^>]*/>", repl, txt)
    if txt != orig:
        _write_profile(profile, txt)
    return notes


def load_tables_from(profile: Path, path: str) -> str:
    """Point the Start Up tables load at path (for example preference:tables.xml)."""
    text = profile.read_text(encoding="utf-8")
    new, count = re.subn(
        r'(<perform\b[^>]*PerformFileModelXml[^>]*\bname=")[^"]*tables\.xml(")',
        lambda m: m.group(1) + path + m.group(2),
        text,
    )
    if count != 1:
        raise StartupPatchError(f"expected one tables load in {profile}, found {count}")
    if new == text:
        return "already"
    _write_profile(profile, new)
    return "changed"


# ---- Panel windows (user-interface.xml) ----

def panel_sizes(tables_path: Path) -> dict[str, tuple[str, str]]:
    """{panel name: (windowwidth, windowheight)} of every Layout Editor panel in the tables at `tables_path`."""
    try:
        root = ET.parse(tables_path).getroot()
    except (OSError, ET.ParseError, ValueError) as exc:
        raise WindowSizesError(f"cannot read {tables_path}: {exc}") from exc
    out = {}
    for panel in root.findall("LayoutEditor"):
        name = (panel.get("name") or "").strip()
        width, height = panel.get("windowwidth"), panel.get("windowheight")
        if not name or not width or not height:
            raise WindowSizesError(f"{tables_path}: Layout Editor panel {name or '(no name)'} has no window size")
        for attr, value in (("windowwidth", width), ("windowheight", height)):
            if not _is_size(value):
                raise WindowSizesError(f"{tables_path}: Layout Editor panel {name} has {attr}={value!r}, not a size")
        out[name] = (width, height)
    if not out:
        raise WindowSizesError(f"{tables_path}: no Layout Editor panel")
    return out


def _is_size(value: str) -> bool:
    """True when `value` is a positive finite number, as a window size must be."""
    try:
        number = float(value)
    except ValueError:
        return False
    return math.isfinite(number) and number > 0


def read_user_interface(path: Path) -> str:
    """The text of the user-interface.xml at `path`; WindowSizesError when it cannot be read or holds no
    <windowDetails>."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WindowSizesError(f"cannot read {path}: {exc}") from exc
    if "<windowDetails" not in text:
        raise WindowSizesError(f"{path}: no <windowDetails>; is it a JMRI user-interface.xml?")
    return text


def _set_attr(tag: str, name: str, value: str) -> str:
    """`tag` with attribute `name` set to `value` (as JMRI writes it, a float: 652 -> "652.0")."""
    value = f"{float(value):.1f}"
    pattern = re.compile(r'\b' + name + r'="[^"]*"')
    if pattern.search(tag):
        return pattern.sub(f'{name}="{value}"', tag, count=1)
    return tag[:-1].rstrip("/").rstrip() + f' {name}="{value}"' + ("/>" if tag.endswith("/>") else ">")


def _get_attr(tag: str, name: str) -> str:
    m = re.search(r'\b' + name + r'="([^"]*)"', tag)
    return m.group(1) if m else "?"


def resize(text: str, sizes: dict[str, tuple[str, str]]) -> tuple[str, list[WindowChange]]:
    """(the user-interface.xml text with each saved panel window at its tables size, the windows that changed)."""
    changes: list[WindowChange] = []

    def one(m: re.Match[str]) -> str:
        name = html.unescape(m.group("name"))     # the attribute as written: P&amp;CV is P&CV
        if name not in sizes:
            return m.group(0)
        tag = m.group(0)
        width, height = sizes[name]
        before = f"{_get_attr(tag, 'width')}x{_get_attr(tag, 'height')}"
        new = _set_attr(_set_attr(tag, "width", width), "height", height)
        after = f"{_get_attr(new, 'width')}x{_get_attr(new, 'height')}"
        if new != tag:
            changes.append(WindowChange(name, before, after))
        return new

    return _WINDOW.sub(one, text), changes


def saved_windows(text: str) -> list[str]:
    """The panel names user-interface.xml holds a window for."""
    return [html.unescape(m.group("name")) for m in _WINDOW.finditer(text)]


def _backup_name(path: Path) -> re.Pattern[str]:
    """<path>.hart-<stamp>.bak, or <path>.hart-<stamp>-<n>.bak for the n-th more copy made in the same second."""
    return re.compile(re.escape(path.name) + r"\.hart-(?P<stamp>\d{8}-\d{6})(?:-(?P<n>[1-9]\d*))?\.bak")


def backups(path: Path) -> list[Path]:
    """The backup copies beside `path` (_backup_name), oldest first: by stamp, then by n."""
    pattern = _backup_name(path)
    found = []
    for p in path.parent.iterdir():
        m = pattern.fullmatch(p.name)
        if m:
            found.append(((m.group("stamp"), int(m.group("n") or 0)), p))
    return [p for _, p in sorted(found)]


def _back_up(path: Path) -> Path:
    """Copy `path` to a new backup beside it and return the copy. The copy is created exclusively, so a second
    backup in the same second gets the next -<n> name instead of replacing the first."""
    stamp = time.strftime(BACKUP_STAMP)
    n = 0
    while True:
        copy = path.with_name(f"{path.name}.hart-{stamp}{f'-{n}' if n else ''}.bak")
        made = False
        try:
            with path.open("rb") as src, copy.open("xb") as dst:
                made = True
                shutil.copyfileobj(src, dst)
            shutil.copystat(path, copy)
        except FileExistsError:
            n += 1
            continue
        except OSError as exc:
            # a half-written copy would count as one of the newest backups and push out a good one
            if made:
                copy.unlink(missing_ok=True)
            raise WindowSizesError(f"cannot back up {path} to {copy}: {exc}") from exc
        return copy


def write_user_interface(path: Path, text: str, *, backup: bool = False) -> Path | None:
    """Write `text` to `path` through a temporary file (hartlib.files.write_atomic), so JMRI never reads half a file.
    With `backup`, first copy the file there to a new <path>.hart-<stamp>.bak beside it (_back_up), keep the newest
    BACKUPS_KEPT of those copies, and return the new copy's path; None without."""
    copy = None
    if backup:
        copy = _back_up(path)
        try:
            for old in backups(path)[:-BACKUPS_KEPT]:
                old.unlink()
        except OSError as exc:
            raise WindowSizesError(f"cannot remove old backups of {path} (kept {copy}): {exc}") from exc
    try:
        write_atomic(path, text)
    except OSError as exc:
        raise WindowSizesError(f"cannot write {path}: {exc}") from exc
    return copy
