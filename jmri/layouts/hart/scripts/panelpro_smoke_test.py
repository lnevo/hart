# JMRI startup Jython script: validate the deployed HART bundle, then exit.
#
# Run through run_panelpro_smoke_test.sh. This file intentionally uses
# Python-2-compatible syntax because JMRI's embedded Jython requires it.

import os
import time
import traceback

import java.lang
import jmri


# Matches reconcile_dispatcher_stations.STATIONS (Jython 2 cannot import it).
# The cut-over panel (2026-11-16): 49 staging masts plus the 41 main and upper control-point masts; staging's sections
# less the 8 head-on pairs Discover drops, plus the main and upper sections (audit_panel_contracts EXPECTED_GRAPH).
MASTS = 90
SECTIONS = 197
TRANSITS = 187
TRAININFO = 374
# The parked features (hartlib.parked.PARKED; run_panelpro_smoke_test.sh passes them, Jython cannot import hartlib).
# While the Dispatcher System is parked the tables hold no section, transit or Dispatcher sensor and the traininfo
# files are not read; while the USS CTC machine or the Dispatcher System is parked its window must not open; while
# Entry/Exit is parked no pair is loaded.
PARKED = set(os.environ.get("HART_PARKED", "").split())
PARKED_WINDOWS = {"uss": u"USS CTC", "dispatcher": u"Dispatcher System"}
if "dispatcher" in PARKED:
    SECTIONS = 0
    TRANSITS = 0

# The main and upper blocks' virtual occupancy sensors (build_layout_le.add_level_sensors), which the LogixNG
# "Main and upper block sensors clear on start" sets INACTIVE when the tables load (owner, 2026-11-17).
LEVEL_SENSOR_PREFIX = "IS:HART:C3:B:"
LEVEL_SENSORS = 125


def level_sensor_errors(sensor_manager):
    """The main and upper virtual block sensors not INACTIVE after load, or a count other than LEVEL_SENSORS."""
    level = [s for s in sensor_manager.getNamedBeanSet() if s.getSystemName().startswith(LEVEL_SENSOR_PREFIX)]
    out = []
    if len(level) != LEVEL_SENSORS:
        out.append("main and upper virtual block sensors=%s expected=%s" % (len(level), LEVEL_SENSORS))
    left = sorted(s.getSystemName() for s in level if s.getKnownState() != jmri.Sensor.INACTIVE)
    if left:
        out.append("main and upper block sensors not clear after load (%s of %s): %s" % (len(left), len(level), ", ".join(left)))
    return out


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
    u"Track McKees Rocks",
    u"Track McKeesport",
)


def station_key(name):
    return name.replace(" ", "_")


def bean_count(manager):
    return int(manager.getNamedBeanSet().size())


class _Done(Exception):
    """The checks of a parked Dispatcher System are done (no traininfo to read)."""


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


class HartSmoke(jmri.jmrit.automat.AbstractAutomaton):
    def handle(self):
        marker = os.environ.get(
            "HART_PANELPRO_SMOKE_MARKER", "/tmp/hart_panelpro_smoke.done"
        )
        errors = []
        deadline = time.time() + 90
        try:
            sensor_manager = jmri.InstanceManager.getDefault(jmri.SensorManager)
            mast_manager = jmri.InstanceManager.getDefault(jmri.SignalMastManager)
            section_manager = jmri.InstanceManager.getDefault(jmri.SectionManager)
            transit_manager = jmri.InstanceManager.getDefault(jmri.TransitManager)

            while time.time() < deadline:
                transits = list(transit_manager.getNamedBeanSet())
                if (
                    bean_count(mast_manager) == MASTS
                    and bean_count(section_manager) == SECTIONS
                    and len(transits) == TRANSITS
                    and all(
                        len(transit.getInternalBlocksList()) > 0
                        for transit in transits
                    )
                    # the panels load after the masts: wait for the Layout Editor panel too, so the parked
                    # window and NX checks below see every panel the tables open
                    and jmri.util.JmriJFrame.getFrame("HART Railroad") is not None
                ):
                    self.waitMsec(2000)
                    break
                self.waitMsec(1000)

            for station in STATIONS:
                key = station_key(station)
                for user_name in (
                    "MoveTo%s_stored" % key,
                    "MoveInProgress%s" % key,
                ):
                    present = sensor_manager.getByUserName(user_name) is not None
                    if "dispatcher" in PARKED and present:
                        errors.append("parked Dispatcher sensor %s loaded" % user_name)
                    elif "dispatcher" not in PARKED and not present:
                        errors.append("missing sensor %s" % user_name)

            if bean_count(mast_manager) != MASTS:
                errors.append(
                    "signal masts=%s expected=%s" % (bean_count(mast_manager), MASTS)
                )
            if bean_count(section_manager) != SECTIONS:
                errors.append(
                    "sections=%s expected=%s" % (bean_count(section_manager), SECTIONS)
                )
            if bean_count(transit_manager) != TRANSITS:
                errors.append(
                    "transits=%s expected=%s" % (bean_count(transit_manager), TRANSITS)
                )
            errors.extend(parked_errors())
            # the LogixNG runs on its own thread after load, and each sensor it sets updates the blocks and
            # masts: give it until the deadline
            while level_sensor_errors(sensor_manager) and time.time() < deadline + 60:
                self.waitMsec(1000)
            errors.extend(level_sensor_errors(sensor_manager))
            if "dispatcher" in PARKED:
                raise _Done()

            traininfo_dir = jmri.util.FileUtil.getExternalFilename(
                "preference:dispatcher/traininfo/"
            )
            traininfo_files = sorted(
                name for name in os.listdir(traininfo_dir) if name.endswith(".xml")
            )
            if len(traininfo_files) != TRAININFO:
                errors.append(
                    "runtime TrainInfo files=%s expected=%s"
                    % (len(traininfo_files), TRAININFO)
                )
            for name in traininfo_files:
                info = jmri.jmrit.dispatcher.TrainInfoFile().readTrainInfo(name)
                if info is None:
                    errors.append("unreadable TrainInfo %s" % name)
                    continue
                transit = transit_manager.getByUserName(info.getTransitName())
                if transit is None:
                    errors.append(
                        "TrainInfo %s references missing transit %s"
                        % (name, info.getTransitName())
                    )
                    continue
                internal_names = [
                    block.getUserName()
                    for block in transit.getInternalBlocksList()
                ]
                start_name = info.getStartBlockName()
                destination_name = info.getDestinationBlockName()
                ordered = False
                for start_index, block_name in enumerate(internal_names):
                    if block_name != start_name:
                        continue
                    if destination_name in internal_names[start_index + 1 :]:
                        ordered = True
                        break
                if not ordered:
                    errors.append(
                        "TrainInfo %s transit lacks ordered route %s -> %s"
                        % (name, start_name, destination_name)
                    )
                    continue

                start_sequence = info.getStartBlockSeq()
                destination_sequence = info.getDestinationBlockSeq()
                if (
                    start_sequence < 1
                    or destination_sequence < start_sequence
                    or destination_sequence > transit.getMaxSequence()
                ):
                    errors.append(
                        "TrainInfo %s has invalid sequence %s..%s for %s"
                        % (
                            name,
                            start_sequence,
                            destination_sequence,
                            transit.getMaxSequence(),
                        )
                    )
        except _Done:
            pass
        except Exception:
            errors.append(traceback.format_exc())

        def _line(text):
            if isinstance(text, unicode):
                return text.encode("utf-8")
            return str(text)

        handle = open(marker, "w")
        try:
            if errors:
                handle.write("fail\n")
                handle.write("\n".join(_line(item) for item in errors))
            else:
                handle.write("ok\n")
                if "dispatcher" in PARKED:
                    handle.write(
                        "%s masts; %s main and upper block sensors clear; parked %s: no section, transit, "
                        "Dispatcher sensor or parked window\n" % (MASTS, LEVEL_SENSORS, " ".join(sorted(PARKED)))
                    )
                else:
                    handle.write(
                        "%s masts; 24 station sensors; %s sections; %s transits; "
                        "%s ordered TrainInfo routes\n"
                        % (MASTS, SECTIONS, TRANSITS, TRAININFO)
                    )
        finally:
            handle.close()

        java.lang.System.exit(1 if errors else 0)
        return False


HartSmoke().start()
