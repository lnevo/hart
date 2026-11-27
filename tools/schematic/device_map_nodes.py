"""The LCOS node allocator of the main and upper device map (build_device_map.build): it hands out each node's
turnout, sensor, block and signal inputs and its OU boards' pins, holds the pinned detectors and the frozen devices of
wiring.csv first, and checks the boards once every device is placed. Staging's nodes are as built (lcos_nodes.csv
level 1) and are never handed out here."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal, NamedTuple

from device_map_inputs import NODES, PINS, UID
from hartlib import railroad, wiring
from map_error import MapError

Input = Literal["turnout", "block", "signal", "sensor"]     # what a node hands out, each numbered from 0
Pin = tuple[int, int]                 # a pinned detector's (node, block input index from 0): read_pins' value


class InputSlot(NamedTuple):
    """An input a node gave out: its slot (the index among the node's inputs of that kind) and the packed LCOS ID."""
    slot: int
    packed: int


class DetectorInput(NamedTuple):
    """A block detector's input: its LCOS node, the block input slot on it, and the packed LCOS ID."""
    node: int
    slot: int
    packed: int


class BoardRun(NamedTuple):
    """A run of consecutive free pins on one 5V OU board: the board and the run's first pin."""
    board: int
    first: int


class HeadPlace(NamedTuple):
    """Where one head of a mast is placed: its signal slot on the node, the packed LCOS ID, and the OU board and
    first of the three pins it takes."""
    signal: int
    packed: int
    board: int
    pin: int


CAP: dict[Input, int] = {"turnout": 8, "block": 8, "signal": 16, "sensor": 16}
# the input a frozen wiring.csv row of each kind holds
FROZEN_INPUT: dict[wiring.Kind, Input] = {"turnout": "turnout", "fb": "sensor", "head": "signal"}
MAX_OU = 4                            # DNOU8 boards per node: the most any node has in LCOS_Layout_Inventory_v85
STAGING_LEVEL = 1                                 # staging: its nodes are as built (lcos_nodes.csv)


class NoBoardRoom(MapError):
    """The draft plant has no 5V board room left in an area for a mast's heads: the heads wait for the wiring plan
    (HEAD_NOT_WIRED). Any other MapError still stops the build."""


class Nodes:
    """Hands out LCOS UIDs per node, in each level and area's node order. Staging's rows of lcos_nodes.csv are the
    nodes as built, never handed out or pinned here."""

    def __init__(self, rows: Iterable[railroad.LcosNode]) -> None:
        self.pool: defaultdict[tuple[int, str], list[int]] = defaultdict(list)    # (level, area) -> its nodes
        for r in rows:
            if r.level != STAGING_LEVEL:
                self.pool[(r.level, r.area)].append(r.node)
        # node -> {what: how many are given out or pinned}
        self.used: defaultdict[int, defaultdict[Input, int]] = defaultdict(lambda: defaultdict(int))
        # (node, what) -> the indices given out or pinned
        self.taken: defaultdict[tuple[int, Input], set[int]] = defaultdict(set)
        self.pins: dict[str, Pin] = {}        # block -> (node, index): wiring.csv's main and upper detectors
        # node -> {OU board: the pins its heads use}
        self.boards: defaultdict[int, defaultdict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        # (kind, device) -> wiring.csv's Wire of a frozen main or upper device
        self.frozen: dict[tuple[wiring.Kind, str], wiring.Wire] = {}
        self.turnout_boards: defaultdict[int, set[int]] = defaultdict(set)    # node -> its frozen turnouts' 12V boards
        self.frozen_turnouts: defaultdict[int, set[int]] = defaultdict(set)   # node -> their LCOS numbers

    def pin(self, pins: Mapping[str, Pin]) -> None:
        """Hold each pinned detector's input (read_pins: {block: (node, input index)}) before any other is given out,
        so the rule never hands it to another block."""
        known = {n for nodes in self.pool.values() for n in nodes}
        for block, (node, k) in sorted(pins.items()):
            if node not in known:
                raise MapError(f"{PINS.name}: {block} is pinned to node {node}, which {NODES.name} does not list")
            self.taken[(node, "block")].add(k)
            self.used[node]["block"] += 1
        self.pins = dict(pins)

    def freeze(self, wires: Iterable[wiring.Wire]) -> None:
        """Hold the node, LCOS number and pins of each frozen main or upper device (wiring.csv's turnout, fb and head
        rows of levels 2 and 3: a control point wired and frozen, freeze_wiring.py) before any other is given out,
        so the rule hands them to nothing else and gives the device the same values again (take_frozen). MapError
        on a node lcos_nodes.csv does not list for main or upper, or a row with no LCOS number."""
        known = {n for nodes in self.pool.values() for n in nodes}
        for w in wires:
            if w.node not in known:
                raise MapError(f"{PINS.name} line {w.line}: {w.device} is on node {w.node}, which {NODES.name} does "
                               "not list for main or upper")
            if w.index is None:
                raise MapError(f"{PINS.name} line {w.line}: {w.device} has no LCOS number to freeze")
            what = FROZEN_INPUT[w.kind]
            self.taken[(w.node, what)].add(w.index)
            self.used[w.node][what] += 1
            if w.kind == "head":                     # its pins, on one board or two
                for board, port in w.pins:
                    self.boards[w.node][int(board[2:])].add(port)
            elif w.kind == "turnout":
                self.turnout_boards[w.node].add(int(w.board[2:]))
                self.frozen_turnouts[w.node].add(w.index)
            self.frozen[(w.kind, w.device)] = w

    def take_frozen(self, kind: wiring.Kind, device: str) -> wiring.Wire | None:
        """wiring.csv's Wire of a frozen device, once; None when it is not frozen."""
        return self.frozen.pop((kind, device), None)

    def check_frozen(self) -> None:
        """Stop when a frozen row names a device the map does not give (a stale or misspelt row)."""
        if self.frozen:
            raise MapError(f"{PINS.name}: frozen rows for devices the device map does not give: "
                           f"{sorted(f'{k} {d}' for k, d in self.frozen)}")

    def room(self, node: int, what: Input, n: int = 1) -> bool:
        """Whether `node` has `n` more inputs of `what` to give."""
        return self.used[node][what] + n <= CAP[what]

    def staging(self, level: int) -> None:
        """MapError when `level` is staging's, whose nodes are never handed out."""
        if level == STAGING_LEVEL:
            raise MapError(f"level {level} is staging: its nodes in {NODES.name} are as built, and the rule hands "
                           "none out")

    def pick(self, level: int, area: str, what: Input, n: int = 1, prefer: Sequence[int] = ()) -> int:
        """The first node with room for `n` of `what`: those of `prefer`, then the level and area's in their order.
        MapError when none has room, or on staging's level."""
        self.staging(level)
        for node in list(prefer) + self.pool[(level, area)]:
            if self.room(node, what, n):
                return node
        raise MapError(f"level {level} {area}: no LCOS node left with room for {n} {what}(s); "
                       f"add one to {NODES.name}")

    def take(self, node: int, what: Input) -> InputSlot:
        """The node's lowest free index of `what` (one a pin holds is not free), and its packed id. A turnout's index
        is its board (index // 4 + 1, assign_ports): one on a board a frozen head is on is not free."""
        heads = {b for b, used in self.boards[node].items() if used}
        k = next((i for i in range(CAP[what]) if i not in self.taken[(node, what)]
                  and not (what == "turnout" and i // 4 + 1 in heads)), None)
        if k is None:
            raise MapError(f"node {node}: no {what} left (frozen heads in wiring.csv hold boards {sorted(heads)})")
        self.taken[(node, what)].add(k)
        self.used[node][what] += 1
        return InputSlot(k, node * 100 + UID[what] + k)

    def take_pinned(self, block: str) -> DetectorInput | None:
        """The input of `block`'s pinned detector, once; None when it has no pin."""
        if block not in self.pins:
            return None
        node, k = self.pins.pop(block)
        return DetectorInput(node, k, node * 100 + UID["block"] + k)

    def detector(self, block: str, level: int, area: str, prefer: int, pin_level: dict[str, int]) -> DetectorInput:
        """The input of `block`'s detector: its pin, else the next free block input of the node `pick`
        gives (`prefer` first). MapError on a pin of another level (`pin_level`: {block: level} of the pins)."""
        pinned = self.take_pinned(block)
        if pinned and pin_level.get(block, level) != level:
            raise MapError(f"{PINS.name}: {block} is a level {level} block, not level {pin_level[block]}")
        if pinned:
            return pinned
        node = self.pick(level, area, "block", prefer=[prefer])
        return DetectorInput(node, *self.take(node, "block"))

    def check_pins(self) -> None:
        """Stop when a pin names a block the map has no detector row for (a stale or misspelt pin)."""
        if self.pins:
            raise MapError(f"{PINS.name}: pins for blocks the device map gives no detector: {sorted(self.pins)}")

    # 5V boards for heads, after the node's 12V turnout boards (call once every turnout and detector is placed)
    def twelve(self, node: int) -> set[int]:
        """The node's turnout boards (12V): the rule's turnouts' (index // 4 + 1, assign_ports) and the frozen
        turnouts' own boards."""
        rule = {k // 4 + 1 for k in self.taken[(node, "turnout")] if k not in self.frozen_turnouts[node]}
        return rule | self.turnout_boards[node]

    def n12(self, node: int) -> int:
        """The node's last 12V board, the highest a turnout is on (0 with none): the rule's heads go after it."""
        return max(self.twelve(node), default=0)

    def _free(self, node: int, board: int) -> list[int]:
        """The pins of one 5V OU board a head may use: all eight but those taken, and pin 8 of the first 5V board on a
        node with detectors (its calibration relay)."""
        cal = board == self.n12(node) + 1 and self.used[node]["block"]
        return [p for p in range(1, 9) if p not in self.boards[node][board] and not (cal and p == 8)]

    def five_volt(self, node: int) -> list[int]:
        """The node's 5V boards with a head on them, in board order."""
        return sorted(b for b, used in self.boards[node].items() if used and b > self.n12(node))

    def _fit(self, node: int, pins: int) -> BoardRun | None:
        """Where `pins` consecutive pins fit, or None: the lowest run on the first 5V board with room (any of them,
        not only the last), else the next new board while the node has OU room."""
        last = max([self.n12(node)] + self.five_volt(node))
        for board in range(self.n12(node) + 1, last + 2):
            if board > MAX_OU:
                break
            free = set(self._free(node, board))
            for first in range(1, 10 - pins):
                if all(p in free for p in range(first, first + pins)):
                    return BoardRun(board, first)
        return None

    def pick_mast(self, level: int, area: str, heads: int, prefer: Sequence[int] = ()) -> int:
        """The first node with signal inputs and a 5V board run for a mast of `heads` heads: those of `prefer`,
        then the level and area's. NoBoardRoom when none has both; MapError on staging's level."""
        self.staging(level)
        for node in list(prefer) + self.pool[(level, area)]:
            if self.room(node, "signal", heads) and self._fit(node, 3 * heads):
                return node
        raise NoBoardRoom(f"level {level} {area}: no LCOS node left with board room for a {heads}-head mast; "
                       f"add one to {NODES.name}")

    def place_mast(self, node: int, heads: int) -> list[HeadPlace]:
        """Each head's place for a mast of `heads` heads on `node` (pick_mast's), all on one 5V board. MapError when
        the node has no run for them."""
        run = self._fit(node, 3 * heads)
        if run is None:
            raise MapError(f"node {node}: no 5V board run for a {heads}-head mast; pick_mast chooses its node")
        out = []
        for h in range(heads):
            k, packed = self.take(node, "signal")
            out.append(HeadPlace(k, packed, run.board, run.first + 3 * h))
        self.boards[node][run.board].update(range(run.first, run.first + 3 * heads))
        return out

    def check_boards(self) -> None:
        """A node with detectors needs a 5V board for the calibration pin; no node may need more than MAX_OU; no head
        is on a 12V board, or on a detector node's calibration relay pin (pin 8 of its first 5V board)."""
        for node, boards in self.boards.items():
            n12 = self.n12(node)
            on12 = sorted(b for b, used in boards.items() if used and b in self.twelve(node))
            if on12:
                raise MapError(f"node {node}: heads on OU{', OU'.join(map(str, on12))}, a 12V board a turnout is on; "
                               "move the frozen head or turnout in wiring.csv")
            if self.used[node]["block"] and 8 in boards.get(n12 + 1, set()):
                raise MapError(f"node {node}: a head is on OU{n12 + 1}-8, the calibration relay's pin of a node with "
                               "detectors; move it in wiring.csv")
        for node, used in self.used.items():
            five = max(len(self.five_volt(node)), 1 if used["block"] else 0)
            if self.n12(node) + five > MAX_OU:
                raise MapError(f"node {node} needs {self.n12(node) + five} DNOU8 boards; the limit is {MAX_OU}")
