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

plan_overrides.json holds the owner's hand edits only. What build_staging_sets.py, build_main_route.py and
build_device_map.py write goes to plan_generated.json (same sections; GENERATED below; T6b). `read` and `read_file`
of "plan_overrides" give the hand file. `merged` / `merged_section` give the view every output is drawn from: the
hand keys, then the generated keys the hand section lacks (a hand value wins), with the generated `name_main` flags
put back on the staging `name` edit. `view` writes that merged view as a folder the schematic plugin reads with
`--data`. A generated write goes through `generated_texts` / `write_generated`, which replace only the keys given
and never touch the hand file.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import paths

SCHEMATIC = paths.LAYOUT_DATA / "schematic"
KINDS = ("plan_overrides", "preferences", "signals")
GENERATED = "plan_generated"  # the generated half of plan_overrides: same sections, written by three builders
NAME_MAIN = "name_main"       # staging's generated key: the indexes of the `name` edit's tracks flagged "main"
SECTIONS = "_sections"        # the key a combined file holds, true (the plugin's layers.SECTIONS)


class LayerFileError(ValueError):
    """A layer file or section cannot be read or written as asked; the message names the file and section."""


def path(kind: str, data: Path = SCHEMATIC) -> Path:
    """The one file of `kind`: <data>/<kind>.json."""
    if kind not in KINDS and kind != GENERATED:
        raise LayerFileError(f"layer kind {kind!r}: the layer files are {', '.join((*KINDS, GENERATED))}")
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
    stale = sorted(f.name for f in Path(data).glob(f"*.{kind}.json") if f.name != "sheet.preferences.json")
    if (Path(data) / "sheet.preferences.json").exists() and kind == "preferences":
        raise LayerFileError(f"sheet.preferences.json beside {p.name}: the page's preferences are the main_upper "
                             f"section of {p.name}; move its keys there and delete it")
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
        if kind == GENERATED:
            raise LayerFileError(f"{path(kind, data).name} is written key by key: use generated_texts")
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


PLAN_GENERATED_FILE = f"{GENERATED}.json"


def merge(hand: dict, generated: dict) -> dict:
    """The whole plan_overrides view from the hand file's and the generated file's contents: per section the hand
    keys, then the generated keys the hand section lacks. The generated `name_main` is not a key of the view: it flags
    those tracks of the staging `name` edit "main" (last in the entry), as the one file used to hold them."""
    out = dict(hand)
    for k, g in generated.items():
        if k.startswith("_"):
            out.setdefault(k, g)
            continue
        sec = out[k] = dict(out.get(k, {}))
        for key, val in g.items():
            if key != NAME_MAIN:
                sec.setdefault(key, val)
        if NAME_MAIN in g:
            sec["edits"] = edits = json.loads(json.dumps(sec.get("edits", [])))
            named = [e for e in edits if isinstance(e, dict) and e.get("op") == "name"]
            if len(named) != 1:
                raise LayerFileError(f"{PLAN_GENERATED_FILE}[{k}]: {NAME_MAIN} needs one `name` edit in "
                                     f"{PLAN_OVERRIDES_FILE}[{k}], found {len(named)}")
            tracks = named[0]["tracks"]
            for i, t in enumerate(tracks):       # the generated flags are the only ones: a hand "main" is dropped
                tracks[i] = [*t[:3], *[x for x in t[3:] if x != "main"]]
            for i in g[NAME_MAIN]:
                if i >= len(tracks):
                    raise LayerFileError(f"{PLAN_GENERATED_FILE}[{k}] {NAME_MAIN}: track {i} is past the "
                                         f"{len(tracks)} the `name` edit has; run build_main_route.py")
                tracks[i] = [*[x for x in tracks[i] if x != "main"], "main"]
    return out


PLAN_OVERRIDES_FILE = "plan_overrides.json"


def merged(data: Path = SCHEMATIC) -> dict:
    """The whole plan_overrides view (the generated file under the hand file). A folder with no plan_generated.json
    (a test's copy of the data) has nothing generated."""
    hand = read_file("plan_overrides", data)
    if not path(GENERATED, data).exists():
        return hand
    return merge(hand, read_file(GENERATED, data))


def merged_section(sheet: str, data: Path = SCHEMATIC) -> dict:
    """One sheet's section of `merged`: what every output is drawn from."""
    return section_of(merged(data), sheet, f"{PLAN_OVERRIDES_FILE}+{PLAN_GENERATED_FILE}")


def generated_texts(updates: Mapping[str, dict], data: Path = SCHEMATIC) -> dict[Path, str]:
    """{plan_generated.json: its whole text} with each sheet's given keys replaced (a new key goes last); the keys
    a builder does not own stay as they are. `updates`: {sheet: {key: value}}. The hand file is never touched."""
    p = path(GENERATED, data)
    whole = read_file(GENERATED, data)
    for sheet, keys in updates.items():
        sec = dict(section_of(whole, sheet, str(p)))
        sec.update(keys)
        whole[sheet] = sec
    return {p: dumps(whole)}


def write_generated(updates: Mapping[str, dict], data: Path = SCHEMATIC) -> list[Path]:
    """Write generated_texts(updates); returns the file when its text changed."""
    changed = []
    for p, text in generated_texts(updates, data).items():
        if p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")
            changed.append(p)
    return changed


def view(data: Path = SCHEMATIC) -> Path:
    """A folder the schematic plugin reads as its `--data`: `data` itself when nothing is generated there, else a
    stable folder under paths.cache_dir("plan-merged") holding the merged plan_overrides.json and links to the rest
    of `data`. A file is rewritten only when its bytes change, so every mtime and path stays put (the plugin's cache
    keys on content and relative paths)."""
    data = Path(data).resolve()
    if not path(GENERATED, data).exists():
        return data
    text = dumps(merged(data))
    root = paths.cache_dir("plan-merged") / hashlib.sha256(str(data).encode()).hexdigest()[:12]
    root.mkdir(parents=True, exist_ok=True)
    keep = {PLAN_OVERRIDES_FILE}
    for entry in data.iterdir():
        if entry.name in (PLAN_OVERRIDES_FILE, PLAN_GENERATED_FILE):
            continue
        keep.add(entry.name)
        link = root / entry.name
        if link.is_symlink() and Path(os.readlink(link)) == entry:
            continue
        tmp_link = root / f".{entry.name}.{os.getpid()}.link"      # swapped in whole: another process may be reading
        tmp_link.unlink(missing_ok=True)
        tmp_link.symlink_to(entry)
        os.replace(tmp_link, link)
    target = root / PLAN_OVERRIDES_FILE
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        tmp = root / f".plan_overrides.{os.getpid()}.tmp"            # one name per process, replaced whole
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
    for stale in root.iterdir():
        if stale.name not in keep and not stale.name.startswith("."):
            stale.unlink()
    return root


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
