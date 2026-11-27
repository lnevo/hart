"""The records build_device_map.py's build() reads, shares between its stages and returns, and the type names of the
plugin's shapes it passes on; build_device_map re-exports the names its callers read."""
from __future__ import annotations

import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, NamedTuple, TypedDict, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
import block_layer  # noqa: E402  the block layer
from device_map_inputs import Places  # noqa: E402
from device_map_nodes import Nodes  # noqa: E402
from hartlib import railroad  # noqa: E402
from mast_plan import Band, Bands  # noqa: E402  the plugin's solved bands
from mast_rule import Joined, Track  # noqa: E402  the plugin's connector partners; a named track

MastKind = Literal["home", "intermediate", "virtual"]    # mast_plan's three lists of masts
Layer = Literal["turnout", "fb", "block", "occupancy", "mast", "head"]     # a device-map row's layer


class DeviceMapRow(TypedDict):
    """A device-map row (device_map_rows.device_row): the master's columns by name, as csv_text and
    devices.master_row read it, with the role and device ID its maker gives. build() fills and sorts these in place
    before they become master rows. The fact columns (hartlib.railroad.DEVICE_FACTS) are empty off their own layer."""
    level: int
    cp: str
    layer: Layer
    id: str
    user_name: str
    system_name: str        # the planned physical device (LCOS), empty with none on a node
    jmri_name: str          # the virtual device the tables and desks use
    node: int | str         # "" with no node
    dcc: int | str          # "" off a turnout
    comment: str
    trial_name: str
    notes: str
    role: str               # hartlib.devices.ROLES
    blocks: str
    detector: str
    stop: str
    switch: str
    facing: str
    protects: str
    dir: str


MasterCells = dict[str, str]    # a master row as hartlib.devices.master_row returns it: the master's columns, all text
# le_names.runs over a band: its tracks joined through turnbacks, in the plugin's shapes
Runs = Callable[[Band], Sequence[Any]]
Corners = Mapping[str, Mapping[str, str]]       # dx_corners: {switch number: {schematic leg: Layout Editor corner}}
VirtualNames = dict[str, tuple[str, str]]       # {mast id: (user name, system name)} of the virtual masts
MastEntry = dict[str, Any]      # a mast mast_plan.plan places (the plugin's JSON shape, read and extended by key)


def cells(row: DeviceMapRow) -> Mapping[str, str]:
    """`row` as hartlib.devices' readers take a row: they read cells by column and write each one as text, so a
    row's int level, node or dcc is their input too."""
    return cast(Mapping[str, str], row)


class Group(NamedTuple):
    """Where a switch's devices belong: its level, its LCOS area and its control point's name ("" in none)."""
    level: int
    area: str
    cp: str

    @property
    def place(self) -> str:
        """The control point's name, else the area: what a row's comment says of where it stands."""
        return self.cp or self.area


class MapBuild(NamedTuple):
    """What build()'s stages share: the plan facts read once at the start, the node allocator, and the rows made so
    far. `rows`, `block_ids`, `home` and `area_of` are filled in place, stage by stage, in build()'s order (a node's
    12V turnout boards come before its 5V head boards)."""
    bands: Bands                        # the plugin's bands
    by_level: dict[int, set[str]]       # labels_by_level: {level: the switch labels drawn on it}
    switches: dict[str, railroad.MainUpperSwitch]   # every main and upper switch, by number
    cp_of: dict[str, str]               # {switch: its control point}
    loc: dict[str, railroad.MainUpperSwitch]        # the switches in no control point (level, area, notes)
    found: list[Track]                  # named_tracks: the main and upper tracks
    corner_blocks: dict[str, dict[str, str]]        # {double crossover: {schematic leg: corner block}}
    split_names: set[str]               # the split tracks' names
    lay: block_layer.Layer
    trials: dict[str, str]              # {block: trial_name} (level_keys)
    track_ids: dict[str, str]           # {block: device ID} (level_keys)
    places: Places
    helix: Mapping[str, Mapping[str, str]]  # read_helix_tracks: {plan helix track: its block and ends}
    nodes: Nodes
    os_pin_level: dict[str, int]        # {OS block pinned by its name: the level its wiring.csv row gives}
    dcc: dict[str, int]                 # {switch: its DCC address}
    rows: list[DeviceMapRow]
    block_ids: dict[tuple[str, str], str]   # (level, block) -> its device ID, for its detector and the masts facing it
    home: dict[str, int]                # switch -> its turnout's node
    area_of: dict[str, tuple[int, str]]     # switch -> (level, area)


class MapInputs(NamedTuple):
    """The railroad facts build() reads beside the drawing: plan_overrides.json's data, the main and upper control
    points (interlockings.csv), the LCOS node rows (lcos_nodes.csv) and the switches in no control point (the local
    switches of switches.csv). Every switch on the main and upper bands must be in exactly one of `cps` and `local`."""
    overrides: Mapping[str, Any]        # plan_overrides.json, the owner's hand edits: the plugin's JSON shape
    cps: Sequence[railroad.Interlocking]
    node_rows: Sequence[railroad.LcosNode]
    local: Sequence[railroad.LocalSwitch] = ()

    @classmethod
    def of(cls, rr: railroad.Railroad) -> "MapInputs":
        """The inputs from `rr`'s sources. railroad.FactsError when one does not read."""
        return cls(rr.plan_overrides.data, rr.level_control_points, rr.lcos_nodes, rr.local_switches)


class MapOutput(NamedTuple):
    """build()'s result: plan_generated.json's main_upper control points (overrides_keys), the device-map rows of
    levels 2 and 3, sorted, and the parts' master rows (links inside an OS block, part_row)."""
    control_points: dict[str, Any]      # overrides_keys: the plugin's JSON shape, written as it is
    rows: list[DeviceMapRow]
    parts: list[MasterCells]


class Drawing(NamedTuple):
    """The solved main and upper drawing build() and master_outputs read: the plugin's bands, their connector
    partners, the runs function and the double crossovers' corners (dx_corners)."""
    bands: Bands
    joined: Joined
    runs: Runs
    corners: dict[str, dict[str, str]]
