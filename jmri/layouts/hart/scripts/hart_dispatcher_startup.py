# JMRI Jython: start Dispatcher System with HART compatibility fixes.
#
# JMRI runs each script eval with its own globals, so a second script cannot
# monkey-patch classes loaded by stock Startup.py. This wrapper loads the stock
# Dispatcher sources into its own namespace, applies the HART patch there, and
# only then starts Dispatcher automata.
#
# Do not add "from __future__ import print_function". JMRI's Jython engine
# keeps that compiler flag, and stock Dispatcher System still uses Python-2
# print statements (Startup.py: print "closed Option").

import jmri


def _exec_file(path):
    handle = open(path, "r")
    try:
        source = handle.read()
    finally:
        handle.close()
    # flags=0, dont_inherit=True: stock Dispatcher System is Python-2 print
    # statements. A prior HART script must not leak print_function onto them.
    code = compile(source, path, "exec", 0, True)
    exec(code, globals())


def start_hart_dispatcher():
    startup = jmri.util.FileUtil.getExternalFilename(
        "program:jython/DispatcherSystem/Startup.py"
    )
    run_master = jmri.util.FileUtil.getExternalFilename(
        "program:jython/DispatcherSystem/RunDispatchMaster.py"
    )
    patch = jmri.util.FileUtil.getExternalFilename(
        "preference:jython/patch_dispatcher_facing.py"
    )

    # Load Startup.py definitions without running its __builtin__ launch block.
    original_name = globals().get("__name__", "__builtin__")
    globals()["__name__"] = "hart_dispatcher_startup_definitions"
    try:
        _exec_file(startup)
    finally:
        globals()["__name__"] = original_name

    sensors.getSensor("stopMasterSensor").setKnownState(INACTIVE)
    sensors.getSensor("modifyMasterSensor").setKnownState(INACTIVE)
    OptionDialog().displayMessage(
        "Wait few seconds to finish starting up, then\n\n"
        "    Set up a train in a section\n"
        "    before dispatching a train "
    )

    _exec_file(run_master)
    _exec_file(patch)
    signature = apply_to_namespace(globals())
    if signature is None:
        raise RuntimeError("HART Dispatcher classes did not load")
    expected = (
        (NewTrainMaster.get_train_speed_factor, "_hart_get_train_speed_factor"),
        (NewTrainMaster.set_speed_factor0, "_hart_set_speed_factor0"),
        (
            MoveTrain.check_route_is_allocated_or_occupied,
            "_hart_check_route_is_allocated_or_occupied",
        ),
        (MoveTrain.set_route_allocated, "_hart_set_route_allocated"),
        (MoveTrain.set_direction, "_hart_set_direction"),
    )
    for method, expected_name in expected:
        if getattr(method, "__name__", "") != expected_name:
            raise RuntimeError(
                "HART Dispatcher patch verification failed: " + expected_name
            )
    memory_manager = jmri.InstanceManager.getDefault(jmri.MemoryManager)
    memory_manager.provideMemory("IM:HART:DISPATCHER_PATCH_STATUS").setValue(
        "ready: facing, first-move polarity, speed factor, route check/allocation subsection"
    )
    print(
        "HART Dispatcher compatibility patch applied in Dispatcher namespace: "
        "facing, first-move polarity, speed factor, route check/allocation subsection"
    )
    RunDispatcherMaster()


if __name__ == "__builtin__":
    start_hart_dispatcher()
