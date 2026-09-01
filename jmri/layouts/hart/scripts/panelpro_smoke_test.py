# JMRI startup Jython script: validate the deployed HART bundle, then exit.
#
# Run through run_panelpro_smoke_test.sh. This file intentionally uses
# Python-2-compatible syntax because JMRI's embedded Jython requires it.

import os
import time
import traceback

import java.lang
import jmri


STATIONS = (
    u"Track Main West",
    u"Track West Main Ext",
    u"Track McKees Rocks",
    u"Track McKeesport",
    u"Track East Lead",
    u"Track Main East",
    u"Track East Main Ext",
    u"Track Brick-Plane",
    u"Track EH-1",
    u"Track EH-2",
    u"Track EH-3",
    u"Track S-R",
    u"Track S-1",
    u"Track S-2",
    u"Track S-3",
    u"Track S-4",
    u"Track Scale",
    u"Track Barn",
    u"Track W-1",
    u"Track W-2",
    u"Track K-1",
    u"Track K-2",
)


def station_key(name):
    return name.replace(" ", "_")


def bean_count(manager):
    return int(manager.getNamedBeanSet().size())


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
                    bean_count(mast_manager) == 45
                    and bean_count(section_manager) == 103
                    and len(transits) == 746
                    and all(
                        len(transit.getInternalBlocksList()) > 0
                        for transit in transits
                    )
                ):
                    break
                self.waitMsec(1000)

            for station in STATIONS:
                key = station_key(station)
                for user_name in (
                    "MoveTo%s_stored" % key,
                    "MoveInProgress%s" % key,
                ):
                    if sensor_manager.getByUserName(user_name) is None:
                        errors.append("missing sensor %s" % user_name)

            if bean_count(mast_manager) != 45:
                errors.append(
                    "signal masts=%s expected=45" % bean_count(mast_manager)
                )
            if bean_count(section_manager) != 103:
                errors.append(
                    "sections=%s expected=103" % bean_count(section_manager)
                )
            if bean_count(transit_manager) != 746:
                errors.append(
                    "transits=%s expected=746" % bean_count(transit_manager)
                )

            traininfo_dir = jmri.util.FileUtil.getExternalFilename(
                "preference:dispatcher/traininfo/"
            )
            traininfo_files = sorted(
                name for name in os.listdir(traininfo_dir) if name.endswith(".xml")
            )
            if len(traininfo_files) != 1548:
                errors.append(
                    "runtime TrainInfo files=%s expected=1548"
                    % len(traininfo_files)
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
                handle.write(
                    "45 masts; 44 station sensors; 103 sections; 746 transits; "
                    "1548 ordered TrainInfo routes\n"
                )
        finally:
            handle.close()

        java.lang.System.exit(1 if errors else 0)
        return False


HartSmoke().start()
