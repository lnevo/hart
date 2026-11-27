# JMRI startup Jython script: validate the deployed HART bundle, then exit.
#
# Run through run_panelpro_smoke_test.sh. This file intentionally uses
# Python-2-compatible syntax because JMRI's embedded Jython requires it.

import json
import numbers
import os
import time
import traceback
from collections import namedtuple

import java.lang
import jmri


# The counts the loaded tables must hold come from panel_counts.json, the file audit_panel_contracts.py reads them
# from (audit_panel_graph.PanelCounts; Jython cannot import it): run_panelpro_smoke_test.sh passes its path in
# HART_PANEL_COUNTS. The smoke test takes the masts, the generated panel's sections and transits, and the traininfo.
COUNT_KEYS = ("generated", "hand_drawn", "masts", "traininfo")
PANEL_KEYS = ("sections", "sml", "transits")
Expected = namedtuple("Expected", "masts sections transits traininfo")


class CountsError(Exception):
    """The panel counts file is not named, cannot be read, or does not hold PanelCounts' keys and whole numbers."""


def _whole(value, where):
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < 0:
        raise CountsError("%s: expected a whole number of 0 or more, found %r" % (where, value))
    return int(value)


def _object(value, keys, where):
    if not isinstance(value, dict) or sorted(value) != sorted(keys):
        found = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise CountsError("%s: expected the keys %s, found %s" % (where, sorted(keys), found))
    return value


def expected_counts(path, parked):
    """The counts at `path` (HART_PANEL_COUNTS) the loaded tables must hold; no section or transit while the
    Dispatcher System is in `parked`. CountsError naming the file and the key when they cannot be read."""
    if not path:
        raise CountsError("HART_PANEL_COUNTS names no panel counts file (run_panelpro_smoke_test.sh sets it)")
    try:
        handle = open(path)
        try:
            data = json.load(handle)
        finally:
            handle.close()
    except (IOError, OSError, ValueError) as exc:
        raise CountsError("%s: cannot read the panel counts: %s" % (path, exc))
    top = _object(data, COUNT_KEYS, path)
    panels = {}
    for kind in ("generated", "hand_drawn"):
        counts = _object(top[kind], PANEL_KEYS, "%s %s" % (path, kind))
        panels[kind] = dict((key, _whole(counts[key], "%s %s.%s" % (path, kind, key))) for key in PANEL_KEYS)
    graph = "dispatcher" not in parked
    return Expected(_whole(top["masts"], path + " masts"), panels["generated"]["sections"] if graph else 0,
                    panels["generated"]["transits"] if graph else 0, _whole(top["traininfo"], path + " traininfo"))


# The parked features (hartlib.parked.PARKED; run_panelpro_smoke_test.sh passes them, Jython cannot import hartlib).
# While the Dispatcher System is parked the tables hold no section, transit or Dispatcher sensor and the traininfo
# files are not read; while the USS CTC machine or the Dispatcher System is parked its window must not open; while
# Entry/Exit is parked no pair is loaded.
PARKED = set(os.environ.get("HART_PARKED", "").split())
PARKED_WINDOWS = {"uss": u"USS CTC", "dispatcher": u"Dispatcher System"}
# The hidden band panels (hartlib.tables.BAND_PANEL_NAMES; Jython cannot import hartlib, test_band_panels.py holds the
# two lists equal): each loads as a Layout Editor panel and the "Hide windows on start" LogixNG hides its window.
BAND_PANELS = (u"Staging Level", u"Main Level", u"Upper Level")

# The main and upper blocks (internal IB:C3: blocks, hartlib.tables_build.master_beans) and their virtual occupancy
# sensors (their detector rows), which the LogixNG "Main and upper block sensors clear on start" sets INACTIVE when the
# tables load. The prefixes are hartlib.level_devices' (Jython cannot import hartlib;
# tools/hosts/tests/test_panelpro_wrappers.py checks they agree).
LEVEL_BLOCK_PREFIX = "IB:C3:"
LEVEL_SENSOR_PREFIX = "IS:HART:C3:B:"
LEVEL_TURNOUT_PREFIX = "IT:HART:C3:"      # the same LogixNG sets each to its startup position
# The prefix is the virtual turnouts' (hartlib.level_devices.TURNOUT_PREFIX), the ones the startup LogixNG sets: a
# main or upper turnout swapped to a physical one (ADR-028) leaves the startup LogixNG and this check with it, as it
# should, since a field turnout reports its own state (naming-layers step 11).


def level_sensors(sensor_manager):
    return [s for s in sensor_manager.getNamedBeanSet() if s.getSystemName().startswith(LEVEL_SENSOR_PREFIX)]


def field_detected(text):
    """{block system name: sensor system name} from HART_FIELD_DETECTED ("<block> <sensor>;" per block):
    the main and upper blocks on a field sensor, a detector swapped in by its device row (ADR-028).
    run_panelpro_smoke_test.sh writes it from the tables.xml PanelPro loads (hartlib.level_devices.field_detected)."""
    out = {}
    for item in (text or "").split(";"):
        parts = item.split()
        if len(parts) == 2:
            out[parts[0]] = parts[1]
        elif parts:
            raise ValueError("HART_FIELD_DETECTED: %r is not <block> <sensor>" % item)
    return out


def block_sensor_errors(blocks, field):
    """What is wrong with the main and upper blocks' sensors: `blocks` is (display name, system name, the
    occupancy sensor's system name or None) for each, `field` {block system name: sensor} (field_detected). A
    block with no sensor fails; one in `field` must be on that sensor; every other on a virtual block sensor."""
    out = []
    none = sorted(d for d, _s, sensor in blocks if sensor is None)
    if none:
        out.append("main and upper blocks with no occupancy sensor: %s" % ", ".join(none))
    wrong = sorted("%s (%s, not %s)" % (d, sensor, field[s]) for d, s, sensor in blocks
                   if sensor is not None and s in field and sensor != field[s])
    if wrong:
        out.append("main and upper blocks not on their field sensor: %s" % ", ".join(wrong))
    bad = sorted(d for d, s, sensor in blocks
                 if sensor is not None and s not in field and not sensor.startswith(LEVEL_SENSOR_PREFIX))
    if bad:
        out.append("main and upper blocks with no virtual occupancy sensor: %s" % ", ".join(bad))
    return out


def level_block_errors(block_manager, sensor_manager):
    """What waiting cannot fix: no virtual block sensor at all, no main and upper block, or a main or upper block
    with no sensor or not on its own (block_sensor_errors)."""
    out = []
    if not level_sensors(sensor_manager):
        out.append("no main and upper virtual block sensor (%s*)" % LEVEL_SENSOR_PREFIX)
    blocks = [b for b in block_manager.getNamedBeanSet() if b.getSystemName().startswith(LEVEL_BLOCK_PREFIX)]
    if not blocks:
        out.append("no main and upper block (%s*)" % LEVEL_BLOCK_PREFIX)
    try:
        field = field_detected(os.environ.get("HART_FIELD_DETECTED", ""))
    except ValueError as exc:
        out.append(str(exc))
        return out
    out.extend(block_sensor_errors(
        [(b.getDisplayName(), b.getSystemName(), b.getSensor().getSystemName() if b.getSensor() is not None else None)
         for b in blocks], field))
    return out


def level_uncleared(sensor_manager):
    """The main and upper virtual block sensors not INACTIVE (the LogixNG has not set them, or it did not run)."""
    return sorted(s.getSystemName() for s in level_sensors(sensor_manager)
                  if s.getKnownState() != jmri.Sensor.INACTIVE)


def level_unset_turnouts():
    """The main and upper virtual turnouts still UNKNOWN (the LogixNG has not set them, or it did not run)."""
    manager = jmri.InstanceManager.getDefault(jmri.TurnoutManager)
    return sorted(t.getSystemName() for t in manager.getNamedBeanSet()
                  if t.getSystemName().startswith(LEVEL_TURNOUT_PREFIX) and t.getKnownState() == jmri.Turnout.UNKNOWN)


STATIONS = (
    u"Track K-1",
    u"Track K-2",
    u"Track East Lead",
    u"Track EH-1",
    u"Track EH-2",
    u"Track EH-3",
    u"Track Scale",
    u"Track Barn",
    u"Track W-1",
    u"Track W-2",
    u"Track Helix Outer",
    u"Track Helix Inner",
)


def station_key(name):
    return name.replace(" ", "_")


def bean_count(manager):
    return int(manager.getNamedBeanSet().size())


def parked_errors():
    """What a parked feature must not leave loaded: its windows, panels and Entry/Exit pairs."""
    errors = []
    titles = set()
    for frame in jmri.util.JmriJFrame.getFrameList():
        titles.add(frame.getTitle())
    editors = jmri.InstanceManager.getDefault(jmri.jmrit.display.EditorManager)
    names = set(editor.getTitle() for editor in editors.getAll())
    for feature, title in sorted(PARKED_WINDOWS.items()):
        if feature in PARKED and (title in titles or title in names):
            errors.append("parked %s: window or panel %s loaded" % (feature, title))
    if "nx" in PARKED:
        nx = jmri.InstanceManager.getDefault(
            jmri.jmrit.entryexit.EntryExitPairs
        )
        pairs = nx.getNamedBeanSet().size()
        if pairs:
            errors.append("parked nx: %s Entry/Exit pairs loaded" % pairs)
    if "uss" in PARKED:
        sensor_manager = jmri.InstanceManager.getDefault(jmri.SensorManager)
        for name in ("IS1:LEVER", "IS:FLEETING"):
            if sensor_manager.getBySystemName(name) is not None:
                errors.append("parked uss: CTC sensor %s loaded" % name)
    return errors


def band_panel_errors(wait):
    """Each band panel loaded as a Layout Editor panel and its window hidden by the LogixNG's hide_band_panels.py,
    which waits for the windows to open. First each band window must exist and have been hidden once (up to 30 s;
    a window shown before the script reaches it is not a failure), then each must stay hidden over six polls in three
    seconds, so a window PanelPro shows again later is still seen."""
    editors = jmri.InstanceManager.getDefault(jmri.jmrit.display.EditorManager)
    names = set(editor.getTitle() for editor in editors.getAll())
    errors = ["band panel %s not loaded" % title for title in BAND_PANELS if title not in names]

    def frame(title):
        return jmri.util.JmriJFrame.getFrame(title)

    hidden_once = set()
    for _ in range(60):
        hidden_once.update(t for t in BAND_PANELS if frame(t) is not None and not frame(t).isVisible())
        if len(hidden_once) == len(BAND_PANELS):
            break
        wait(500)
    errors.extend("band panel %s has no window" % t for t in BAND_PANELS if frame(t) is None)
    errors.extend("band panel %s window never hidden; the LogixNG should hide it" % t for t in BAND_PANELS
                  if frame(t) is not None and t not in hidden_once)
    shown = set()
    for _ in range(6):
        wait(500)
        shown.update(t for t in hidden_once if frame(t) is not None and frame(t).isVisible())
    errors.extend("band panel %s window shown again after it was hidden" % t for t in sorted(shown))
    return errors


def station_sensor_errors(sensor_manager):
    """Each station's two Dispatcher sensors: loaded unless the Dispatcher System is parked, absent if it is."""
    errors = []
    for station in STATIONS:
        key = station_key(station)
        for user_name in ("MoveTo%s_stored" % key, "MoveInProgress%s" % key):
            present = sensor_manager.getByUserName(user_name) is not None
            if "dispatcher" in PARKED and present:
                errors.append("parked Dispatcher sensor %s loaded" % user_name)
            elif "dispatcher" not in PARKED and not present:
                errors.append("missing sensor %s" % user_name)
    return errors


def count_errors(expected, mast_manager, section_manager, transit_manager):
    """The mast, section and transit counts against `expected` (an Expected)."""
    errors = []
    for what, manager, want in (("signal masts", mast_manager, expected.masts),
                                ("sections", section_manager, expected.sections),
                                ("transits", transit_manager, expected.transits)):
        got = bean_count(manager)
        if got != want:
            errors.append("%s=%s expected=%s" % (what, got, want))
    return errors


def ordered_route(internal_names, start_name, destination_name):
    """True when the transit's blocks hold the start block and, after it, the destination."""
    for start_index, block_name in enumerate(internal_names):
        if block_name == start_name and destination_name in internal_names[start_index + 1:]:
            return True
    return False


def traininfo_errors(transit_manager, want):
    """Every runtime TrainInfo file: `want` of them, each readable, on a transit that exists, with its start
    block before its destination and its block sequence inside the transit."""
    errors = []
    traininfo_dir = jmri.util.FileUtil.getExternalFilename("preference:dispatcher/traininfo/")
    traininfo_files = sorted(name for name in os.listdir(traininfo_dir) if name.endswith(".xml"))
    if len(traininfo_files) != want:
        errors.append("runtime TrainInfo files=%s expected=%s" % (len(traininfo_files), want))
    for name in traininfo_files:
        info = jmri.jmrit.dispatcher.TrainInfoFile().readTrainInfo(name)
        if info is None:
            errors.append("unreadable TrainInfo %s" % name)
            continue
        transit = transit_manager.getByUserName(info.getTransitName())
        if transit is None:
            errors.append("TrainInfo %s references missing transit %s" % (name, info.getTransitName()))
            continue
        internal_names = [block.getUserName() for block in transit.getInternalBlocksList()]
        start_name = info.getStartBlockName()
        destination_name = info.getDestinationBlockName()
        if not ordered_route(internal_names, start_name, destination_name):
            errors.append("TrainInfo %s transit lacks ordered route %s -> %s" % (name, start_name, destination_name))
            continue
        start_sequence = info.getStartBlockSeq()
        destination_sequence = info.getDestinationBlockSeq()
        if (
            start_sequence < 1
            or destination_sequence < start_sequence
            or destination_sequence > transit.getMaxSequence()
        ):
            errors.append("TrainInfo %s has invalid sequence %s..%s for %s"
                          % (name, start_sequence, destination_sequence, transit.getMaxSequence()))
    return errors


def _line(text):
    if isinstance(text, unicode):
        return text.encode("utf-8")
    return str(text)


def marker_text(errors, level_line, expected):
    """What the marker file says: "fail" and each error, or "ok" and what was checked against `expected` (an
    Expected; None when the counts could not be read, which is an error)."""
    if errors:
        return "fail\n" + "\n".join(_line(item) for item in errors)
    if "dispatcher" in PARKED:
        return ("ok\n%s masts; %s; parked %s: no section, transit, Dispatcher sensor or parked window; "
                "band panels %s loaded and hidden\n"
                % (expected.masts, level_line, " ".join(sorted(PARKED)), ", ".join(BAND_PANELS)))
    return ("ok\n%s masts; %s; 24 station sensors; %s sections; %s transits; "
            "%s ordered TrainInfo routes; band panels %s loaded and hidden\n"
            % (expected.masts, level_line, expected.sections, expected.transits, expected.traininfo,
               ", ".join(BAND_PANELS)))


class HartSmoke(jmri.jmrit.automat.AbstractAutomaton):
    def handle(self):
        self.level_line = "main and upper block sensors not checked"
        marker = os.environ.get(
            "HART_PANELPRO_SMOKE_MARKER", "/tmp/hart_panelpro_smoke.done"
        )
        errors = []
        expected = None
        deadline = time.time() + 90
        try:
            expected = expected_counts(os.environ.get("HART_PANEL_COUNTS", ""), PARKED)
            sensor_manager = jmri.InstanceManager.getDefault(jmri.SensorManager)
            mast_manager = jmri.InstanceManager.getDefault(jmri.SignalMastManager)
            section_manager = jmri.InstanceManager.getDefault(jmri.SectionManager)
            transit_manager = jmri.InstanceManager.getDefault(jmri.TransitManager)
            self._wait_for_load(expected, mast_manager, section_manager, transit_manager, deadline)
            errors.extend(station_sensor_errors(sensor_manager))
            errors.extend(count_errors(expected, mast_manager, section_manager, transit_manager))
            errors.extend(parked_errors())
            errors.extend(band_panel_errors(self.waitMsec))
            errors.extend(self._level_errors(sensor_manager, deadline))
            if "dispatcher" not in PARKED:
                errors.extend(traininfo_errors(transit_manager, expected.traininfo))
        except CountsError as exc:
            errors.append(str(exc))
        except Exception:
            errors.append(traceback.format_exc())

        handle = open(marker, "w")
        try:
            handle.write(marker_text(errors, self.level_line, expected))
        finally:
            handle.close()

        java.lang.System.exit(1 if errors else 0)
        return False

    def _wait_for_load(self, expected, mast_manager, section_manager, transit_manager, deadline):
        """Until `deadline`: wait for the `expected` masts, sections and transits (each transit with its blocks)
        and the HART Railroad panel, then 2 s more."""
        while time.time() < deadline:
            transits = list(transit_manager.getNamedBeanSet())
            if (
                bean_count(mast_manager) == expected.masts
                and bean_count(section_manager) == expected.sections
                and len(transits) == expected.transits
                and all(
                    len(transit.getInternalBlocksList()) > 0
                    for transit in transits
                )
                # the panels load after the masts: wait for the Layout Editor panel too, so the parked
                # window and NX checks below see every panel the tables open
                and jmri.util.JmriJFrame.getFrame("HART Railroad") is not None
            ):
                self.waitMsec(2000)
                return
            self.waitMsec(1000)

    def _level_errors(self, sensor_manager, deadline):
        """The main and upper blocks, their sensors and turnouts after the start-up LogixNG; sets level_line."""
        block_manager = jmri.InstanceManager.getDefault(jmri.BlockManager)
        errors = list(level_block_errors(block_manager, sensor_manager))
        # the LogixNG runs on its own thread after load, and each sensor it sets updates the blocks and
        # masts: wait for it (and only for it) a while past the deadline
        while (level_uncleared(sensor_manager) or level_unset_turnouts()) and time.time() < deadline + 60:
            self.waitMsec(1000)
        unset = level_unset_turnouts()
        if unset:
            errors.append("main and upper turnouts still Unknown after load: %s" % ", ".join(unset))
        left = level_uncleared(sensor_manager)
        if left:
            errors.append("main and upper block sensors not clear after load (%s of %s): %s"
                          % (len(left), len(level_sensors(sensor_manager)), ", ".join(left)))
        turnouts = [t for t in jmri.InstanceManager.getDefault(jmri.TurnoutManager).getNamedBeanSet()
                    if t.getSystemName().startswith(LEVEL_TURNOUT_PREFIX)]
        thrown = len([t for t in turnouts if t.getKnownState() == jmri.Turnout.THROWN])
        closed = len([t for t in turnouts if t.getKnownState() == jmri.Turnout.CLOSED])
        self.level_line = ("%s main and upper block sensors clear; main and upper turnouts %s closed, %s thrown, "
                           "%s unknown" % (len(level_sensors(sensor_manager)), closed, thrown, len(unset)))
        return errors


HartSmoke().start()
