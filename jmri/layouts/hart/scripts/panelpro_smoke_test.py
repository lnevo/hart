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
    u"Main West",
    u"West Main Ext",
    u"McKees Rocks",
    u"McKeesport",
    u"South Yard East",
    u"Main East",
    u"East Main Ext",
    u"Brick-Plane",
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
                    bean_count(mast_manager) == 23
                    and bean_count(section_manager) == 41
                    and len(transits) == 102
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

            if bean_count(mast_manager) != 23:
                errors.append(
                    "signal masts=%s expected=23" % bean_count(mast_manager)
                )
            if bean_count(section_manager) != 41:
                errors.append(
                    "sections=%s expected=41" % bean_count(section_manager)
                )
            if bean_count(transit_manager) != 102:
                errors.append(
                    "transits=%s expected=102" % bean_count(transit_manager)
                )

            traininfo_dir = jmri.util.FileUtil.getExternalFilename(
                "preference:dispatcher/traininfo/"
            )
            traininfo_files = sorted(
                name for name in os.listdir(traininfo_dir) if name.endswith(".xml")
            )
            if len(traininfo_files) != 220:
                errors.append(
                    "runtime TrainInfo files=%s expected=220"
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
                    "23 masts; 16 station sensors; 41 sections; 102 transits; "
                    "220 ordered TrainInfo routes\n"
                )
        finally:
            handle.close()

        java.lang.System.exit(1 if errors else 0)
        return False


HartSmoke().start()
