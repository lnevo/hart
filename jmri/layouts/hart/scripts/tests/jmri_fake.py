"""A small in-memory stand-in for JMRI, Java and Swing, so HART's Jython scripts load in CPython tests.

Nothing here talks to a layout. The MQTT "adapter" is a list that records what a
script would publish; no MQTT client is imported, and `load_script` blocks socket
connections while a script runs, so a test cannot reach a broker or a host by mistake.
Timers and threads never run on their own: a test fires them with `fire_timers()` /
`run_threads()`.
"""
from __future__ import annotations

import contextlib
import socket
import sys
import types
from pathlib import Path

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

    def getPropertyChangeListeners(self):
        return list(self.listeners)

    def removePropertyChangeListener(self, listener):
        self.listeners = [l for l in self.listeners if l is not listener]


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

    def newMemory(self, system_name, user_name=None):
        """JMRI MemoryManager.newMemory: always creates; callers check getMemory first."""
        if system_name in self.beans:
            raise ValueError("%s already exists" % system_name)
        bean = self.add(self._make(system_name))
        bean.setUserName(user_name)
        return bean

    def getNamedBeanSet(self):
        return list(self.beans.values())

    getTurnout = getSensor = getSignalHead = getSignalMast = getMemory = getBySystemName = _get
    provideTurnout = provideSensor = provideMemory = _provide

    def register(self, bean):
        self.add(bean)


class FakePower:
    def __init__(self, power=PowerManager.OFF):
        self.power, self.listeners = power, []

    def getPower(self):
        return self.power

    def setPower(self, value):
        self.power = value

    def addPropertyChangeListener(self, listener):
        self.listeners.append(listener)


class RecordingAdapter:
    """Stands in for JMRI's MqttAdapter: records publishes, sends nothing anywhere."""

    def __init__(self):
        self.published = []
        self.subscribed = []

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload, retain))

    def subscribe(self, topic, listener):
        self.subscribed.append(topic)


class FakeMemo:
    def __init__(self, adapter):
        self._adapter = adapter

    def getMqttAdapter(self):
        return self._adapter


# --- Swing / Java -------------------------------------------------------------------


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
        self.memories = Manager(FakeMemory)
        self.power = FakePower()
        self.adapter = RecordingAdapter()
        self.memo = FakeMemo(self.adapter) if mqtt else None
        self.editors = []

    def instance(self, cls):
        return {
            "MqttSystemConnectionMemo": self.memo,
            "SignalHeadManager": self.heads,
            "SignalMastManager": self.masts,
            "PowerManager": self.power,
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

    class SignalHeadManager:
        pass

    class SignalMastManager:
        pass

    class SignalMastLogicManager:
        pass

    class EditorManager:
        pass

    class AbstractShutDownTask(_Base):
        def __init__(self, *args):
            pass

        def setDoRun(self, value):
            pass

    power_cls = type("PowerManager", (PowerManager,), {})
    instance_manager = types.SimpleNamespace(getDefault=layout.instance)
    mqtt = mod("jmri.jmrix.mqtt", MqttSystemConnectionMemo=MqttSystemConnectionMemo,
               MqttEventListener=iface("MqttEventListener"))
    display = mod("jmri.jmrit.display", EditorManager=EditorManager, SensorIcon=iface("SensorIcon"),
                  SignalHeadIcon=iface("SignalHeadIcon"), BlockContentsIcon=iface("BlockContentsIcon"))
    implementation = mod("jmri.implementation", AbstractShutDownTask=AbstractShutDownTask,
                         VirtualSignalHead=FakeHead)
    jmri = mod("jmri", Turnout=Turnout, Sensor=Sensor, SignalHead=SignalHead, PowerManager=power_cls,
               InstanceManager=instance_manager, SignalHeadManager=SignalHeadManager,
               SignalMastManager=SignalMastManager, SignalMastLogicManager=SignalMastLogicManager,
               implementation=implementation,
               jmrix=mod("jmri.jmrix", mqtt=mqtt), jmrit=mod("jmri.jmrit", display=display),
               util=mod("jmri.util", ThreadingUtil=types.SimpleNamespace(),
                        swing=mod("jmri.util.swing", JmriJOptionPane=types.SimpleNamespace())))
    lang = mod("java.lang", Runnable=iface("Runnable"), Thread=Thread)
    awt_event = mod("java.awt.event", ActionListener=iface("ActionListener"), MouseAdapter=iface("MouseAdapter"),
                    MouseEvent=types.SimpleNamespace(BUTTON1=1), WindowAdapter=iface("WindowAdapter"))
    beans = mod("java.beans", PropertyChangeListener=iface("PropertyChangeListener"))
    java = mod("java", lang=lang, beans=beans, awt=mod("java.awt", event=awt_event))
    swing = mod("javax.swing", SwingUtilities=SwingUtilities, Timer=Timer, JButton=iface("JButton"),
                JOptionPane=types.SimpleNamespace(showMessageDialog=lambda *a: None))
    return {
        "jmri": jmri, "jmri.jmrix": jmri.jmrix, "jmri.jmrix.mqtt": mqtt, "jmri.jmrit": jmri.jmrit,
        "jmri.jmrit.display": display, "jmri.implementation": implementation, "jmri.util": jmri.util,
        "jmri.util.swing": jmri.util.swing, "java": java, "java.lang": lang, "java.beans": beans,
        "java.awt": java.awt, "java.awt.event": awt_event, "javax": mod("javax", swing=swing),
        "javax.swing": swing, "apps": mod("apps", Apps=types.SimpleNamespace()),
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
def jmri_modules(layout):
    saved = {k: sys.modules.get(k) for k in _modules(layout)}
    sys.modules.update(_modules(layout))
    try:
        with no_network():
            yield
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def load_script(path: Path, layout: Layout) -> dict:
    """Run a Jython script against `layout`; returns its globals for the test to drive.

    Jython names a Java method `await`, a reserved word in Python 3; it is renamed in the
    loaded copy only (the script on disk is untouched).
    """
    Timer.pending.clear()
    Thread.started.clear()
    source = Path(path).read_text(encoding="utf-8").replace(".await(", ".await_(")
    env = {"__name__": "hart_script_under_test", "turnouts": layout.turnouts, "sensors": layout.sensors,
           "routes": layout.routes, "signals": layout.heads, "masts": layout.masts,
           "memories": layout.memories}
    with jmri_modules(layout), contextlib.redirect_stdout(_Quiet()):
        exec(compile(source, str(path), "exec"), env)
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
