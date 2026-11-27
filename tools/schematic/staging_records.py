"""The records staging_device_map.py reads staging's rows into and gives its readers: the plugin's names for the
staging band (StagingNames), its masts as the plugin and build_signals.py read them, the type names of the shapes
it passes on, and the error its readers raise (StagingMapError). staging_device_map re-exports them."""
from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plan_tracks import Leg  # noqa: E402  a band end (node, port)

Ref = tuple[str, bool]              # a strand's (piece reference, whether it runs against the piece): piece_refs
Beyond = Callable[[Leg], str]       # the key of what is beyond a connector end (band_refs)
Row = dict[str, str]                # a device-master or masts.csv row as its reader gives it: column -> text
Joined = Mapping[tuple[int, str], tuple[int, str]]      # the plugin's connector partners: (band, node) -> (band, node)
MastKind = Literal["turnout", "end bumper", "anchor"]   # the kind of slot a mast stands in (mast_kind)
TrackRuns = dict[str, dict[int, tuple[int, str]]]       # {piece: {k: (n, trial key)}} of the block rows' track keys


class StagingMapError(RuntimeError):
    """Staging's device-map rows, masts.csv's staging rows or the staging drawing break a rule staging_device_map reads
    them by; the message names the file and row, or the switch or track."""



class Idents(TypedDict):
    """The Layout Editor idents load() gives the staging band: each switch node's turnout ident (switches.csv's
    le_ident), and no boundary, end or segment idents."""
    turnouts: dict[str, str]
    boundaries: list[Any]
    ends: dict[str, Any]
    segments: dict[str, Any]


class StagingMast(TypedDict):
    """A staging mast as the plugin reads a drawn mast (load_masts)."""
    mast: str
    facing: str
    protects: list[str]
    kind: MastKind
    hidden: bool
    icon: list[int]
    leg: NotRequired[str]            # a turnout mast's leg (normal or diverging), when masts.csv gives one
    or_join: NotRequired[bool]       # an end bumper mast, which may stand at a helix join instead


class StagingNames(TypedDict):
    """The plugin's names for the staging band (load): {switch node: turnout name}, {switch node: OS block}, {strand
    id: its blocks from the strand's first end}, and as load() is asked, {plain switch node: normal leg}, the idents
    and the masts."""
    turnouts: dict[str, str]
    os: dict[str, str]
    blocks: dict[str, list[str]]
    normal: NotRequired[dict[str, str]]
    idents: NotRequired[Idents]
    masts: NotRequired[list[StagingMast]]


class SignalMast(TypedDict):
    """A staging mast as build_signals.py reads it (load_signal_masts): masts.csv's row with its plan facts."""
    mast: str
    kind: MastKind
    facing: str
    protects: list[str]
    signal: str
    toward: str
    run: list[str]
    names: list[str]
    edge_cm: float
    cm_from_toward: float
    dir: str
    signal_kind: str
    heads: int
    schematic_edge: str
    schematic_toward_node: str


class MastFact(TypedDict):
    """A staging mast's slot, blocks and, for a turnout mast, its turnout's panel name (mast_facts)."""
    kind: MastKind
    facing: str
    protects: list[str]
    hidden: bool
    turnout: NotRequired[str]
