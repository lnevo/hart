"""A small in-memory stand-in for JMRI, Java and Swing, so HART's Jython scripts load in CPython tests.

Nothing here talks to a layout. The MQTT "adapter" is a list that records what a
script would publish; no MQTT client is imported, and `load_script` blocks socket
connections while a script runs, so a test cannot reach a broker or a host by mistake.
Timers and threads never run on their own: a test fires them with `fire_timers()` /
`run_threads()`.
"""
from __future__ import annotations

import atexit
import contextlib
import shutil
import socket
import sys
import tempfile
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "tools/hartlib/src"))
from hartlib import coordinator  # noqa: E402

# The loader signal_coordinator.py and panel_status.py import their sibling modules with; the deploy installs it
# in preference:jython beside them.
SIBLING_LOADER = REPO / "jmri/scripts/jython_siblings.py"

# --- constants (values only need to be distinct) ---------------------------------


class Turnout:
    UNKNOWN, CLOSED, THROWN, INCONSISTENT = 1, 2, 4, 8
    DIRECT, ONESENSOR, TWOSENSOR = 1, 4, 8


class Sensor:
    UNKNOWN, ACTIVE, INACTIVE, INCONSISTENT = 1, 2, 4, 8


class SignalHead:
    DARK, RED, FLASHRED, YELLOW, FLASHYELLOW, GREEN, FLASHGREEN, LUNAR, FLASHLUNAR = 0, 1, 2, 4, 8, 16, 32, 64, 128
    NAMES = {0: "Dark", 1: "Red", 2: "Flashing Red", 4: "Yellow", 8: "Flashing Yellow", 16: "Green",
             32: "Flashing Green", 64: "Lunar", 128: "Flashing Lunar"}


class PowerManager:
    UNKNOWN, ON, OFF = 0, 2, 4


# --- beans --------------------------------------------------------------------------


class Bean:
    def __init__(self, system_name, user_name=None):
        self._sys = system_name
        self._user = user_name
        self.listeners = []

    def getSystemName(self):
        return self._sys

    def getUserName(self):
        return self._user

    def getDisplayName(self):
        return self._user or self._sys

    def addPropertyChangeListener(self, listener):
        self.listeners.append(listener)

    def getPropertyChangeListeners(self):
        return list(self.listeners)

    def removePropertyChangeListener(self, listener):
        self.listeners = [l for l in self.listeners if l is not listener]


class FakeSensor(Bean):
    def __init__(self, system_name, state=Sensor.UNKNOWN):
        super().__init__(system_name)
        self.state = state

    def getKnownState(self):
        return self.state

    def setKnownState(self, state):
        self.state = state


class FakeTurnout(Bean):
    def __init__(self, system_name, first=None, second=None, mode=Turnout.DIRECT, known=Turnout.UNKNOWN):
        super().__init__(system_name)
        self.first, self.second, self.mode, self.known = first, second, mode, known
        self.commanded = []  # setCommandedState calls: must stay empty for plant turnouts

    def getFirstSensor(self):
        return self.first

    def getSecondSensor(self):
        return self.second

    def getKnownState(self):
        return self.known

    def newKnownState(self, state):
        self.known = state

    def setCommandedState(self, state):
        self.commanded.append(state)

    def getFeedbackMode(self):
        return self.mode

    def setFeedbackMode(self, mode):
        self.mode = mode

    def setInitialKnownStateFromFeedback(self):
        pass


class _ValueEvent:
    def __init__(self, name, old, new, source=None):
        self._name, self._old, self._new, self._source = name, old, new, source

    def getSource(self):
        return self._source

    def getPropertyName(self):
        return self._name

    def getOldValue(self):
        return self._old

    def getNewValue(self):
        return self._new


class FakeMemory(Bean):
    """JMRI Memory: setValue fires a "value" change only when the value changes, like JMRI."""

    def __init__(self, system_name, value=None):
        super().__init__(system_name)
        self.value = value

    def getValue(self):
        return self.value

    def setValue(self, value):
        old, self.value = self.value, value
        if old != value:
            for listener in list(self.listeners):
                listener.propertyChange(_ValueEvent("value", old, value, self))

    def setUserName(self, name):
        self._user = name


class FakeRoute(Bean):
    def __init__(self, system_name, user_name, enabled=True):
        super().__init__(system_name, user_name)
        self.enabled = enabled
        self.history = []

    def getEnabled(self):
        return self.enabled

    def setEnabled(self, value):
        self.enabled = value
        self.history.append(value)


class FakeHead(Bean):
    def __init__(self, system_name, appearance=SignalHead.RED):
        super().__init__(system_name)
        self.appearance, self.held, self.lit = appearance, False, True

    def getAppearance(self):
        return self.appearance

    def setAppearance(self, value):
        self.appearance = value

    def getAppearanceName(self):
        return SignalHead.NAMES.get(self.appearance, str(self.appearance))

    def setHeld(self, value):
        self.held = value

    def setLit(self, value):
        self.lit = value


class FakeMast(Bean):
    def __init__(self, system_name, user_name=None, aspect="Stop"):
        super().__init__(system_name, user_name)
        self.aspect, self.held, self.lit = aspect, False, True

    def getAspect(self):
        return self.aspect

    def setAspect(self, value):
        self.aspect = value

    def setHeld(self, value):
        self.held = value

    def setLit(self, value):
        self.lit = value


# --- managers -----------------------------------------------------------------------


class Manager:
    def __init__(self, make):
        self.beans = {}
        self._make = make

    def add(self, bean):
        self.beans[bean.getSystemName()] = bean
        return bean

    def _get(self, name):
        return self.beans.get(name)

    def _provide(self, name):
        return self.beans.get(name) or self.add(self._make(name))

    def getNamedBeanSet(self):
        return list(self.beans.values())

    getTurnout = getSensor = getSignalHead = getSignalMast = getMemory = getBySystemName = _get
    provideTurnout = provideSensor = provideMemory = _provide

    def register(self, bean):
        self.add(bean)


class MemoryManager(Manager):
    def newMemory(self, system_name, user_name=None):
        """JMRI MemoryManager.newMemory: always creates; callers check getMemory first."""
        if system_name in self.beans:
            raise ValueError("%s already exists" % system_name)
        bean = self.add(self._make(system_name))
        bean.setUserName(user_name)
        return bean


class FakePower:
    def __init__(self, power=PowerManager.OFF):
        self.power, self.listeners = power, []

    def getPower(self):
        return self.power

    def setPower(self, value):
        self.power = value

    def addPropertyChangeListener(self, listener):
        self.listeners.append(listener)

    def getPropertyChangeListeners(self):
        return list(self.listeners)

    def removePropertyChangeListener(self, listener):
        self.listeners = [l for l in self.listeners if l is not listener]


class RecordingAdapter:
    """Stands in for JMRI's MqttAdapter: records publishes, sends nothing anywhere."""

    def __init__(self):
        self.published = []
        self.subscribed = []
        self.unsubscribed = []  # (topic, listener)

    # Stock MqttAdapter.publish(topic, payload) retains (its `retained` field is true), so the
    # two-argument form records True here, as the broker would see it.
    def publish(self, topic, payload, retain=True):
        self.published.append((topic, payload, retain))

    def subscribe(self, topic, listener):
        self.subscribed.append(topic)

    def unsubscribe(self, topic, listener):
        self.unsubscribed.append((topic, listener))


class FakeShutDownManager:
    def __init__(self):
        self.tasks = []

    def register(self, task):
        if task not in self.tasks:
            self.tasks.append(task)

    def deregister(self, task):
        self.tasks = [t for t in self.tasks if t is not task]


class FakeMemo:
    def __init__(self, adapter):
        self._adapter = adapter

    def getMqttAdapter(self):
        return self._adapter


# --- Swing / Java -------------------------------------------------------------------


class FakeButton:
    """javax.swing.JButton: text, enabled flag and action listeners; click() fires them."""

    def __init__(self, text=""):
        self.text, self.enabled, self.actions, self.parent = text, True, [], None

    def getText(self):
        return self.text

    def setText(self, text):
        self.text = text

    def setEnabled(self, value):
        self.enabled = value

    def addActionListener(self, listener):
        self.actions.append(listener)

    def getParent(self):
        return self.parent

    def click(self):
        for listener in list(self.actions):
            listener(_Event(self))


class _Event:
    def __init__(self, source):
        self._source = source

    def getSource(self):
        return self._source


class Timer:
    pending = []

    def __init__(self, delay, listener):
        self.delay, self.listeners, self.running = delay, [listener] if listener else [], False

    def setRepeats(self, value):
        pass

    def addActionListener(self, listener):
        self.listeners.append(listener)

    def start(self):
        self.running = True
        Timer.pending.append(self)

    restart = start

    def stop(self):
        self.running = False


class SwingUtilities:
    @staticmethod
    def isEventDispatchThread():
        return True

    @staticmethod
    def invokeLater(runnable):
        runnable.run()


class Thread:
    started = []

    def __init__(self, runnable=None, name=None):
        self.runnable = runnable

    def start(self):
        Thread.started.append(self)

    @staticmethod
    def sleep(ms):
        pass


class _Base:
    """Java interfaces the scripts subclass; plain objects here."""


def fire_timers(limit=100):
    """Run pending timers in order until none are left (or `limit`, to stop retry loops)."""
    n = 0
    while Timer.pending and n < limit:
        t = Timer.pending.pop(0)
        if not t.running:
            continue
        for listener in list(t.listeners):
            listener.actionPerformed(_Event(t))
        n += 1
    return n


def run_threads():
    while Thread.started:
        Thread.started.pop(0).runnable.run()


# --- module tree --------------------------------------------------------------------


class Layout:
    """One fake JMRI: managers, power, MQTT recorder. `load_script` exposes it to a script."""

    def __init__(self, mqtt=True):
        self.turnouts = Manager(FakeTurnout)
        self.sensors = Manager(FakeSensor)
        self.routes = Manager(lambda n: FakeRoute(n, n))
        self.heads = Manager(FakeHead)
        self.masts = Manager(FakeMast)
        self.memories = MemoryManager(FakeMemory)
        self.power = FakePower()
        self.adapter = RecordingAdapter()
        self.memo = FakeMemo(self.adapter) if mqtt else None
        self.editors = []
        self.shutdown = FakeShutDownManager()
        self.button_space = None  # Apps.buttonSpace(); a test sets one to have a main window
        # FileUtil's preference:jython; load_script sets it to the script's own folder when a test does not.
        self.jython_dir = None

    def instance(self, cls):
        return {
            "MqttSystemConnectionMemo": self.memo,
            "TurnoutManager": self.turnouts,
            "SignalHeadManager": self.heads,
            "SignalMastManager": self.masts,
            "PowerManager": self.power,
            "ShutDownManager": self.shutdown,
            "EditorManager": types.SimpleNamespace(getAll=lambda: self.editors),
        }.get(getattr(cls, "__name__", ""))


def _modules(layout):
    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        return m

    def iface(name):
        return type(name, (_Base,), {})

    class MqttSystemConnectionMemo:
        pass

    class TurnoutManager:
        pass

    class SignalHeadManager:
        pass

    class SignalMastManager:
        pass

    class SignalMastLogicManager:
        pass

    class EditorManager:
        pass

    class ShutDownManager:
        pass

    class AbstractShutDownTask(_Base):
        def __init__(self, *args):
            pass

        def setDoRun(self, value):
            pass

    def external_filename(name):
        if name != "preference:jython":
            raise ValueError(f"jmri_fake FileUtil knows only preference:jython, not {name!r}")
        if layout.jython_dir is None:
            raise ValueError("jmri_fake: no jython folder set (load_script sets it)")
        return str(layout.jython_dir)

    power_cls = type("PowerManager", (PowerManager,), {})
    instance_manager = types.SimpleNamespace(getDefault=layout.instance, getNullableDefault=layout.instance)
    mqtt = mod("jmri.jmrix.mqtt", MqttSystemConnectionMemo=MqttSystemConnectionMemo,
               MqttEventListener=iface("MqttEventListener"))
    display = mod("jmri.jmrit.display", EditorManager=EditorManager, SensorIcon=iface("SensorIcon"),
                  SignalHeadIcon=iface("SignalHeadIcon"), BlockContentsIcon=iface("BlockContentsIcon"))
    implementation = mod("jmri.implementation", AbstractShutDownTask=AbstractShutDownTask,
                         VirtualSignalHead=FakeHead)
    jmri = mod("jmri", Turnout=Turnout, Sensor=Sensor, SignalHead=SignalHead, PowerManager=power_cls,
               InstanceManager=instance_manager, TurnoutManager=TurnoutManager, SignalHeadManager=SignalHeadManager,
               SignalMastManager=SignalMastManager, SignalMastLogicManager=SignalMastLogicManager,
               ShutDownManager=ShutDownManager, implementation=implementation,
               jmrix=mod("jmri.jmrix", mqtt=mqtt), jmrit=mod("jmri.jmrit", display=display),
               util=mod("jmri.util", ThreadingUtil=types.SimpleNamespace(),
                        FileUtil=types.SimpleNamespace(getExternalFilename=external_filename),
                        swing=mod("jmri.util.swing", JmriJOptionPane=types.SimpleNamespace())))
    # A fake bean or Swing call fails with RuntimeError: here it is java.lang.RuntimeException, which the scripts
    # catch for a Java failure.
    lang = mod("java.lang", Runnable=iface("Runnable"), Thread=Thread, RuntimeException=RuntimeError,
               InterruptedException=type("InterruptedException", (Exception,), {}))
    reflect = mod("java.lang.reflect",
                  InvocationTargetException=type("InvocationTargetException", (Exception,), {}))
    lang.reflect = reflect
    awt_event = mod("java.awt.event", ActionListener=iface("ActionListener"), MouseAdapter=iface("MouseAdapter"),
                    MouseEvent=types.SimpleNamespace(BUTTON1=1), WindowAdapter=iface("WindowAdapter"))
    beans = mod("java.beans", PropertyChangeListener=iface("PropertyChangeListener"))
    java = mod("java", lang=lang, beans=beans, awt=mod("java.awt", event=awt_event))
    swing = mod("javax.swing", SwingUtilities=SwingUtilities, Timer=Timer, JButton=FakeButton,
                JOptionPane=types.SimpleNamespace(showMessageDialog=lambda *a: None))
    return {
        "jmri": jmri, "jmri.jmrix": jmri.jmrix, "jmri.jmrix.mqtt": mqtt, "jmri.jmrit": jmri.jmrit,
        "jmri.jmrit.display": display, "jmri.implementation": implementation, "jmri.util": jmri.util,
        "jmri.util.swing": jmri.util.swing, "java": java, "java.lang": lang, "java.lang.reflect": reflect,
        "java.beans": beans,
        "java.awt": java.awt, "java.awt.event": awt_event, "javax": mod("javax", swing=swing),
        "javax.swing": swing, "apps": mod("apps", Apps=types.SimpleNamespace(buttonSpace=lambda: layout.button_space)),
    }


@contextlib.contextmanager
def no_network():
    """Refuse every socket connection while a script runs."""
    def refuse(*args, **kwargs):
        raise OSError("network blocked in HART script tests")

    saved = socket.socket.connect, socket.socket.connect_ex, socket.create_connection
    socket.socket.connect = socket.socket.connect_ex = refuse
    socket.create_connection = refuse
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = saved


@contextlib.contextmanager
def fake_modules(modules):
    """Put `modules` (name -> module) in sys.modules, then put back only those names.

    Not `mock.patch.dict(sys.modules, ...)`: on exit that resets all of sys.modules to its
    earlier copy, so a real module first imported while the fakes were in place is dropped,
    and the next import makes a second copy of it beside the one other modules still hold."""
    saved = {k: sys.modules.get(k) for k in modules}
    sys.modules.update(modules)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


@contextlib.contextmanager
def jmri_modules(layout):
    with fake_modules(_modules(layout)), no_network():
        yield


class ScriptGlobals(dict):
    """A loaded script's globals. A test's write to a name also reaches each sibling module the
    script loaded (its SIBLING_MODULES) that holds the same object under that name.

    So `env["Thread"] = Recorder` patches the Thread that code moved into a sibling reads too,
    as it did when that code was in the script. A sibling's own, different object of that name
    is left alone. The script's own assignments do not pass through here.
    """

    siblings = ()

    def __setitem__(self, key, value):
        old = self.get(key, _UNSET)
        if old is not _UNSET:
            for module in self.siblings:
                if getattr(module, key, _UNSET) is old:
                    setattr(module, key, value)
        super().__setitem__(key, value)


_UNSET = object()


def stage_jython(script: Path, folder: Path) -> Path:
    """Copy `script`, the sibling modules it names (hartlib.coordinator) and SIBLING_LOADER into `folder`, as the
    deploy installs them in preference:jython; returns the copied script."""
    folder.mkdir(parents=True, exist_ok=True)
    for path in [*coordinator.files(script), SIBLING_LOADER]:
        shutil.copy(path, folder / path.name)
    return folder / script.name


def _staged_folder(script: Path) -> Path:
    """A new jython folder holding `script` and its siblings, removed when the test process ends."""
    holder = tempfile.TemporaryDirectory(prefix="jmri_fake_jython_")
    atexit.register(holder.cleanup)
    folder = Path(holder.name) / "jython"
    stage_jython(script, folder)
    return folder


def load_script(path: Path, layout: Layout) -> ScriptGlobals:
    """Run a Jython script against `layout`; returns its globals for the test to drive.

    Jython names a Java method `await`, a reserved word in Python 3; it is renamed in the
    loaded copy only (the script on disk is untouched), so sibling modules must not call it.
    preference:jython is the script's own folder unless the test set `layout.jython_dir`; for a script with
    sibling modules (hartlib.coordinator) it is a new folder staged as the deploy installs it. The
    sys.path entry a script adds for its siblings is taken out again afterwards, and no
    bytecode is written beside them.
    """
    Timer.pending.clear()
    Thread.started.clear()
    path = Path(path)
    if layout.jython_dir is None:
        if path.name in coordinator.TUPLE_NAMES:
            layout.jython_dir = _staged_folder(path.resolve())
        else:
            layout.jython_dir = path.resolve().parent
    source = path.read_text(encoding="utf-8").replace(".await(", ".await_(")
    env = ScriptGlobals(__name__="hart_script_under_test", turnouts=layout.turnouts, sensors=layout.sensors,
                        routes=layout.routes, signals=layout.heads, masts=layout.masts,
                        memories=layout.memories)
    saved_path, saved_bytecode = list(sys.path), sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        with jmri_modules(layout), contextlib.redirect_stdout(_Quiet()):
            exec(compile(source, str(path), "exec"), env)
    finally:
        sys.path[:] = saved_path
        sys.dont_write_bytecode = saved_bytecode
    env.siblings = tuple(sys.modules[name] for name in env.get("SIBLING_MODULES", ()))
    return env


class _Quiet:
    def write(self, text):
        pass

    def flush(self):
        pass


@contextlib.contextmanager
def running(layout):
    """Keep the fake modules in place while a test calls into a loaded script."""
    with jmri_modules(layout), contextlib.redirect_stdout(_Quiet()):
        yield
