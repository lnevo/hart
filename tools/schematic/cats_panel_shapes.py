"""cats_panel.py's shapes of the bindings, the same on every level (turnout_routes, occupancy_spec,
block_entry, mast_template), and the prefixes and disciplines they are made with. Moved out of
cats_panel.py unchanged; cats_panel.py re-exports every name."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_device_map as bdm  # noqa: E402  the device map's naming helpers (base, band_level, natural)
from hartlib.cats import station_plate  # noqa: E402

from cats_panel_facts import mast_type  # noqa: E402

# Main and upper: CTC on the CTC desk, CATS holds their signals and releases them (owner, 2026-11-17); ABS on the twin
MAIN_UPPER_DISCIPLINE = "CTC"
# The discipline of a staging block occupancy_bindings.csv gives none
STAGING_DISCIPLINE = "CTC"
# The staging turnouts and detectors: LCOS over MQTT (M2T, M2S)
STAGING_TURNOUT_PREFIX = "M2T"
STAGING_SENSOR_PREFIX = "M2S"
# A main or upper switch is commanded and reported by the turnout tables.xml holds under its user name, Switch <n>:
# its device-master row's bean (hartlib.tables_build.bean_name, the row's jmri_name; internal until the plant is
# wired, hartlib.level_devices), so a swap to a physical turnout is one row edit (ADR-028) and the desk follows it.
# It is closed on the drawn leg B: the Layout Editor builder gives these levels no normal leg, so the plugin draws leg
# B as the route the turnout's closed state sets (continuing 2 when leg B is Layout Editor leg B, 4 when it is leg
# C), as the desk's NORMAL is leg B.
LEVEL_SENSOR_PREFIX = "IS"          # a main or upper block's virtual occupancy sensor (IS:HART:C3:B:...)
# A JMRI system name: the connection's letter and digits and the type letter (IT, M2T: the desk's JMRIPREFIX), then
# the rest (its DECADDR)
_SYSTEM_NAME = re.compile(r"([A-Z]\d*[A-Z])(.+)")


def split_system_name(system: str) -> tuple[str, str]:
    """(JMRIPREFIX, DECADDR) of a JMRI system name: "IT:HART:C3:107" -> ("IT", ":HART:C3:107"), "M2T408" -> ("M2T",
    "408"). SystemExit on a name of no such shape."""
    m = _SYSTEM_NAME.fullmatch(system or "")
    if not m:
        raise SystemExit(f"{system!r} is not a JMRI system name (connection letter and digits, type letter, name)")
    return m.group(1), m.group(2)


# --- every level: the shapes of the bindings -------------------------------------------------------------------

def legs_of(d):
    """{leg: strand} of a drawn node, its in and out legs together."""
    return d["ins"] | d["outs"]


def level_band(bands, bi, bound_bi) -> bool:
    """True for band `bi` when it is a main or upper band (bdm.band_level by its title), not the bound one."""
    return bi != bound_bi and bool(bdm.band_level(bands[bi][0]))


def level_bands(bands, bound_bi):
    """[(band index, band, options)] of the main and upper bands."""
    return [(bi, band, opts) for bi, (_title, band, opts) in enumerate(bands) if level_band(bands, bi, bound_bi)]


def turnout_routes(prefix, addr, user, closed, thrown) -> dict:
    """The routes of a switch whose leg `closed` the turnout's closed state sets and leg `thrown` its thrown state:
    each leg's SELECTEDREPORT and ROUTECOMMAND, the turnout `prefix` + `addr` (user name `user`)."""
    if {closed, thrown} != {"B", "C"}:
        raise SystemExit(f"{user}: closed leg {closed!r} and thrown leg {thrown!r} must be legs B and C, one each")
    io = lambda cmd: {"DECADDR": addr, "JMRIPREFIX": prefix, "USER_NAME": user, "command": cmd}
    return {closed: {"SELECTEDREPORT": io("close"), "ROUTECOMMAND": io("close")},
            thrown: {"SELECTEDREPORT": io("throw"), "ROUTECOMMAND": io("throw")}}


def occupancy_spec(prefix, addr, user) -> dict:
    """The OCCUPIEDSPEC / UNOCCUPIEDSPEC of a block bound to sensor `prefix` + `addr` (user name `user`): occupied
    when it closes, unoccupied when it throws."""
    return {"occupied": {"DECADDR": addr, "JMRIPREFIX": prefix, "USER_NAME": user, "command": "close"},
            "unoccupied": {"DECADDR": addr, "JMRIPREFIX": prefix, "command": "throw"}}


def block_entry(panel_name, name, discipline, plate=None) -> dict:
    """A desk block's binding before its sensor: the JMRI block `name` it takes (left out when it is the panel name
    `panel_name`), its station plate (`plate`, else station_plate of the name) and its CATS discipline."""
    e = {"name": name, "station": plate or station_plate(name), "discipline": discipline}
    if name == panel_name:
        del e["name"]
    return e


def mast_template(name, F, by_type):
    """The CATS template of mast `name` on any level: its own row in signal_head_plan.csv (a wired mast) wins, else
    the one masts of its appearance type take (`by_type`, template_by_type), by its system name in tables.xml; None
    when neither. One rule for every level: a main or upper mast given a row of its own takes that row's template."""
    return F.templates.get(name) or by_type.get(mast_type(F.mast_system.get(name)))
