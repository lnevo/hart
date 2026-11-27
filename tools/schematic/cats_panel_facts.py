"""build_cats_panel.py's facts: what the bindings are written from (load_facts reads them from the repo), the
staging tracks, the main and upper device map and the mast templates; and CatsPanelError, the error every desk module
raises."""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  the pinned plugin and the sheet cache
from map_error import MapError  # noqa: E402
import plan_bands  # noqa: E402
import staging_device_map as sdm  # noqa: E402  the staging tracks and their blocks (the staging rows of the device master)
from hartlib import hand_lists, paths, railroad  # noqa: E402
from hartlib.errors import HartlibError  # noqa: E402
from hartlib.cats import appearance_templates, mast_templates  # noqa: E402

sys.path[:0] = [str(paths.CATS_DIR / "scripts"), str(paths.LAYOUT_SCRIPTS)]
import cats_turnout_io as tio  # noqa: E402
import digicon_lib as le  # noqa: E402

DEVICE_MAP = railroad.Sources.under().devices      # the device master


class CatsPanelError(HartlibError):
    """A fact the desks are built from that is missing, doubled or contradicts another: the message names the file,
    switch, block or mast. build_cats_panel.main turns it into an exit."""


class StagingTracks:
    """The staging tracks between switches and ends, each with its blocks in order: staging_device_map.staging_chains
    (ends by switches.csv le_ident)."""

    def __init__(self, chains):
        self.chains = chains            # [{ends: [(le_ident or "END", band port), ...], blocks: [...]}]

    def block_between(self, a, b, what):
        """The block of the one staging track from turnout `a` to `b`: its only block. Stops when there is no such
        track, several, or a track of several blocks (one desk cell takes one block: the staging device map must give
        the track to one of them, where its gap is)."""
        found = [c for c in self.chains if {e[0] for e in c["ends"]} == {a, b} and "END" not in
                 {e[0] for e in c["ends"]} and a != b]
        if len(found) != 1:
            raise CatsPanelError(f"{what}: {'no' if not found else len(found)} staging tracks join {a} and {b} "
                             "in the staging device map; cannot tell which block it is part of")
        blocks = found[0]["blocks"]
        if len(set(blocks)) != 1:
            raise CatsPanelError(f"{what}: the staging track from {a} to {b} holds blocks "
                             f"{', '.join(sorted(set(blocks)))}; give it to the one its gap leaves it in "
                             "(a part row naming that block in the device master: block_overrides.csv, or the rule in "
                             "block_layer.py)")
        return blocks[0]


# The main and upper rows of the device master: block rows (each with its level and the schematic tracks it holds, `trial`) and
# each block's occupancy row (its virtual sensor, and the planned detector when there is one); hartlib.railroad reads and
# checks it.
DeviceMap = railroad.DeviceMap


def load_device_map(path=DEVICE_MAP):
    try:
        return railroad.read_device_map(path)
    except railroad.FactsError as exc:
        raise CatsPanelError(f"build_cats_panel.py: {exc}") from exc


@dataclass
class Facts:
    """What the bindings are written from (load_facts reads them from the repo)."""
    switches: dict              # number -> hartlib.railroad.Switch
    turnout_io: dict            # Layout Editor turnout -> (M2T address, user name)
    occupancy: dict             # block -> (M2S address, sensor user name)
    discipline: dict            # block -> CATS discipline
    layout: StagingTracks
    templates: dict             # mast user name -> signal template
    masts: set                  # JMRI mast user names
    device: DeviceMap = field(default_factory=DeviceMap)   # main and upper
    sensors: dict = field(default_factory=dict)             # JMRI sensor user name -> system name
    turnouts: dict = field(default_factory=dict)            # JMRI turnout user name -> system name
    mast_system: dict = field(default_factory=dict)         # JMRI mast user name -> system name
    level_masts: list = field(default_factory=list)         # masts.csv rows of the device map's levels (hartlib.level_masts)
    helix: dict = field(default_factory=dict)       # plan helix track name -> its block (read_helix_tracks)
    half_letters: dict = field(default_factory=dict)   # (level, crossover half's OS block ID) -> a or b (half_label)


def staging_tracks() -> list[dict]:
    """The staging tracks (staging_device_map.staging_chains) of the staging band as the Layout Editor draws it."""
    try:
        with pd.cache_on():
            band, _opts, _core = sdm.staging_band()
        return sdm.staging_chains(band, sdm.load(band))
    except (sdm.StagingMapError, sdm.lc.BuildError) as exc:      # the map, or the plugin and the drawing
        raise CatsPanelError(f"build_cats_panel.py: staging device map: {exc}") from exc


def load_facts(rr: railroad.Railroad | None = None):
    """The facts from the repo (hartlib.railroad, every layer: the desks are built after the device map and the
    main and upper masts): tables.xml (read once) for its turnouts, sensors, layout blocks and masts, never a Layout
    Editor panel; the staging tracks from the staging device map. `rr`: a Railroad over other sources (a test's copy
    of the device master and its tables); default the repo's."""
    rr = railroad.Railroad() if rr is None else rr
    try:
        t = rr.tables
        dm_levels = {r.level for r in rr.device_map.rows}       # main and upper: the device map's levels
        return Facts(rr.switches, tio.load_turnouts(t.root, rr.switches), le.load_occupancy(t.root, rr.sources.devices),
                     le.load_disciplines(rr.sources.devices),
                     StagingTracks(staging_tracks()), mast_templates(systems=t.masts), set(t.masts),
                     rr.device_map,
                     t.sensors, t.turnouts, t.masts, [r for r in rr.masts if r["level"] in dm_levels],
                     {plan: h["block"] for plan, h in plan_bands.read_helix_tracks().items()},
                     hand_lists.half_letters(Path(pd.DATA) / hand_lists.OVERRIDES_NAME))
    except (railroad.FactsError, MapError, hand_lists.HandListError) as exc:
        raise CatsPanelError(f"build_cats_panel.py: {exc}") from exc


def mast_type(system):
    """A signal head mast's appearance type from its system name (IF$shsm:basic:one-low(IH1) -> one-low)."""
    m = re.match(r"IF\$(?:shsm|vsm):[^:]+:([^()]+)\(", system or "")
    return m.group(1) if m else None


def template_by_type(F):
    """{appearance type: CATS template}: as signal_head_plan.csv gives them (hartlib.cats.appearance_templates), and
    the stock basic types by head count where it gives none. `F` is unused: kept so the callers stay as they were."""
    try:
        out = appearance_templates()
    except ValueError as exc:
        raise CatsPanelError(str(exc)) from exc
    # the stock basic appearances by head count, where the plan gives none: one head shows Clear, Approach and Stop
    # (CATS "single"), two add the Diverging aspects ("double"); a dwarf shows the aspects of its high twin. The
    # wiring plan lists wired masts only (6LB since 2026-11-19), so most types come from here.
    for kind, template in (("one-low", "single"), ("one-searchlight", "single"), ("two-searchlight", "double"),
                           ("two-low", "double")):
        out.setdefault(kind, template)
    return out
