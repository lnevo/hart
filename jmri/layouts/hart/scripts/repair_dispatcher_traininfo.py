# JMRI Jython: validate/repair generated Dispatcher TrainInfo transit bindings.
#
# The Dispatcher System generates TrainInfo files from the station graph.  If
# signal-facing changes alter generated section endpoints, a TrainInfo can
# still reference an existing Transit whose internal blocks no longer contain
# its requested start or destination.  JMRI then rejects the dispatch.
#
# Environment:
#   HART_TRAININFO_REPAIR=1       write repaired TrainInfo files
#   HART_TRAININFO_DIR=/path/     override TrainInfo directory
#   HART_TRAININFO_MARKER=/path   write ok/fail report
#   HART_TRAININFO_EXIT=1         exit PanelPro after completion

from __future__ import print_function

import os
import re
import time
import traceback

import java.lang
import jmri


REPAIR = os.environ.get("HART_TRAININFO_REPAIR", "") == "1"
TRAININFO_DIR = os.environ.get("HART_TRAININFO_DIR", "")
MARKER = os.environ.get("HART_TRAININFO_MARKER", "")
EXIT = os.environ.get("HART_TRAININFO_EXIT", "") == "1"


def _block_names(transit):
    return [block.getUserName() for block in transit.getInternalBlocksList()]


def _ordered_spans(names, start_name, destination_name):
    spans = []
    for start_index, name in enumerate(names):
        if name != start_name:
            continue
        for destination_index in range(start_index + 1, len(names)):
            if names[destination_index] == destination_name:
                spans.append(
                    (
                        destination_index - start_index,
                        start_index,
                        destination_index,
                    )
                )
    return spans


def _sequence_pairs(transit, start_name, destination_name):
    starts = []
    destinations = []
    for sequence in range(1, transit.getMaxSequence() + 1):
        for section in transit.getSectionListBySeq(sequence):
            names = [block.getUserName() for block in section.getBlockList()]
            if start_name in names:
                starts.append(sequence)
            if destination_name in names:
                destinations.append(sequence)
    return [
        (start, destination)
        for start in starts
        for destination in destinations
        if start <= destination
    ]


def _via_hint(filename):
    match = re.search(r"_Via_(.+)_\d+_(?:fwd|rvs)\.xml$", filename)
    if not match:
        return ""
    return match.group(1).replace("_", " ").lower()


def _best_transit(transits, filename, start_name, destination_name):
    hint = _via_hint(filename)
    candidates = []
    for transit in transits:
        names = _block_names(transit)
        spans = _ordered_spans(names, start_name, destination_name)
        if not spans:
            continue
        sequences = _sequence_pairs(transit, start_name, destination_name)
        if not sequences:
            continue
        span = min(spans)[0]
        start_sequence, destination_sequence = min(
            sequences, key=lambda pair: (pair[1] - pair[0], pair)
        )
        transit_name = transit.getUserName()
        hint_mismatch = 0 if hint and hint in transit_name.lower() else 1
        candidates.append(
            (
                span,
                hint_mismatch,
                destination_sequence - start_sequence,
                transit_name,
                start_sequence,
                destination_sequence,
            )
        )
    return min(candidates) if candidates else None


def _write_marker(status, lines):
    if not MARKER:
        return
    handle = open(MARKER, "w")
    try:
        handle.write(status + "\n")
        handle.write("\n".join(lines))
    finally:
        handle.close()


def run():
    manager = jmri.InstanceManager.getDefault(jmri.TransitManager)
    transits = list(manager.getNamedBeanSet())
    traininfo_file = jmri.jmrit.dispatcher.TrainInfoFile()
    if TRAININFO_DIR:
        location = TRAININFO_DIR
        if not location.endswith(os.sep):
            location += os.sep
        traininfo_file.setFileLocation(location)

    files = sorted(traininfo_file.getTrainInfoFileNames())
    repaired = []
    errors = []
    for filename in files:
        info = traininfo_file.readTrainInfo(filename)
        transit = manager.getByUserName(info.getTransitName())
        names = _block_names(transit) if transit is not None else []
        start_name = info.getStartBlockName()
        destination_name = info.getDestinationBlockName()
        if _ordered_spans(names, start_name, destination_name):
            continue

        candidate = _best_transit(
            transits, filename, start_name, destination_name
        )
        if candidate is None:
            errors.append(
                "%s: no transit contains %s -> %s"
                % (filename, start_name, destination_name)
            )
            continue

        (
            unused_span,
            unused_hint_mismatch,
            unused_sequence_span,
            transit_name,
            start_sequence,
            destination_sequence,
        ) = candidate
        repaired.append(
            "%s: %s -> %s [%s..%s]"
            % (
                filename,
                info.getTransitName(),
                transit_name,
                start_sequence,
                destination_sequence,
            )
        )
        if REPAIR:
            info.setTransitName(transit_name)
            info.setTransitId(transit_name)
            info.setStartBlockSeq(start_sequence)
            info.setDestinationBlockSeq(destination_sequence)
            traininfo_file.writeTrainInfo(info, filename)

    lines = [
        "files=%s stale=%s repaired=%s mode=%s"
        % (
            len(files),
            len(repaired),
            len(repaired) if REPAIR else 0,
            "write" if REPAIR else "check",
        )
    ]
    lines.extend(repaired)
    lines.extend(errors)
    status = "fail" if errors or (repaired and not REPAIR) else "ok"
    _write_marker(status, lines)
    for line in lines:
        print("repair_dispatcher_traininfo:", line)
    return status


class HartTrainInfoRepair(jmri.jmrit.automat.AbstractAutomaton):
    def handle(self):
        try:
            manager = jmri.InstanceManager.getDefault(jmri.TransitManager)
            deadline = time.time() + 90
            while time.time() < deadline:
                transits = list(manager.getNamedBeanSet())
                if (
                    len(transits) == 175
                    and transits
                    and all(
                        len(transit.getInternalBlocksList()) > 0
                        for transit in transits
                    )
                ):
                    break
                self.waitMsec(1000)
            status = run()
        except Exception:
            status = "fail"
            details = traceback.format_exc()
            _write_marker(status, [details])
            print(details)
        if EXIT:
            java.lang.System.exit(0 if status == "ok" else 1)
        return False


HartTrainInfoRepair().start()
