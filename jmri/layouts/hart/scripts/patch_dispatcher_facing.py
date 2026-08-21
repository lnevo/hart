# JMRI Jython: HART compatibility fixes for Dispatcher System.
#
# Stock MoveTrain.py maps dialog "forward" to train_direction "reverse" (and
# the reverse), so a through-station registration loads the *_rvs.xml traininfo.
# Those files share the same forward transit (allocated sections stay Forward)
# and only set runInReverse=yes, so the loco backs even when the dispatcher
# graph is forward.
#
# It also assumes every Operations engine comment and table speed-factor cell
# is non-null, and its optional route-clear gate scans an entire shared transit
# instead of only the requested start/destination subsection.
#
# This script may run before DispatcherSystem.py has loaded its classes.  A
# daemon retries and re-applies the patch after any Dispatcher System reload.
# Python-2 compatible for JMRI's embedded Jython.

from __future__ import print_function

import __main__
import threading
import time

_PATCH = r'''
def _hart_normalize_speed_factor(value):
    if value is None:
        return "100"
    text = str(value).strip()
    if text == "" or text == "-1":
        return "100"
    try:
        number = float(text)
    except (TypeError, ValueError):
        return "100"
    if number <= 0:
        return "100"
    if number == int(number):
        return str(int(number))
    return str(number)


def _hart_requested_route_blocks(block_list, start_name, destination_name):
    """Return blocks after start through destination, or None if invalid."""
    candidates = []
    for start_index, block in enumerate(block_list):
        if block.getUserName() != start_name:
            continue
        for destination_index in range(start_index + 1, len(block_list)):
            if block_list[destination_index].getUserName() == destination_name:
                candidates.append(
                    (destination_index - start_index, start_index, destination_index)
                )
    if not candidates:
        return None
    unused_distance, start_index, destination_index = min(candidates)
    return block_list[start_index + 1 : destination_index + 1]


def _hart_set_train_direction(self, block_name, in_siding):
    self.od.CLOSED_OPTION = True
    while self.od.CLOSED_OPTION == True:
        msg = "In block: " + block_name + "\n" + "What way is train facing\ntowards highlighted block?"
        title = "Set Train Facing Direction"
        result = self.od.customQuestionMessage2str(msg, title, "forward", "reverse")
        if self.od.CLOSED_OPTION == True:
            OptionDialog().displayMessage("Sorry Can't Cancel at this point")
    return [result, result]


def _hart_save_action(self, event):
    [train, block, direction, length, speed_factor] = [0, 1, 2, 4, 5]
    for row in reversed(range(len(self.model.data))):
        train_name = self.model.data[row][train]
        block_name = self.model.data[row][block]
        train_direction = self.model.data[row][direction]
        train_length = self.model.data[row][length]
        train_speed_factor = _hart_normalize_speed_factor(
            self.model.data[row][speed_factor]
        )
        if train_name != "" and train_name != None and block_name != "" and block_name != None:
            if train_name not in trains_allocated:
                trains_allocated.append(train_name)
            self.super.add_to_train_list_and_set_new_train_location0(
                train_name, block_name, train_direction, train_length, train_speed_factor
            )
            self.super.set_blockcontents(block_name, train_name)
            self.super.set_length0(train_name)
            self.super.set_speed_factor0(train_name)
            self.model.data.pop(row)
    self.completeTablePanel()
    if self.model.getRowCount() == 0:
        self.frame.dispatchEvent(WindowEvent(self.frame, WindowEvent.WINDOW_CLOSING))


def _hart_get_train_speed_factor(self, new_train_name):
    EngineManager = jmri.InstanceManager.getDefault(
        jmri.jmrit.operations.rollingstock.engines.EngineManager
    )
    engine = EngineManager.newRS("Set by Dispatcher System", new_train_name)
    comment = engine.getComment() or ""
    speed_factor = "100"
    if "speed factor" in comment:
        words = comment.split(" ")
        try:
            index = words.index("speed")
            if len(words) > index + 2:
                speed_factor = words[index + 2]
        except ValueError:
            pass
    return [engine, _hart_normalize_speed_factor(speed_factor)]


def _hart_set_speed_factor0(self, new_train_name):
    engine, speed_factor = _hart_get_train_speed_factor(self, new_train_name)
    engine.setComment("speed factor " + _hart_normalize_speed_factor(speed_factor))


def _hart_set_speed_factor(self, new_train_name):
    engine, current = _hart_get_train_speed_factor(self, new_train_name)
    title = "Scale the speed of the engine/train"
    msg = "speed factor of " + new_train_name + " = " + current + "%"
    request = self.od.customQuestionMessage2str(msg, title, "OK", "Change")
    if request == "Change":
        value = self.od.input(
            "input speed factor % of " + new_train_name,
            "speed factor of " + new_train_name,
            current,
        )
        if value is not None and str(value).strip() != "":
            engine.setComment(
                "speed factor " + _hart_normalize_speed_factor(value)
            )


def _hart_check_route_is_allocated_or_occupied(
    self, traininfoFileName, startBlockName
):
    train_info = jmri.jmrit.dispatcher.TrainInfoFile().readTrainInfo(
        traininfoFileName
    )
    transit_manager = jmri.InstanceManager.getDefault(jmri.TransitManager)
    transit = transit_manager.getTransit(train_info.getTransitName())
    if transit is None:
        print(
            "HART Dispatcher: route blocked; missing transit "
            + str(train_info.getTransitName())
        )
        return True

    requested = _hart_route_blocks(
        transit, train_info, startBlockName
    )
    if requested is None:
        print(
            "HART Dispatcher: route blocked; transit %s does not contain "
            "requested subsection %s -> %s"
            % (
                train_info.getTransitName(),
                startBlockName,
                train_info.getDestinationBlockName(),
            )
        )
        return True

    required_block_name = train_info.getBlockName()
    if required_block_name:
        required_block = blocks.getBlock(required_block_name)
        if required_block is None:
            print(
                "HART Dispatcher: route blocked; missing required block "
                + required_block_name
            )
            return True
        if required_block not in requested:
            requested.append(required_block)

    layout_block_manager = jmri.InstanceManager.getDefault(
        jmri.jmrit.display.layoutEditor.LayoutBlockManager
    )
    for block in requested:
        sensor = block.getSensor()
        if sensor is None or sensor.getKnownState() == jmri.Sensor.ACTIVE:
            return True
        layout_block = layout_block_manager.getLayoutBlock(block)
        if layout_block is None or layout_block.getUseExtraColor():
            return True
    return False


def _hart_route_blocks(transit, train_info, start_name):
    """Resolve only the TrainInfo subsection, excluding its occupied start."""
    destination_name = train_info.getDestinationBlockName()
    start_block = blocks.getBlock(start_name)
    if start_block is None:
        return None

    # This is JMRI's path-relative API used by Dispatcher Simulation and
    # CreateTransits.  A generated Transit may begin well before the requested
    # station, so never use getInternalBlocksList() without subsection bounds.
    destination_blocks = transit.getDestinationBlocksList(start_block, False)
    if destination_blocks is not None:
        path = list(destination_blocks)
        requested = _hart_requested_route_blocks(
            [start_block] + path, start_name, destination_name
        )
        if requested is not None:
            return requested

    # Fail-safe fallback for generated loop transits: honor the exact section
    # sequence bounds persisted in TrainInfo, then trim at the named endpoints.
    sequence_blocks = []
    start_sequence = int(train_info.getStartBlockSeq())
    destination_sequence = int(train_info.getDestinationBlockSeq())
    if (
        start_sequence < 1
        or destination_sequence < start_sequence
        or destination_sequence > int(transit.getMaxSequence())
    ):
        return None
    for sequence in range(start_sequence, destination_sequence + 1):
        for section in transit.getSectionListBySeq(sequence):
            for block in section.getBlockList():
                if (
                    sequence_blocks
                    and sequence_blocks[-1].getSystemName()
                    == block.getSystemName()
                ):
                    continue
                sequence_blocks.append(block)
    return _hart_requested_route_blocks(
        sequence_blocks, start_name, destination_name
    )


def _hart_set_route_allocated(self, traininfoFileName, startBlockName):
    train_info = jmri.jmrit.dispatcher.TrainInfoFile().readTrainInfo(
        traininfoFileName
    )
    transit_manager = jmri.InstanceManager.getDefault(jmri.TransitManager)
    transit = transit_manager.getTransit(train_info.getTransitName())
    if transit is None:
        print(
            "HART Dispatcher: cannot allocate missing transit "
            + str(train_info.getTransitName())
        )
        return
    requested = _hart_route_blocks(transit, train_info, startBlockName)
    if requested is None:
        print(
            "HART Dispatcher: cannot allocate invalid subsection %s -> %s"
            % (startBlockName, train_info.getDestinationBlockName())
        )
        return
    layout_block_manager = jmri.InstanceManager.getDefault(
        jmri.jmrit.display.layoutEditor.LayoutBlockManager
    )
    for block in requested:
        layout_block = layout_block_manager.getLayoutBlock(block)
        if layout_block is not None:
            layout_block.setUseExtraColor(True)
    if self.logLevel > 0:
        print("allocated route", traininfoFileName)


def _hart_populate_existing(self, blocks_to_put_in_dropdown):
    for row in reversed(range(len(self.data))):
        self.data.pop(row)
    items_to_put_in_dropdown = []
    for block_name in blocks_to_put_in_dropdown:
        train_name = NewTrainMaster().get_blockcontents(block_name)
        if train_name == "" or train_name is None:
            train_direction = "unassigned"
            train_length = -1
            current_speed_factor = -1
        else:
            [engine, current_length] = NewTrainMaster().get_train_length(train_name)
            train_length = engine.getLength()
            [engine, current_speed_factor] = NewTrainMaster().get_train_speed_factor(train_name)
            train = trains[train_name]
            train_direction = train["direction"]
        items_to_put_in_dropdown.append(
            [train_name, block_name, train_direction, False, train_length, current_speed_factor]
        )
    for item in items_to_put_in_dropdown:
        self.data.append(item)
'''


def apply_to_namespace(namespace):
    required = ("MoveTrain", "NewTrainMaster", "createandshowGUI", "MyTableModel")
    if not all(name in namespace for name in required):
        return None

    eval(compile(_PATCH, "hart_dispatcher_patch", "exec"), namespace)

    namespace["MoveTrain"].check_route_is_allocated_or_occupied = (
        namespace["_hart_check_route_is_allocated_or_occupied"]
    )
    namespace["MoveTrain"].set_route_allocated = namespace[
        "_hart_set_route_allocated"
    ]
    namespace["NewTrainMaster"].set_train_direction = (
        namespace["_hart_set_train_direction"]
    )
    namespace["NewTrainMaster"].get_train_speed_factor = (
        namespace["_hart_get_train_speed_factor"]
    )
    namespace["NewTrainMaster"].set_speed_factor = namespace[
        "_hart_set_speed_factor"
    ]
    namespace["NewTrainMaster"].set_speed_factor0 = namespace[
        "_hart_set_speed_factor0"
    ]
    namespace["createandshowGUI"].save_action = namespace["_hart_save_action"]
    namespace["MyTableModel"].populate_existing = namespace[
        "_hart_populate_existing"
    ]
    return tuple(id(namespace[name]) for name in required)


def _apply_patch():
    return apply_to_namespace(__main__.__dict__)


def _patch_loop():
    last_signature = None
    while True:
        try:
            signature = _apply_patch()
            if signature is not None and signature != last_signature:
                last_signature = signature
                print(
                    "HART Dispatcher compatibility patch applied: "
                    "facing, speed factor, route subsection"
                )
        except Exception as exc:
            print("HART Dispatcher compatibility patch retry: " + str(exc))
        time.sleep(1.0)


if not getattr(__main__, "_hart_dispatcher_patch_thread_started", False):
    __main__._hart_dispatcher_patch_thread_started = True
    _thread = threading.Thread(
        target=_patch_loop, name="hart_dispatcher_compat_patch"
    )
    _thread.setDaemon(True)
    _thread.start()
    print("HART Dispatcher compatibility patch waiting for Dispatcher System")
