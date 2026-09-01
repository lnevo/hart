# JMRI Jython: run stock Dispatcher System Stage 1; auto-Yes shared-sensor.
#
# Does not patch CreateIcons, CreateTransits, CreateGraph, or MoveTrain.
# Do not add print_function (breaks stock Startup.py).

import os
import shutil
import sys
import time
import traceback

import java.io
import java.lang
import jmri
from java.awt import Color, Dimension, Font
from javax.swing import Box, BoxLayout, JButton, JDialog, JFrame, JLabel
from javax.swing import JOptionPane, JPanel, JTextArea, WindowConstants
from jmri.util import FileUtil


def _log(msg):
    print "stage1:", msg
    sys.stdout.flush()


def _mark(status, detail):
    marker = os.environ.get("HART_STAGE1_MARKER", "/tmp/hart_stage1.done")
    handle = open(marker, "w")
    try:
        handle.write(status + "\n" + detail + "\n")
    finally:
        handle.close()


class _AutoYes(object):
    # Callable objects: Jython binds assigned functions as JOptionPane methods.
    def __call__(self, *args):
        _log("auto-Yes dialog")
        return JOptionPane.YES_OPTION


class _AutoOk(object):
    def __call__(self, *args):
        _log("auto-OK dialog")
        return None


def _install_dialog_yes():
    JOptionPane.showConfirmDialog = _AutoYes()
    JOptionPane.showMessageDialog = _AutoOk()
    JOptionPane.showOptionDialog = _AutoYes()


def _store_user(path):
    cm = jmri.InstanceManager.getNullableDefault(jmri.ConfigureManager)
    if cm is None:
        raise RuntimeError("no ConfigureManager")
    ok = cm.storeUser(java.io.File(path))
    if not ok:
        raise RuntimeError("storeUser failed: " + path)


def _copy(src, dest):
    dest_dir = os.path.dirname(dest)
    if dest_dir and not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    shutil.copy2(src, dest)
    _log("copied " + src + " -> " + dest)


def _exec_program(relpath):
    path = FileUtil.getExternalFilename(relpath)
    _log("exec " + path)
    exec(open(path).read(), globals())


def _run_stage1():
    _install_dialog_yes()
    _exec_program("program:jython/DispatcherSystem/CreateIcons.py")
    _log("CreateIcons loaded; running processPanels")
    result = processPanels()
    if str(result) != "Success":
        raise RuntimeError("CreateIcons processPanels returned " + str(result))
    _log("CreateIcons Success; building transits")

    my_path_to_jars = FileUtil.getExternalFilename(
        "program:jython/DispatcherSystem/jars/jgrapht.jar"
    )
    sys.path.append(my_path_to_jars)
    _exec_program("program:jython/DispatcherSystem/CreateGraph.py")
    global le
    global g
    le = LabelledEdge
    g = StationGraph()
    _exec_program("program:jython/DispatcherSystem/CreateTransits.py")
    global dpg
    dpg = DisplayProgress()
    CreateTransits().run_transits()
    _log("CreateTransits finished")


def _wait_layout():
    deadline = time.time() + 90
    while time.time() < deadline:
        editor = jmri.InstanceManager.getDefault(
            jmri.jmrit.display.EditorManager
        )
        for panel in editor.getList():
            if isinstance(panel, jmri.jmrit.display.layoutEditor.LayoutEditor):
                return panel
        time.sleep(1)
    return None


def _finish():
    if _wait_layout() is None:
        _mark("fail", "no Layout Editor panel loaded")
        java.lang.System.exit(1)
        return

    repo_tables = os.environ.get("HART_STAGE1_TABLES", "")
    repo_traininfo = os.environ.get("HART_STAGE1_TRAININFO", "")
    store_path = os.environ.get(
        "HART_STAGE1_STORE",
        FileUtil.getUserFilesPath() + "tables.xml",
    )
    try:
        _run_stage1()
        _store_user(store_path)
        sections = jmri.InstanceManager.getDefault(
            jmri.SectionManager
        ).getNamedBeanSet().size()
        transits = jmri.InstanceManager.getDefault(
            jmri.TransitManager
        ).getNamedBeanSet().size()
        masts = jmri.InstanceManager.getDefault(
            jmri.SignalMastManager
        ).getNamedBeanSet().size()
        detail = "masts=%s sections=%s transits=%s stored=%s" % (
            int(masts),
            int(sections),
            int(transits),
            store_path,
        )
        if repo_tables:
            _copy(store_path, repo_tables)
        traininfo_src = FileUtil.getExternalFilename(
            "preference:dispatcher/traininfo/"
        )
        if repo_traininfo and os.path.isdir(traininfo_src):
            if os.path.isdir(repo_traininfo):
                for name in os.listdir(repo_traininfo):
                    if name.endswith(".xml"):
                        os.remove(os.path.join(repo_traininfo, name))
            else:
                os.makedirs(repo_traininfo)
            for name in os.listdir(traininfo_src):
                if name.endswith(".xml"):
                    _copy(
                        os.path.join(traininfo_src, name),
                        os.path.join(repo_traininfo, name),
                    )
            detail = detail + " traininfo=%s" % len(
                [n for n in os.listdir(repo_traininfo) if n.endswith(".xml")]
            )
        _log(detail)
        _mark("ok", detail)
        java.lang.System.exit(0)
    except:
        text = traceback.format_exc()
        _log(text)
        _mark("fail", text)
        java.lang.System.exit(1)


# Not an AbstractAutomaton: CreateIcons.stop_all_threads() would kill us
# before Store. Stock Stage 1 also runs from a button, not an Automaton.
_stage1_thread = java.lang.Thread(_finish)
_stage1_thread.setName("hart-stage1")
_stage1_thread.setDaemon(False)
_stage1_thread.start()
