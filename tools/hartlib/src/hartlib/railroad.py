"""The railroad's facts, loaded once into typed objects and held to the rules that join the files.

    from hartlib import railroad
    rr = railroad.Railroad()                      # every layer, from this checkout's files
    rr = railroad.Railroad(upto="inputs")         # a builder of a later layer reads only what comes before it
    rr.switches[9].legs[0].closed                 # "Track EH-2"
    rr.device_map.sensors["BS Switch 101"]        # "IS:HART:C3:B:OS101"
    problems = rr.check()                         # [Problem(invariant, message)], [] when the files agree

    python3 -m hartlib.railroad check [--upto LAYER]    # tools/check.sh runs it

Some of these files are written by the panel builders (tools/schematic/build_panels.sh runs them in order), so the
facts come in layers, in the order the pipeline makes them. A Railroad built `upto` a layer refuses (LayerError) to
read a later one: build_device_map.py loads upto="inputs", because it writes the device map, and so never reads a
stale copy of its own output. Each file is read the first time it is asked for, once.

    inputs      hand-kept: switches.csv (every level's switches, one row per OS block or half, ADR-021; its main and
                upper hands are the hands layer), staging's rows of devices.csv,
                schematic/interlockings.csv (every level's), lcos_nodes.csv (every level),
                the helix tracks (plan_overrides.json's helix ends and map, preferences.json's track_labels: each
                helix track one block, Track <plan name>, from staging up the helix, owner 2026-11-20/21),
                plan_overrides.json's main_upper section (its edits; build_device_map.py rewrites only its
                control_points and stations keys), block_lengths.csv
    hands       the hand of switches.csv's plan rows      build_hands.py
    device_map  the main and upper rows of devices.csv      build_device_map.py
    masts       schematic/masts.csv, every level's masts  build_masts.py (hartlib.level_masts)
    tables      jmri/layouts/hart/output/tables.xml       build_layout_le.py --as-live, and PanelPro's Store

Every reader checks its own file's shape and stops with FactsError naming the file and line. The rules between files
are INVARIANTS, each run by Railroad.check once every layer it reads is loaded; a problem names the files and rows
that disagree. KNOWN lists problems already reported to the owner, each by its exact message: `check` prints them
and passes, any other problem fails, and a KNOWN message that no longer happens fails so the list stays honest.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from functools import cached_property
from typing import Callable  # noqa: F401

from . import level_devices, level_masts, paths, tables  # noqa: F401  re-exported: callers use railroad.tables
# The fact readers and the invariants moved to railroad_facts and railroad_invariants; every name stays importable
# from hartlib.railroad (`from hartlib.railroad import X`, `railroad.X`).
from .railroad_facts import *  # noqa: F401,F403
from .railroad_facts import _int, _level, _where, _yes  # noqa: F401
from .railroad_facts import (LAYERS, LEVEL_NUMBERS, WRITERS, BlockLength, DeviceMap, FactsError, Hand, HelixTrack, LayerError,
                             Interlocking, LcosNode, LocalSwitch, MainUpperSwitch, PlanOverrides, StagingDevices,
                             Sources, Mast, Switch, SwitchRow, TablesNames, hands, join_main_upper,
                             local_switches, read_block_lengths, read_switch_rows, staging_switches,
                             read_device_map, read_hands, read_helix_tracks, read_lcos_nodes,
                             read_interlockings, read_local_switches, read_staging_devices, read_staging_rows,
                             read_plan_overrides, read_masts, read_switches, read_tables)
from .railroad_invariants import INVARIANTS, Invariant, Problem, invariant  # noqa: F401
from .railroad_invariants import (_device_map, _hands, _lcos_nodes, _masts, _name_clash, _staging_devices,  # noqa: F401
                                  _plan_overrides, _staging_blocks, _switch_numbers, _tables)


class Railroad:
    """The facts, each file read on first use, up to the layer `upto` (see the module text)."""

    def __init__(self, sources: Sources | None = None, upto: str = LAYERS[-1]):
        if upto not in LAYERS:
            raise ValueError(f"upto is one of {', '.join(LAYERS)}, not {upto!r}")
        self.sources = sources or Sources.under()
        self.upto = upto

    def _need(self, layer: str, what: str) -> None:
        if LAYERS.index(layer) > LAYERS.index(self.upto):
            raise LayerError(f"{what} is the {layer} layer, written by {WRITERS[layer]}; this Railroad reads up to "
                             f"the {self.upto} layer, so it may not read it (it would be a stale copy of a later step)")

    def has(self, layer: str) -> bool:
        return LAYERS.index(layer) <= LAYERS.index(self.upto)

    # inputs
    @cached_property
    def staging_rows(self) -> list[tuple[int, dict[str, str]]]:
        """Staging's rows of devices.csv as read, once: staging_devices checks every row, switches look only at
        theirs."""
        return read_staging_rows(self.sources.devices)

    @cached_property
    def staging_devices(self) -> StagingDevices:
        return read_staging_devices(self.sources.devices, self.staging_rows)

    @cached_property
    def switch_rows(self) -> list[SwitchRow]:
        """switches.csv as read, once: the staging switches, the local switches and the hands are views of it."""
        return read_switch_rows(self.sources.switches)

    @cached_property
    def switches(self) -> dict[int, Switch]:
        """The staging switches (level 1 of switches.csv)."""
        return staging_switches(self.switch_rows, self.sources.switches, self.sources.devices, self.staging_rows)

    @cached_property
    def interlockings(self) -> list[Interlocking]:
        """Every level's interlockings (interlockings.csv)."""
        return read_interlockings(self.sources.interlockings)

    @cached_property
    def level_control_points(self) -> list[Interlocking]:
        """The main and upper interlockings, which are also their control points ("CP <lowest switch>")."""
        return [i for i in self.interlockings if i.level in LEVEL_NUMBERS]

    @cached_property
    def local_switches(self) -> list[LocalSwitch]:
        return local_switches(self.switch_rows)

    @cached_property
    def lcos_nodes(self) -> list[LcosNode]:
        return read_lcos_nodes(self.sources.lcos_nodes)

    @cached_property
    def helix_tracks(self) -> dict[str, HelixTrack]:
        return read_helix_tracks(self.sources.plan_overrides)

    @cached_property
    def plan_overrides(self) -> PlanOverrides:
        return read_plan_overrides(self.sources.plan_overrides)

    @cached_property
    def block_lengths(self) -> dict[str, BlockLength]:
        return read_block_lengths(self.sources.block_lengths)

    @cached_property
    def main_upper_switches(self) -> dict[str, MainUpperSwitch]:
        """Switch number -> its control point or local row (join_main_upper)."""
        return join_main_upper(self.level_control_points, self.local_switches, self.sources.switches.name)

    # later layers
    @cached_property
    def hands(self) -> dict[str, Hand]:
        """The main and upper hands of switches.csv. The file is an input, but build_hands.py writes these cells (its
        plan rows), so they are read as the hands layer."""
        self._need("hands", f"the hands of {self.sources.switches.name}")
        return hands(self.switch_rows)

    @cached_property
    def device_map(self) -> DeviceMap:
        self._need("device_map", self.sources.devices.name)
        return read_device_map(self.sources.devices)

    @cached_property
    def masts(self) -> list[dict]:
        """masts.csv's rows, every level (hartlib.level_masts.read: dicts with `level`, `line` and `heads` as
        (system, user) pairs)."""
        self._need("masts", self.sources.masts.name)
        try:
            return level_masts.read(None, self.sources.masts)
        except (OSError, ValueError) as exc:
            raise FactsError(str(exc)) from None

    @cached_property
    def tables(self) -> TablesNames:
        self._need("tables", self.sources.tables.name)
        return read_tables(self.sources.tables)

    def check(self) -> list["Problem"]:
        """Every invariant whose layers this Railroad reads, in INVARIANTS order."""
        out = []
        for inv in INVARIANTS:
            if self.has(inv.layer):
                out += [Problem(inv.name, m) for m in inv.run(self)]
        return out


# ---------------------------------------------------------------- the check command

# Problems already reported to the owner, each by its exact message (str(Problem)) -> why it is left. Empty since
# 2026-11-17: the owner decided the throat blocks (live rows added) and the BS unused aliases (they point at the
# free detectors' live names). Add an entry only for a problem the owner has been told about and chose to leave.
KNOWN: dict[str, str] = {}


def run_check(rr: Railroad, known: dict[str, str] = KNOWN) -> tuple[list[str], list[str]]:
    """(failures, known lines): every problem not in `known`, and every `known` message of an invariant that ran
    which no longer happens."""
    seen = [str(p) for p in rr.check()]
    ran = {inv.name for inv in INVARIANTS if rr.has(inv.layer)}
    fails = [m for m in seen if m not in known]
    fails += [f"KNOWN entry no longer happens; remove it from KNOWN: {m}" for m in known
              if m not in seen and m.split(":", 1)[0] in ran]
    hits = Counter(known[m] for m in seen if m in known)
    return fails, [f"{reason} ({n} problem(s))" for reason, n in hits.items()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hartlib.railroad", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="hold the fact files to every invariant (tools/check.sh)")
    c.add_argument("--upto", choices=LAYERS, default=LAYERS[-1], help="the last layer to read (default: all)")
    sub.add_parser("invariants", help="list the invariants and the layer each reads")
    args = ap.parse_args(argv)
    if args.cmd == "invariants":
        for inv in INVARIANTS:
            print(f"{inv.name} ({inv.layer}): {' '.join(inv.doc.split())}")
        return 0
    rr = Railroad(upto=args.upto)
    try:
        fails, known = run_check(rr)
    except FactsError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    for line in known:
        print(f"KNOWN {line}")
    for line in fails:
        print(f"FAIL {line}", file=sys.stderr)
    counts = defaultdict(int)
    for inv in INVARIANTS:
        counts["run" if rr.has(inv.layer) else "skipped"] += 1
    print(f"railroad facts: {counts['run']} invariants up to {args.upto}, {len(fails)} failure(s), "
          f"{len(known)} known")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

