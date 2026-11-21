"""build_cats_panel.py's facts: what the bindings are written from (load_facts reads them from the repo), the
staging tracks, the main and upper device map and the mast templates. Moved out of build_cats_panel.py unchanged."""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_draft as pd  # noqa: E402  the pinned plugin and the sheet cache
import mast_rule as mr  # noqa: E402  the helix tracks (plan_overrides.json)
import staging_device_map as sdm  # noqa: E402  the staging tracks and their blocks (the staging rows of devices.csv)
from hartlib import paths, railroad  # noqa: E402
from hartlib.cats import appearance_templates, mast_templates  # noqa: E402

sys.path[:0] = [str(paths.CATS_DIR / "scripts"), str(paths.LAYOUT_SCRIPTS)]
import cats_turnout_io as tio  # noqa: E402
import digicon_lib as le  # noqa: E402

DEVICE_MAP = railroad.Sources.under().devices      # devices.csv


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
            raise SystemExit(f"{what}: {'no' if not found else len(found)} staging tracks join {a} and {b} "
                             "in the staging device map; cannot tell which block it is part of")
        blocks = found[0]["blocks"]
        if len(set(blocks)) != 1:
            raise SystemExit(f"{what}: the staging track from {a} to {b} holds blocks "
                             f"{', '.join(sorted(set(blocks)))}; give it to the one its gap leaves it in "
                             "(a part row naming that block in devices.csv: block_overrides.csv, or the rule in "
                             "block_layer.py)")
        return blocks[0]


# The main and upper rows of devices.csv: block rows (each with its level and the schematic tracks it holds, `trial`) and
# occupancy sensors by name (virtual, and the planned detector when there is one); hartlib.railroad reads and checks it.
DeviceMap = railroad.DeviceMap


def load_device_map(path=DEVICE_MAP):
    try:
        return railroad.read_device_map(path)
    except railroad.FactsError as exc:
        raise SystemExit(f"build_cats_panel.py: {exc}") from None


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
    level_masts: list = field(default_factory=list)         # main_upper_masts.csv rows (hartlib.level_masts)
    helix: dict = field(default_factory=dict)       # helix track's shown name (the desk's) -> its block (read_helix_tracks)


def staging_tracks() -> list[dict]:
    """The staging tracks (staging_device_map.staging_chains) of the staging band as the Layout Editor draws it."""
    try:
        with pd.cache_on():
            band, _opts, _core = sdm.staging_band()
        return sdm.staging_chains(band, sdm.load(band))
    except (sdm.StagingMapError, sdm.lc.BuildError) as exc:      # the map, or the plugin and the drawing
        raise SystemExit(f"build_cats_panel.py: staging device map: {exc}") from None


def load_facts():
    """The facts from the repo (hartlib.railroad, every layer: the desks are built after the device map and the
    main and upper masts): tables.xml (read once) for its turnouts, sensors, layout blocks and masts, never a Layout
    Editor panel; the staging tracks from the staging device map."""
    rr = railroad.Railroad()
    try:
        t = rr.tables
        return Facts(rr.switches, tio.load_turnouts(t.root, rr.switches), le.load_occupancy(t.root), le.load_disciplines(),
                     StagingTracks(staging_tracks()), mast_templates(systems=t.masts), set(t.masts),
                     rr.device_map,
                     t.sensors, t.turnouts, t.masts, rr.level_masts,
                     {h["shown"]: h["block"] for h in mr.read_helix_tracks().values()})
    except (railroad.FactsError, mr.MapError) as exc:
        raise SystemExit(f"build_cats_panel.py: {exc}") from None


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
        raise SystemExit(str(exc)) from None
    # the stock basic appearances by head count, where the plan gives none: one head shows Clear, Approach and Stop
    # (CATS "single"), two add the Diverging aspects ("double"); a dwarf shows the aspects of its high twin. The
    # wiring plan lists wired masts only (6LB since 2026-11-19), so most types come from here.
    for kind, template in (("one-low", "single"), ("one-searchlight", "single"), ("two-searchlight", "double"),
                           ("two-low", "double")):
        out.setdefault(kind, template)
    return out
