"""The schematic's layer files: one file per kind, a section per sheet.

jmri/layouts/hart/data/schematic/ holds plan_overrides.json, preferences.json and signals.json (level-unification
step 3). Each is a JSON object with "_sections": true, a "_note", and one section per sheet, keyed by the sheet's
input name (`staging`, `main_upper`: publish_draft.INPUTS); a section holds what the old <sheet>.<kind>.json held.
The schematic-maps plugin (0.1.49 and later) reads the same files by itself; every hart script that reads or writes a
section goes through this module, so the JSON formatting and the checks are in one place.

    layer_files.read("plan_overrides", "staging")                  the staging section (LayerFileError if missing)
    layer_files.Section("preferences", "main_upper").read()        the same, as a value a caller can pass around
    layer_files.texts({("plan_overrides", "staging"): {...}})      {file: the whole text with those sections replaced}

Checks, each a LayerFileError naming the file: the file is a readable JSON object with "_sections": true; every key
not starting with "_" holds an object; no old per-sheet file <sheet>.<kind>.json lies beside it (the plugin would
stop on it too, and a reader here would not see it); a section asked for exists (no section is created by a write:
a new sheet is added by hand, with its note).
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import paths

SCHEMATIC = paths.LAYOUT_DATA / "schematic"
KINDS = ("plan_overrides", "preferences", "signals")
SECTIONS = "_sections"        # the key a combined file holds, true (the plugin's layers.SECTIONS)


class LayerFileError(ValueError):
    """A layer file or section cannot be read or written as asked; the message names the file and section."""


def path(kind: str, data: Path = SCHEMATIC) -> Path:
    """The one file of `kind`: <data>/<kind>.json."""
    if kind not in KINDS:
        raise LayerFileError(f"layer kind {kind!r}: the layer files are {', '.join(KINDS)}")
    return Path(data) / f"{kind}.json"


def dumps(whole: dict) -> str:
    """The text of a layer file: one-space indent, UTF-8 as written, a final newline."""
    return json.dumps(whole, indent=1, ensure_ascii=False) + "\n"


def parse(text: str, kind: str, where: str) -> dict:
    """The whole file from its text, checked. `where` names it in errors (a path, or path@commit)."""
    try:
        whole = json.loads(text)
    except ValueError as exc:
        raise LayerFileError(f"{where}: not JSON ({exc})") from None
    if not isinstance(whole, dict) or whole.get(SECTIONS) is not True:
        raise LayerFileError(f'{where}: not a layer file of sections (it needs "{SECTIONS}": true)')
    bad = sorted(k for k, v in whole.items() if not k.startswith("_") and not isinstance(v, dict))
    if bad:
        raise LayerFileError(f"{where}: section(s) {', '.join(bad)} are not objects")
    return whole


def read_file(kind: str, data: Path = SCHEMATIC) -> dict:
    """The whole file of `kind`, notes included, checked; the old per-sheet files must be gone."""
    p = path(kind, data)
    stale = sorted(f.name for f in Path(data).glob(f"*.{kind}.json"))
    if stale:
        raise LayerFileError(f"{', '.join(stale)} beside {p.name}: move each into its section of {p.name} and "
                             "delete it (the plugin stops on an input with both)")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise LayerFileError(f"{p}: cannot be read ({exc.strerror or exc})") from None
    return parse(text, kind, str(p))


def sheets(kind: str, data: Path = SCHEMATIC) -> list[str]:
    """The section names of the file of `kind`, in file order."""
    return [k for k in read_file(kind, data) if not k.startswith("_")]


def section_of(whole: dict, sheet: str, where: str) -> dict:
    if not isinstance(sheet, str) or not sheet or sheet.startswith("_"):
        raise LayerFileError(f"{where}: {sheet!r} is no sheet name (a name starting with _ is a note)")
    if sheet not in whole:
        have = [k for k in whole if not k.startswith("_")]
        raise LayerFileError(f"{where}: no section {sheet!r} (it has {', '.join(have) or 'none'})")
    return whole[sheet]


def read(kind: str, sheet: str, data: Path = SCHEMATIC) -> dict:
    """The section `sheet` of the file of `kind`. LayerFileError if the file or the section is missing."""
    return section_of(read_file(kind, data), sheet, str(path(kind, data)))


def texts(updates: Mapping[tuple[str, str], dict], data: Path = SCHEMATIC) -> dict[Path, str]:
    """{file: its whole text with the given sections replaced} for every file `updates` touches; other sections and
    the notes are kept as they are. `updates`: {(kind, sheet): new section}. Each section must exist already."""
    by_kind: dict[str, dict[str, dict]] = {}
    for (kind, sheet), section in updates.items():
        if not isinstance(section, dict):
            raise LayerFileError(f"{path(kind, data).name} section {sheet!r}: must be an object, "
                                 f"not {type(section).__name__}")
        by_kind.setdefault(kind, {})[sheet] = section
    out = {}
    for kind, new in by_kind.items():
        p = path(kind, data)
        whole = read_file(kind, data)
        for sheet, section in new.items():
            section_of(whole, sheet, str(p))
            whole[sheet] = section
        out[p] = dumps(whole)
    return out


def write(updates: Mapping[tuple[str, str], dict], data: Path = SCHEMATIC) -> list[Path]:
    """Write texts(updates); returns the files whose text changed (the others are left untouched)."""
    changed = []
    for p, text in texts(updates, data).items():
        if p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")
            changed.append(p)
    return changed


@dataclass(frozen=True)
class Section:
    """One sheet's section of one layer file, as a value a caller can hand on (the page's preferences, say)."""
    kind: str
    sheet: str
    data: Path = SCHEMATIC

    @property
    def path(self) -> Path:
        return path(self.kind, self.data)

    @property
    def name(self) -> str:
        """How messages name it: preferences.json[main_upper]."""
        return f"{self.path.name}[{self.sheet}]"

    def read(self) -> dict:
        return read(self.kind, self.sheet, self.data)

    def of(self, text: str, where: str | None = None) -> dict:
        """This section out of a whole file's text (the file at another commit, say)."""
        return section_of(parse(text, self.kind, where or str(self.path)), self.sheet, where or str(self.path))

    def text_with(self, section: dict) -> str:
        """The whole file's text with this section replaced."""
        return texts({(self.kind, self.sheet): section}, self.data)[self.path]

    def write(self, section: dict) -> bool:
        """Replace this section in its file; True if the file changed."""
        return bool(write({(self.kind, self.sheet): section}, self.data))
