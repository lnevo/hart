"""The physical wiring source: jmri/layouts/hart/data/wiring.csv, one row per device on an LCOS node (owner,
2026-11-20: the repo keeps the wiring the inventory workbook holds, edited here).

Staging's rows are what JMRI holds, as wired (status `wired`), and the ports assigned to devices not connected yet
(status `planned`: a button or relay on its port with nothing connected, a reserved calibration relay port). Main
and upper are still being designed: their devices are given nodes and ports by build_device_map.py's rule, except
the rows here, which the rule then leaves alone (status `planned` for a device the owner placed, `wired` once a
control point is wired and frozen).

Columns (COLUMNS):
- level 1, 2 or 3; kind: turnout, fb (turnout feedback), head (signal head), detector (block occupancy), button (a
  fascia button on an input), relay (on an output) or calibration (the relay on an output that resets the DCC power
  so the node's block detectors calibrate; every node with detectors has one reserved, owner 2026-11-21). Buttons
  and relays are wired on the nodes but have no JMRI device (owner, 2026-11-20: live today, more to come); their
  index is blank. A calibration row's status is wired where the relay is in, planned where the port is reserved.
- id: the device's ID in the device master (hartlib.device_ids; naming-layers step 5): switch:<n>, fb:<n>:N|R, a
  head's <mast id>:top|bottom|single, a detector's det:<block id> (det:block:17C-29C, det:os:19). The row holds no
  name: `read` gives each Wire the device's user name from the name store (hartlib.devices.user_names; a detector's
  is its block's), so a rename in devices_field.csv changes no row here and the frozen pins stay as they are. A main
  or upper detector on a track is named by switch_a, switch_b, parallel and half instead (mast_rule.track_key: lower
  number first), a key from the plan as well. A staging detector with neither is a spare input.
- device: a button's, relay's or calibration relay's label (Switch 1 BTN, C4 calibration relay): they have no JMRI
  device, so no ID. Empty on every other row.
- node: the LCOS radio address. index: the LCOS number in the device's wiring text, "Turnout: <i>", "Sensor: <i>",
  "Signal: <i>" from 0, "Block: <i>" from 1 (1 to 8). board (OU<n> or IN<n>) and ports: where a turnout, feedback or
  head lands; a detector has neither (its input is the index). A head is on one node, but its three pins may span
  two OU boards (owner, 2026-11-21): a port that is on another board than `board` names it, "OU<n>-<pin>"
  (board OU2, ports "7,OU3-8,OU3-7"). Every other device is on one board.
- status: wired or planned. notes: text for people. (Power districts are not mapped yet; the owner,
  2026-11-21: the inventory's were old names, not real.)

The JMRI address follows from node and index (address), and the wiring text from all four (wiring_text): the device master
holds both only as written from here.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import NamedTuple

from . import paths
from .device_ids import HEAD_PLACES
from .railroad_facts import STAGING_LEVEL, FactsError

PATH = paths.WIRING
NODES = paths.LAYOUT_DATA / "schematic" / "lcos_nodes.csv"   # each node's level and area (board_location)
COLUMNS = ["level", "kind", "id", "device", "switch_a", "switch_b", "parallel", "half", "node", "index", "board", "ports",
           "status", "notes"]
KINDS = ("turnout", "fb", "head", "detector", "button", "relay", "calibration")
LOCAL = ("button", "relay", "calibration")      # on a node, no JMRI device: no index, no address
STATUSES = ("wired", "planned")
# kind -> (system name prefix, LCOS UID offset, the word in the wiring text, the board it lands on, ports per device)
LCOS = {"turnout": ("M2T", 8, "Turnout", "OU", 2), "fb": ("M2S", 67, "Sensor", "IN", 1),
        "head": ("IH", 32, "Signal", "OU", 3), "detector": ("M2S", 0, "Block", "", 0),
        "button": ("", 0, "", "IN", 1), "relay": ("", 0, "", "OU", 1), "calibration": ("", 0, "", "OU", 1)}
CAP = {"turnout": 8, "fb": 16, "head": 16, "detector": 8}     # LCOS numbers per node (a detector's from 1)
BOARD = re.compile(r"^(OU|IN)([1-4])$")
OWN_BOARD = re.compile(r"(OU[1-4])-([1-8])")       # a head's pin on another board than its row's: "OU3-8"


class Wire(NamedTuple):
    line: int
    level: int
    kind: str
    device: str                           # the user name (the name store's for a row with an id), a detector's block's
    switch_a: str
    switch_b: str
    parallel: str
    half: str
    node: int
    index: int | None
    board: str
    ports: tuple[int, ...]
    status: str
    notes: str
    boards: tuple[str, ...] = ()          # each port's board (a head's may span two OU boards); `board` if empty
    id: str = ""                          # the device's ID (a detector's det:<block id>); empty on a local or spare row
    mast: str = ""                        # a head's mast's user name (the name store's of its id less the place)

    @property
    def place(self) -> str:
        """A head's place on its mast, from its id (mast:...:top|bottom|single); "" for any other row."""
        tail = self.id.rsplit(":", 1)[-1] if self.kind == "head" else ""
        return tail if tail in HEAD_PLACES else ""

    @property
    def pins(self) -> list[tuple[str, int]]:
        """[(board, port)] in port order."""
        return list(zip(self.boards or (self.board,) * len(self.ports), self.ports))

    @property
    def port_text(self) -> str:
        """The ports grouped by board as the wiring text gives them: "OU: 2 Ports: 7 | OU: 3 Ports: 8,7"."""
        groups: list[tuple[str, list[int]]] = []
        for board, port in self.pins:
            if groups and groups[-1][0] == board:
                groups[-1][1].append(port)
            else:
                groups.append((board, [port]))
        return " | ".join(f"{b[:2]}: {b[2:]} Ports: {','.join(map(str, ps))}" for b, ps in groups)

    @property
    def address(self) -> str:
        """The JMRI system name: M2T, M2S or IH and node x 100 + the UID offset + the index (a detector's from 0).
        A button or relay has none (ValueError)."""
        if self.kind in LOCAL:
            raise ValueError(f"a {self.kind} has no JMRI address")
        prefix, uid, _word, _board, _n = LCOS[self.kind]
        return f"{prefix}{self.node * 100 + uid + self.index - (self.kind == 'detector')}"

    @property
    def wiring_text(self) -> str:
        """The device's wiring as the device master and the JMRI comment tell it: "Node: 4 Turnout: 0 | OU: 1 Ports: 1,2",
        a detector's "Node: 13 Block: 1"."""
        word = LCOS[self.kind][2]
        if self.kind in LOCAL:
            return f"Node: {self.node} | {self.port_text}"
        text = f"Node: {self.node} {word}: {self.index}"
        if self.kind == "detector":
            return text
        return f"{text} | {self.port_text}"

    @property
    def input(self) -> str:
        """A detector's node input as the block comment gives it: "Block 13-1"."""
        return f"Block {self.node}-{self.index}"


ID_PREFIX = {"turnout": "switch:", "fb": "fb:", "head": "mast:", "detector": "det:"}    # a row's id by its kind


def names_beside(path: Path):
    """The name store's {(level, id): user name} for the wiring file `path`: the device master beside it (a test's
    copy puts devices_generated.csv and devices_field.csv there), else the repo's."""
    from . import devices
    data = Path(path).parent
    return devices.user_names(devices.Files.under(data) if (data / devices.GENERATED_FILE).is_file() else None)


class _LoadFailed(FactsError):
    """The device master or field file did not load: read() stops once with its message, not once per row."""


GENERATED_NAMES = ((re.compile(r"switch:(\d+)"), "Switch {}"), (re.compile(r"fb:(\d+):([NR])"), "FB Switch {} {}"))


class _Names:
    """How read() names a row's id: `given` ({(level, id): user name}) when the caller passes one; else a staging
    device by its field row's user name, or for a turnout or feedback row with none (or no field row) the name its id
    gives (Switch <n>, FB Switch <n> N), from the field file alone (any other device with no field row, a head the
    mast rule names, by the merged view) (`files`' field file, else the one beside the wiring file, else the
    repo's: a staging builder reads the owner's cells there and never its own last output, ADR-029); any other level's
    by the merged view (`files`, else names_beside). Each file is read once, and only when a row needs it."""

    def __init__(self, path: Path, given, files=None):
        self.path, self.given, self.files, self.field, self.merged = path, given, files, None, None
        self._plan = None

    def plan_switches(self) -> set[str]:
        """The switch numbers of the staging plan graph (track_names.plan_switches): the schematic folder beside the
        wiring file when it has the plan, else the repo's. Read once, only when a row needs it."""
        if self._plan is None:
            from . import layer_files, track_names
            beside = Path(self.path).parent / "schematic"
            folder = beside if (beside / track_names.PLAN_GRAPHS["staging"]).is_file() else track_names.SCHEMATIC
            try:
                self._plan = set(track_names.plan_switches(
                    "staging", layer_files.read("plan_overrides", "staging", folder), folder))
            except (track_names.TrackNameError, layer_files.LayerFileError) as exc:
                raise _LoadFailed(str(exc)) from None
        return self._plan

    def __call__(self, level: str, ident: str, where: str) -> str:
        from . import devices
        if self.given is not None:
            return devices.name_of(self.given, level, ident, where)
        if level == STAGING_LEVEL:
            if self.field is None:
                files = self.files
                if files is None:
                    data = Path(self.path).parent
                    files = devices.Files.under(data) if (data / devices.FIELD_FILE).is_file() else None
                try:
                    index = devices.field_index(files)
                except FactsError as exc:
                    raise _LoadFailed(str(exc)) from None
                self.field = {k: r["user_name"] for k, r in index.items()}
            name = self.field.get((level, ident))
            if name:
                return name
            # a turnout or feedback with no owner's name (no field row, or one with no user_name): the name its id
            # gives, as the builder generates it (naming-layers step 7: a staging device needs no field row)
            for pattern, form in GENERATED_NAMES:
                m = pattern.fullmatch(ident)
                if m:
                    if name is None and m.group(1) not in self.plan_switches():
                        raise FactsError(f"{where}: {ident} is no level {level} device of the device master (the "
                                         f"staging plan has no switch {m.group(1)}: the ID is mistyped, or a new "
                                         "export dropped it)")
                    return form.format(*m.groups())
            if name is not None:
                raise FactsError(f"{where}: {ident}'s row in {devices.FIELD_FILE} has no user_name: give it its name")
            # no field row (a staging head or mast the mast rule names, a detector): the merged view; when that does
            # not load either (a field row taken out or moved to another id), the row stays unnamed and the staging
            # builder, which finds it by id, says what is missing
        if self.merged is None:
            try:
                self.merged = devices.user_names(self.files) if self.files is not None else names_beside(self.path)
            except FactsError as exc:
                if level == STAGING_LEVEL:
                    self.merged = {}
                    self.unloaded = str(exc)
                else:
                    raise _LoadFailed(str(exc)) from None
        if level == STAGING_LEVEL and getattr(self, "unloaded", None):
            return ""
        return devices.name_of(self.merged, level, ident, where)


def read(path: Path | None = None, names=None, levels=None, files=None) -> list[Wire]:
    """The rows of wiring.csv, each checked. Stops (FactsError, naming the file and line) on a file not in COLUMNS, an
    unknown level, kind or status, a number that is not one, an index past its kind's range, a board or ports that do
    not fit the kind, a device given twice on its level, two devices on one LCOS number or on one port of a board, or
    an id the device master does not have. Each Wire's `device` is its id's user name in `names` ({(level, id): user
    name}, hartlib.devices.user_names; default a staging device's field row, any other's the merged view: _Names), a
    detector's its block's, so the wiring follows a rename with no row changed. `levels` (default every level): the
    levels whose rows are named; a row of another level keeps its id and an empty `device`, so a staging builder that
    reads only staging's names never opens the generated file. `files` (a hartlib.devices.Files): the device master
    a copy's builder names its rows from."""
    path = path or PATH
    store_name = _Names(path, names, files)
    wanted = None if levels is None else {str(lv) for lv in levels}
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows, header = list(reader), reader.fieldnames or []
    except OSError as exc:
        raise FactsError(f"cannot read {path.name}: {exc}") from None
    if list(header) != COLUMNS:
        raise FactsError(f"{path.name}: columns {list(header)}, not {COLUMNS}")
    out, bad = [], []
    names, numbers, pins = {}, {}, {}
    for i, raw in enumerate(rows, 2):
        if None in raw:
            bad.append(f"line {i}: more fields than columns")
            continue
        r = {k: (v or "").strip() for k, v in raw.items()}
        at = f"line {i}"
        if r["level"] not in ("1", "2", "3"):
            bad.append(f"{at}: level is 1, 2 or 3, not {r['level']!r}")
            continue
        if r["kind"] not in KINDS:
            bad.append(f"{at}: kind is one of {', '.join(KINDS)}, not {r['kind']!r}")
            continue
        if r["status"] not in STATUSES:
            bad.append(f"{at}: status is wired or planned, not {r['status']!r}")
            continue
        kind = r["kind"]
        try:
            node = int(r["node"])
            index = None if kind in LOCAL and not r["index"] else int(r["index"])
            items = [p.strip() for p in r["ports"].split(",")] if r["ports"] else []
            spans = [OWN_BOARD.fullmatch(p) for p in items]
            odd = [p for p, m in zip(items, spans) if not m and not p.isdigit()]
            if odd:
                bad.append(f"{at}: port {odd[0]!r} is a pin 1 to 8, or a pin on another board as OU<1-4>-<1-8>")
                continue
            ports = tuple(int(m.group(2)) if m else int(p) for p, m in zip(items, spans))
            boards = tuple(m.group(1) if m else r["board"] for m in spans)
        except ValueError:
            bad.append(f"{at}: node, index and ports are numbers")
            continue
        if any(spans) and kind != "head":
            bad.append(f"{at}: only a head's pins may span two boards; a {kind} is on its board alone")
            continue
        low = 1 if kind == "detector" else 0
        if kind in LOCAL:
            if index is not None:
                bad.append(f"{at}: a {kind} has no JMRI device, so no index")
                continue
        elif not low <= index < low + CAP[kind]:
            bad.append(f"{at}: a {kind}'s index is {low} to {low + CAP[kind] - 1}, not {index}")
            continue
        keyed = any(r[c] for c in ("switch_a", "switch_b", "parallel", "half"))
        ident = r["id"]
        if kind in LOCAL:
            if ident or keyed or not r["device"]:
                bad.append(f"{at}: a {kind} has no JMRI device, so no id or switches: give its label in device")
                continue
        elif r["device"]:
            bad.append(f"{at}: a {kind} is named by its id, not device (device is a button's, relay's or calibration "
                       "relay's label)")
            continue
        elif ident and not ident.startswith(ID_PREFIX[kind]):
            bad.append(f"{at}: a {kind}'s id starts {ID_PREFIX[kind]}, not {ident!r}")
            continue
        if kind == "detector":
            if r["board"] or ports:
                bad.append(f"{at}: a detector has no board or ports (its input is its index)")
                continue
            if keyed and r["level"] == "1":
                bad.append(f"{at}: a staging detector is named by its block's id alone, not by switches")
                continue
            if keyed and ident:
                bad.append(f"{at}: a detector is named by its id or, on main and upper, by its switches, not both")
                continue
        else:
            m = BOARD.match(r["board"])
            want = LCOS[kind]
            if keyed:
                bad.append(f"{at}: a {kind} is named by its id alone")
                continue
            if kind not in LOCAL and not ident:
                bad.append(f"{at}: a {kind} needs its id")
                continue
            if not m or m.group(1) != want[3]:
                bad.append(f"{at}: a {kind} lands on an {want[3]} board ({want[3]}1 to {want[3]}4), not {r['board']!r}")
                continue
            if spans and spans[0]:
                bad.append(f"{at}: the first pin {items[0]} is on the row's board {r['board']}: give it as a pin alone")
                continue
            if any(m and m.group(1) == r["board"] for m in spans):
                bad.append(f"{at}: a pin on the row's own board {r['board']} is given as a pin alone, not "
                           f"{r['board']}-<pin>")
                continue
            if len(set(boards)) > 2:
                bad.append(f"{at}: a head spans at most two boards, not {', '.join(sorted(set(boards)))}")
                continue
            if any(boards[j] == r["board"] and boards[j - 1] != r["board"] for j in range(1, len(boards))):
                bad.append(f"{at}: a head's pins on {r['board']} come first, then those on the other board")
                continue
            if len(ports) != want[4] or not all(1 <= p <= 8 for p in ports):
                bad.append(f"{at}: a {kind} takes {want[4]} port(s) of 1 to 8, not {r['ports']!r}")
                continue
        level = int(r["level"])
        name = ident or r["device"] or (",".join(r[c] for c in ("switch_a", "switch_b", "parallel", "half"))
                                        if keyed else "")
        device, mast = r["device"], ""
        if kind == "head" and ident and ident.rsplit(":", 1)[-1] not in HEAD_PLACES:
            bad.append(f"{at}: a head's id is its mast's id and its place ({', '.join(HEAD_PLACES)}), not {ident!r}")
            continue
        if ident and (wanted is None or r["level"] in wanted):
            try:
                device = store_name(r["level"], ident[len("det:"):] if kind == "detector" else ident,
                                    f"{path.name} {at}")
                if kind == "head" and level == FIELD:     # a wired head's mast: digicon_rows, device_map_masts
                    mast = store_name(r["level"], ident.rsplit(":", 1)[0], f"{path.name} {at}")
            except _LoadFailed:
                raise
            except FactsError as exc:
                bad.append(str(exc).removeprefix(f"{path.name} "))
                continue
        if name and (level, kind, name) in names:
            bad.append(f"{at}: {kind} {name} is line {names[level, kind, name]}'s as well")
            continue
        number = (node, LCOS[kind][2], index)
        if kind not in LOCAL and number in numbers:
            bad.append(f"{at}: node {node} {LCOS[kind][2]} {index} is line {numbers[number]}'s as well")
            continue
        own = list(zip(boards, ports))
        if len(set(own)) != len(own):
            bad.append(f"{at}: a pin is given twice ({r['ports']})")
            continue
        taken = [(b, p) for b, p in own if (node, b, p) in pins]
        if taken:
            bad.append(f"{at}: node {node} " + ", ".join(f"{b}-{p} is line {pins[node, b, p]}'s" for b, p in taken))
            continue
        if name:
            names[level, kind, name] = i
        if kind not in LOCAL:
            numbers[number] = i
        for b, p in own:
            pins[node, b, p] = i
        out.append(Wire(i, level, kind, device, r["switch_a"], r["switch_b"], r["parallel"], r["half"], node,
                        index, r["board"], ports, r["status"], r["notes"], boards, ident, mast))
    if bad:
        raise FactsError(f"{path.name}: " + "; ".join(bad))
    return out


HEAD_NAME = re.compile(r"^Head (?P<key>\S+)(?: (?P<pos>Top|Bottom))?$")
DIGICON_COLUMNS = ["port_id", "parent_node_id", "mqtt_node", "board_location", "signal_index", "uid", "packed",
                   "system_name", "user_name", "mast_user_name", "disc_role", "head_role", "lamp_color", "topic",
                   "device_type", "voltage_rail", "notes"]


_HEAD_TEXT = re.compile(r"Node: (\d+) Signal: (\d+)((?: \| OU: [1-4] Ports: \d+(?:,\d+)*)+)")
_HEAD_PORTS = re.compile(r"OU: ([1-4]) Ports: (\d+(?:,\d+)*)")


def field_heads(files=None) -> list[Wire]:
    """The main and upper heads swapped in by their device rows (a head row whose assignment is field, ADR-028), as
    Wires from the row's node and wiring text ("Node: 33 Signal: 0 | OU: 3 Ports: 1,2,3": wiring.csv's frozen pins, or
    the rule's), in the device master's order. `files` (a hartlib.devices.Files): the device master to read, default
    the repo's. FactsError on such a row whose wiring text is not a head's, or whose jmri_name is not the LCOS head
    that text gives."""
    from . import devices
    rows = list(devices.load(files))
    masts = {(r["level"], r["id"]): r["user_name"] for r in rows if r["layer"] == "mast"}
    out, bad = [], []
    for r in rows:
        if r["layer"] != "head" or r["level"] == STAGING_LEVEL or r["assignment"] != "field":
            continue
        m = _HEAD_TEXT.fullmatch(r["wiring"])
        if not m:
            bad.append(f"level {r['level']} head {r['user_name']}: wiring {r['wiring']!r} is not "
                       "Node: <n> Signal: <i> | OU: <b> Ports: <p,p,p>")
            continue
        pins = [(f"OU{b}", int(p)) for b, ps in _HEAD_PORTS.findall(m.group(3)) for p in ps.split(",")]
        w = Wire(0, int(r["level"]), "head", r["user_name"], "", "", "", "", int(m.group(1)), int(m.group(2)),
                 pins[0][0], tuple(p for _b, p in pins), "wired", r["notes"], tuple(b for b, _p in pins), r["id"],
                 masts.get((r["level"], r["id"].rsplit(":", 1)[0]), ""))
        if w.address != r["jmri_name"]:
            bad.append(f"level {r['level']} head {r['user_name']}: jmri_name {r['jmri_name']!r} is not the LCOS head "
                       f"{w.address} its wiring gives")
            continue
        out.append(w)
    if bad:
        raise FactsError("the device master's field heads: " + "; ".join(bad))
    return out


def digicon_rows(path: Path | None = None, files=None) -> list[dict[str, str]]:
    """The wired Digicon searchlight heads, one row per lamp pin, in the columns the old signal_wiring.csv had
    (DIGICON_COLUMNS): staging's wiring.csv head rows of status wired (staging's heads are bound as built), and each
    main or upper head whose device row's assignment is field (field_heads, from `files`, else the device master
    beside the wiring file, else the repo's): a main or upper head frozen in wiring.csv is still a virtual head in JMRI
    until its row swaps the physical one in. Each head is one LCOS signal object, its three ports R (Stop), Y
    (Approach) and G (Clear) in that order. A head named "Head <mast> Top" or "Bottom" is its mast's top (T) or bottom
    (B) disc; a head with neither is the mast's one disc (S), its lamps "Head <mast> R". board_location is the node's
    place in lcos_nodes.csv ("West - Staging"). FactsError on a head whose name is not "Head <mast>[ Top| Bottom]"."""
    from . import devices
    from .railroad_facts import read_lcos_nodes
    level_name = {1: "Staging", 2: "Main", 3: "Upper"}
    place = {n.node: f"{n.area} - {level_name[n.level]}" for n in read_lcos_nodes(NODES)}
    if files is None:
        data = Path(path or PATH).parent
        files = devices.Files.under(data) if (data / devices.GENERATED_FILE).is_file() else None
    staging = [w for w in read(path) if w.kind == "head" and w.status == "wired" and w.level == FIELD]
    out, bad = [], []
    for w in staging + field_heads(files):
        # the mast and the place come from the head's id, not its name, so a renamed head keeps its lamps
        key = w.mast.removeprefix("Mast ")
        if not w.mast.startswith("Mast ") or not w.place:
            bad.append(f"line {w.line}: {w.id!r} is no head of a mast (Mast <key>, its id ending top, bottom or single)")
            continue
        role = {"top": "T", "bottom": "B"}.get(w.place, "S")
        lamp_of = f"Head {key} {role}" if role != "S" else f"Head {key}"
        uid = LCOS["head"][1] + w.index
        packed = w.node * 100 + uid
        for (board, port), lamp in zip(w.pins, "RYG"):
            out.append(dict(port_id=f"C{w.node}-{board}-{port}", parent_node_id=f"C{w.node}",
                            mqtt_node=str(w.node), board_location=place.get(w.node, ""), signal_index=str(w.index),
                            uid=str(uid), packed=str(packed), system_name=f"IH{packed}",
                            user_name=f"{lamp_of} {lamp}", mast_user_name=w.mast,
                            disc_role=role, head_role=role, lamp_color=lamp, topic=f"track/signalhead/{packed}",
                            device_type="Searchlight Signal Head", voltage_rail="5V",
                            notes=f"LCOS Signal {w.index} UID {uid}; STOP/APPROACH/CLEAR; lamp {lamp}"))
    if bad:
        raise FactsError(f"{(path or PATH).name}: " + "; ".join(bad))
    return out


def calibration_ports(path: Path | None = None) -> set[str]:
    """The port IDs of wiring.csv's calibration relays ("C4-OU2-8"): no lamp may be put on one."""
    return {f"C{w.node}-{w.board}-{w.ports[0]}" for w in read(path) if w.kind == "calibration"}


# --- one way: rules -> proposal (devices_generated.csv) -> freeze_wiring.py -> wiring.csv -> device map ------------
# freeze_wiring.py is the only writer of main and upper rows with status wired. Its rows carry the note below, which
# names the control point; that note is how a frozen control point is told from one the rule still proposes for.

FREEZE_NOTE = re.compile(r"frozen from the device map's rule \((?P<cp>[^,()]+), \d{4}-\d{2}-\d{2}\)")
FIELD = 1                                     # staging's level: kept by hand as built, never frozen
FROZEN_KINDS = ("turnout", "fb", "head")      # the devices whose node, number and pins the build holds


def freeze_note(cp: str, day: str) -> str:
    """The note freeze_wiring.py puts on each row it writes."""
    return f"frozen from the device map's rule ({cp}, {day})"


def frozen_cp(w: Wire) -> str | None:
    """The control point whose freeze wrote this row (from its note), or None."""
    m = FREEZE_NOTE.search(w.notes)
    return m.group("cp") if m else None


class Held(NamedTuple):
    """What wiring.csv holds of main and upper, which the build reads instead of proposing."""
    devices: list[Wire]          # turnout, fb and head rows: node, LCOS number and pins kept (Nodes.freeze)
    detectors: list[Wire]        # detector rows, planned (the owner's pin) or wired (frozen): inputs kept (read_pins)
    cps: frozenset[str]          # the control points frozen: the build proposes no device for them


def held(path: Path | None = None, wires: list[Wire] | None = None) -> Held:
    """The main and upper rows of wiring.csv the build takes as given (`wires`: rows already read)."""
    wires = read(path) if wires is None else wires
    upper = [w for w in wires if w.level != FIELD]
    return Held([w for w in upper if w.kind in FROZEN_KINDS], [w for w in upper if w.kind == "detector"],
                frozenset(cp for w in upper if (cp := frozen_cp(w))))


def canonical(rows: list[dict]) -> str:
    """wiring.csv's text as freeze_wiring.py writes it: staging, main, upper in file order, LF lines."""
    order = {"1": 0, "2": 1, "3": 2}
    buf = io.StringIO()
    out = csv.DictWriter(buf, COLUMNS, lineterminator="\n")
    out.writeheader()
    out.writerows(sorted(rows, key=lambda r: order[r["level"]]))
    return buf.getvalue()


def audit(path: Path | None = None) -> list[str]:
    """What shows wiring.csv was changed other than by freeze_wiring.py: a main or upper row wired with no freeze
    note, a frozen control point with a row not wired, or text that is not the form freeze_wiring.py writes.
    (Staging's rows are kept by hand, as built; main and upper rows still planned are the owner's pins.)"""
    path = path or PATH
    text = path.read_bytes().decode("utf-8")           # as written: line ends and all
    wires = read(path)
    problems = []
    for w in wires:
        if w.level == FIELD or w.kind in LOCAL:         # staging's, and a node's own buttons and relays, are by hand
            continue
        who = w.device or "-".join(x for x in (w.switch_a, w.switch_b) if x)
        cp = frozen_cp(w)
        if w.status == "wired" and not cp:
            problems.append(f"line {w.line}: main/upper {w.kind} {who} is wired, but no freeze wrote it "
                            "(make wiring-freeze CP=...)")
        if cp and w.status != "wired":
            problems.append(f"line {w.line}: {w.kind} {who} is of {cp}, which is frozen, but is {w.status}")
    try:
        same = canonical(list(csv.DictReader(io.StringIO(text, newline="")))) == text
    except (ValueError, KeyError, csv.Error):                 # a row with fields past the columns
        same = False
    if not same:
        problems.append("the text is not the form freeze_wiring.py writes (columns, LF lines, staging then main "
                        "then upper)")
    return problems
